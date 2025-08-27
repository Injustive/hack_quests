import asyncio
import uuid
from datetime import datetime, timezone, timedelta
import random
from .config import ACTUAL_CAPTCHA_SOLVER
from .utils import galxe_task_retry
from .db import GalxeDb
from .twitter_task import GalxeTwitterTask
from .email_client import EmailClient
from .exceptions import EmailVerificationException
from utils.utils import Logger, generate_random, retry, check_res_status, sleep
from faker import Faker

global_lock = asyncio.Lock()


class GalxeTask(Logger):
    def __init__(self,
                 session,
                 client,
                 twitter_token=None,
                 email=None,
                 captcha_solver: ACTUAL_CAPTCHA_SOLVER | None = None,
                 db: GalxeDb = None):
        self.session = session
        self.client = client
        self.twitter_token = twitter_token
        self.email = email
        self.captcha_solver = captcha_solver
        self.galxe_address_id = None
        self.db = db
        super().__init__(self.client.address, additional={'pk': self.client.key,
                                                          'proxy': self.session.proxies.get('http')})
        self.twitter_task = GalxeTwitterTask(twitter_token, session, client, self.logger, db)

    async def galxe_login(self):
        galxe_login_response = (await self.galxe_login_request()).json()
        auth_token = galxe_login_response['data']['signin']
        self.session.headers.update({'Authorization': auth_token})
        self.logger.success('Successfully logged in!')

    @retry()
    @check_res_status()
    async def galxe_login_request(self):
        url = 'https://graphigo.prd.galaxy.eco/query'
        issued_at_str, expiration_time_str = self.get_activity_time_login()
        message_to_sign = (
            'galxe.com wants you to sign in with your Ethereum account:\n'
            f'{self.client.address}\n\n'
            'Sign in with Ethereum to the app.\n\n'
            'URI: https://galxe.com\n'
            'Version: 1\n'
            'Chain ID: 1\n'
            f'Nonce: {generate_random(17)}\n'
            f'Issued At: {issued_at_str}\n'
            f'Expiration Time: {expiration_time_str}'
        )
        json_data = {
            'operationName': 'SignIn',
            'variables': {
                'input': {
                    'address': self.client_address,
                    'message': message_to_sign,
                    'signature': self.client.get_signed_code(message_to_sign),
                    'addressType': 'EVM',
                },
            },
            'query': 'mutation SignIn($input: Auth) {\n  signin(input: $input)\n}\n',
        }
        return await self.session.post(url, json=json_data)

    async def registration_and_binding(self):
        if await self.is_address_registered():
            self.logger.info('Address already registered!')
            await self.bind_available_socials()
        else:
            await self.start_galxe_registration()
            await self.bind_available_socials()

    async def minimise_registration(self):
        if await self.is_address_registered():
            self.logger.info('Address already registered!')
            await self.bind_minimise()
        else:
            await self.start_galxe_registration()
            await self.bind_minimise()

    async def bind_minimise(self):
        await self.db.initialise_bound_socials_table(self.client.address)
        account_status = await self.check_galxe_account_info()
        for key in account_status:
            if key == 'need_add_email' and account_status[key]:
                await self.add_email()
        galxe_account_data = (await self.check_galxe_account_info_request()).json()['data']['addressInfo']
        email = galxe_account_data.get('email')
        await self.db.bound_socials_insert_email(self.client.address, email)

    async def bind_available_socials(self):
        await self.db.initialise_bound_socials_table(self.client.address)
        while True:
            account_status = await self.check_galxe_account_info()
            for key in account_status:
                if key == 'need_add_email' and account_status[key]:
                    await self.add_email()
                elif key == 'need_add_twitter' and account_status[key]:
                    await self.bind_twitter()
            galxe_account_data = (await self.check_galxe_account_info_request()).json()['data']['addressInfo']
            email = galxe_account_data.get('email')
            galxe_twitter_username = galxe_account_data.get('twitterUserName')
            await self.db.bound_socials_insert_email(self.client.address, email)
            token_twitter_username = await self.twitter_task.get_account_username()
            if galxe_twitter_username == token_twitter_username:
                await self.db.bound_socials_insert_twitter(self.client.address, self.twitter_token, token_twitter_username)
            else:
                self.logger.error('Your twitter token username and galxe twitter username are different! '
                                  'Trying to rebind twitter...')
                await self.remove_twitter()
                continue
            break

    async def bind_twitter(self):
        tweet_url = await self.twitter_task.connect_to_website(self.galxe_address_id)
        self.logger.success('Tweet for binding account posted successfully!')
        await self.galxe_twitter_check_account(tweet_url)
        await self.galxe_twitter_verify_account(tweet_url)
        self.logger.success('Twitter bound successfully!')
        async with global_lock:
            twitter_username = await self.twitter_task.get_account_username()
            await self.db.bound_socials_insert_twitter(self.client.address,
                                                       self.twitter_token,
                                                       twitter_username)

    @retry()
    @check_res_status()
    async def galxe_twitter_check_account(self, tweet_url):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = (
            'mutation checkTwitterAccount($input: VerifyTwitterAccountInput!) '
            '{\n  checkTwitterAccount(input: $input) {\n    address\n    twitterUserID\n    twitterUserName\n'
            '    __typename\n  }\n}\n'
        )
        json_data = {
            'operationName': 'checkTwitterAccount',
            'variables': {
                'input': {
                    'address': self.client.address,
                    'tweetURL': tweet_url,
                },
            },
            'query': query,
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def galxe_twitter_verify_account(self, tweet_url):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = (
            'mutation VerifyTwitterAccount($input: VerifyTwitterAccountInput!) '
            '{\n  verifyTwitterAccount(input: $input) {\n    address\n    twitterUserID\n    twitterUserName\n'
            '    __typename\n  }\n}\n'
        )
        json_data = {
            'operationName': 'VerifyTwitterAccount',
            'variables': {
                'input': {
                    'address': self.client.address,
                    'tweetURL': tweet_url,
                },
            },
            'query': query,
        }
        return await self.session.post(url, json=json_data)

    async def is_address_registered(self):
        is_address_registered_response = (await self.is_address_registered_request()).json()
        return is_address_registered_response["data"]["galxeIdExist"]

    @retry()
    @check_res_status()
    async def is_address_registered_request(self):
        url = 'https://graphigo.prd.galaxy.eco/query'
        self.session.headers.update({'request-id': self.get_random_request_id()})
        json_data = {
            'operationName': 'GalxeIDExist',
            'variables': {
                'schema': f'EVM:{self.client.address}',
            },
            'query': 'query GalxeIDExist($schema: String!) {\n  galxeIdExist(schema: $schema)\n}\n',
        }
        return await self.session.post(url, json=json_data)

    async def start_galxe_registration(self):
        username = self.get_random_username()
        while True:
            username_exist = (await self.check_if_username_exist(username)).json()['data']['usernameExist']
            if not username_exist:
                break
            username = self.get_random_username()
        register_account_response = (await self.register_account_request(username)).json()
        if register_account_response['data']['createNewAccount']:
            self.logger.success(f'Galxe account registered successfully with username: {username}')
        else:
            self.logger.error(f'Something went wrong with registering new galxe account. {register_account_response}')

    async def check_galxe_account_info(self):
        check_galxe_account_info_response = (await self.check_galxe_account_info_request()).json()
        self.galxe_address_id = check_galxe_account_info_response['data']['addressInfo']['id']
        need_add_email = False
        need_add_twitter = False
        need_add_discord = False
        if not check_galxe_account_info_response['data']['addressInfo']['hasEmail']:
            need_add_email = True
        if not check_galxe_account_info_response['data']['addressInfo']['hasTwitter']:
            need_add_twitter = True
        if not check_galxe_account_info_response['data']['addressInfo']['hasDiscord']:
            need_add_discord = True
        account_status = {'need_add_email': need_add_email,
                          'need_add_twitter': need_add_twitter,
                          'need_add_discord': need_add_discord}
        self.logger.info(f'Got account status info: {account_status}')
        return account_status

    @retry()
    @check_res_status()
    async def check_galxe_account_info_request(self):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = (
            'query BasicUserInfo($address: String!) '
            '{\n  addressInfo(address: $address) {\n    id\n    username\n    avatar\n    address\n    '
            'evmAddressSecondary {\n      address\n      __typename\n    }\n    hasEmail\n    solanaAddress\n'
            '    aptosAddress\n    seiAddress\n    injectiveAddress\n    flowAddress\n    starknetAddress\n    '
            'bitcoinAddress\n    hasEvmAddress\n    hasSolanaAddress\n    hasAptosAddress\n    hasInjectiveAddress\n'
            '    hasFlowAddress\n    hasStarknetAddress\n    hasBitcoinAddress\n    hasTwitter\n    hasGithub\n    '
            'hasDiscord\n    hasTelegram\n    displayEmail\n    displayTwitter\n    displayGithub\n    displayDiscord\n'
            '    displayTelegram\n    displayNamePref\n    email\n    twitterUserID\n    twitterUserName\n    '
            'githubUserID\n    githubUserName\n    discordUserID\n    discordUserName\n    telegramUserID\n    '
            'telegramUserName\n    enableEmailSubs\n    subscriptions\n    isWhitelisted\n    isInvited\n    isAdmin\n'
            '    accessToken\n    __typename\n  }\n}\n'
        )
        json_data = {
            'operationName': 'BasicUserInfo',
            'variables': {
                'address': self.client.address,
            },
            'query': query,
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def register_account_request(self, username):
        url = 'https://graphigo.prd.galaxy.eco/query'
        json_data = {
            'operationName': 'CreateNewAccount',
            'variables': {
                'input': {
                    'schema': f'EVM:{self.client.address}',
                    'socialUsername': '',
                    'username': username,
                },
            },
            'query': 'mutation CreateNewAccount($input: CreateNewAccount!) {\n  createNewAccount(input: $input)\n}\n',
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def check_if_username_exist(self, username):
        url = 'https://graphigo.prd.galaxy.eco/query'
        json_data = {
            'operationName': 'IsUsernameExisting',
            'variables': {
                'username': username,
            },
            'query': 'query IsUsernameExisting($username: String!) {\n  usernameExist(username: $username)\n}\n',
        }
        return await self.session.post(url, json=json_data)

    @galxe_task_retry
    async def add_email(self):
        self.logger.info('Starting binding email...')
        _, solution = await self.captcha_solver.solve_captcha(self.logger)
        await self.request_to_add_email(solution)
        self.logger.success('Successfully sent bind email request!')
        await sleep(10, 15)
        verif_code = await EmailClient(self.email.split(':')[0], self.email.split(':')[1], self.logger).get_code()
        if verif_code is False:
            self.logger.error('Something went wrong with getting verification code! Trying again...')
            raise EmailVerificationException
        self.logger.success('Successfully got email verification code!')
        email_bind_response = (await self.send_email_verif_code(verif_code)).json()
        if email_bind_response.get('errors'):
            self.logger.error('Something went wrong with binding email! Trying again...')
            raise EmailVerificationException
        if not email_bind_response['data']['updateEmail']:
            self.logger.success('Email bound successfully!')
            await self.db.bound_socials_insert_email(self.client.address, self.email)
        else:
            self.logger.error('Email binding failed')

    @retry()
    @check_res_status(expected_statuses=[200, 201, 422])
    async def send_email_verif_code(self, verif_code):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = ('mutation UpdateEmail($input: UpdateEmailInput!) '
                 '{\n  updateEmail(input: $input) {\n    code\n    message\n    __typename\n  }\n}\n')
        json_data = {
            'operationName': 'UpdateEmail',
            'variables': {
                'input': {
                    'address': self.client.address,
                    'email': self.email.split(':')[0],
                    'verificationCode': verif_code,
                },
            },
            'query': query,
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def request_to_add_email(self, solution):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = (
            'mutation SendVerifyCode($input: SendVerificationEmailInput!) '
            '{\n  sendVerificationCode(input: $input) {\n    code\n    message\n    __typename\n  }\n}\n'
        )
        json_data = {
            'operationName': 'SendVerifyCode',
            'variables': {
                'input': {
                    'address': self.client.address,
                    'email': self.email.split(':')[0],
                    'captcha': {
                        'lotNumber': solution['lot_number'],
                        'captchaOutput': solution['seccode']['captcha_output'],
                        'passToken': solution['seccode']['pass_token'],
                        'genTime': solution['seccode']['gen_time'],
                    },
                },
            },
            'query': query,
        }
        return await self.session.post(url, json=json_data)

    async def check_account(self, with_db=True):
        return await self.twitter_task.check_account(with_db)

    async def remove_twitter(self):
        remove_twitter_response = (await self.remove_twitter_request()).json()
        if not remove_twitter_response.get('data', {}).get('deleteSocialAccount', True):
            self.logger.success('Twitter successfully removed!')
        else:
            self.logger.error("Can't remove twitter account...")

    async def start_rebinding_twitter(self):
        account_status = await self.check_galxe_account_info()
        if not account_status['need_add_twitter']:
            remove_twitter_response = (await self.remove_twitter_request()).json()
            if not remove_twitter_response.get('data', {}).get('deleteSocialAccount', True):
                self.logger.success('Old twitter successfully removed!')
            else:
                self.logger.error("Can't remove twitter account...")
        await self.bind_twitter()

    @retry()
    @check_res_status()
    async def remove_twitter_request(self):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = (
            'mutation DeleteSocialAccount($input: DeleteSocialAccountInput!) {\n  deleteSocialAccount(input: $input)'
            ' {\n    code\n    message\n    __typename\n  }\n}\n'
        )
        json_data = {
            'operationName': 'DeleteSocialAccount',
            'variables': {
                'input': {
                    'address': self.client.address,
                    'type': 'TWITTER',
                },
            },
            'query': query,
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def connect_aptos_wallet(self, aptos_address, aptos_public_key, nonce, message_to_sign, signature):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = 'mutation UpdateUserAddress($input: UpdateUserAddressInput!) {\n  updateUserAddress(input: $input) {\n    code\n    message\n    __typename\n  }\n}'
        json_data = {
            'operationName': 'UpdateUserAddress',
            'variables': {
                'input': {
                    'address': self.client.address,
                    'addressType': 'EVM',
                    'updateAddress': str(aptos_address),
                    'updateAddressType': 'APTOS',
                    'sig': str(signature),
                    'sigNonce': nonce,
                    'addressPublicKey': str(aptos_public_key),
                    'message': message_to_sign
                },
            },
            'query': query
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def connect_sui_wallet(self, sui_address, nonce, message_to_sign, signature):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = 'mutation UpdateUserAddress($input: UpdateUserAddressInput!) {\n  updateUserAddress(input: $input) {\n    code\n    message\n    __typename\n  }\n}'
        json_data = {
            'operationName': 'UpdateUserAddress',
            'variables': {
                'input': {
                    'address': self.client.address,
                    'addressType': 'EVM',
                    'updateAddress': str(sui_address),
                    'updateAddressType': 'SUI',
                    'sig': str(signature),
                    'sigNonce': nonce,
                    'addressPublicKey': "",
                    'message': message_to_sign
                },
            },
            'query': query
        }
        return await self.session.post(url, json=json_data)

    @staticmethod
    def get_activity_time_login():
        issued_at = datetime.now(timezone.utc)
        expiration_time = issued_at + timedelta(days=7)
        issued_at_str = issued_at.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        expiration_time_str = expiration_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        return issued_at_str, expiration_time_str

    @staticmethod
    def get_random_request_id():
        return str(uuid.uuid4())

    @staticmethod
    def get_random_username(min_lenght=6) -> str:
        return Faker().user_name().ljust(min_lenght, str(random.randint(1, 9)))
