from .router import OkxRouter
from utils.utils import get_new_utils_db_path_name, build_utils_db_path
from .database.models import (OkxSubMainModel, OkxConfigModel, OkxMainSubModel,
                              WithdrawOkxWalletModel, WithdrawWalletOkxModel)
from .database.engine import OKXDbManager, OKXWithdrawManager, OKXWalletWithdrawManager
from .sub_to_main_transfer import run as sub_to_main_run
from .main_to_sub_transfer import run as main_to_sub_run
from .withdraw_from_okx import run as withdraw_from_okx_run
from .withdraw_to_okx import run as withdraw_to_okx_run
import asyncio
from utils.config import CONFIG, dict_to_namespace
import traceback
from loguru import logger
import json
from eth_account import Account
from utils.utils import namespace_to_dict, get_data_lines
import os
from utils.client import Client
from utils.run_config import ROOT_DIR
from .database.utils import create_okx_models, pair_okx_tables, get_okx_models
from utils.models import RpcProviders


class OkxRunner:
    def __init__(self):
        self.router = OkxRouter()
        self.db_name = None

    def get_action(self):
        action = self.router.action
        self.db_name = self.router.db
        return action

    async def task_runner(self, db_name, db_model, runner):
        if self.db_name == 'new':
            new_db = get_new_utils_db_path_name(self.router.pkg_name, db_name)
            try:
                config_json = {"OKX": vars(CONFIG.OKX)}
                config_json = namespace_to_dict(config_json)
                okx_models = {}
                okx_config_models = {}
                for okx_account in config_json['OKX']['ACCOUNTS']:
                    main_model, config_model = create_okx_models(db_model, db_name, okx_account.lower())
                    okx_models[okx_account] = main_model
                    okx_config_models[okx_account] = config_model
                async with OKXDbManager(new_db, db_model) as db_manager:
                    await db_manager.create_tables()
                for okx_account in config_json['OKX']['ACCOUNTS']:
                    async with OKXDbManager(new_db, okx_config_models[okx_account]) as db_manager:
                        await db_manager.write_config(json.dumps({"OKX": config_json['OKX']['ACCOUNTS'][okx_account]}))
            except Exception as e:
                os.remove(new_db)
                logger.error(f'Error while handling database: {e}\n[{traceback.format_exc()}]')
                return
            self.db_name = new_db
        async with OKXDbManager(build_utils_db_path(self.router.pkg_name,
                                                           self.db_name),
                                                           db_model) as db_manager:
            tables = await db_manager.get_all_tables()
        for okx_account in pair_okx_tables(tables, prefix=f"{self.router.pkg_name}_{db_name}_"):
            main_table, config_table, account_num = okx_account
            main_model, config_model = get_okx_models(db_model, main_table, config_table, account_num)
            async with OKXDbManager(build_utils_db_path(self.router.pkg_name,
                                                               self.db_name),
                                           config_model) as db_manager:
                config = await db_manager.get_config()
                config = dict_to_namespace(json.loads(config.config))
            async with OKXDbManager(build_utils_db_path(self.router.pkg_name,
                                                               self.db_name),
                                           main_model) as db_manager:
                await runner(db_manager, config)

    async def sub_to_main_transfer_task(self):
        await self.task_runner(db_name='sub_to_main_transfer',
                               db_model=OkxSubMainModel,
                               runner=sub_to_main_run)

    async def main_to_sub_transfer_task(self):
        await self.task_runner(db_name='main_to_sub_transfer',
                               db_model=OkxMainSubModel,
                               runner=main_to_sub_run)

    async def okx_to_wallets_transfer_task(self):
        db_name = 'withdraw_to_wallets'
        pks = list(get_data_lines(os.path.join(ROOT_DIR, 'data', 'pks.txt')))
        if self.db_name == 'new':
            new_db = get_new_utils_db_path_name(self.router.pkg_name, db_name)
            try:
                config_json = {"OKX": vars(CONFIG.OKX)}
                config_json = namespace_to_dict(config_json)
                okx_models = {}
                okx_config_models = {}
                for okx_account in config_json['OKX']['ACCOUNTS']:
                    main_model, config_model = create_okx_models(WithdrawOkxWalletModel, db_name, okx_account.lower())
                    okx_models[okx_account] = main_model
                    okx_config_models[okx_account] = config_model
                async with OKXWithdrawManager(new_db, WithdrawOkxWalletModel) as db_manager:
                    await db_manager.create_tables()
                for okx_account in config_json['OKX']['ACCOUNTS']:
                    async with OKXWithdrawManager(new_db, okx_models[okx_account]) as db_manager:
                        for pk in pks:
                            address = Account.from_key(pk).address
                            data = {'to': address, 'withdrawn': False}
                            await db_manager.create_note(pk)
                            await db_manager.bulk_write_prop(pk, data)
                    async with OKXWithdrawManager(new_db, okx_config_models[okx_account]) as db_manager:
                        await db_manager.write_config(json.dumps({"OKX": config_json['OKX']['ACCOUNTS'][okx_account]}))
            except Exception as e:
                os.remove(new_db)
                logger.error(f'Error while handling database: {e}\n[{traceback.format_exc()}]')
                return
            self.db_name = new_db
        async with OKXWithdrawManager(build_utils_db_path(self.router.pkg_name,
                                                           self.db_name),
                                                           WithdrawOkxWalletModel) as db_manager:
            tables = await db_manager.get_all_tables()
        for okx_account in pair_okx_tables(tables, prefix=f"{self.router.pkg_name}_{db_name}_"):
            main_table, config_table, account_num = okx_account
            main_model, config_model = get_okx_models(WithdrawOkxWalletModel, main_table, config_table, account_num)
            async with OKXWithdrawManager(build_utils_db_path(self.router.pkg_name,
                                                               self.db_name),
                                           config_model) as db_manager:
                config = await db_manager.get_config()
                config = dict_to_namespace(json.loads(config.config))
            async with OKXWithdrawManager(build_utils_db_path(self.router.pkg_name,
                                                               self.db_name),
                                           main_model) as db_manager:
                await withdraw_from_okx_run(db_manager, config)

    async def wallets_to_okx_transfer_task(self):
        db_name = 'withdraw_to_okx'
        pks = list(get_data_lines(os.path.join(ROOT_DIR, 'data', 'pks.txt')))
        okx_sub_addresses = list(get_data_lines(os.path.join(ROOT_DIR, 'data', 'okx_sub_adresses.txt')))
        if self.db_name == 'new':
            new_db = get_new_utils_db_path_name(self.router.pkg_name, db_name)
            try:
                config_json = {"OKX": vars(CONFIG.OKX)}
                config_json = namespace_to_dict(config_json)
                async with OKXWalletWithdrawManager(new_db, WithdrawWalletOkxModel) as db_manager:
                    await db_manager.create_tables()
                    if config_json['OKX']['WITHDRAW_TO_OKX']['WITHDRAW_ALL_TO_ONE']:
                        withdraw_to = config_json['OKX']['WITHDRAW_TO_OKX']['WITHDRAW_TO']
                        logger.info(f"Withdrawing from all wallets to {withdraw_to} OKX...")
                        for pk in pks:
                            await db_manager.create_note(pk)
                            data = {'to': withdraw_to, 'from_': Account.from_key(pk).address}
                            await db_manager.bulk_write_prop(pk, data)
                    else:
                        for wallet_pk, okx_sub_address in zip(pks, okx_sub_addresses):
                            data = {'to': okx_sub_address, 'from_': Account.from_key(wallet_pk).address}
                            await db_manager.create_note(wallet_pk)
                            await db_manager.bulk_write_prop(wallet_pk, data)
                async with OKXWalletWithdrawManager(new_db, OkxConfigModel) as db_manager:
                    await db_manager.write_config(json.dumps({"OKX": config_json['OKX']['WITHDRAW_TO_OKX']}))
            except Exception as e:
                os.remove(new_db)
                logger.error(f'Error while handling database: {e}\n[{traceback.format_exc()}]')
                return
            self.db_name = new_db
        async with OKXWalletWithdrawManager(build_utils_db_path(self.router.pkg_name,
                                                          self.db_name),
                                            OkxConfigModel) as db_manager:
            config = await db_manager.get_config()
            config = dict_to_namespace(json.loads(config.config))
        async with OKXWalletWithdrawManager(build_utils_db_path(self.router.pkg_name,
                                                          self.db_name),
                                            WithdrawWalletOkxModel) as db_manager:
            await withdraw_to_okx_run(db_manager, config)

    def run(self):
        action = self.get_action()
        if 'Transfer from subaccounts to main' in action:
            asyncio.run(self.sub_to_main_transfer_task())
        elif 'Transfer from main to subaccounts' in action:
            asyncio.run(self.main_to_sub_transfer_task())
        elif 'Withdraw from okx to wallets' in action:
            asyncio.run(self.okx_to_wallets_transfer_task())
        elif 'Withdraw from wallets to okx' in action:
            asyncio.run(self.wallets_to_okx_transfer_task())
