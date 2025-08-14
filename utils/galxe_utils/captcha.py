import concurrent.futures

import twocaptcha
from twocaptcha import TwoCaptcha
import json
from capmonstercloudclient import CapMonsterClient, ClientOptions
from capmonstercloudclient.exceptions import GetBalanceError
from capmonstercloudclient.requests import (GeetestRequest,
                                            RecaptchaV2Request,
                                            RecaptchaV3ProxylessRequest,
                                            TurnstileRequest,
                                            TurnstileProxylessRequest,
                                            HcaptchaRequest,
                                            ImageToTextRequest,
                                            RecaptchaV2EnterpriseRequest,)
from urllib.parse import urlparse
import asyncio
import aiohttp
from http.client import HTTPException
from typing import Dict, Union
from utils.utils import retry, check_res_status, get_session, sleep
import base64
import httpx


class CaptchaSolver:
    def __init__(self, session = None, api_key: str = None, logger=None):
        if api_key is None:
            raise Exception("2captcha API key is missing. Set it in settings.py")

        self.config = {
            "apiKey": api_key,
        }

        self.proxy = session.proxies.get("http")
        self.solver = TwoCaptcha(**self.config)
        self.logger = logger

    def get_balance(self):
        return self.solver.balance()

    def sync_send_bad_report_request(self, captcha_id):
        return self.solver.report(captcha_id, False)

    async def send_report(self, captcha_id):
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            await loop.run_in_executor(pool, lambda: self.sync_send_bad_report_request(captcha_id))

    def solve(self):
        captcha = self.solver.geetest_v4(captcha_id='244bcb8b9846215df5af4c624a750db4',
                                         url='https://app.galxe.com',
                                         proxy={"type": "HTTP", "uri": self.proxy})
        return captcha

    def solve_recaptcha_v3_enterprise_request(self, url, key, action):
        captcha = self.solver.recaptcha(
            sitekey=key,
            url=url,
            version='v3',
            action=action,
            score=0.9,
            enterprise=1,
            invisible=1,
            userAgent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
        )
        return captcha

    async def solve_recaptcha_v3_enterprise(self, url, key, action):
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            while True:
                try:
                    solution = await loop.run_in_executor(pool, lambda: self.solve_recaptcha_v3_enterprise_request(url,
                                                                                                                   key,
                                                                                                                   action))
                    captcha_id = solution['captchaId']
                    self.logger.success('Captcha solved successfully!')
                    solution = solution['code']
                    return captcha_id, solution
                except twocaptcha.api.ApiException as e:
                    self.logger.error(f'Error with solving captcha {e}. Trying again...')
                except twocaptcha.api.NetworkException as e:
                    self.logger.error(f'Network error with solving captcha {e}. Trying again...')
                except twocaptcha.solver.TimeoutException as e:
                    self.logger.error(f'Timeout exception {e}. Trying again...')

    def solve_turnstile_request(self, url, key):
        captcha = self.solver.turnstile(
            sitekey=key,
            url=url
        )
        return captcha

    async def solve_turnstile(self, url, key):
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            while True:
                try:
                    solution = await loop.run_in_executor(pool, lambda: self.solve_turnstile_request(url, key))
                    self.logger.success('Captcha solved successfully!')
                    solution = {'token': solution['code']}
                    return solution
                except twocaptcha.api.ApiException as e:
                    self.logger.error(f'Error with solving captcha {e}. Trying again...')
                except twocaptcha.api.NetworkException as e:
                    self.logger.error(f'Network error with solving captcha {e}. Trying again...')
                except twocaptcha.solver.TimeoutException as e:
                    self.logger.error(f'Timeout exception {e}. Trying again...')
                except Exception as e:
                    self.logger.error(f'Unknown exception {e}. Trying again...')

    async def solve_captcha(self, logger):
        self.logger = logger
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            while True:
                try:
                    solution = await loop.run_in_executor(pool, lambda: self.solve())
                    captcha_id = solution['captchaId']
                    logger.success('Captcha solved successfully!')
                    solution_code = json.loads(solution['code'])
                    solution = {
                        'lot_number': solution_code['lot_number'],
                        'seccode': {
                            'captcha_output': solution_code['captcha_output'],
                            'pass_token': solution_code['pass_token'],
                            'gen_time': solution_code['gen_time'],
                        }
                    }
                    return captcha_id, solution
                except twocaptcha.api.ApiException as e:
                    logger.error(f'Error with solving captcha {e}. Trying again...')
                except twocaptcha.api.NetworkException as e:
                    logger.error(f'Network error with solving captcha {e}. Trying again...')
                except twocaptcha.solver.TimeoutException as e:
                    logger.error(f'Timeout exception {e}. Trying again...')

    async def solve_captcha(self, logger):
        self.logger = logger
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            while True:
                try:
                    solution = await loop.run_in_executor(pool, lambda: self.solve())
                    captcha_id = solution['captchaId']
                    logger.success('Captcha solved successfully!')
                    solution_code = json.loads(solution['code'])
                    solution = {
                        'lot_number': solution_code['lot_number'],
                        'seccode': {
                            'captcha_output': solution_code['captcha_output'],
                            'pass_token': solution_code['pass_token'],
                            'gen_time': solution_code['gen_time'],
                        }
                    }
                    return captcha_id, solution
                except twocaptcha.api.ApiException as e:
                    logger.error(f'Error with solving captcha {e}. Trying again...')
                except twocaptcha.api.NetworkException as e:
                    logger.error(f'Network error with solving captcha {e}. Trying again...')
                except twocaptcha.solver.TimeoutException as e:
                    logger.error(f'Timeout exception {e}. Trying again...')

    def solve_img_to_text_request(self, img):
        captcha = self.solver.normal(img,
                                     minLen=6,
                                     maxLem=6,
                                     regsense=1,
                                     language=2,
                                     caseSensitive=True,
                                     proxy={"type": "HTTP", "uri": self.proxy})
        return captcha

    async def solve_img_to_text(self, img):
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            while True:
                try:
                    solution = await loop.run_in_executor(pool, lambda: self.solve_img_to_text_request(img))
                    return solution['captchaId'], solution['code']
                except twocaptcha.api.ApiException as e:
                    self.logger.error(f'Error with solving captcha {e}. Trying again...')
                except twocaptcha.api.NetworkException as e:
                    self.logger.error(f'Network error with solving captcha {e}. Trying again...')
                except twocaptcha.solver.TimeoutException as e:
                    self.logger.error(f'Timeout exception {e}. Trying again...')

    async def send_bad_report(self, captcha_id):
        self.logger.info('Sending bad captcha report...')
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            await loop.run_in_executor(pool, lambda: self.sync_send_bad_report(captcha_id))


class CapmonsterSolver:
    def __init__(self, session = None, api_key: str = None, logger=None):
        if api_key is None:
            raise Exception("Capmonster API key is missing. Set it in config.py")
        self.config = {
            "api_key": api_key,
            'ssl': False
        }
        self.proxy = session.proxies.get("http")
        parsed_url = urlparse(self.proxy)
        self.proxy_type = parsed_url.scheme
        self.proxy_login = parsed_url.username
        self.proxy_password = parsed_url.password
        self.proxy_ip = parsed_url.hostname
        self.proxy_port = parsed_url.port
        self.client_options = ClientOptions(**self.config)
        self.cap_monster_client = CustomCapmonsterClient(options=self.client_options)
        self.logger = logger

    async def solve_geetest4_request(self):
        geetest_4_request = GeetestRequest(gt='244bcb8b9846215df5af4c624a750db4',
                                           websiteUrl='https://app.galxe.com',
                                           version=4,
                                           proxyType=self.proxy_type,
                                           proxyAddress=self.proxy_ip,
                                           proxyPort=self.proxy_port,
                                           proxyLogin=self.proxy_login,
                                           proxyPassword=self.proxy_password,)
        return await self.cap_monster_client.solve_captcha(geetest_4_request)

    async def solve_recaptchav2_request(self, key, url):
        recaptchav2_request = RecaptchaV2Request(websiteUrl=url,
                                                 websiteKey=key,
                                                 proxyType=self.proxy_type,
                                                 proxyAddress=self.proxy_ip,
                                                 proxyPort=self.proxy_port,
                                                 proxyLogin=self.proxy_login,
                                                 proxyPassword=self.proxy_password)
        return await self.cap_monster_client.solve_captcha(recaptchav2_request)


    async def solve_recaptchav2_enterprise_request(self, url, key):
        recaptchav2_request = RecaptchaV2EnterpriseRequest(websiteUrl=url,
                                                         websiteKey=key,
                                                         proxyType=self.proxy_type,
                                                         proxyAddress=self.proxy_ip,
                                                         proxyPort=self.proxy_port,
                                                         proxyLogin=self.proxy_login,
                                                         proxyPassword=self.proxy_password)
        return await self.cap_monster_client.solve_captcha(recaptchav2_request)

    async def solve_recaptchav2_enterprise(self, url, key):
        while True:
            try:
                solution = await self.solve_recaptchav2_enterprise_request(url, key)
                return solution
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')


    async def solve_recaptchav3_request(self, key, url, action, min_score):
        recaptchav3_request = RecaptchaV3ProxylessRequest(websiteUrl=url,
                                                          websiteKey=key,
                                                          pageAction=action,
                                                          min_score=min_score)
        return await self.cap_monster_client.solve_captcha(recaptchav3_request)

    async def solve_captcha(self, logger):
        self.logger = logger
        while True:
            try:
                solution = await self.solve_geetest4_request()
                captcha_id = solution['captcha_id']
                logger.success('Captcha solved successfully!')
                solution = {
                    'lot_number': solution['lot_number'],
                    'seccode': {
                        'captcha_output': solution['captcha_output'],
                        'pass_token': solution['pass_token'],
                        'gen_time': solution['gen_time']
                    }
                }
                return captcha_id, solution
            except GetBalanceError:
                logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                logger.error(f'Captcha exception {e}')

    async def solve_recaptchav2(self,
                                url='https://faucet.movementlabs.xyz',
                                key='6LdVjR0qAAAAAFSjzYqyRFsnUDn-iRrzQmv0nnp3'):
        while True:
            try:
                solution = await self.solve_recaptchav2_request(key, url)
                return solution
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

    async def solve_recaptchav3(self,
                                url='https://faucet.movementlabs.xyz',
                                key='6LdVjR0qAAAAAFSjzYqyRFsnUDn-iRrzQmv0nnp3',
                                action='drip_request',
                                min_score=0.9):
        while True:
            try:
                solution = await self.solve_recaptchav3_request(key, url, action, min_score)
                return solution
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

    async def turnstile_cookies_request(self, url, key, cloudflare_response_base64, user_agent):
        turnstile_request = TurnstileRequest(websiteURL=url,
                                             websiteKey=key,
                                             cloudflareTaskType="cf_clearance",
                                             htmlPageBase64=cloudflare_response_base64,
                                             userAgent=user_agent,
                                             proxyType=self.proxy_type,
                                             proxyAddress=self.proxy_ip,
                                             proxyPort=self.proxy_port,
                                             proxyLogin=self.proxy_login,
                                             proxyPassword=self.proxy_password)
        return await self.cap_monster_client.solve_captcha(turnstile_request)

    async def solve_turnstile_cookies(self, url, key, cloudflare_response_base64, user_agent):
        while True:
            try:
                solution = await self.turnstile_cookies_request(url, key, cloudflare_response_base64, user_agent)
                return solution
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

    async def turnstile_request(self, url, key):
        turnstile_request = TurnstileProxylessRequest(websiteURL=url,
                                                      websiteKey=key)
        return await self.cap_monster_client.solve_captcha(turnstile_request)

    async def solve_turnstile(self, url, key):
        while True:
            try:
                solution = await self.turnstile_request(url, key)
                return solution
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

    async def turnstile_token_request(self, url, key):
        turnstile_request = TurnstileRequest(websiteURL=url,
                                             websiteKey=key,
                                             cloudflareTaskType='token',
                                             pageAction='managed',
                                             userAgent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                                             data=None,
                                             pageData=None,
                                             proxyType=self.proxy_type,
                                             proxyAddress=self.proxy_ip,
                                             proxyPort=self.proxy_port,
                                             proxyLogin=self.proxy_login,
                                             proxyPassword=self.proxy_password)
        return await self.cap_monster_client.solve_captcha(turnstile_request)

    async def solve_turnstile_token(self, url, key):
        while True:
            try:
                solution = await self.turnstile_token_request(url, key)
                return solution
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

    async def hcaptcha_request(self, url, key):
        hcaptcha_request = HcaptchaRequest(websiteUrl=url,
                                            websiteKey=key,
                                            proxyType=self.proxy_type,
                                            proxyAddress=self.proxy_ip,
                                            proxyPort=self.proxy_port,
                                            proxyLogin=self.proxy_login,
                                            proxyPassword=self.proxy_password)
        return await self.cap_monster_client.solve_captcha(hcaptcha_request)

    async def solve_hcaptcha(self, url, key):
        while True:
            try:
                solution = await self.hcaptcha_request(url, key)
                return solution
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

    async def img_to_text_request(self, img_base64: str):
        image_to_text_request = ImageToTextRequest(
            image_bytes=base64.b64decode(img_base64),
            recognizingThreshold=85,
            module_name='universal'
        )
        return await self.cap_monster_client.solve_captcha(image_to_text_request)

    async def solve_img_to_text(self, img_base64: str):
        while True:
            try:
                solution = await self.img_to_text_request(img_base64)
                if not isinstance(solution, dict) or "text" not in solution:
                    self.logger.error(f"Unexpected response: {solution}")
                    continue
                captcha_text = solution["text"].upper()
                return captcha_text
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

class BestcaptchaSolver:
    def __init__(self, session, api_key: str = None, logger=None):
        if api_key is None:
            raise Exception("BestcaptchaSolver API key is missing. Set it in config.py")
        self.api_key = api_key
        self.logger = logger
        self.session = session

    async def solve_hcaptcha(self, url, key):
        captcha_response = (await self.solve_hcaptcha_submit(url, key)).json()
        captcha_id = captcha_response['id']
        while True:
            retrive_captcha_response = (await self.solve_hcaptcha_retrieve(captcha_id)).json()
            if retrive_captcha_response['status'] == 'completed':
                self.logger.success("Hcaptcha solved successfully!")
                return retrive_captcha_response['solution']
            elif retrive_captcha_response['status'] == 'pending':
                self.logger.info("Hcaptcha still solving...")
                await sleep(30)
            else:
                self.logger.error(f"Captcha solving error! {retrive_captcha_response}")
                break

    @retry()
    @check_res_status()
    async def solve_hcaptcha_submit(self, page_url, key):
        url = 'https://bcsapi.xyz/api/captcha/hcaptcha'
        json_data= {
            "page_url": page_url,
            "site_key": key,
            "access_token": self.api_key,
            "user_agent": self.session.headers['User-Agent']
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def solve_hcaptcha_retrieve(self, captcha_id):
        url = f'https://bcsapi.xyz/api/captcha/{captcha_id}?access_token={self.api_key}'
        return await self.session.get(url)

class SolviumSolver:
    def __init__(self, session, api_key: str = None, logger=None):
        if api_key is None:
            raise Exception("Solvium API key is missing. Set it in settings.py")
        self.config = {
            "apiKey": api_key,
        }
        self.base_url = "https://captcha.solvium.io/api/v1"
        self.session = session
        self.proxy = self.session.proxies.get('http')
        self.logger = logger
        self.headers = {
            "Authorization": f"Bearer {self.config.get('apiKey')}",
        }

    @retry()
    @check_res_status()
    async def make_request(self, url, **kwargs):
        return await self.session.get(url, **kwargs)

    async def create_hcaptcha_task(self, url, key):
        req_url = f"{self.base_url}/task/noname?url={url}&sitekey={key}"
        try:
            response = await self.make_request(req_url, headers=self.headers, timeout=30)
            result = response.json()
            if result.get("message") == "Task created" and "task_id" in result:
                return result["task_id"]
            self.logger.error(f"Error creating Turnstile task with Solvium: {result}")
            return
        except Exception as e:
            self.logger.error(f"Error creating Turnstile task with Solvium: {e}")
            return

    async def create_recaptcha_v3_enterprise_task(self, url, key, action, enterprise=True):
        req_url = f"{self.base_url}/task/"
        params = {
            "url": url,
            "sitekey": key,
            "action": action,
        }
        if enterprise:
            params["enterprise"] = "true"
        try:
            response = await self.make_request(req_url, params=params, headers=self.headers, timeout=30)
            result = response.json()
            if result.get("message") == "Task created" and "task_id" in result:
                return result["task_id"]
            self.logger.error(f"Error creating RecaptchaV3 task with Solvium: {result}")
            return
        except Exception as e:
            self.logger.error(f"Error creating RecaptchaV3 task with Solvium: {e}")
            return

    async def create_turnstile_task(self, url, key) :
        req_url = f"{self.base_url}/task/turnstile"
        try:
            response = await self.make_request(req_url,
                                               params={"url": url, "sitekey": key},
                                               headers=self.headers,
                                               timeout=30)
            result = response.json()
            if "task_id" in result:
                return result["task_id"]
            self.logger.error(f"Error creating Turnstile task with Solvium: {result}")
            return
        except Exception as e:
            self.logger.error(f"Error creating Turnstile task with Solvium: {e}")
            return

    async def create_vercel_task(self, challenge_token):
        req_url = f"{self.base_url}/task/vercel"
        try:
            response = await self.make_request(req_url,
                                               params={"challengeToken": challenge_token},
                                               timeout=30,)
            result = response.json()
            if result.get("message") == "Task created" and "task_id" in result:
                return result["task_id"]
            self.logger.error(f"Error creating Vercel task with Solvium: {result}")
            return
        except Exception as e:
            self.logger.error(f"Error creating Vercel task with Solvium: {e}")
            return

    async def get_task_result(self, task_id):
        max_attempts = 30
        for _ in range(max_attempts):
            try:
                url = f"{self.base_url}/task/status/{task_id}"
                response = await self.make_request(url, headers=self.headers, timeout=30)
                result = response.json()
                if (
                        result.get("status") == "completed"
                        and result.get("result")
                        and result["result"].get("solution")
                ):
                    solution = result["result"]["solution"]
                    return solution
                elif (
                        result.get("status") == "running"
                        or result.get("status") == "pending"
                ):
                    await sleep(10, 15)
                    continue
                else:
                    self.logger.error(f"Error getting result with Solvium: {result}")
                    return
            except Exception as e:
                self.logger.error(f"Error getting result with Solvium: {e}")
                return
        self.logger.error("Max polling attempts reached without getting a result with Solvium")
        return

    async def solve_hcaptcha(self, url, key):
        while True:
            task_id = await self.create_hcaptcha_task(url, key)
            if not task_id:
                self.logger.error("Can't get hcaptcha task. Trying again...")
                await sleep(10, 15)
                continue
            return await self.get_task_result(task_id)

    async def solve_turnstile(self, url, key):
        while True:
            task_id = await self.create_turnstile_task(url, key)
            if not task_id:
                self.logger.error("Can't get turnstile task. Trying again...")
                await sleep(10, 15)
                continue
        return await self.get_task_result(task_id)

    async def solve_recaptcha_v3_enterprise(self, url, key, action, enterprise=True):
        while True:
            task_id = await self.create_recaptcha_v3_enterprise_task(url, key, action, enterprise=enterprise)
            if not task_id:
                self.logger.error("Can't get recaptchav3 task. Trying again...")
                await sleep(10, 15)
                continue
        return await self.get_task_result(task_id)

    async def solve_vercel_challenge(self, challenge_token):
        while True:
            solution = await self.create_vercel_task(challenge_token)
            self.logger.error("Can't solve versel task. Trying again...")
            await sleep(10, 15)
            continue
        return solution

class SctgSolver:
    def __init__(self, session, api_key: str = None, logger=None):
        if api_key is None:
            raise Exception("Sctg API key is missing. Set it in settings.py")
        self.config = {
            "apiKey": api_key,
        }
        self.base_url = "http://api.sctg.xyz"
        self.session = session
        self.proxy = self.session.proxies.get('http')
        self.logger = logger

    @retry()
    @check_res_status()
    async def make_request(self, url, **kwargs):
        return await self.session.get(url, **kwargs)

    async def in_api(self, data):
        params = {"key": self.config.get('apiKey')}
        for key in data:
            params[key] = data[key]
        return await self.make_request(self.base_url + '/in.php', params=params, verify=False, timeout=15)

    async def res_api(self, api_id):
        params = {"key": self.config.get('apiKey'), "id": api_id}
        return await self.make_request(self.base_url + '/res.php', params=params, verify=False, timeout=15)

    async def get_balance(self):
        params = {"key": self.config.get('apiKey'), "action": "getbalance"}
        return (await self.make_request(self.base_url + '/res.php', params=params, verify=False, timeout=15)).text

    async def run(self, data):
        get_in = await self.in_api(data)
        if get_in:
            if "|" in get_in.text:
                api_id = get_in.text.split("|")[1]
            else:
                return get_in.text
        else:
            return "ERROR_CAPTCHA_UNSOLVABLE"
        while True:
            get_res = await self.res_api(api_id)
            if get_res:
                answer = get_res.text
                if 'CAPCHA_NOT_READY' in answer:
                    await sleep(10, 15)
                    continue
                elif "|" in answer:
                    return {"token": answer.split("|")[1]}
                else:
                    return {"token": answer}

    async def solve_turnstile(self, url, key):
        data = {"method": "turnstile", "pageurl": url, "sitekey": key}
        return await self.run(data)

    async def solve_hcaptcha(self, url, key):
        data = {"method": "hcaptcha", "pageurl": url, "sitekey": key}
        return await self.run(data)

class NoCaptcha:
    def __init__(self, session, api_key: str = None, logger=None):
        if api_key is None:
            raise Exception("NoCaptcha API key is missing. Set it in settings.py")
        self.config = {
            "apiKey": api_key,
        }
        self.base_url = "http://api.nocaptcha.io"
        self.session = session
        self.proxy = self.session.proxies.get('http')
        self.logger = logger

    @retry()
    @check_res_status()
    async def make_request(self, url, method, **kwargs):
        if method == "get":
            return await self.session.get(url, **kwargs)
        return await self.session.post(url, **kwargs)

    async def solve_hcaptcha(self,
                             url,
                             key,
                             invisible=False,
                             need_ekey=False,
                             rqdata=None,
                             domain=None,
                             region=None,
                             use_proxy=True):
        data = {
            "sitekey": key,
            "referer": url,
            "invisible": invisible,
            "need_ekey": need_ekey,
        }
        if rqdata:
            data["rqdata"] = rqdata
        if domain:
            data["domain"] = domain
        if self.proxy and use_proxy:
            data["proxy"] = self.proxy
            if region:
                data["region"] = region
        headers = {
            "User-Token": self.config.get('apiKey'),
            "Content-Type": "application/json",
            "Developer-Id": "SWVtru",
        }
        url = f"{self.base_url}/api/wanda/hcaptcha/universal"
        try:
            response = await self.make_request(url, 'post', json=data, headers=headers, timeout=30)
            result = response.json()
            if result.get("status") == 1:
                return {"token": result.get("data", {}).get("generated_pass_UUID")}
            self.logger.error(f"Error solving hCaptcha: {result}")
            return
        except Exception as e:
            self.logger.error(f"Error solving hCaptcha: {e}")
            return

    async def solve_recaptcha_v3_enterprise(self, url, key, invisible=True, title="Clusters", action="SIGNUP"):
        req_url = f"{self.base_url}/api/wanda/recaptcha/enterprise"
        data = {
            "referer": url,
            "sitekey": key,
            "size": "invisible" if invisible else "normal",
            "title": title,
            "action": action
        }
        headers = {
            "User-Token": self.config.get('apiKey'),
            "Content-Type": "application/json",
            "Developer-Id": "SWVtru",
        }
        try:
            response = await self.make_request(req_url, 'post', json=data, headers=headers, timeout=30)
            result = response.json()
            if result.get("status") == 1:
                return {"token": result.get("data", {}).get("token")}
            self.logger.error(f"Error solving recaptcha: {result}")
            return
        except Exception as e:
            self.logger.error(f"Error solving recaptcha: {e}")
            return



class LocalCapmonsterSolver:
    def __init__(self, session, api_key: str = None, logger=None):
        self.config = {
            "apiKey": api_key,
        }
        self.base_url = 'http://127.0.0.1:5033'
        self.session = session
        self.proxy = self.session.proxies.get('http')
        self.logger = logger

    @retry()
    @check_res_status()
    async def make_request(self, url, method, **kwargs):
        async with httpx.AsyncClient() as client:
            if method == "get":
                return await client.get(url, **kwargs)
            return await client.post(url, **kwargs)

    async def create_task(self, url, key):
        api_url = self.base_url + '/createTask'
        payload = {
            "clientKey": self.config.get('apiKey'),
            "task": {
                "type": "AntiTurnstileTaskProxyLess",
                "websiteURL": url,
                "websiteKey": key
            }
        }
        return await self.make_request(api_url, 'post', json=payload)

    async def solve_turnstile(self, url, key):
        while True:
            task_id = await self.get_new_task(url, key)
            payload = {
                "clientKey": self.config.get('apiKey'),
                "taskId": task_id
            }
            base_url = self.base_url + '/getTaskResult'
            while True:
                r = (await self.make_request(base_url, 'post', json=payload)).json()
                if r['status'] == 'error' and r['errorDescription'] == 'Response expired or task not exists':
                    self.logger.error("Captcha response expired or task not exists. Getting new task...")
                    break
                if r['status'] == 'ready':
                    return {'token': r['solution']['token']}
                else:
                    await sleep(1, 5)

    async def get_new_task(self, url, key):
        while True:
            create_task_response = (await self.create_task(url, key)).json()
            if create_task_response['status'] == 'idle':
                task_id = create_task_response['taskId']
                return task_id
            else:
                self.logger.error(f"Error creating task: {create_task_response}")
                await sleep(1, 5)

class CustomCapmonsterClient(CapMonsterClient):
    async def _getTaskResult(self, task_id: str) -> Dict[str, Union[int, str, None]]:
        body = {
            'clientKey': self.options.api_key,
            'taskId': task_id
        }
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as session:
            async with session.post(url=self.options.service_url + '/getTaskResult',
                                    json=body,
                                    timeout=aiohttp.ClientTimeout(total=self.options.client_timeout),
                                    headers=self.headers,
                                    ssl=None) as resp:
                if resp.status != 200:
                    if resp.status == 500:
                        return {'errorId': 0, 'status': 'processing'}
                    else:
                        raise HTTPException(f'Cannot grab result. Status code: {resp.status}.')
                else:
                    return await resp.json(content_type=None)

    async def _createTask(self, request) -> Dict[str, Union[str, int]]:
        task = request.getTaskDict()
        body = {
                "clientKey": self.options.api_key,
                "task": task,
                "softId": self.options.default_soft_id
               }
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as session:
            async with session.post(url=self.options.service_url + '/createTask',
                                    json=body,
                                    timeout=aiohttp.ClientTimeout(total=self.options.client_timeout),
                                    headers=self.headers,
                                    ssl=None) as resp:
                if resp.status != 200:
                    raise HTTPException(f'Cannot create task. Status code: {resp.status}.')
                else:
                    return await resp.json(content_type=None)