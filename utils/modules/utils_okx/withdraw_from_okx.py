import math
import random
from decimal import Decimal, ROUND_FLOOR

from .okx_main import OKX, CONFIG
from loguru import logger
from utils.utils import sleep, with_retry, asset_balance
from utils.models import RpcProviders
from utils.client import Client
from datetime import datetime
from .utils import OKX_NETWORK_MAP
from utils.utils import namespace_to_dict
from utils.config import dict_to_namespace


class OKXWithdrawFrom(OKX):
    def __init__(self, client, log, account):
        config = dict_to_namespace({"OKX": namespace_to_dict(account)})
        super().__init__(config=config, log=log)
        self.config = config
        self.withdraw_state_map = {
            "0": "Waiting approval",
            "1": "Waiting execution",
            "2": "Executed successfully",
            "-1": "Cancelled",
            "-2": "Error",
            "-3": "Waiting manual approval",
            "15": 'Pending transaction validation'
        }
        self.client = client
        self.logger = log

    async def withdraw_from_okx(self):
        currency = self.config.OKX.WITHDRAW_TO_WALLETS.CURRENCY
        chain = OKX_NETWORK_MAP[self.config.OKX.WITHDRAW_TO_WALLETS.CHAIN]
        max_withdraw_fee = self.config.OKX.WITHDRAW_TO_WALLETS.MAX_WITHDRAW_FEE
        try:
            can_withdraw, withdraw_fee = self.check_network_availability(currency, chain)
        except ValueError as e:
            self.logger.error(e)
            return
        if not can_withdraw:
            self.logger.error("You can't withdraw in this chain!")
            return
        if max_withdraw_fee != "any" and withdraw_fee > max_withdraw_fee:
            self.logger.error(f"Max withdraw fee exceeded. In config - {max_withdraw_fee}. OKX - {withdraw_fee}")
            return
        main_balance = with_retry(self.main_balance,
                                  currency=currency,
                                  max_attempts=5,
                                  mark="get balance")
        amount = self.config.OKX.WITHDRAW_TO_WALLETS.AMOUNT_TYPE
        if amount == "p":
            random_percentage = random.randint(*self.config.OKX.WITHDRAW_TO_WALLETS.AMOUNT)
            random_amount = Decimal(main_balance) * Decimal(str(random_percentage / 100))
            random_amount = float(random_amount.quantize(Decimal('0.00001'), rounding=ROUND_FLOOR))
        else:
            random_amount = random.randint(*self.config.OKX.WITHDRAW_TO_WALLETS.AMOUNT)

        if main_balance < random_amount-withdraw_fee or main_balance < 0.00001:
            self.logger.error(f"You don't have enough funds on main account. "
                         f"Need {random_amount} {currency}, you have {main_balance}")
            return
        if self.config.OKX.WITHDRAW_TO_WALLETS.WAIT_FOR_DEPOSIT:
            if currency.lower() == "eth":
                asset_to_check = currency.lower()
            else:
                asset_to_check = self.config.OKX.WITHDRAW_TO_WALLETS.CURRENCY_CONTRACT_ADDRESS_TO_CHECK
            balance_before_withdraw = await asset_balance(self, asset_to_check)
        withdraw_response = with_retry(self.funding.withdrawal,
                                       ccy=currency,
                                       amt=str(round(random_amount-withdraw_fee, 5)),
                                       dest="4",
                                       toAddr=self.client.address,
                                       chain=f"{currency}-{chain}",
                                       max_attempts=5,
                                       mark="withdraw")
        if withdraw_response.get("code") == "0":
            withdrawal_data = withdraw_response.get("data")[0]
            wd_id = withdrawal_data.get("wdId")
            self.logger.info(f"Sent {random_amount} {currency}-{chain} to {self.client.address}... "
                        f"Waiting for confirmation...")
            attemps = 1
            while attemps <= 10:
                withdrawal_history = with_retry(self.funding.get_withdrawal_history,
                                                wdId=wd_id,
                                                max_attempts=5,
                                                mark="get withdrawal history")
                if withdrawal_history.get("code") != "0":
                    self.logger.error(f"Something went wrong with getting withdrawal history. {withdrawal_history}."
                                 f" Trying again... {attemps}/10")
                    attemps += 1
                    continue
                withdrawal_history_data = withdrawal_history.get("data")[0]
                withdrawal_status = withdrawal_history_data['state']
                if withdrawal_status in ["0", "1", "15"]:
                    self.logger.info(f"Withdraw sent... "
                                f"Waiting for confirmation... {attemps}/{10}")
                    attemps += 1
                    await sleep(30, 60)
                    continue
                if withdrawal_status == "2":
                    tx_id = withdrawal_history_data["txId"]
                    self.logger.success(f"Successfully withdrawn! TxId - {tx_id}")
                    if self.config.OKX.WITHDRAW_TO_WALLETS.WAIT_FOR_DEPOSIT:
                        while True:
                            if currency.lower() == "eth":
                                asset_to_check = currency.lower()
                            else:
                                asset_to_check = self.config.OKX.WITHDRAW_TO_WALLETS.CURRENCY_CONTRACT_ADDRESS_TO_CHECK
                            balance_after_withdraw = await asset_balance(self, asset_to_check)
                            if balance_after_withdraw <= balance_before_withdraw:
                                self.logger.info("Checking wallet balance...")
                                await sleep(30, 60)
                            else:
                                self.logger.success(f"Your {currency} on your destination wallet!")
                                break
                    break
                else:
                    msg = (f"Withdraw failed. "
                           f"Status - {withdrawal_status} - {self.withdraw_state_map.get(withdrawal_status)}")
                    self.logger.error(msg)
                    raise ValueError(msg)
        else:
            msg = f"Something went wrong with withdrawing. {withdraw_response}"
            self.logger.error(msg)
            raise ValueError(msg)


class OKXWithdrawFromDb(OKX):
    def __init__(self, config, db_manager):
        super().__init__(config)
        self.db_manager = db_manager
        self.db_config = config
        self.withdraw_state_map = {
            "0": "Waiting approval",
            "1": "Waiting execution",
            "2": "Executed successfully",
            "-1": "Cancelled",
            "-2": "Error",
            "-3": "Waiting manual approval",
            "15": "Pending transaction validation"
        }
        self.client = None

    async def wait_for_withdraw_status(self, note, wd_id, currency):
        withdraw_status = None
        attemps = 1
        while attemps <= 10:
            withdrawal_history = with_retry(self.funding.get_withdrawal_history,
                                            wdId=wd_id,
                                            max_attempts=5,
                                            mark="get withdrawal history")
            if withdrawal_history.get("code") != "0":
                logger.error(f"Something went wrong with getting withdrawal history. {withdrawal_history}."
                             f" Trying again... {attemps}/10")
                attemps += 1
                continue
            withdrawal_history_data = withdrawal_history.get("data")[0]
            withdrawal_status = withdrawal_history_data['state']
            data = {"withdraw_status": withdrawal_status,
                    "human_like_withdraw_status": self.withdraw_state_map.get(withdrawal_status)}
            await self.db_manager.bulk_write_prop(note.to_pk, data)
            if withdrawal_status in ["0", "1", "15"]:
                logger.info(f"Withdraw sent... "
                            f"Waiting for confirmation... {attemps}/{10}")
                attemps += 1
                await sleep(30, 60)
                continue
            if withdrawal_status == "2":
                tx_id = withdrawal_history_data["txId"]
                date = datetime.fromtimestamp(int(withdrawal_history_data["ts"]) / 1000)
                logger.success(f"Successfully withdrawn! TxId - {tx_id}")
                data = {
                    "withdraw_time": date,
                    "tx_id": tx_id,
                    "withdrawn": True,
                }
                await self.db_manager.bulk_write_prop(note.to_pk, data)
                withdraw_status = True
                break
            else:
                logger.error(f"Withdraw failed. "
                             f"Status - {withdrawal_status} - {self.withdraw_state_map.get(withdrawal_status)}")
                break
        main_balance = with_retry(self.main_balance,
                                  currency=currency,
                                  max_attempts=5,
                                  mark="get balance")
        data = {"balance_after_withdraw": main_balance}
        await self.db_manager.bulk_write_prop(note.to_pk, data)
        return withdraw_status

    async def withdraw_from_okx(self):
        currency = self.db_config.OKX.WITHDRAW_TO_WALLETS.CURRENCY
        chain = OKX_NETWORK_MAP[self.db_config.OKX.WITHDRAW_TO_WALLETS.CHAIN.upper()]
        max_withdraw_fee = self.db_config.OKX.WITHDRAW_TO_WALLETS.MAX_WITHDRAW_FEE
        try:
            can_withdraw, withdraw_fee = self.check_network_availability(currency, chain)
        except ValueError as e:
            logger.error(e)
            return
        if not can_withdraw:
            logger.error("You can't withdraw in this chain!")
            return
        if max_withdraw_fee != "any" and withdraw_fee > max_withdraw_fee:
            logger.error(f"Max withdraw fee exceeded. In config - {max_withdraw_fee}. OKX - {withdraw_fee}")
            return
        for note in await self.db_manager.get_all_notes():
            if note.withdrawn or note.withdraw_status == '2':
                amount = note.amount
                chain = note.chain
                logger.info(f"Already withdrawn {amount} {chain} to this address: {note.to}")
                continue
            main_balance = with_retry(self.main_balance,
                                      currency=currency,
                                      max_attempts=5,
                                      mark="get balance")
            if note.withdraw_status in ["0", "1"]:
                logger.info("Looks like your previous withdraw still in progress...")
                wd_id = note.withdraw_order
                currency = note.currency
                await self.wait_for_withdraw_status(note, wd_id, currency)
                continue
            elif note.withdraw_status is not None:
                logger.info("Looks like your previous withdraw was unsuccessful. Trying again...")
                random_amount = note.amount
                chain = note.chain
                currency = note.currency
            else:
                amount = self.db_config.OKX.WITHDRAW_TO_WALLETS.AMOUNT_TYPE
                if amount == "p":
                    random_percentage = random.randint(*self.db_config.OKX.WITHDRAW_TO_WALLETS.AMOUNT)
                    random_amount = Decimal(main_balance) * Decimal(str(random_percentage / 100))
                    random_amount = float(random_amount.quantize(Decimal('0.00001'), rounding=ROUND_FLOOR))
                else:
                    random_amount = round(random.uniform(*self.db_config.OKX.WITHDRAW_TO_WALLETS.AMOUNT), 5)
            if main_balance < random_amount-withdraw_fee or main_balance < 0.00001:
                logger.error(f"You don't have enough funds on main account. "
                             f"Need {random_amount} {currency}, you have {main_balance}")
                continue
            if self.db_config.OKX.WITHDRAW_TO_WALLETS.WAIT_FOR_DEPOSIT:
                self.client = Client(note.to_pk, getattr(RpcProviders, self.db_config.OKX.WITHDRAW_TO_WALLETS.CHAIN).value)
                if currency.lower() == "eth":
                    asset_to_check = currency.lower()
                else:
                    asset_to_check = self.db_config.OKX.WITHDRAW_TO_WALLETS.CURRENCY_CONTRACT_ADDRESS_TO_CHECK
                balance_before_withdraw = await asset_balance(self, asset_to_check)
            withdraw_response = with_retry(self.funding.withdrawal,
                ccy=currency,
                amt=str(round(random_amount-withdraw_fee, 5)),
                dest="4",
                toAddr=note.to,
                chain=f"{currency}-{chain}",
                max_attempts=5,
                mark="withdraw"
            )
            if withdraw_response.get("code") == "0":
                withdrawal_data = withdraw_response.get("data")[0]
                wd_id = withdrawal_data.get("wdId")
                data = {"amount": random_amount,
                        "fee": withdraw_fee,
                        "chain": chain,
                        "currency": currency,
                        "withdraw_order": wd_id,
                        "balance_before_withdraw": main_balance}
                await self.db_manager.bulk_write_prop(note.to_pk, data)
                logger.info(f"Sent {random_amount} {currency}-{chain} to {note.to}... "
                            f"Waiting for confirmation...")
                status = await self.wait_for_withdraw_status(note, wd_id, currency)
                if status:
                    if self.db_config.OKX.WITHDRAW_TO_WALLETS.WAIT_FOR_DEPOSIT:
                        while True:
                            if currency.lower() == "eth":
                                asset_to_check = currency.lower()
                            else:
                                asset_to_check = self.db_config.OKX.WITHDRAW_TO_WALLETS.CURRENCY_CONTRACT_ADDRESS_TO_CHECK
                            balance_after_withdraw = await asset_balance(self, asset_to_check)
                            if balance_after_withdraw <= balance_before_withdraw:
                                logger.info("Checking wallet balance...")
                                await sleep(30, 60)
                            else:
                                logger.success(f"Your {currency} on your destination wallet!")
                                break
            else:
                logger.error(f"Something went wrong with withdrawing. {withdraw_response}")

async def run(db_manager, db_config):
    okx = OKXWithdrawFromDb(config=db_config, db_manager=db_manager)
    await okx.withdraw_from_okx()