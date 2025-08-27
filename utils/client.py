import asyncio

import pyuseragents
from eth_account import Account
from eth_account.messages import encode_defunct, SignableMessage
from web3 import Web3
from web3.eth import AsyncEth
from .paths import SEED_TO_ADDRESS_JS, SIGN_MESSAGE_BIP322_JS, SEED_TO_ADDRESS_SOLANA_JS, SIGN_MESSAGE_SOLANA_JS
import json
from loguru import logger


class Client:
    def __init__(self,  key: str, http_provider: str = 'https://rpc.ankr.com/bsc', proxy=None):
        self.w3 = None
        self.key = key
        self.address = self.get_address_from_private()
        self.headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'user-agent': pyuseragents.random()
        }
        self.proxy = proxy
        self.http_provider = http_provider
        self.chain_id = None
        Account.enable_unaudited_hdwallet_features()
        self.define_new_provider(self.http_provider)

    def define_new_provider(self, http_provider: str, chain_id=None):
        self.chain_id = chain_id
        self.w3 = Web3(Web3.AsyncHTTPProvider(http_provider,
                                              request_kwargs={'proxy': self.proxy,
                                                              'headers': self.headers,
                                                              'ssl': False}),
                       modules={'eth': (AsyncEth,)}, middlewares=[])
        self.http_provider = http_provider

    def reconnect_with_new_proxy(self, proxy: str):
        self.headers.update({'user-agent': pyuseragents.random()})
        self.proxy = proxy
        self.define_new_provider(self.http_provider)


    def sign(self, encoded_msg: SignableMessage):
        return self.w3.eth.account.sign_message(encoded_msg, self.key)

    def get_signed_code(self, msg) -> str:
        return self.sign(encode_defunct(text=msg)).signature.hex()

    def get_address_from_private(self):
        return Account.from_key(self.key).address

    def __repr__(self):
        return f'Client <{self.address}>'


class BTCClient:
    def __init__(self, seed):
        self.wif = None
        self.address = None
        self._seed = seed

    async def init(self):
        await self.__get_wif_pk()

    async def __get_wif_pk(self):
        args = (self._seed, )
        process = await asyncio.create_subprocess_exec(
            'node', SEED_TO_ADDRESS_JS, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            result = json.loads(stdout.decode())
            self.wif = result['wif']
            self.address = result['address']
        else:
            print("Something went wrong with getting wif, address...")

    async def sign_message_bip322(self, message):
        args = (self.wif, self.address, message)
        process = await asyncio.create_subprocess_exec(
            'node', SIGN_MESSAGE_BIP322_JS, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            return json.loads(stdout.decode())
        else:
            print("Something went wrong with signing bip322 message...")

class SolanaClient:
    def __init__(self, seed, address=None):
        self.address = address if address else None
        self._seed = seed

    async def init(self):
        await self.__get_address()

    async def __get_address(self):
        args = (self._seed, )
        process = await asyncio.create_subprocess_exec(
            'node', SEED_TO_ADDRESS_SOLANA_JS, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            result = json.loads(stdout.decode())
            self.address = result['address']
        else:
            print(f"Something went wrong with getting address... {stdout.decode()}")

    async def sign_message(self, message, encoding='58'):
        args = (self._seed, message, encoding)
        process = await asyncio.create_subprocess_exec(
            'node', SIGN_MESSAGE_SOLANA_JS, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            return json.loads(stdout.decode())
        else:
            print(f"Something went wrong with signing message.. {stdout.decode()}")

    def reconnect_with_new_proxy(self, proxy):
        pass
