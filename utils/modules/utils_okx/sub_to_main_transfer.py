import random
from decimal import Decimal, ROUND_FLOOR

from .okx_main import OKX, CONFIG
from loguru import logger
from tabulate import tabulate
from utils.utils import namespace_to_dict
from utils.config import dict_to_namespace


class OKXSubToMainTransfer(OKX):
    def __init__(self, log, account):
        config = dict_to_namespace({"OKX": namespace_to_dict(account)})
        super().__init__(config=config, log=log)
        self.config = config
        self.logger = log

    async def sub_to_main_transfer(self):
        if len(self.config.OKX.SUB_TO_MAIN.SUB_LIST) == 1 and "all" in self.config.OKX.SUB_TO_MAIN.SUB_LIST[0]:
            subaccounts = self.all_subaccounts
        else:
            subaccounts = self.config.OKX.SUB_TO_MAIN.SUB_LIST
        currency = self.config.OKX.SUB_TO_MAIN.CURRENCY
        balances = self.get_subaccount_balances(subaccounts, currency)
        headers = ["Subaccount", f"{currency} balance"]
        table = tabulate(balances.items(), headers=headers, tablefmt="fancy_grid")
        self.logger.info(f'Subaccounts balance: \n{table}')
        for subaccount in subaccounts:
            if not balances[subaccount]:
                self.logger.error(f"You don't have any {currency} on `{subaccount}`")
                continue
            amount = self.config.OKX.SUB_TO_MAIN.AMOUNT_TYPE
            if amount == "p":
                random_percentage = random.randint(*self.config.OKX.SUB_TO_MAIN.AMOUNT)
                random_amount = Decimal(balances[subaccount]) * Decimal(str(random_percentage / 100))
                random_amount = float(random_amount.quantize(Decimal('0.00001'), rounding=ROUND_FLOOR))
            else:
                random_amount = random.randint(*self.config.OKX.SUB_TO_MAIN.AMOUNT)
            if balances[subaccount] < random_amount or balances[subaccount] < 0.00001:
                if self.config.OKX.SUB_TO_MAIN.SEND_ALL_IF_BALANCE_LESS_AMOUNT:
                    random_amount = balances[subaccount]
                else:
                    self.logger.error(f"You don't have enough funds on {subaccount}. "
                                 f"Need {random_amount} {currency}, you have {balances[subaccount]}")
                    continue
            self.logger.info(f"Transferring {random_amount} {currency} from `{subaccount}` to main account...")
            transfer_response = self.funding.funds_transfer(
                ccy=currency,
                amt=random_amount,
                from_="6",
                to="6",
                type="2",
                subAcct=subaccount
            )
            if transfer_response["code"] == "0":
                self.logger.success(f"Successfully transferred {random_amount} {currency} from `{subaccount}`")
            else:
                msg = f"Error transferring from {subaccount}"
                self.logger.error(msg)
                raise ValueError(msg)

class OKXSubToMainTransferWithDb(OKX):
    def __init__(self, config, db_manager):
        super().__init__(config)
        self.db_manager = db_manager
        self.db_config = config

    async def sub_to_main_transfer(self):
        if len(self.db_config.OKX.SUB_TO_MAIN.SUB_LIST) == 1 and "all" in self.db_config.OKX.SUB_TO_MAIN.SUB_LIST[0]:
            subaccounts = self.all_subaccounts
        else:
            subaccounts = self.db_config.OKX.SUB_TO_MAIN.SUB_LIST
        currency = self.db_config.OKX.SUB_TO_MAIN.CURRENCY
        balances = self.get_subaccount_balances(subaccounts, currency)
        headers = ["Subaccount", f"{currency} balance before"]
        table = tabulate(balances.items(), headers=headers, tablefmt="fancy_grid")
        logger.info(f'Subaccounts balance before transfer: \n{table}')
        main_balance = self.main_balance(currency)
        logger.info(f"Main balance before transfers {main_balance}")
        for subaccount in subaccounts:
            sub_account_info = await self.db_manager.get_note(subaccount)
            if sub_account_info and sub_account_info.transferred:
                amount = sub_account_info.transferred_amount
                currency = sub_account_info.transferred_currency
                logger.info(f"Already transferred {amount} {currency} from `{subaccount}` to main")
                continue
            await self.db_manager.create_note(subaccount)
            if not balances[subaccount]:
                logger.error(f"You don't have any {currency} on `{subaccount}`")
                continue
            amount = self.db_config.OKX.SUB_TO_MAIN.AMOUNT_TYPE
            if amount == "p":
                random_percentage = random.randint(*self.db_config.OKX.SUB_TO_MAIN.AMOUNT)
                random_amount = Decimal(balances[subaccount]) * Decimal(str(random_percentage / 100))
                random_amount = float(random_amount.quantize(Decimal('0.00001'), rounding=ROUND_FLOOR))
            else:
                random_amount = random.randint(*self.db_config.OKX.SUB_TO_MAIN.AMOUNT)
            if balances[subaccount] < random_amount or balances[subaccount] < 0.00001:
                if self.db_config.OKX.SUB_TO_MAIN.SEND_ALL_IF_BALANCE_LESS_AMOUNT:
                    random_amount = balances[subaccount]
                else:
                    logger.error(f"You don't have enough funds on {subaccount}. "
                                 f"Need {random_amount} {currency}, you have {balances[subaccount]}")
                    continue
            await self.db_manager.write_prop(subaccount, 'balance_before_transfer', balances[subaccount])
            logger.info(f"Transferring {random_amount} {currency} from `{subaccount}` to main account...")
            transfer_response = self.funding.funds_transfer(
                ccy=currency,
                amt=random_amount,
                from_="6",
                to="6",
                type="2",
                subAcct=subaccount
            )
            if transfer_response["code"] == "0":
                logger.success(f"Successfully transferred {random_amount} {currency} from `{subaccount}`")
                balance_after = self.get_subaccount_balance(subaccount, currency)
                await self.db_manager.write_prop(subaccount, 'balance_after_transfer', balance_after)
                await self.db_manager.write_prop(subaccount, 'transferred', True)
                await self.db_manager.write_prop(subaccount, 'transferred_amount', random_amount)
                await self.db_manager.write_prop(subaccount, 'transferred_currency', currency)
            else:
                logger.error(f"Error transferring from {subaccount}. {transfer_response}")
        balances = self.get_subaccount_balances(subaccounts, currency)
        headers = ["Subaccount", f"{currency} balance after"]
        table = tabulate(balances.items(), headers=headers, tablefmt="fancy_grid")
        logger.info(f'Subaccounts balance after transfers: \n{table}')
        main_balance = self.main_balance(currency)
        logger.info(f"Main balance after transfers {main_balance}")


async def run(db_manager, db_config):
    okx = OKXSubToMainTransferWithDb(config=db_config, db_manager=db_manager)
    await okx.sub_to_main_transfer()