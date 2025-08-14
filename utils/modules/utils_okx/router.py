from utils.router import MainRouter, UtilsDbRouter
import os
from utils.run_config import ROOT_DIR


class OkxRouter(MainRouter, UtilsDbRouter):
    def __init__(self):
        super().__init__()
        self.pkg_name = 'okx'
        self.db_name_filter = None

    def get_choices(self):
        return ['Transfer from subaccounts to main',
                'Transfer from main to subaccounts',
                'Withdraw from okx to wallets',
                'Withdraw from wallets to okx']

    @property
    def action(self):
        action_mapping = dict(zip(self.get_choices(), ['sub_to_main',
                                                       'main_to_sub',
                                                       'withdraw_to_wallets',
                                                       'withdraw_to_okx']))
        action = self.get_action()
        self.db_name_filter = action_mapping[action]
        self.start_db_router()
        return action

    def choose_db(self):
        dbs_path = os.path.join(ROOT_DIR, 'data', 'database', self.pkg_name)
        os.makedirs(dbs_path, exist_ok=True)
        dbs = [f for f in os.listdir(dbs_path) if f.endswith(".db") and
               f.startswith(f"{self.pkg_name}_{self.db_name_filter}")] + ['new']
        return dbs
