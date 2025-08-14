from utils.utils import (retry, check_res_status, generate_random, sleep,
                         wait_tx_status, read_json, Contract,
                         get_utc_now, get_data_lines, Logger, JSException,
                         retry_js, MaxLenException, get_gas_params, estimate_gas)
from utils.models import TxStatusResponse
from hashids import Hashids
import time
import math
from ..paths import MINT_CUBE_ABI
from .utils import pass_transaction


class Task(Logger):
    def __init__(self, session, client, db_manager):
        self.session = session
        self.client = client
        self.user_address_id = None
        self.signed_msg = None
        self.nonce = None
        self.db_manager = db_manager
        self.tx_hash = None
        super().__init__(self.client.address, additional={'pk': self.client.key,
                                                          'proxy': self.session.proxies.get('http')})

    async def login(self):
        await sleep(5, 30)
        while True:
            try:
                hashids = Hashids(salt='l3.tsit')
                hashid = hashids.encode(math.floor(time.time()))
                self.session.headers.update({'x-l3-tsit': hashid,
                                             'origin': 'https://app.layer3.xyz',
                                             'referer': 'https://app.layer3.xyz/'})
                connect_intent_id = generate_random(21)
                nonce_response = await self.get_nonce(connect_intent_id)
                one_time_key = next(result['result']['data']['json']
                                    for result in nonce_response.json() if result['result']['data']['json'])
                self.nonce = one_time_key
                login_response = await self.complete_login(connect_intent_id, one_time_key)
                if 'Just a moment' in login_response.text:
                    raise MaxLenException
                await sleep()
                login_result_json = next(result['result']['data']['json'] for
                                         result in login_response.json() if result['result']['data']['json'])
                access_token, user_address_id = login_result_json.get('accessToken'), \
                    login_result_json['user']['UserAddresses'][0]['id']
                break
            except KeyError:
                self.logger.error(f'Account not registered. Trying again...')
                await self.register_new_account()
        self.user_address_id = user_address_id
        self.session.cookies.update({'layer3_app_access_token': access_token})
        self.logger.success('Login successfully completed!')

    @retry()
    @check_res_status()
    async def get_nonce(self, connect_intent_id):
        url = 'https://app.layer3.xyz/api/trpc/track.walletModal,auth.getWalletSignatureNonce,track.walletModal?batch=1'
        json_data = {
            '0': {
                'json': {
                    'connectIntentId': connect_intent_id,
                    'data': {
                        'strategy': 'io.metamask',
                        'buttonName': 'MetaMask',
                        'browser': 'Chrome',
                        'os': 'macOS',
                    },
                },
            },
            '1': {
                'json': None,
                'meta': {
                    'values': [
                        'undefined',
                    ],
                },
            },
            '2': {
                'json': {
                    'connectIntentId': connect_intent_id,
                    'data': {
                        'strategy': 'io.metamask',
                        'buttonName': 'MetaMask',
                        'browser': 'Chrome',
                        'os': 'macOS',
                        'didConnect': True,
                        'connectedWalletConnector': 'INJECTED',
                        'connectedWalletName': 'MetaMask',
                    },
                },
            },
        }
        return await self.session.post(url, json=json_data, timeout=10)

    async def complete_login(self, connect_intent_id, one_time_key):
        message_to_sign = f'Layer3 One-Time Key: {one_time_key}'
        self.signed_msg = self.client.get_signed_code(message_to_sign)
        url = 'https://app.layer3.xyz/api/trpc/track.walletModal,auth.login?batch=1'
        json_data = {
            '0': {
                'json': {
                    'connectIntentId': connect_intent_id,
                    'data': {
                        'strategy': 'io.metamask',
                        'buttonName': 'MetaMask',
                        'browser': 'Chrome',
                        'os': 'Windows',
                        'didConnect': True,
                        'connectedWalletConnector': 'INJECTED',
                        'connectedWalletName': 'MetaMask',
                        'didSign': True,
                    },
                },
            },
            '1': {
                'json': {
                    'signedMessage': self.signed_msg,
                    'nonce': one_time_key,
                    'walletMetadata': {
                        'walletName': 'MetaMask',
                        'connectorType': 'INJECTED',
                        'os': 'Windows',
                        'browser': 'Chrome',
                    },
                    'address': self.client.address,
                    'captchaValue': None,
                    'chainId': 59144,
                    'baseNetwork': 'EVM',
                    'zone': 'MAIN',
                    'referralString': None,
                },
                'meta': {
                    'values': {
                        'captchaValue': [
                            'undefined',
                        ],
                    },
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def register_login_request(self):
        await sleep(5, 30)
        hashids = Hashids(salt='l3.tsit')
        hashid = hashids.encode(math.floor(time.time()))
        self.session.headers.update({'x-l3-tsit': hashid})
        connect_intent_id = generate_random(21)
        nonce_response = await self.get_nonce(connect_intent_id)
        one_time_key = next(result['result']['data']['json']
                            for result in nonce_response.json() if result['result']['data']['json'])
        self.nonce = one_time_key
        message_to_sign = f'Layer3 One-Time Key: {one_time_key}'
        self.signed_msg = self.client.get_signed_code(message_to_sign)
        url = 'https://app.layer3.xyz/api/trpc/track.walletModal,auth.login?batch=1'
        json_data = {
            '0': {
                'json': {
                    'connectIntentId': connect_intent_id,
                    'data': {
                        'strategy': 'io.metamask',
                        'buttonName': 'MetaMask',
                        'browser': 'Chrome',
                        'os': 'macOS',
                        'didConnect': True,
                        'connectedWalletConnector': 'INJECTED',
                        'connectedWalletName': 'MetaMask',
                        'didSign': True,
                    },
                },
            },
            '1': {
                'json': {
                    'signedMessage': self.signed_msg,
                    'nonce': one_time_key,
                    'walletMetadata': {
                        'walletName': 'MetaMask',
                        'connectorType': 'INJECTED',
                        'os': 'macOS',
                        'browser': 'Chrome',
                    },
                    'address': self.client.address,
                    'captchaValue': None,
                    'chainId': 1,
                    'baseNetwork': 'EVM',
                    'zone': "MAIN",
                    'referralString': '',
                },
                'meta': {
                    'values': {
                        'captchaValue': [
                            'undefined',
                        ],
                    },
                },
            },
        }
        return await self.session.post(url, json=json_data)

    async def register_new_account(self):
        await self.register_login_request()
        res = await self.register_new_account_request()
        if res.status_code == 501:
            self.logger.info('Seems like you already registered')
            return
        self.logger.success('Successfully registered new account!')

    @retry()
    @check_res_status(expected_statuses=[200, 201, 501])
    async def register_new_account_request(self):
        await sleep(5, 30)
        url = 'https://app.layer3.xyz/api/trpc/auth.login?batch=1'
        json_data = {
            '0': {
                'json': {
                    'signedMessage': self.signed_msg,
                    'nonce': self.nonce,
                    'walletMetadata': {
                        'walletName': 'MetaMask',
                        'connectorType': 'INJECTED',
                        'os': 'macOS',
                        'browser': 'Chrome',
                    },
                    'address': self.client.address,
                    'captchaValue': 'mock-captcha-value',
                    'chainId': 1,
                    'baseNetwork': 'EVM',
                    'zone': "MAIN",
                    'referralString': '',
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def quest_view(self, slug=None, quest_id=None):
        url = ('https://app.layer3.xyz/api/trpc/track.questView?batch=1' if slug
               else 'https://app.layer3.xyz/api/trpc/questStep.setQuestStepAsViewed?batch=1')
        json_data = {
            '0': {
                'json': {'slug': slug} if slug else {'questStepId': quest_id}
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status(expected_statuses=[200, 201, 400])
    async def complete_quest_step_request(self, quest_id, last_skipped_time=None):
        url = 'https://app.layer3.xyz/api/trpc/questStep.completeQuestStep?batch=1'
        values = {'inputData': ['undefined']}
        if last_skipped_time:
            values['lastStepSkippedTime'] = ['Date']

        json_data = {
            '0': {
                'json': {
                    'questStepId': quest_id,
                    'inputData': None,
                    'userAddressId': self.user_address_id,
                    'embedOrigin': None,
                    'referralString': None,
                    'walletMetadata': {
                        'walletName': 'Injected',
                        'connectorType': 'INJECTED',
                        'os': 'macOS',
                        'browser': 'Chrome',
                    },
                    'lastStepSkippedTime': last_skipped_time,
                    'payInL3': False,
                },
                'meta': {
                    'values': values,
                },
            },
        }
        return await self.session.post(url, json=json_data)

    async def complete_quest_step(self, quest_id, step=1, _raise=False, last_skipped_time=None):
        while True:
            complete_response = await self.complete_quest_step_request(quest_id, last_skipped_time=last_skipped_time)
            if complete_response.status_code not in [200, 201]:
                if _raise:
                    return False, complete_response.text
                else:
                    self.logger.error(f"Failed to complete quest {quest_id}: {complete_response.text}")
                    await sleep(5, 10)
                    continue
            self.logger.success(f"Successfully completed quest step {step}!")
            return True, None

    async def mint_cube(self, task_id, price, referer='', task_name=""):
        await self.cube_task(task_id, price, referer=referer)
        await sleep(30, 60)
        while True:
            res = await self.complete_quest(task_id=task_id, referer=referer)
            if res.status_code == 400 and "You have not minted a cube!" in res.text:
                await sleep(3)
                self.logger.error(f"Can't complete quest `{task_name}`. Trying again...")
                await self.process_cube_mint_request(self.tx_hash)
            elif res.status_code == 200:
                self.logger.success(f'Quest `{task_name}` completed!')
                break
            else:
                self.logger.error(f'Something went wrong with completing quest `{task_name}`:{res.text}')

    async def cube_task(self, task_id, value=0.35, referer=None):
        cube_data = (await self.get_cube_data(task_id, referer)).json()[0]['result']['data']['json']
        self.cube_uuid = cube_data['uuid']
        serialized_cube_input = cube_data['serializedCubeInput']['json']
        quest_id = serialized_cube_input['questId']
        nonce = serialized_cube_input['nonce']
        price = serialized_cube_input['price']
        is_native = serialized_cube_input['isNative']
        wallet_provider = serialized_cube_input['walletProvider']
        token_uri = serialized_cube_input['tokenURI']
        embed_origin = serialized_cube_input['embedOrigin']
        transactions = serialized_cube_input['transactions']
        recipients = serialized_cube_input['recipients']
        reward = serialized_cube_input['reward']
        token_address = self.client.w3.to_checksum_address(reward['tokenAddress'])
        chain_id = reward['chainId']
        amount = reward['amount']
        token_id = reward['tokenId']
        token_type = reward['tokenType']
        rake_bps = reward['rakeBps']
        factory_address = self.client.w3.to_checksum_address(reward['factoryAddress'])
        reward_recipient_address = self.client.w3.to_checksum_address(reward['rewardRecipientAddress'])
        reward = {
            'token_address': token_address,
            'chain_id': int(chain_id),
            'amount': int(amount),
            'token_id': int(token_id),
            'token_type': int(token_type),
            'rake_bps': int(rake_bps),
            'factory_address': factory_address,
            'reward_recipient_address': reward_recipient_address
        }
        signature = cube_data['signature']
        cube_data = {
            "questId": int(quest_id),
            "nonce": int(nonce),
            "price": int(price),
            "isNative": is_native,
            "toAddress": self.client.address,
            "walletProvider": wallet_provider,
            "tokenURI": token_uri,
            "embedOrigin": embed_origin,
            "transactions": transactions,
            "recipients": recipients,
            "reward": reward
        }
        status, tx_hash = await self.mint_cube_tx(cube_data, signature, value)
        if status == TxStatusResponse.GOOD:
            self.tx_hash = tx_hash
            await self.cube_mint_send_receipt()
            await self.process_cube_mint_request(tx_hash)
        elif status == TxStatusResponse.ALREADY_MINTED:
            self.logger.info('Cube already minted!')

    @retry()
    @check_res_status(expected_statuses=[200, 201, 400])
    async def process_cube_mint_request(self, tx_hash):
        url = 'https://app.layer3.xyz/api/trpc/cube.processCubeMint?batch=1'
        json_data = {
            '0': {
                'json': {
                    'txHash': tx_hash,
                    'cubeChainId': await self.client.w3.eth.chain_id,
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def cube_mint_send_receipt(self):
        url = 'https://app.layer3.xyz/api/trpc/cube.getCubeMintAsMutation?batch=1'
        json_data = {
            '0': {
                'json': {
                    'cubeReceiptUuid': self.cube_uuid,
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @pass_transaction(success_message='Cube successfully minted!')
    async def mint_cube_tx(self, cube_data, signature, value):
        cube_data_struct = (
            cube_data["questId"],
            cube_data["nonce"],
            cube_data["price"],
            cube_data["isNative"],
            cube_data["toAddress"],
            cube_data["walletProvider"],
            cube_data["tokenURI"],
            cube_data["embedOrigin"],
            cube_data["transactions"],
            cube_data["recipients"],
            # [{'BPS': 3300, 'recipient': '0xB9FBf026727e388Bdb0B032189ed401cae2fc64D'}],
            (
                cube_data["reward"]["token_address"],
                cube_data["reward"]["chain_id"],
                cube_data["reward"]["amount"],
                cube_data["reward"]["token_id"],
                cube_data["reward"]["token_type"],
                cube_data["reward"]["rake_bps"],
                cube_data["reward"]["factory_address"],
                cube_data["reward"]["reward_recipient_address"]
            )
        )
        mint_cube_abi = read_json(MINT_CUBE_ABI)
        contract_address = self.client.w3.to_checksum_address('0x1195Cf65f83B3A5768F3C496D3A05AD6412c64B7')
        contract = await Contract(self.client).get_contract(contract_address=contract_address, abi=mint_cube_abi)
        gas_params = await get_gas_params(self)
        transaction = await contract.functions.mintCube(cube_data_struct, bytes.fromhex(signature[2:])).build_transaction({
            'chainId': await self.client.w3.eth.chain_id,
            'from': self.client.address,
            'nonce': await self.client.w3.eth.get_transaction_count(self.client.address),
            **gas_params
        })
        if value:
            transaction['value'] = self.client.w3.to_wei(value, 'ether')
        transaction['gas'] = await estimate_gas(self, transaction)
        signed_txn = self.client.w3.eth.account.sign_transaction(transaction, private_key=self.client.key)
        tx_hash = await self.client.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        return tx_hash.hex()

    @retry()
    @check_res_status()
    async def get_cube_data(self, task_id, referer=''):
        url = 'https://app.layer3.xyz/api/trpc/cube.getOrCreateCubeReceipt?batch=1'
        json_data = {
            '0': {
                'json': {
                    'type': 'quest',
                    'id': task_id,
                    'walletMetadata': None,
                    'embedOrigin': None,
                    'referralString': referer,
                    'payInL3': False,
                    'willBeMintedWithSmartWallet': False
                },
                'meta': {
                    'values': {
                        'embedOrigin': [
                            'undefined',
                        ],
                    },
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status(expected_statuses=[200, 201, 400])
    async def complete_quest(self, task_id, referer=''):
        url = 'https://app.layer3.xyz/api/trpc/questCompletion.completeQuest?batch=1'
        json_data = {
            '0': {
                'json': {
                    'questId': task_id,
                    'embedOrigin': None,
                    'referralString': referer,
                },
            },
        }
        return await self.session.post(url, json=json_data)