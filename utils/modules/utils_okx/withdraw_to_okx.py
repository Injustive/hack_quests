import random
import time
from decimal import Decimal, ROUND_FLOOR

from .okx_main import OKX, CONFIG
from loguru import logger
from tabulate import tabulate
from utils.utils import sleep, with_retry, asset_balance, get_decimals, transfer, Logger, get_contract_symbol, get_gas_params
from datetime import datetime
from utils.models import RpcProviders, TxStatusResponse
from utils.client import Client


class OKXWithdrawTo:
    async def withdraw_to_okx(self, client, okx_address):
        pass


class OKXWithdrawToDb:
    def __init__(self, config, db_manager):
        self.db_manager = db_manager
        self.db_config = config
        self.client = None
        self.logger = None

    async def withdraw_to_okx(self):
        currency = self.db_config.OKX.CURRENCY
        chain = self.db_config.OKX.CHAIN
        rpc = self.db_config.OKX.RPC
        decimals = None
        if rpc == 'default':
            rpc = getattr(RpcProviders, chain.upper()).value
        for note in await self.db_manager.get_all_notes():
            self.client = Client(key=note.from_pk, http_provider=rpc)
            self.logger = Logger(self.client.address, log_to_file=False).logger
            if currency == 'eth':
                symbol = currency
            else:
                try:
                    symbol = await get_contract_symbol(self, currency)
                except Exception:
                    symbol = currency
            if note.withdrawn:
                self.logger.info(f"Already transferred!")
                return
            amount = self.db_config.OKX.AMOUNT_TYPE
            balance = await asset_balance(self, currency)
            if currency != 'eth':
                decimals = await get_decimals(self, currency)
                balance = round(balance / 10 ** decimals, 5)
            if amount == "p":
                random_percentage = random.uniform(*self.db_config.OKX.AMOUNT)
                random_amount = Decimal(balance) * Decimal(str(random_percentage / 100))
                random_amount = float(random_amount.quantize(Decimal('0.00001'), rounding=ROUND_FLOOR))
                if len(set(self.db_config.OKX.AMOUNT)) == 1 and currency == 'eth':
                    gas_params = await get_gas_params(self)
                    gas_cost = gas_params["maxFeePerGas"] * 21000
                    withdraw_amount = balance - (balance * 0.0001)
                    if withdraw_amount <= 0:
                        self.logger.error("You don't have enough funds to withdraw!")
                        return
                    random_amount = self.client.w3.from_wei(self.client.w3.to_wei(withdraw_amount,
                                                                                  'ether') - gas_cost,
                                                            'ether')
            else:
                random_amount = round(random.uniform(*self.db_config.OKX.AMOUNT), 5)
            if currency == 'eth':
                value = self.client.w3.to_wei(random_amount, 'ether')
            else:
                value = int(random_amount * 10 ** decimals)
            self.logger.info(f"Transferring {random_amount} {symbol} to OKX {note.to}...")
            tx_status = await transfer(self, currency, note.to, value)
            if tx_status == TxStatusResponse.GOOD:
                balance_after = await asset_balance(self, currency)
                if currency != 'eth':
                    balance_after = round(balance_after / 10 ** decimals, 5)
                data = {"amount": random_amount,
                        "chain": chain,
                        "currency": symbol,
                        "currency_contract_address": currency,
                        "withdrawn": True,
                        "withdraw_time": datetime.fromtimestamp(time.time()),
                        "balance_before_withdraw": balance,
                        "balance_after_withdraw": balance_after}
                await self.db_manager.bulk_write_prop(note.from_pk, data)


async def run(db_manager, db_config):
    okx = OKXWithdrawToDb(config=db_config, db_manager=db_manager)
    await okx.withdraw_to_okx()
