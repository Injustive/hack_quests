import asyncio
from functools import wraps
import twitter
from prettytable import PrettyTable
from utils.utils import retry, check_res_status, sleep
from .exceptions import GalxeVerificationException, EmailVerificationException
from .db import GalxeDb
from .paths import GLOBAL_DB
from .captcha import CaptchaSolver


global_lock = asyncio.Lock()


def galxe_task_retry(func):
    async def wrapper(obj, *args, **kwargs):
        attempts = 3
        while True:
            try:
                await func(obj, *args, **kwargs)
                break
            except (GalxeVerificationException, EmailVerificationException) as e:
                msg = str(e)
                if 'Please join the server first before claim the role reward' in msg:
                    raise
                print(e)
                obj.logger.info('Sleeping some time for verification...')
                await sleep(60, 70)
                attempts -= 1
                if attempts == 0:
                    obj.logger.error("Can't complete this task!")
                    raise
    return wrapper


class MainGalxeTaskCompleter:
    def __init__(self, client, session, token, logger, captcha_solver, db):
        self.session = session
        self.client = client
        self.logger = logger
        self.token = token
        self.twitter_account = twitter.Account(auth_token=self.token) if self.token else None
        self.db = db
        self.captcha_solver = captcha_solver
        self.current_captcha_id = None

    @galxe_task_retry
    async def complete_and_verify_task(self, cred_id, campaign_id, delay=None):
        _, captcha = await self.captcha_solver.solve_captcha(self.logger)
        await self.complete_galxe_task(captcha, cred_id, campaign_id)
        self.logger.success(f'Task {cred_id} completed successfully!')
        if delay is not None:
            await sleep(delay)
        else:
            await sleep(1, 5)
        captcha_id, captcha = await self.captcha_solver.solve_captcha(self.logger)
        verify_galxe_response = (await self.verify_galxe_task(captcha, cred_id, campaign_id, with_twitter=True)).json()
        try:
            completed = verify_galxe_response['data']['syncCredentialValue']['value']['allow']
        except TypeError:
            self.logger.error(f'{self.client.address} {campaign_id} campaign error')
            raise
        if completed:
            self.logger.success(f'Task {cred_id} verified successfully!')
        else:
            self.logger.error(f'Task {cred_id} campaign {campaign_id} verification failed. Trying again...')
            if self.captcha_solver == CaptchaSolver:
                await self.captcha_solver.send_bad_report(captcha_id)
            raise GalxeVerificationException

    @galxe_task_retry
    async def complete_and_verify_oat_task(self, cred_id, campaign_id):
        _, captcha = await self.captcha_solver.solve_captcha(self.logger)
        await self.complete_galxe_task(captcha, cred_id, campaign_id)
        self.logger.success(f'Task {cred_id} completed successfully!')
        captcha_id, captcha = await self.captcha_solver.solve_captcha(self.logger)
        verify_galxe_response = (await self.verify_oat_task(cred_id)).json()
        try:
            completed = verify_galxe_response['data']['syncEvaluateCredentialValue']['result']
        except TypeError:
            self.logger.error(f'{self.client.address} {campaign_id} campaign error')
            raise
        if completed:
            self.logger.success(f'Task {cred_id} verified successfully!')
        else:
            self.logger.error(f'Task {cred_id} campaign {campaign_id} verification failed. Trying again...')
            if self.captcha_solver == CaptchaSolver:
                await self.captcha_solver.send_bad_report(captcha_id)
            raise GalxeVerificationException

    @retry()
    @check_res_status()
    async def verify_oat_task(self, cred_id):
        self.logger.info(f'Starting verifying {cred_id} task')
        url = 'https://graphigo.prd.galaxy.eco/query'
        query =  'mutation syncEvaluateCredentialValue($input: SyncEvaluateCredentialValueInput!) {\n  syncEvaluateCredentialValue(input: $input) {\n    result\n    value {\n      allow\n      survey {\n        answers\n        __typename\n      }\n      quiz {\n        allow\n        correct\n        __typename\n      }\n      __typename\n    }\n    message\n    __typename\n  }\n}'
        json_data = {
            'operationName': 'syncEvaluateCredentialValue',
            'variables': {
                'input': {
                    'syncOptions': {
                        'address': f'EVM:{self.client.address}',
                        'credId': cred_id,
                    },
                    'evalExpr': {
                        'address': f'EVM:{self.client.address}',
                        'credId': cred_id,
                        'entityExpr': {
                            'credId': cred_id,
                            'attrs': [
                                {
                                    '__typename': 'ExprEntityAttr',
                                    'attrName': 'ebUSD',
                                    'operatorSymbol': '>',
                                    'targetValue': '1799',
                                },
                            ],
                            'attrFormula': 'ALL',
                        },
                    },
                },
            },
            'query': query
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def complete_galxe_task(self, captcha, cred_id, campaign_id):
        self.logger.info(f'Starting completing {cred_id} task')
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = (
            'mutation AddTypedCredentialItems($input: MutateTypedCredItemInput!) '
            '{\n  typedCredentialItems(input: $input) {\n    id\n    __typename\n  }\n}\n'
        )
        json_data = {
            'operationName': 'AddTypedCredentialItems',
            'variables': {
                'input': {
                    'credId': cred_id,
                    'campaignId': campaign_id,
                    'operation': 'APPEND',
                    'items': [
                        f'EVM:{self.client.address}',
                    ],
                    'captcha': self.get_captcha_data(captcha)
                },
            },
            'query': query,
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def verify_galxe_task(self, captcha, cred_id, campaign_id, with_twitter=False):
        self.logger.info(f'Starting verifying {cred_id} task')
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = (
            'mutation SyncCredentialValue($input: SyncCredentialValueInput!) {\n  syncCredentialValue(input: $input) '
            '{\n    value {\n      address\n      spaceUsers {\n        follow\n        points\n        '
            'participations\n        __typename\n      }\n      campaignReferral {\n        count\n        '
            '__typename\n      }\n      gitcoinPassport {\n        score\n        lastScoreTimestamp\n        '
            '__typename\n      }\n      walletBalance {\n        balance\n        __typename\n      }\n      '
            'multiDimension {\n        value\n        __typename\n      }\n      allow\n      survey {\n        '
            'answers\n        __typename\n      }\n      quiz {\n        allow\n        correct\n        __typename\n'
            '      }\n      __typename\n    }\n    message\n    __typename\n  }\n}\n'
        )
        json_data = {
            'operationName': 'SyncCredentialValue',
            'variables': {
                'input': {
                    'syncOptions': {
                        'credId': cred_id,
                        'address': f'EVM:{self.client.address}'
                    },
                },
            },
            'query': query,
        }
        if with_twitter:
            json_data['variables']['input']['syncOptions']['twitter'] = {
                'campaignID': campaign_id,
                'captcha': self.get_captcha_data(captcha)
            }
        return await self.session.post(url, json=json_data)

    async def follow_space_task(self, space_id, cred_id):
        await self.follow_space(space_id)
        self.logger.success(f'Followed {space_id} space!')
        await self.verify_follow_space(cred_id)
        self.logger.success(f'Follow space task completed!')

    @retry()
    @check_res_status()
    async def follow_space(self, space_id):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = 'mutation followSpace($spaceIds: [Int!]) {\n  followSpace(spaceIds: $spaceIds)\n}\n'
        json_data = {
            'operationName': 'followSpace',
            'variables': {
                'spaceIds': [
                    space_id,
                ],
            },
            'query': query
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def verify_follow_space(self, cred_id):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = 'mutation syncEvaluateCredentialValue($input: SyncEvaluateCredentialValueInput!) {\n  syncEvaluateCredentialValue(input: $input) {\n    result\n    value {\n      allow\n      survey {\n        answers\n        __typename\n      }\n      quiz {\n        allow\n        correct\n        __typename\n      }\n      __typename\n    }\n    message\n    __typename\n  }\n}'
        json_data = {
            'operationName': 'syncEvaluateCredentialValue',
            'variables': {
                'input': {
                    'syncOptions': {
                        'address': f'EVM:{self.client.address}',
                        'credId': cred_id,
                    },
                    'evalExpr': {
                        'address': f'EVM:{self.client.address}',
                        'credId': cred_id,
                        'entityExpr': {
                            'credId': cred_id,
                            'attrs': [
                                {
                                    '__typename': 'ExprEntityAttr',
                                    'attrName': 'points',
                                    'operatorSymbol': '>=',
                                    'targetValue': '5',
                                },
                            ],
                            'attrFormula': 'ALL',
                        },
                    },
                },
            },
            'query': query
        }
        return await self.session.post(url, json=json_data)

    async def complete_survey(self, cred_id, answers):
        self.logger.info(f'Starting completing survey {cred_id}')
        await self.read_survey(cred_id)
        self.logger.success(f'Survey {cred_id} read successfully!')
        await sleep(1, 5)
        await self.verify_survey(cred_id, answers)
        self.logger.success(f'Survey {cred_id} completed successfully!')

    @retry()
    @check_res_status()
    async def verify_survey(self, cred_id, answers):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = 'mutation SyncCredentialValue($input: SyncCredentialValueInput!) {\n  syncCredentialValue(input: $input) {\n    value {\n      address\n      spaceUsers {\n        follow\n        points\n        participations\n        __typename\n      }\n      campaignReferral {\n        count\n        __typename\n      }\n      gitcoinPassport {\n        score\n        lastScoreTimestamp\n        __typename\n      }\n      walletBalance {\n        balance\n        __typename\n      }\n      multiDimension {\n        value\n        __typename\n      }\n      allow\n      survey {\n        answers\n        __typename\n      }\n      quiz {\n        allow\n        correct\n        __typename\n      }\n      __typename\n    }\n    message\n    __typename\n  }\n}'
        json_data = {
            'operationName': 'SyncCredentialValue',
            'variables': {
                'input': {
                    'syncOptions': {
                        'credId': cred_id,
                        'address': f'EVM:{self.client.address}',
                        'survey': {
                            'answers': answers,
                        },
                    },
                },
            },
            'query': query
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def read_survey(self, cred_id):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = 'query readSurvey($id: ID!) {\n  credential(id: $id) {\n    metadata {\n      survey {\n        ...SurveyCredMetadataFrag\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment SurveyCredMetadataFrag on SurveyCredMetadata {\n  surveies {\n    title\n    type\n    items {\n      value\n      __typename\n    }\n    __typename\n  }\n  __typename\n}'
        json_data = {
            'operationName': 'readSurvey',
            'variables': {
                'id': cred_id,
            },
            'query': query
        }
        return await self.session.post(url, json=json_data)

    @galxe_task_retry
    async def complete_campaign(self, campaign_id, points, mint_count=0, chain='GRAVITY_ALPHA', is_oat=False, address=None):
        self.logger.info(f'Starting complete campaign {campaign_id}')
        claim_campaign_response = (await self.claim_completed_campaign(campaign_id, points, mint_count, chain, address)).json()
        if claim_campaign_response.get('errors'):
            if 'you need completed pre-sequence camp' in str(claim_campaign_response.get('errors')):
                self.logger.success(f'Completed campaign {campaign_id}')
                return
            self.logger.error(f"Can't complete campaign. Error - {claim_campaign_response.get('errors')}. Trying again...")
            raise GalxeVerificationException(f"Failed to complete campaign {campaign_id}. "
                                             f"Error - {claim_campaign_response.get('errors')}")
        allow = claim_campaign_response['data']['prepareParticipate']
        if is_oat:
            if allow['allow']:
                self.logger.success(f'Completed campaign {campaign_id}')
                return

        if allow['disallowReason']:
            if allow['disallowReason'] == 'Exceed Point limit, available claim points count is 0' or allow['disallowReason'] == 'Exceed limit, available claim count is 0':
                self.logger.info('Seems like this campaign was already completed')
                return
            elif 'Exceed Point limit, available claim points count is' in allow['disallowReason']:
                points = int(allow['disallowReason'].split('Exceed Point limit, available claim points count is ')[-1])
                self.logger.info(f'Trying to claim this campaign with {points} points')
                await self.complete_campaign(campaign_id, points, mint_count, chain)
            raise GalxeVerificationException(f"Failed to complete campaign {campaign_id}. "
                                             f"Reason - {allow['disallowReason']}")
        allow = allow['loyaltyPointsTxResp']
        if allow['allow']:
            self.logger.success(f'Completed campaign {campaign_id}')
        else:
            reason = allow['disallowReason']
            if reason == '':
                reason = 'empty rewards'
            self.logger.error(f"Can't complete campaign {campaign_id}. Reason - {reason}")
            if reason == 'empty rewards':
                return
            elif reason == 'Exceed Point limit, available claim points count is 0' or reason == 'Exceed limit, available claim count is 0':
                self.logger.info('Seems like this campaign was already completed')
                return
            elif 'Exceed Point limit, available claim points count is' in reason:
                points = int(reason.split('Exceed Point limit, available claim points count is ')[-1])
                self.logger.info(f'Trying to claim this campaign with {points} points')
                await self.complete_campaign(campaign_id, points)
            raise GalxeVerificationException(f"Failed to complete campaign {campaign_id}. "
                                             f"Reason - {allow['disallowReason']}")

    @retry()
    @check_res_status()
    async def claim_completed_campaign(self, campaign_id, points, mint_count=0, chain='GRAVITY_ALPHA', address=None):
        if address is not None:
            address = f'APTOS:{address}'
        url = 'https://graphigo.prd.galaxy.eco/query'
        _, captcha = await self.captcha_solver.solve_captcha(self.logger)
        query = "mutation PrepareParticipate($input: PrepareParticipateInput!) {\n  prepareParticipate(input: $input) {\n    allow\n    disallowReason\n    signature\n    nonce\n    mintFuncInfo {\n      funcName\n      nftCoreAddress\n      verifyIDs\n      powahs\n      cap\n      __typename\n    }\n    extLinkResp {\n      success\n      data\n      error\n      __typename\n    }\n    metaTxResp {\n      metaSig2\n      autoTaskUrl\n      metaSpaceAddr\n      forwarderAddr\n      metaTxHash\n      reqQueueing\n      __typename\n    }\n    solanaTxResp {\n      mint\n      updateAuthority\n      explorerUrl\n      signedTx\n      verifyID\n      __typename\n    }\n    aptosTxResp {\n      signatureExpiredAt\n      tokenName\n      __typename\n    }\n    spaceStation\n    airdropRewardCampaignTxResp {\n      airdropID\n      verifyID\n      index\n      account\n      amount\n      proof\n      customReward\n      __typename\n    }\n    tokenRewardCampaignTxResp {\n      signatureExpiredAt\n      verifyID\n      encodeAddress\n      weight\n      __typename\n    }\n    loyaltyPointsTxResp {\n      TotalClaimedPoints\n      VerifyIDs\n      loyaltyPointDistributionStation\n      signature\n      disallowReason\n      nonce\n      allow\n      loyaltyPointContract\n      Points\n      reqQueueing\n      __typename\n    }\n    flowTxResp {\n      Name\n      Description\n      Thumbnail\n      __typename\n    }\n    xrplLinks\n    suiTxResp {\n      packageId\n      tableId\n      nftName\n      campaignId\n      verifyID\n      imgUrl\n      signatureExpiredAt\n      __typename\n    }\n    __typename\n  }\n}"
        json_data = {
            'operationName': 'PrepareParticipate',
            'variables': {
                'input': {
                    'signature': '',
                    'campaignID': campaign_id,
                    'address': f'EVM:{self.client.address}' if address is None else address,
                    'mintCount': mint_count,
                    'chain': chain,
                    'pointMintAmount': points,
                    'captcha': self.get_captcha_data(captcha)
                },
            },
            'query': query,
        }
        return await self.session.post(url, json=json_data)

    @galxe_task_retry
    async def complete_quiz(self, cred_id, answers):
        await self.read_quiz(cred_id)
        await sleep()
        quiz_response = (await self.complete_galxe_quiz(cred_id, answers)).json()['data']['syncCredentialValue']['value']['quiz']['allow']
        if quiz_response:
            self.logger.success('Quiz completed successfully')
        else:
            self.logger.error('Quiz failed')
            raise GalxeVerificationException

    @retry()
    @check_res_status()
    async def read_quiz(self, cred_id):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = (
            'query readQuiz($id: ID!) {\n  credential(id: $id) {\n    ...CredQuizFrag\n    __typename\n  '
            '}\n}\n\nfragment CredQuizFrag on Cred {\n  credQuiz {\n    quizzes {\n      title\n      typ'
            'e\n      items {\n        value\n        __typename\n      }\n      __typename\n    }\n    _'
            '_typename\n  }\n  __typename\n}\n'
        )
        json_data = {
            'operationName': 'readQuiz',
            'variables': {
                'id': cred_id,
            },
            'query': query,
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def complete_galxe_quiz(self, cred_id, answers):
        url = 'https://graphigo.prd.galaxy.eco/query'
        query = (
            'mutation SyncCredentialValue($input: SyncCredentialValueInput!) {\n  syncCredentialValue(input: '
            '$input) {\n    value {\n      address\n      spaceUsers {\n        follow\n        points\n     '
            '   participations\n        __typename\n      }\n      campaignReferral {\n        count\n       '
            ' __typename\n      }\n      gitcoinPassport {\n        score\n        lastScoreTimestamp\n      '
            '  __typename\n      }\n      walletBalance {\n        balance\n        __typename\n      }\n    '
            '  multiDimension {\n        value\n        __typename\n      }\n      allow\n      survey {\n   '
            '     answers\n        __typename\n      }\n      quiz {\n        allow\n        correct\n       '
            ' __typename\n      }\n      __typename\n    }\n    message\n    __typename\n  }\n}\n'
        )
        json_data = {
            'operationName': 'SyncCredentialValue',
            'variables': {
                'input': {
                    'syncOptions': {
                        'credId': cred_id,
                        'address': f'EVM:{self.client.address}',
                        'quiz': {
                            'answers': answers
                        }
                    },
                },
            },
            'query': query,
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def participate(self, address, tx_hash, verify_ids, campaign_id, chain, nonce):
        url = 'https://graphigo.prd.galaxy.eco/query'
        if address is not None:
            address = f'APTOS:{address}'
        json_data = {
            'operationName': 'Participate',
            'variables': {
                'input': {
                    'signature': '',
                    'address': f'EVM:{self.client.address}' if address is None else address,
                    'tx': tx_hash,
                    'verifyIDs': verify_ids,
                    'chain': chain,
                    'campaignID': campaign_id,
                    'nonce': nonce,
                },
            },
            'query': 'mutation Participate($input: ParticipateInput!) {\n  participate(input: $input) {\n    participated\n    __typename\n  }\n}',
        }
        return await self.session.post(url, json=json_data)

    @staticmethod
    def get_captcha_data(captcha):
        return {'lotNumber': captcha['lot_number'],
                'captchaOutput': captcha['seccode']['captcha_output'],
                'passToken': captcha['seccode']['pass_token'],
                'genTime': captcha['seccode']['gen_time']}


def with_recomplete(with_twitter=False):
    def outer(func):
        @wraps(func)
        async def wrapper(obj, *args, **kwargs):
            await func(obj, *args, **kwargs)
            twitter_username_db = await obj.db.get_bound_twitter_token(obj.client.address)
            if not twitter_username_db:
                twitter_username = await obj.twitter_task.get_account_username()
            else:
                twitter_username = twitter_username_db.get('twitter_username')
            await obj.db.insert_completed_twitter_task(obj.client.address,
                                                       twitter_username,
                                                       with_twitter,
                                                       obj.__class__.__name__,
                                                       func.__name__,
                                                       args,
                                                       kwargs)
        return wrapper
    return outer


def check_task_completed(func):
    @wraps(func)
    async def outer(obj, *args, **kwargs):
        obj_cls = obj.__class__.__name__
        obj_func = func.__name__
        twitter_username_db = await obj.db.get_bound_twitter_token(obj.client.address)
        if not twitter_username_db:
            twitter_username = await obj.twitter_task.get_account_username()
        else:
            twitter_username = twitter_username_db.get('twitter_username')
        task = await obj.db.get_completed_tasks_by_cls_and_func(obj.client.address,
                                                                obj_cls,
                                                                obj_func,
                                                                twitter_username)
        if task:
            obj.logger.info("This task with this account data already completed!")
        else:
            await func(obj, *args, **kwargs)
    return outer


async def build_twitter_table(db_path):
    db = GalxeDb(db_path)
    table = PrettyTable()
    table.field_names = [
        "Address",
        "GOOD",
        "Bad",
        "LOCKED",
        "SUSPENDED"
    ]
    for doc in await db.get_twitter_stat():
        address = doc['address']
        token = doc['token']
        status = doc['status']
        token_statuses = ['-'] * 4
        token_statuses[table.field_names.index(status)-1] = token
        table.add_row(
            [
                address,
                *token_statuses
            ])
    await db.truncate_stat_table()
    return table


async def build_bound_accounts_data():
    db = GalxeDb(GLOBAL_DB)
    table = PrettyTable()
    table.field_names = [
        "Address",
        'Email',
        'Twitter_token',
        'Twitter_username',
        'Aptos wallet',
        'Sui wallet'
    ]
    bound_socials_data = await db.get_bound_socials_all()
    for doc in bound_socials_data:
        address = doc.get('address')
        email = doc.get('email')
        email_formatted = (email[:7] + '...' + email[-15:]) if email else email
        twitter_token = doc.get('twitter')
        twitter_username = doc.get('twitter_username')
        aptos_wallet = doc.get('aptos_address')
        aptos_address_formatted = (aptos_wallet[:7] + '...' + aptos_wallet[-3:]) if aptos_wallet else aptos_wallet
        sui_wallet = doc.get('sui_address')
        sui_address_formatted = (sui_wallet[:7] + '...' + sui_wallet[-5:]) if sui_wallet else sui_wallet
        table.add_row(
            [
                address,
                email_formatted,
                twitter_token,
                twitter_username,
                aptos_address_formatted,
                sui_address_formatted
            ])
    return table
