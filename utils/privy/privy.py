import os
import time
import asyncio
from enum import StrEnum
from uuid import uuid4
from typing import Optional
from dataclasses import dataclass

from .privy_utils import (random_string, sha256safe, sha256, b64e, b64d,
                         generate_device_id, generate_encryption_key, get_key_hash,
                         shamir_split, shamir_combine, account_from_entropy,
                         encrypt_share, decrypt_share)
from utils.utils import retry, check_res_status, get_utc_now, generate_solana_mnemonic
from utils.client import Client, SolanaClient
import copy
from mnemonic import Mnemonic


SIWE_MESSAGE_FMT = ('{{site}} wants you to sign in with your Ethereum account:\n'
                    '{{address}}\n\n'
                    'By signing, you are proving you own this wallet and logging in. '
                    'This does not initiate a transaction or cost any fees.\n\n'
                    'URI: {{uri}}\n'
                    'Version: 1\n'
                    'Chain ID: {{chain_id}}\n'
                    'Nonce: {{nonce}}\n'
                    'Issued At: {{issued_at}}\n'
                    'Resources:\n- https://privy.io')

EMBEDDED_MESSAGE_FMT = ('auth.privy.io wants you to sign in with your Ethereum account:\n'
                        '{{address}}\n\n'
                        'You are proving you own {{address}}.\n\n'
                        'URI: https://auth.privy.io\n'
                        'Version: 1\n'
                        'Chain ID: 1\n'
                        'Nonce: {{nonce}}\n'
                        'Issued At: {{issued_at}}\n'
                        'Resources:\n- https://privy.io')

class LoginMethod(StrEnum):
    WALLET = "wallet"
    EMBEDDED_WALLET = "embedded_wallet"
    TWITTER = "twitter"
    EMAIL = "email"


@dataclass
class PrivyConfig:
    project: str
    origin: str
    app_id: str
    client_id: str = ''
    react_version: str = '2.8.3'
    ca_id: str = ''
    with_embedded_wallet: bool = True
    initial_login_method: LoginMethod = LoginMethod.WALLET
    chain_id: str = '8453'


class Privy:
    def __init__(self, client, session, logger, config: PrivyConfig):
        self.client = client
        self.session = session
        self.logger = logger
        self.config = config
        self.embedded_wallet = None
        self.initial_headers = copy.deepcopy(self.session.headers)

    @retry()
    @check_res_status()
    async def privy_init(self):
        url = f"https://auth.privy.io/api/v1/siwe/init"
        json_data = {
            'address': self.client.address
        }
        return await self.session.post(url, json=json_data)

    async def login(self):
        self.session.headers.update({
            "privy-app-id": self.config.app_id,
            "privy-client": f"react-auth:{self.config.react_version}",
            "privy-client-id": self.config.client_id,
            "origin": self.config.origin,
        })
        nonce = (await self.privy_init()).json()['nonce']
        auth_response = (await self.authenticate(nonce)).json()
        jwt = auth_response['token']
        self.session.headers.update({"Authorization": "Bearer " + jwt})
        return auth_response

    async def authenticate(self, nonce):
        url = f'https://privy.{self.config.project}/api/v1/siwe/authenticate'
        site = self.config.origin
        if site.startswith('https://'):
            site = site[8:]
        issued_at = get_utc_now()
        msg_to_sign = (SIWE_MESSAGE_FMT.
               replace('{{site}}', site).
               replace('{{address}}', self.client.address).
               replace('{{uri}}', self.config.origin).
               replace('{{chain_id}}', self.config.chain_id).
               replace('{{nonce}}', nonce).
               replace('{{issued_at}}', issued_at))
        json_data = {
            'message': msg_to_sign,
            'signature': self.client.get_signed_code(msg_to_sign),
            'chainId': f'eip155:{self.config.chain_id}',
            'walletClientType': 'rabby_wallet',
            'connectorType': 'injected',
            'mode': 'login-or-sign-up',
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def _embedded_wallets_init(self):
        url = f'https://privy.{self.config.project}/api/v1/embedded_wallets/init'
        json_data = {
            'address': self.embedded_wallet.address,
            'chain_type': 'ethereum',
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status(expected_statuses=[200, 201, 400])
    async def _embedded_wallet_submit(self,
                                      device_auth_share,
                                      encrypted_recovery_share,
                                      encrypted_recovery_share_iv,
                                      entropy_key,
                                      recovery_auth_share,
                                      recovery_key,
                                      recovery_key_hash,
                                      message,
                                      signature):
        url = f'https://privy.{self.config.project}/api/v1/embedded_wallets'
        json_data = {
            'chain_type': 'ethereum',
            'device_auth_share': device_auth_share,
            'device_id': generate_device_id(),
            'encrypted_recovery_share': encrypted_recovery_share,
            'encrypted_recovery_share_iv': encrypted_recovery_share_iv,
            'entropy_key': entropy_key,
            'entropy_key_verifier': 'ethereum-address-verifier',
            'imported': False,
            'message': message,
            'recovery_auth_share': recovery_auth_share,
            'recovery_key': recovery_key,
            'recovery_key_hash': recovery_key_hash,
            'recovery_type': 'privy_generated_recovery_key',
            'signature': signature,
        }
        return await self.session.post(url, json=json_data)

    async def generate_embedded_wallet(self):
        self.logger.info('Starting generating embedded eth wallet...')
        entropy = os.urandom(16)
        share, device_auth_share = tuple(shamir_split(entropy))
        recovery, recovery_auth_share = tuple(shamir_split(entropy))

        share, device_auth_share = b64e(share), b64e(device_auth_share)
        recovery_auth_share = b64e(recovery_auth_share)

        encryption_key = generate_encryption_key()
        encrypted_recovery_share, encrypted_recovery_share_iv = encrypt_share(recovery, encryption_key)

        recovery_key_hash = b64e(sha256(encryption_key))
        recovery_key = b64e(encryption_key)

        account = account_from_entropy(entropy)
        self.embedded_wallet = Client(key=account.key.hex())
        nonce = (await self._embedded_wallets_init()).json()['nonce']
        issued_at = get_utc_now()
        message = (EMBEDDED_MESSAGE_FMT.
                   replace('{{address}}', self.embedded_wallet.address).
                   replace('{{nonce}}', nonce).
                   replace('{{issued_at}}', issued_at))
        signature = self.embedded_wallet.get_signed_code(message)
        entropy_key = self.embedded_wallet.address
        submit_response = (await self._embedded_wallet_submit(
            device_auth_share,
            encrypted_recovery_share, encrypted_recovery_share_iv,
            entropy_key,
            recovery_auth_share, recovery_key, recovery_key_hash,
            message, signature,
        )).json()
        if not submit_response.get('created_at'):
            self.logger.error(f"Failed to create embedded wallet: {submit_response}.")
            return
        else:
            self.logger.success(f'Generated embedded eth wallet: {self.embedded_wallet.address}')
        return account

    @retry()
    @check_res_status()
    async def sessions(self):
        url = f'https://privy.{self.config.project}/api/v1/sessions'
        json_data = {
            'refresh_token': 'deprecated',
        }
        return await self.session.post(url, json=json_data)

    async def update_login(self):
        jwt = (await self.sessions()).json()['token']
        self.session.headers['Authorization'] = f'Bearer {jwt}'

    @retry()
    @check_res_status()
    async def privy_share(self, embedded_wallet):
        url = f'https://privy.{self.config.project}/api/v1/embedded_wallets/{embedded_wallet}/share'
        json_data = {
            'device_id': generate_device_id(),
            'chain_type': 'ethereum',
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def _recovery_key_material(self, wallet):
        url = f'https://{self.config.origin[7:]}/api/v1/embedded_wallets/{wallet}/recovery/key_material'
        return await self.session.post(url, json={'chain_type': 'ethereum'})

    @retry()
    @check_res_status()
    async def _recovery_auth_share(self, wallet):
        url = f'https://{self.config.origin[7:]}/api/v1/embedded_wallets/{wallet}/recovery/auth_share'
        return await self.session.post(url, json={'chain_type': 'ethereum'})

    @retry()
    @check_res_status()
    async def _recovery_shares(self, wallet, recovery_key_hash):
        url = f'https://{self.config.origin[7:]}/api/v1/embedded_wallets/{wallet}/recovery/shares'
        return await self.session.post(url, json={'chain_type': 'ethereum',
                                                  'recovery_key_hash': recovery_key_hash})

    @retry()
    @check_res_status()
    async def _recovery_device(self, wallet, device_auth_share):
        url = f'https://{self.config.origin[7:]}/api/v1/embedded_wallets/{wallet}/recovery/device'
        return await self.session.post(url, json={'chain_type': 'ethereum',
                                                  'device_auth_share': device_auth_share,
                                                  'device_id': generate_device_id()})


    async def recover_embedded_wallet(self):
        self.logger.info('Starting recover embedded wallet')
        linked_accounts = (await self.login())['user']['linked_accounts']
        self.embedded_wallet = next((
            a['address'] for a in linked_accounts
            if a.get('connector_type') == 'embedded' and
            a.get('recovery_method') == 'privy'
        ), '')
        if not self.embedded_wallet:
            self.logger.error("Privy address not found")
            return
        rec_key_response = (await self._recovery_key_material(self.embedded_wallet)).json()
        r_key, r_type = rec_key_response['recovery_key'], rec_key_response['recovery_type']
        if r_type != 'privy_generated_recovery_key':
            self.logger.error("Unsupported recovery key type")
            raise Exception('Unsupported recovery key type')
        auth_share = (await self._recovery_auth_share(self.embedded_wallet)).json()['share']
        recovery_key_hash = get_key_hash(r_key)
        rec_shares_response = (await self._recovery_shares(
            self.embedded_wallet,
            recovery_key_hash,
        )).json()
        enc_r_share, enc_r_share_iv, imported = (rec_shares_response['encrypted_recovery_share'],
                                                 rec_shares_response['encrypted_recovery_share_iv'],
                                                 rec_shares_response['imported'])
        if imported:
            self.logger.error("'Imported recovery not supported")
            raise Exception('Imported recovery not supported')
        shares = [decrypt_share(enc_r_share, enc_r_share_iv, r_key), b64d(auth_share)]
        entropy = shamir_combine(shares)
        acc = account_from_entropy(entropy)
        if acc.address.lower() != self.embedded_wallet.lower():
            self.logger.error("Failed to recover the expected wallet")
            raise Exception('Failed to recover the expected wallet')

        share, device_auth_share = tuple(shamir_split(entropy))
        share, device_auth_share = b64e(share), b64e(device_auth_share)

        await self._recovery_device(self.embedded_wallet, device_auth_share)
        await self.sessions()
        self.logger.success('Successfully recovered embedded wallet!')
        self.session.headers = self.initial_headers
        return acc

    @retry()
    @check_res_status()
    async def _embedded_wallet_solana_init(self, address):
        url = 'https://privy.doma.xyz/api/v1/embedded_wallets/init'
        json_data = {
            'address': address,
            'chain_type': 'solana',
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status(expected_statuses=[200, 201, 400])
    async def _embedded_wallet_solana_submit(self, solana_client, nonce, device_id, device_auth_share):
        url = 'https://privy.doma.xyz/api/v1/embedded_wallets/add_solana'
        msg_to_sign = f'privy.{self.config.project} wants you to sign in with your Solana account:\n{solana_client.address}\n\nYou are proving you own {solana_client.address}.\n\nURI: https://privy.{self.config.project}\nVersion: 1\nChain ID: mainnet\nNonce: {nonce}\nIssued At: {get_utc_now()}\nResources:\n- https://privy.io'
        json_data = {
            'message': msg_to_sign,
            'signature': await solana_client.sign_message(msg_to_sign, encoding='64'),
            'device_id': device_id,
            'device_auth_share': device_auth_share,
        }
        return await self.session.post(url, json=json_data)

    async def generate_solana_wallet(self):
        self.logger.info("Starting generating solana embedded wallet...")
        mnemonic = Mnemonic("english").generate(128)
        entropy16 = Mnemonic("english").to_entropy(mnemonic)
        _, device_auth_raw = shamir_split(entropy16)
        device_auth_share = b64e(device_auth_raw)
        sol_client = SolanaClient(mnemonic)
        await sol_client.init()
        nonce = (await self._embedded_wallet_solana_init(sol_client.address)).json()['nonce']
        submit_response = await self._embedded_wallet_solana_submit(
            solana_client=sol_client,
            nonce=nonce,
            device_id=generate_device_id(),
            device_auth_share=device_auth_share,
        )
        if submit_response.status_code in [200, 201]:
            linked_accounts = submit_response.json()['linked_accounts']
            for account in linked_accounts:
                if account.get('connector_type') == 'embedded' and account['chain_type'] == 'solana':
                    self.logger.success(f'Generated embedded solana wallet: {sol_client.address}')
                    return sol_client
            else:
                self.logger.error("Failed to generate embedded solana wallet!")
        else:
            self.logger.error(f"Failed to generate embedded solana wallet! {submit_response.text}")
