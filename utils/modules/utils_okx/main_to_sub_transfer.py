import random
from decimal import Decimal, ROUND_FLOOR

from .okx_main import OKX, CONFIG
from loguru import logger
from tabulate import tabulate


class OKXMainToSubTransfer(OKX):
    async def main_to_subaccount_transfer(self):
        if len(CONFIG.OKX.MAIN_TO_SUB.SUB_LIST) == 1 and "all" in CONFIG.OKX.MAIN_TO_SUB.SUB_LIST[0]:
            subaccounts = self.all_subaccounts
        else:
            subaccounts = CONFIG.OKX.MAIN_TO_SUB.SUB_LIST
        currency = CONFIG.OKX.MAIN_TO_SUB.CURRENCY
        balances = self.get_subaccount_balances(subaccounts, currency)
        headers = ["Subaccount", f"{currency} balance before"]
        table = tabulate(balances.items(), headers=headers, tablefmt="fancy_grid")
        logger.info(f'Subaccounts balance before transfers: \n{table}')
        main_balance = self.main_balance(currency)
        logger.info(f"Main balance before transfers {main_balance}")
        for subaccount in subaccounts:
            main_balance = self.main_balance(currency)
            amount = CONFIG.OKX.MAIN_TO_SUB.AMOUNT_TYPE
            if amount == "p":
                random_percentage = random.randint(*CONFIG.OKX.MAIN_TO_SUB.AMOUNT)
                random_amount = Decimal(main_balance) * Decimal(str(random_percentage / 100))
                random_amount = float(random_amount.quantize(Decimal('0.00001'), rounding=ROUND_FLOOR))
            else:
                random_amount = random.randint(*CONFIG.OKX.MAIN_TO_SUB.AMOUNT)
            if main_balance < random_amount or random_amount < 0.000001:
                logger.error(f"You don't have enough funds on main account. "
                             f"Need {random_amount} {currency}, you have {main_balance}")
                return
            logger.info(f"Transferring {random_amount} {currency} to `{subaccount}` from main account...")
            transfer_response = self.funding.funds_transfer(
                ccy=currency,
                amt=random_amount,
                from_="6",
                to="6",
                subAcct=subaccount,
                type="1"
            )
            if transfer_response["code"] == "0":
                logger.success(f"Successfully transferred {random_amount} {currency} to `{subaccount}`")
            else:
                logger.error(f"Error transferring to {subaccount}. {transfer_response}")
        balances = self.get_subaccount_balances(subaccounts, currency)
        headers = ["Subaccount", f"{currency} balance after"]
        table = tabulate(balances.items(), headers=headers, tablefmt="fancy_grid")
        logger.info(f'Subaccounts balance after transfers: \n{table}')
        main_balance = self.main_balance(currency)
        logger.info(f"Main balance after transfers {main_balance}")


class OKXMainToSubTransferWithDb(OKX):
    def __init__(self, config, db_manager):
        super().__init__(config)
        self.db_manager = db_manager
        self.db_config = config

    async def main_to_subaccount_transfer(self):
        if len(self.db_config.OKX.MAIN_TO_SUB.SUB_LIST) == 1 and "all" in self.db_config.OKX.MAIN_TO_SUB.SUB_LIST[0]:
            subaccounts = self.all_subaccounts
        else:
            subaccounts = self.db_config.OKX.MAIN_TO_SUB.SUB_LIST
        currency = self.db_config.OKX.MAIN_TO_SUB.CURRENCY
        balances = self.get_subaccount_balances(subaccounts, currency)
        headers = ["Subaccount", f"{currency} balance before"]
        table = tabulate(balances.items(), headers=headers, tablefmt="fancy_grid")
        logger.info(f'Subaccounts balance before transfer: \n{table}')
        main_balance = self.main_balance(currency)
        logger.info(f"Main balance before transfers {main_balance}")
        for subaccount in subaccounts:
            main_balance = self.main_balance(currency)
            sub_account_info = await self.db_manager.get_note(subaccount)
            if sub_account_info and sub_account_info.transferred:
                amount = sub_account_info.transferred_amount
                currency = sub_account_info.transferred_currency
                logger.info(f"Already transferred {amount} {currency} to `{subaccount}`")
                continue
            await self.db_manager.create_note(subaccount)
            amount = self.db_config.OKX.MAIN_TO_SUB.AMOUNT_TYPE
            if amount == "p":
                random_percentage = random.randint(*self.db_config.OKX.MAIN_TO_SUB.AMOUNT)
                random_amount = Decimal(main_balance) * Decimal(str(random_percentage / 100))
                random_amount = float(random_amount.quantize(Decimal('0.00001'), rounding=ROUND_FLOOR))
            else:
                random_amount = random.randint(*self.db_config.OKX.MAIN_TO_SUB.AMOUNT)
            if main_balance < random_amount or random_amount < 0.00001:
                logger.error(f"You don't have enough funds on main account. "
                             f"Need {random_amount} {currency}, you have {main_balance}")
                return
            await self.db_manager.write_prop(subaccount, 'balance_before_transfer', balances[subaccount])
            logger.info(f"Transferring {random_amount} {currency} from main account to `{subaccount}`...")
            transfer_response = self.funding.funds_transfer(
                ccy=currency,
                amt=random_amount,
                from_="6",
                to="6",
                subAcct=subaccount,
                type="1"
            )
            if transfer_response["code"] == "0":
                logger.success(f"Successfully transferred {random_amount} {currency} to `{subaccount}`")
                balance_after = self.get_subaccount_balance(subaccount, currency)
                await self.db_manager.write_prop(subaccount, 'balance_after_transfer', balance_after)
                await self.db_manager.write_prop(subaccount, 'transferred', True)
                await self.db_manager.write_prop(subaccount, 'transferred_amount', random_amount)
                await self.db_manager.write_prop(subaccount, 'transferred_currency', currency)
            else:
                logger.error(f"Error transferring to {subaccount}. {transfer_response}")
        balances = self.get_subaccount_balances(subaccounts, currency)
        headers = ["Subaccount", f"{currency} balance after"]
        table = tabulate(balances.items(), headers=headers, tablefmt="fancy_grid")
        logger.info(f'Subaccounts balance after transfers: \n{table}')
        main_balance = self.main_balance(currency)
        logger.info(f"Main balance after transfers {main_balance}")


async def run(db_manager, db_config):
    okx = OKXMainToSubTransferWithDb(config=db_config, db_manager=db_manager)
    await okx.main_to_subaccount_transfer()