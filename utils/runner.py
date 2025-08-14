import asyncio
import sys
from curl_cffi.requests.errors import RequestsError
from .run_config import current_run, ROOT_DIR
import os
from loguru import logger
from .utils import get_data_lines, sleep, MaxLenException, Logger
from .models import Proxy
from .client import Client
from abc import ABC, abstractmethod
import random
import traceback
from aiohttp.client_exceptions import ClientResponseError


class MainRunner(ABC):
    @abstractmethod
    async def run_task(self, *data):
        pass

    @abstractmethod
    def get_action(self):
        pass

    @staticmethod
    def justify_data(sample, data):
        if len(sample) > len(data):
            data = data + [None] * (len(sample) - len(data))
        return data

    def prepare_data(self):
        project_proxies = os.path.join(ROOT_DIR, current_run.PACKAGE, 'data', 'proxies.txt')
        project_sids = os.path.join(ROOT_DIR, current_run.PACKAGE, 'data', 'sids.txt')
        proxies = list(get_data_lines(project_proxies))
        sids = list(get_data_lines(project_sids))
        if len(sids) > len(proxies):
            logger.warning(f'Not enough proxies to run all accounts with proxy! '
                           f'Sids - {len(sids)}. Proxies - {len(proxies)}')
        elif not sids:
            logger.error('No data to run!')
            return
        logger.info(f'Running {len(sids)} accounts...')

        prepared_proxies = []
        prepared_clients = []
        proxies = self.justify_data(sids, proxies)
        for sid, raw_proxy in zip(sids, proxies):
            proxy = Proxy(raw_proxy)
            client = Client(sid, proxy=proxy.w3_proxy)
            prepared_proxies.append(proxy)
            prepared_clients.append(client)

            if not raw_proxy:
                logger.warning(f"There isn't proxy for this account: {client.address}. Running it without proxy")
        prepared_data = {'proxies': prepared_proxies, 'clients': prepared_clients}
        return prepared_data

    async def run_task_with_retry(self, client, proxy, action, barrier):
        while True:
            try:
                await self.run_task(client, proxy, action, barrier)
                break
            except MaxLenException as e:
                print(f"{client.address}. Task failed with exception: {e}. Retrying...")
                await sleep(5, 30)

    async def prepare_run(self):
        prepared_data = self.prepare_data()
        proxies, clients = prepared_data['proxies'], prepared_data['clients']
        barrier = asyncio.Barrier(len(clients))
        self.action = self.get_action()
        tasks = [asyncio.create_task(self.run_task_with_retry(client, proxy, self.action, barrier)) for client, proxy in zip(clients, proxies)]
        await asyncio.wait(tasks)

    def run(self):
        def set_windows_event_loop_policy():
            if sys.version_info >= (3, 8) and sys.platform.lower().startswith("win"):
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        set_windows_event_loop_policy()
        asyncio.run(self.prepare_run())


class TwitterRunner(MainRunner):
    def prepare_data(self):
        prepared_data = super().prepare_data()
        project_twitter_tokens = os.path.join(ROOT_DIR, current_run.PACKAGE, 'data', 'twitter_tokens.txt')
        tokens = list(get_data_lines(project_twitter_tokens))
        prepared_data.update({"tokens": tokens})
        return prepared_data

    async def run_task_with_retry(self, client, proxy, twitter, action):
        while True:
            try:
                await self.run_task(client, proxy, twitter, action)
                break
            except MaxLenException as e:
                print(f"{client.address}. Task failed with exception: {e}. Retrying...")
                await sleep(5, 30)

    async def prepare_run(self):
        def justifier(sample, data):
            if len(sample) > len(data):
                data = data + [None] * (len(sample) - len(data))
            return data
        prepared_data = self.prepare_data()
        proxies, clients, tokens = prepared_data.values()
        proxies = justifier(clients, proxies)
        tokens = justifier(clients, tokens)
        action = self.get_action()
        tasks = [asyncio.create_task(self.run_task_with_retry(client, proxy, twitter_token, action))
                 for client, proxy, twitter_token in zip(clients, proxies, tokens)]
        await asyncio.wait(tasks)
        return action

    async def run_task(self, *data):
        pass


class ModernRunner:
    def __init__(self):
        self.action, self.db_name = self.get_action()
        self.prepared_data = None
        self.global_data = None
        self.data_list = None

    async def run_task_with_retry(self, data):
        client = data['client']
        proxy = data['proxy']
        proxy = proxy.session_proxy.get('http') if proxy.session_proxy else None
        logger = Logger(client.address, additional={'pk': client.key,
                                                    'proxy': proxy}).logger
        extra_proxies = self.global_data['extra_proxies']
        need_to_sleep = True
        while True:
            try:
                return await self.run_task(data, need_to_sleep=need_to_sleep)
            except MaxLenException:
                logger.error(f"Task failed with exception: Cloudflare. Retrying...")
                await sleep(5, 30)
                need_to_sleep = False
            except (RequestsError,ClientResponseError) as e:
                if not extra_proxies:
                    logger.error('There is no extra proxy available!')
                    break
                logger.error(f"Task failed with exception: {type(e)}: {e}. Trying to get extra proxy...")
                random_proxy_index = random.randint(0, len(extra_proxies) - 1)
                random_proxy = extra_proxies.pop(random_proxy_index)
                logger.info(f'GOT PROXY {random_proxy}! Reconnecting...')
                proxy = Proxy(proxy=random_proxy)
                data['proxy'] = proxy
                client.reconnect_with_new_proxy(proxy.w3_proxy)
                need_to_sleep = False
            except Exception as e:
                if 'Page.goto: net::ERR_TIMED_OUT' in str(e):
                    if not extra_proxies:
                        logger.error('There is no extra proxy available!')
                        break
                    logger.error(f"Task failed with exception: {type(e)}: {e}. Trying to get extra proxy...")
                    random_proxy_index = random.randint(0, len(extra_proxies) - 1)
                    random_proxy = extra_proxies.pop(random_proxy_index)
                    logger.info(f'GOT PROXY {random_proxy}! Reconnecting...')
                    proxy = Proxy(proxy=random_proxy)
                    data['proxy'] = proxy
                    client.reconnect_with_new_proxy(proxy.w3_proxy)
                    need_to_sleep = False
                    continue
                logger.error(f"Task failed with exception: {type(e)}: {e}|[{traceback.format_exc()}]. Retrying...")
                await sleep(5, 30)
                need_to_sleep = False

    async def initialize(self):
        self.global_data = self.get_global_data()

    def prepare_data(self):
        project_proxies = os.path.join(ROOT_DIR, current_run.PACKAGE, 'data', 'proxies.txt')
        project_sids = os.path.join(ROOT_DIR, current_run.PACKAGE, 'data', 'sids.txt')
        proxies = list(get_data_lines(project_proxies))
        sids = list(get_data_lines(project_sids))
        if len(sids) > len(proxies):
            logger.warning(f'Not enough proxies to run all accounts with proxy! '
                           f'Sids - {len(sids)}. Proxies - {len(proxies)}')
        elif not sids:
            logger.error('No data to run!')
            return

        prepared_proxies = []
        prepared_clients = []
        proxies = self.justify_data(sids, proxies)
        for sid, raw_proxy in zip(sids, proxies):
            proxy = Proxy(raw_proxy)
            client = Client(sid, proxy=proxy.w3_proxy)
            prepared_proxies.append(proxy)
            prepared_clients.append(client)

            if not raw_proxy:
                logger.warning(f"There isn't proxy for this account: {client.address}. Running it without proxy")
        prepared_data = {'proxies': prepared_proxies, 'clients': prepared_clients}
        return prepared_data

    @staticmethod
    def justify_data(sample, data):
        if len(sample) > len(data):
            data = data + [None] * (len(sample) - len(data))
        return data

    #old version without db
    async def prepare_run(self):
        await self.initialize()
        self.prepared_data = self.prepare_data()
        tasks = []
        for curr in range(len(self.prepared_data['clients'])):
            data = {key: value[curr] for key, value in self.prepared_data.items()}
            tasks.append(asyncio.create_task(self.run_task_with_retry(data)))
        results, _ = await asyncio.wait(tasks)
        await self.after_run(results)

    async def prepare_db_run(self):
        self.prepared_data = self.prepare_data()
        tasks = []
        try:
            data_list = await self.handle_db()
            self.data_list = data_list
        except Exception as e:
            logger.error(f'Error while handling database: {e}\n[{traceback.format_exc()}]')
            return
        await self.initialize()
        logger.info(f'Running {len(data_list)} accounts...')
        for data in data_list:
            tasks.append(asyncio.create_task(self.run_task_with_retry(data)))
        results, _ = await asyncio.wait(tasks)
        await self.after_run(results)

    def get_global_data(self):
        extra_proxies = list(get_data_lines(os.path.join(ROOT_DIR, current_run.PACKAGE, 'data', 'extra_proxies.txt')))
        global_data = {'extra_proxies': extra_proxies}
        return global_data

    async def run_task(self, data, need_to_sleep=True):
        pass

    def run(self):
        def set_windows_event_loop_policy():
            if sys.version_info >= (3, 8) and sys.platform.lower().startswith("win"):
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        set_windows_event_loop_policy()
        asyncio.run(self.prepare_db_run())

    async def after_run(self, results):
        pass

    def get_action(self):
        router = self.Router()
        return router.action, router.db

