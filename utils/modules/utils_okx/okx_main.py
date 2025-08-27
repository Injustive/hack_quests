from utils.config import CONFIG
from okx.Funding import FundingAPI
from loguru import logger
from okx.SubAccount import SubAccountAPI
from utils.utils import with_retry


class OKX:
    def __init__(self, config, log=None):
        self.config = config
        self._api_key = self.config.OKX.ACCOUNT.API_KEY
        self._secret_key = self.config.OKX.ACCOUNT.SECRET_KEY
        self._passphrase = self.config.OKX.ACCOUNT.PASSPHRASE
        self.funding = FundingAPI(
            api_key=self._api_key,
            api_secret_key=self._secret_key,
            passphrase=self._passphrase,
            flag="0"
        )
        self.subaccount_api = SubAccountAPI(
            api_key=self._api_key,
            api_secret_key=self._secret_key,
            passphrase=self._passphrase,
            flag="0"
        )
        self.logger = log if log else logger

    @property
    def all_subaccounts(self):
        subaccounts_response = with_retry(self.subaccount_api.get_subaccount_list,
                                          max_attempts=5,
                                          mark="get_subaccounts")
        if subaccounts_response.get("code") == '0':
            subs = []
            data = subaccounts_response.get('data')
            for sub in data:
                if sub['enable']:
                    subs.append(sub['label'])
            return subs
        else:
            raise Exception(f"Error getting subaccounts! {subaccounts_response}")

    def get_subaccount_balances(self, subaccounts, currency):
        balances = {}
        for subaccount in subaccounts:
            balance_response = with_retry(self.subaccount_api.get_funding_balance,
                                          subAcct=subaccount,
                                          max_attempts=5,
                                          mark="get_subaccount_balances")
            if balance_response["code"] == "0":
                for asset in balance_response["data"]:
                    if asset["ccy"] == currency:
                        balances[subaccount] = float(asset["availBal"])
                        break
                else:
                    balances[subaccount] = 0.0
            else:
                self.logger.error(f"Error getting {subaccount} balance")
                balances[subaccount] = 0.0
        return balances

    def get_subaccount_balance(self, subaccount, currency):
        balance_response = with_retry(self.subaccount_api.get_funding_balance,
                                          subAcct=subaccount,
                                          max_attempts=5,
                                          mark="get_subaccount_balance")
        if balance_response["code"] == "0":
            for asset in balance_response["data"]:
                if asset["ccy"] == currency:
                    return float(asset["availBal"])
            else:
                return 0.0
        else:
            self.logger.error(f"Error getting {subaccount} balance")
            return 0.0

    def main_balance(self, currency):
        balance_response = with_retry(self.funding.get_balances,
                                      ccy=currency,
                                      max_attempts=5,
                                      mark="get main okx balance")
        if balance_response["code"] == "0":
            for asset in balance_response["data"]:
                if asset["ccy"] == currency:
                    return float(asset["availBal"])
            else:
                return 0.0
        else:
            self.logger.error(f"Error getting main balance")
            return 0.0

    def check_network_availability(self, currency, network):
        currencies_response = with_retry(self.funding.get_currencies, max_attempts=5, mark="get currencies")
        if currencies_response.get("code") != "0":
            raise ValueError(f"Can't get currency list. {currencies_response}")
        currencies = currencies_response.get("data", [])
        available_chains = []
        for currency_info in currencies:
            if currency_info["ccy"] == currency:
                chain = currency_info.get("chain")
                chain = chain.split(f"{currency}-")[-1]
                available_chains.append(chain)
                if chain == network:
                    can_withdraw = currency_info.get("canWd", False)
                    withdraw_fee = float(currency_info.get("minFee", "0"))
                    return can_withdraw, withdraw_fee
        raise ValueError(f"Maybe your currency ({currency}) or chain ({network}) is not supported. "
                         f"Available chains for this currency: {available_chains}")