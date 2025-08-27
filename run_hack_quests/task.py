from os import fstat

import faker
from utils.client import Client
from utils.utils import (retry, check_res_status, get_utc_now,
                         get_data_lines, sleep, Logger,
                         read_json, Contract, generate_random_hex_string,
                         get_utc_now, approve_asset, asset_balance, get_decimals, approve_if_insufficient_allowance,
                         generate_random, retry_js, JSException, ModernTask, get_session, get_gas_params, estimate_gas)
import re
import json
import random
from .tasks.phases import Phases
from faker import Faker
import string
from .config import GATHER_REF, USE_REF, FEED_PET_MAX_LVL, SLEEP_FROM_TO
from .paths import REFERRALS, UNUSED_REFERRALS
from eth_abi import encode as abi_encode
from datetime import timezone, timedelta, datetime


class Task(Logger, ModernTask):
    def __init__(self, session, client: Client, db_manager):
        self.session = session
        self.client = client
        self.db_manager = db_manager
        super().__init__(self.client.address, additional={'pk': self.client.key,
                                                          'proxy': self.session.proxies.get('http')})
        self.user_id = None

    @retry()
    @check_res_status()
    async def get_nonce(self):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation GetNonce($address: String!) {\n  nonce: getNonce(address: $address) {\n    nonce\n    message\n  }\n}\n    ',
            'variables': {
                'address': self.client.address,
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def login_request(self, nonce, msg_to_sign):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation LoginByWallet($input: SignInByWalletInput!) {\n  loginByWallet(input: $input) {\n    access_token\n    refresh_token\n    user {\n      ...baseUserInfo\n    }\n  }\n}\n    \n    fragment baseUserInfo on UserExtend {\n  id\n  uid\n  name\n  avatar\n  username\n  nickname\n  email\n  role\n  voteRole\n  status\n  inviteCode\n  invitedBy\n  hackCoin {\n    coin\n  }\n  levelInfo {\n    level\n    exp\n  }\n  organizations {\n    id\n    creatorId\n    slug\n    name\n    displayName\n    backgroundImage\n    oneLineIntro\n    about\n    logo\n    webSite\n    socialLinks\n    profileSectionState\n    permissionCode\n    permissions\n    createdAt\n    active\n    members {\n      id\n      userId\n      isOwner\n    }\n    features {\n      featureCode\n    }\n  }\n}\n    ',
            'variables': {
                'input': {
                    'address': self.client.address,
                    'chainId': 1,
                    'signature': self.client.get_signed_code(msg_to_sign),
                    'message': msg_to_sign,
                    'nonce': nonce,
                    'walletType': 'io.rabby',
                },
            },
        }
        return await self.session.post(url, json=json_data)

    async def login(self, reg=False):
        while True:
            nonce_response = (await self.get_nonce()).json()['data']['nonce']
            nonce = nonce_response['nonce']
            msg_to_sign = nonce_response['message']
            try:
                login_response = (await self.login_request(nonce, msg_to_sign)).json()
                if ' 402 Payment Required' in str(login_response):
                    self.logger.error("Server error. Trying again in 60-90 min...")
                    await sleep(3600, 4400)
                    continue
                login_response = login_response['data']['loginByWallet']
            except TypeError:
                self.logger.error("Need to send login request again...")
                await sleep(5, 10)
                continue
            break
        self.user_id = login_response['user']['id']
        jwt = login_response['access_token']
        self.session.headers['Authorization'] = 'Bearer ' + jwt
        if not reg:
            self.logger.success("Successfully logged in!")

    @retry()
    @check_res_status()
    async def activate_user(self, code):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation ActivateUser($accessToken: String!, $inviteCode: String) {\n  activateUser(access_token: $accessToken, inviteCode: $inviteCode) {\n    access_token\n    user {\n      ...baseUserInfo\n    }\n    status\n    error\n  }\n}\n    \n    fragment baseUserInfo on UserExtend {\n  id\n  uid\n  name\n  avatar\n  username\n  nickname\n  email\n  role\n  voteRole\n  status\n  inviteCode\n  invitedBy\n  hackCoin {\n    coin\n  }\n  levelInfo {\n    level\n    exp\n  }\n  organizations {\n    id\n    creatorId\n    slug\n    name\n    displayName\n    backgroundImage\n    oneLineIntro\n    about\n    logo\n    webSite\n    socialLinks\n    profileSectionState\n    permissionCode\n    permissions\n    createdAt\n    active\n    members {\n      id\n      userId\n      isOwner\n    }\n    features {\n      featureCode\n    }\n  }\n}\n    ',
            'variables': {
                'accessToken': self.session.headers['Authorization'].split('Bearer ')[1]
            }
        }
        if code:
            self.logger.info(f"Using {code} referral code...")
            json_data['variables']['inviteCode'] = code
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def update_user_step(self):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation UpdateUserSettings($input: UserSettingsCreateInput!) {\n  updateUserSettings(input: $input)\n}\n    ',
            'variables': {
                'input': {
                    'guideStep': 5,
                },
            },
        }
        return await self.session.post(url, json=json_data)

    async def registration(self):
        await self.login(reg=True)
        random_code = await self.random_referral if USE_REF else None
        await self.activate_user(random_code)
        await self.update_user_step()
        if USE_REF:
            await self.db_manager.insert_column(self.client.key, 'applied_referral_code', random_code)
        self.logger.success("Successfully registered!")

    @property
    async def random_referral(self):
        codes = list(i for i in get_data_lines(REFERRALS) if i)
        if not codes:
            self.logger.error("REFERRALS.TXT IS BLANK")
            return
        own_code = await self.db_manager.get_column(self.client.key, 'own_referral_code')
        if len(codes) == 1 and codes[0] == own_code:
            self.logger.info("Can't get code, because you have only you own referral code!")
            return None
        while True:
            random_code = random.choice(list(i for i in get_data_lines(REFERRALS) if i))
            if random_code == own_code:
                continue
            return random_code

    async def write_ref_codes(self):
        await self.login()
        while True:
            home = await self.home()
            home_text = home.text[home.text.index(r'"claimed\":\"Claimed\",\"yes\":\"Yes\",\"no\":\"No\"'):]
            INVITE_RE = re.compile(r'inviteCode\\":\\"([A-Z0-9]{10})\\"')
            m = INVITE_RE.search(home_text)
            code = m.group(1)
            if not code:
                self.logger.error("Need to get referral code again...")
                await sleep(5, 10)
                continue
            break
        self.write_invite_code(code)
        await self.db_manager.insert_column(self.client.key, 'own_referral_code', code)

    def write_invite_code(self, invite_code):
        WRITE_TO = REFERRALS if GATHER_REF else UNUSED_REFERRALS
        all_referrals = list(get_data_lines(REFERRALS))
        unused_referrals = list(get_data_lines(UNUSED_REFERRALS))
        if invite_code not in all_referrals and invite_code not in unused_referrals:
            self.logger.info(f"Got {invite_code} referral code. Writing...")
            with open(WRITE_TO, 'a') as file:
                file.write(invite_code + '\n')

    @retry()
    @check_res_status()
    async def get_projects(self):
        url = 'https://www.hackquest.io/projects'
        params = {
            'page': str(random.randint(1, 300)),
            '_rsc': 'ezc2l',
        }
        headers = {
            'accept': '*/*',
            'accept-language': 'uk-UA,uk;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6',
            'next-router-state-tree': '%5B%22%22%2C%7B%22children%22%3A%5B%5B%22locale%22%2C%22en%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22(main)%22%2C%7B%22children%22%3A%5B%22(build)%22%2C%7B%22children%22%3A%5B%22projects%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fprojects%22%2C%22refresh%22%5D%7D%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D',
            'next-url': '/en/projects',
            'priority': 'u=1, i',
            'referer': 'https://www.hackquest.io/projects',
            'rsc': '1',
            'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self.session.headers['User-Agent']
        }
        return await self.session.get(url, params=params, headers=headers)

    @retry()
    @check_res_status()
    async def like_project(self, project_id):
        url = 'https://www.hackquest.io/projects'
        headers = {
            'accept': 'text/x-component',
            'accept-language': 'uk-UA,uk;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6',
            'content-type': 'text/plain;charset=UTF-8',
            'next-action': '8b246d4f3cc053b0895934945aecf62e6607f457',
            'next-router-state-tree': '%5B%22%22%2C%7B%22children%22%3A%5B%5B%22locale%22%2C%22en%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22(main)%22%2C%7B%22children%22%3A%5B%22(build)%22%2C%7B%22children%22%3A%5B%22projects%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fprojects%22%2C%22refresh%22%5D%7D%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D',
            'origin': 'https://www.hackquest.io',
            'priority': 'u=1, i',
            'referer': 'https://www.hackquest.io/projects',
            'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self.session.headers['User-Agent']
        }
        data = f'["{project_id}"]'
        return await self.session.post(url, data=data, headers=headers)

    @retry()
    @check_res_status()
    async def home(self):
        url = 'https://www.hackquest.io/home'
        return await self.session.get(url, timeout=180)

    def _deescape_next_dump(self, text):
        text = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), text)
        text = re.sub(r'\\([{}\[\]"])', r'\1', text)
        text = text.replace('\\/', '/')
        return text

    def _extract_json_array(self, text, key = "missions"):
        m = re.search(rf'"{re.escape(key)}"\s*:\s*\[', text)
        if not m:
            raise ValueError("array not found")
        i = m.end() - 1
        depth = 0
        in_str = False
        esc = False
        for j in range(i, len(text)):
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        return json.loads(text[i:j + 1])
        raise ValueError("unterminated array")

    def extract_my_pet(self, raw):
        cleaned = self._deescape_next_dump(raw)
        try:
            return self._extract_json_array(cleaned, "myPet")
        except Exception:
            pass
        for m in re.finditer(r'"myPet"\s*:', cleaned):
            brace_pos = cleaned.find('{', m.end())
            if brace_pos == -1:
                continue
            depth = 0
            in_str = False
            esc = False
            for j in range(brace_pos, len(cleaned)):
                ch = cleaned[j]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(cleaned[brace_pos:j + 1])
                            except Exception:
                                break
        return None

    def extract_missions(self, raw, loop_mode="DAILY"):
        cleaned = self._deescape_next_dump(raw)
        try:
            missions = self._extract_json_array(cleaned, "missions")
            return [m for m in missions if m.get("loopMode") == loop_mode]
        except Exception:
            pass

        out = []
        for m in re.finditer(fr'"loopMode"\s*:\s*{loop_mode}', cleaned):
            start = cleaned.rfind("{", 0, m.start())
            if start == -1:
                continue
            depth = 0
            in_str = False
            esc = False
            for i in range(start, len(cleaned)):
                ch = cleaned[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                obj = json.loads(cleaned[start:i + 1])
                            except Exception:
                                break
                            if obj.get("loopMode") == loop_mode:
                                out.append(obj)
                            break
        uniq = {}
        for o in out:
            uniq[o.get("id") or json.dumps(o, sort_keys=True)] = o
        return list(uniq.values())

    @retry()
    @check_res_status()
    async def claim_mission(self, mission_id):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation ClaimMissionReward($missionId: String!) {\n  claimMissionReward(missionId: $missionId) {\n    coin\n    exp\n  }\n}\n    ',
            'variables': {
                'missionId': mission_id,
            },
        }
        return await self.session.post(url, json=json_data)

    def random_username(self, prefix_at=False, min_len=4, max_len=15):
        letters_digits = string.ascii_lowercase + string.digits
        rest_chars = letters_digits + "_"
        length = random.randint(min_len, max_len)
        handle = random.choice(letters_digits) + ''.join(
            random.choice(rest_chars) for _ in range(length - 1)
        )
        return handle if prefix_at else handle

    def _fake_info(self):
        fake = Faker()
        gender = random.choice(["Man", "Woman"])
        first = fake.first_name_male() if gender == "Man" else fake.first_name_female()
        if gender == "Man" and hasattr(fake, "last_name_male"):
            last = fake.last_name_male()
        elif gender == "Woman" and hasattr(fake, "last_name_female"):
            last = fake.last_name_female()
        else:
            last = fake.last_name()
        return {
            "firstName": first,
            "lastName": last,
            "bio": fake.job(),
            "gender": gender,
            "university": random.choice(["MIT", "Stanford University", "Imperial College London",
                                         "University of Oxford", "Harvard University", "University of Cambridge"]),
            "location": fake.city(),
            "twitter": self.random_username(),
            "github": self.random_username(),
            "discord": self.random_username(),
            "email": fake.email()
        }

    @retry()
    @check_res_status()
    async def register_hackathon_step_1(self, random_data):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation HackathonRegister($hackathonId: String!, $data: HackathonRegisterCreateInfoInput!) {\n  hackathonRegister(hackathonId: $hackathonId, data: $data) {\n    id\n    info\n    isRegister\n    joinState\n    status\n  }\n}\n    ',
            'variables': {
                'hackathonId': '3a878d2d-c57c-4987-94c5-864ee0586943',
                'data': {
                    'info': {
                        'About': {
                            'firstName': random_data['firstName'],
                            'lastName': random_data['lastName'],
                            'bio': random_data['bio'],
                            'gender': random_data['gender'],
                            'university': random_data['university'],
                            'location': random_data['location'],
                        },
                    },
                    'status': 'OnlineProfiles',
                    'utmSource': '',
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def register_hackathon_step_2(self, random_data):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation HackathonRegister($hackathonId: String!, $data: HackathonRegisterCreateInfoInput!) {\n  hackathonRegister(hackathonId: $hackathonId, data: $data) {\n    id\n    info\n    isRegister\n    joinState\n    status\n  }\n}\n    ',
            'variables': {
                'hackathonId': '3a878d2d-c57c-4987-94c5-864ee0586943',
                'data': {
                    'info': {
                        'About': {
                            'firstName': random_data['firstName'],
                            'lastName': random_data['lastName'],
                            'bio': random_data['bio'],
                            'gender': random_data['gender'],
                            'university': random_data['university'],
                            'location': random_data['location'],
                        },
                        'OnlineProfiles': {
                            'github': random_data['github'],
                            'twitter': random_data['twitter'],
                        },
                    },
                    'status': 'Contact',
                    'utmSource': '',
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def register_hackathon_step_3(self, random_data):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation HackathonRegister($hackathonId: String!, $data: HackathonRegisterCreateInfoInput!) {\n  hackathonRegister(hackathonId: $hackathonId, data: $data) {\n    id\n    info\n    isRegister\n    joinState\n    status\n  }\n}\n    ',
            'variables': {
                'hackathonId': '3a878d2d-c57c-4987-94c5-864ee0586943',
                'data': {
                    'info': {
                        'About': {
                            'firstName': random_data['firstName'],
                            'lastName': random_data['lastName'],
                            'bio': random_data['bio'],
                            'gender': random_data['gender'],
                            'university': random_data['university'],
                            'location': random_data['location'],
                        },
                        'OnlineProfiles': {
                            'github': random_data['github'],
                            'twitter': random_data['twitter'],
                        },
                        'Contact': {
                            'email': random_data['email'],
                            'discord': random_data['discord']
                        },
                    },
                    'status': 'Contact',
                    'isRegister': True,
                    'utmSource': '',
                },
            },
        }
        return await self.session.post(url, json=json_data)

    async def register_in_hackathon(self):
        random_data = self._fake_info()
        await self.register_hackathon_step_1(random_data)
        await sleep(3, 5)
        await self.register_hackathon_step_2(random_data)
        await sleep(3, 5)
        await self.register_hackathon_step_3(random_data)
        self.logger.success("Successfully registered in hackathon!")

    @staticmethod
    def seconds_until_next_day(min_delay, max_delay):
        now = datetime.now(timezone.utc)
        next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_left = (next_day - now).total_seconds()
        random_delay = random.randint(min_delay, max_delay)
        return int(seconds_left + random_delay)

    async def infinity_run_daily(self):
        while True:
            await self.login()
            await self.run_daily()
            random_sleep_daily_time = self.seconds_until_next_day(*SLEEP_FROM_TO)
            self.logger.info(f"Sleeping for {random_sleep_daily_time}s before next day...")
            await sleep(random_sleep_daily_time)

    async def run_daily(self):
        if await self.db_manager.get_column(self.client.key, 'need_to_recomplete'):
            self.logger.info("Starting recompleting unfinished tasks...")
            phases_task = Phases(self.session,
                                 self.client,
                                 self.db_manager,
                                 self.logger)
            await phases_task.recomplete_quests()
            await self.db_manager.insert_column(self.client.key, 'need_to_recomplete', False)
        await self.create_pet()
        while True:
            try:
                res = await self.get_projects()
                match = re.search(r'b:(\{.*?\})(?=\s*\w+:|$)', res.text, re.S)
                json_str = match.group(1)
                break
            except AttributeError:
                continue
        projects = json.loads(json_str)['data']
        while True:
            home = await self.home()
            home_text = home.text[home.text.index(r'"claimed\":\"Claimed\",\"yes\":\"Yes\",\"no\":\"No\"'):]
            daily = self.extract_missions(home_text)
            if not daily:
                self.logger.error("Need to get tasks again...")
                await sleep(5, 10)
                continue
            break
        random.shuffle(daily)
        completed = False
        for task in daily:
            if task['name'] == 'Daily Project Like':
                if not task['progress'] or not task['progress']['completed']:
                    self.logger.info(f"Need to complete task `{task['name']}` today")
                    random_projects = random.sample(projects, random.randint(4, 7))
                    for project in random_projects:
                        self.logger.info(f"Liking project {project['name']}...")
                        await self.like_project(project['id'])
                        await sleep(10, 15)
                    completed = True
            elif task['name'] == 'Daily Course Complete':
                if not task['progress'] or not task['progress']['completed']:
                    self.logger.info(f"Need to complete task `{task['name']}` today")
                    phases_task = Phases(self.session,
                                         self.client,
                                         self.db_manager,
                                         self.logger)
                    await phases_task.complete_unit()
                    completed = True
        if completed:
            self.logger.info("Sleeping 2-3 minutes before claiming tasks...")
            await sleep(120, 180)
        while True:
            home = await self.home()
            home_text = home.text[home.text.index(r'"claimed\":\"Claimed\",\"yes\":\"Yes\",\"no\":\"No\"'):]
            daily = self.extract_missions(home_text)
            if not daily:
                self.logger.error("Need to get tasks again...")
                await sleep(5, 10)
                continue
            break
        random.shuffle(daily)
        for task in daily:
            if task['progress'] and task['progress']['completed']:
                if task['progress']['claimed']:
                    self.logger.info(f"Task {task['name']} already completed today!")
                else:
                    claim_mission_response = (await self.claim_mission(task['id'])).json()['data']['claimMissionReward']
                    self.logger.success(f"Task {task['name']} claimed successfully! Your reward: {claim_mission_response}")
            else:
                self.logger.error(f"Task {task['name']} not completed today!")

        while True:
            home = await self.home()
            home_text = home.text[home.text.index(r'"claimed\":\"Claimed\",\"yes\":\"Yes\",\"no\":\"No\"'):]
            one_time = self.extract_missions(home_text, loop_mode="ONE_TIME")
            if not one_time:
                self.logger.error("Need to get tasks again....")
                await sleep(5, 10)
                continue
            break
        completed = False
        for task in one_time:
            if task['name'] == 'Register Hackathon':
                if not task['progress'] or not task['progress']['completed']:
                    self.logger.info(f"Need to complete task one-time `{task['name']}`")
                    await self.register_in_hackathon()
                    completed = True
            elif task['name'] == 'Quack Private':
                if not task['progress'] or not task['progress']['completed']:
                    await self.mint_nft_task()
        if completed:
            self.logger.info("Sleeping 2-3 minutes before claiming tasks...")
            await sleep(120, 180)
        while True:
            home = await self.home()
            home_text = home.text[home.text.index(r'"claimed\":\"Claimed\",\"yes\":\"Yes\",\"no\":\"No\"'):]
            one_time = self.extract_missions(home_text, loop_mode="ONE_TIME")
            if not one_time:
                self.logger.error("Need to get tasks again....")
                await sleep(5, 10)
                continue
            break
        random.shuffle(one_time)
        for task in one_time:
            if task['progress'] and task['progress']['completed']:
                if task['progress']['claimed']:
                    self.logger.info(f"Task {task['name']} already completed!")
                else:
                    claim_mission_response = (await self.claim_mission(task['id'])).json()['data']['claimMissionReward']
                    self.logger.success(f"Task {task['name']} claimed successfully! Your reward: {claim_mission_response}")
                    await sleep(10, 30)
            else:
                self.logger.error(f"Task {task['name']} not completed!")
        await self.feed_pet()

    async def mint_nft_task(self):
        home = await self.home()
        home_text = home.text[home.text.index(r'"claimed\":\"Claimed\",\"yes\":\"Yes\",\"no\":\"No\"'):]
        my_pet = self.extract_my_pet(home_text)
        if not my_pet.get('name'):
            self.logger.error("You need to create your pet first!")
            return
        nft_signature = (await self.get_nft_signature()).json()['data']['nftSignature']['signature']
        task_id = (await self.sponsored_call(nft_signature)).json()['taskId']
        while True:
            task_status = (await self.get_task_status(task_id)).json()['task']
            if task_status['taskState'] == 'ExecPending' or task_status['taskState'] == 'CheckPending':
                self.logger.info(f"Waiting for task completion...Current status - {task_status['taskState']}")
                await sleep(10, 15)
                continue
            elif task_status['taskState'] == 'ExecSuccess':
                self.logger.success("Task completed successfully!")
                tx_hash = task_status['transactionHash']
                await self.complete_task_mint_nft(tx_hash)
                break
            else:
                self.logger.error(f"Task completed unexpectedly! {task_status}")
                break

    @retry()
    @check_res_status()
    async def complete_task_mint_nft(self, tx_hash):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation MintTask($missionId: String!, $transitionHash: String!) {\n  mintTask(missionId: $missionId, transitionHash: $transitionHash)\n}\n    ',
            'variables': {
                'missionId': '00a11a0d-f991-4899-b29e-86440d0e6079',
                'transitionHash': tx_hash,
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def get_task_status(self, task_id):
        url = f'https://api.gelato.digital/tasks/status/{task_id}'
        return await self.session.get(url)

    @retry()
    @check_res_status()
    async def sponsored_call(self, signature):
        url = 'https://api.gelato.digital/relays/v2/sponsored-call'
        name = "QUACK_NFT_Pet_HiQuackPrivate_ONE_TIME"
        sig_bytes = self.client.w3.to_bytes(hexstr=signature)
        selector = '0x4618968b'
        types = ['address', 'string', 'string', 'bytes[]', 'bytes']
        values = [self.client.address, self.user_id, name, [], sig_bytes]
        encoded_args = abi_encode(types, values)
        data = selector + encoded_args.hex()
        json_data = {
            'chainId': '41923',
            'target': '0x9994dA6379be8C0edd970d82bfA73869609f889D',
            'data': data,
            'sponsorApiKey': 'ylhPSeNIOkCZcmsJrqI9nomTtTtifkVcRyWSnjy5Eg8_',
        }
        return await self.session.post(url, json=json_data)

    async def create_pet(self):
        home = await self.home()
        home_text = home.text[home.text.index(r'"claimed\":\"Claimed\",\"yes\":\"Yes\",\"no\":\"No\"'):]
        my_pet = self.extract_my_pet(home_text)
        if not my_pet.get('name'):
            self.logger.info("You have not your own pet. Creating...")
            while True:
                create_pet_response = (await self.create_pet_request()).json()
                if 'already exists' in str(create_pet_response):
                    self.logger.info("This pet username already exists. Trying again...")
                    continue
                break
            self.logger.success("Successfully created pet!")
            await sleep(60, 90)
            await self.mint_nft_task()
        else:
            self.logger.info(f"You already have pet. Name - {my_pet.get('name')}. Level - {my_pet.get('level')}")

    @retry()
    @check_res_status()
    async def create_pet_request(self):
        url = 'https://api.hackquest.io/graphql'
        fake = Faker()
        pet_name = fake.word() + fake.word() + str(random.randint(1000, 9999))
        self.logger.info(f"Creating pet with {pet_name} name...")
        json_data = {
            'query': '\n    mutation CreatePet($name: String!) {\n  createPet(name: $name) {\n    id\n    name\n    level\n    exp\n    expNextLevel\n    userId\n    hatch\n    extra\n  }\n}\n    ',
            'variables': {
                'name': pet_name,
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def get_nft_signature(self):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation NftSignature($missionId: String!, $address: String!) {\n  nftSignature(missionId: $missionId, address: $address) {\n    signature\n    msg\n  }\n}\n    ',
            'variables': {
                'missionId': '00a11a0d-f991-4899-b29e-86440d0e6079',
                'address': self.client.address,
            },
        }
        return await self.session.post(url, json=json_data)

    async def feed_pet(self):
        max_pet_lvl_in_db = await self.db_manager.get_column(self.client.key, 'max_pet_lvl')
        if max_pet_lvl_in_db is None:
            max_lvl = random.randint(*FEED_PET_MAX_LVL)
            await self.db_manager.insert_column(self.client.key, 'max_pet_lvl', max_lvl)
        while True:
            home = await self.home()
            home_text = home.text[home.text.index(r'"claimed\":\"Claimed\",\"yes\":\"Yes\",\"no\":\"No\"'):]
            my_pet = self.extract_my_pet(home_text)
            current_pet_lvl = my_pet.get('level')
            if current_pet_lvl is None:
                self.logger.error("Need to get pet info again..")
                await sleep(5, 10)
                continue
            break
        max_pet_lvl_in_db = await self.db_manager.get_column(self.client.key, 'max_pet_lvl')
        if current_pet_lvl >= max_pet_lvl_in_db:
            self.logger.info("You already have pet with greater lvl than needed")
            return

        while True:
            feed_response = (await self.feed_pet_request()).json()
            if 'Insufficient hack coin' in str(feed_response):
                self.logger.error("Need more hack coins to feed. Try again later")
                break
            try:
                pet_lvl = feed_response['data']['feedPet']['level']
            except TypeError:
                self.logger.error("Need to get pet info again..")
                await sleep(5, 10)
                continue
            if pet_lvl >= max_pet_lvl_in_db:
                self.logger.info("You already have pet with greater lvl than needed")
                return
            self.logger.success("Feed successfully!")
            await sleep(5, 10)





    @retry()
    @check_res_status()
    async def feed_pet_request(self):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation FeedPet($amount: Float!) {\n  feedPet(amount: $amount) {\n    userId\n    level\n    exp\n  }\n}\n    ',
            'variables': {
                'amount': 5,
            },
        }
        return await self.session.post(url, json=json_data)
