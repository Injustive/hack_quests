import asyncio
import copy

from tinydb import TinyDB, Query
from .paths import GLOBAL_DB
global_lock = asyncio.Lock()


class GalxeDb:
    TWITTER = Query()

    def __init__(self, db_path):
        self.db_path = db_path
        self.db = TinyDB(db_path)
        self.global_db = TinyDB(GLOBAL_DB)
        self.completed_twitter_tasks_table = self.db.table('completed_twitter_tasks')
        self.completed_onchain_spartans_tasks_table = self.db.table('completed_onchain_spartans_tasks')
        self.completed_galxe_spartans_tasks_table = self.db.table('completed_galxe_spartans_tasks')
        self.spartans_faucet_table = self.db.table('spartans_faucet_table')
        self.bound_socials_table = self.global_db.table('bound_socials_table')
        self.twitter_stat_table = self.db.table('twitter_stat_table')
        self.temporal_twitter_accounts_table = self.db.table('temporal_twitter_accounts_table')
        self.layer_hub_completed_table = self.db.table('layer_hub_completed_table')

    async def insert_completed_twitter_task(self,
                                            address,
                                            twitter_username,
                                            with_twitter,
                                            cls_name,
                                            func_to_complete,
                                            args,
                                            kwargs):
        async with global_lock:
            existing_record = self.completed_twitter_tasks_table.get((self.TWITTER.address == address) &
                                                                           (self.TWITTER.twitter_username == twitter_username) &
                                                                           (self.TWITTER.func_to_complete.func.fragment(
                                                                               {'cls': cls_name,
                                                                                'method': func_to_complete})
                                                                           ))
            if existing_record is None:
                copied_completed_twitter_tasks_table = copy.copy(self.completed_twitter_tasks_table)
                copied_completed_twitter_tasks_table.insert({'address': address,
                                                             'twitter_username': twitter_username,
                                                             'with_twitter': with_twitter,
                                                             'func_to_complete':
                                                                {'func': {'cls': cls_name,
                                                                          'method': func_to_complete},
                                                                          'args': args,
                                                                          'kwargs': kwargs}
                                                             })

    async def get_completed_twitter_tasks(self, address):
        return self.completed_twitter_tasks_table.search(self.TWITTER.address == address)

    async def get_completed_tasks_by_cls_and_func(self, address, cls, func, twitter_username):
        copied_completed_twitter_tasks_table = copy.copy(self.completed_twitter_tasks_table)
        return copied_completed_twitter_tasks_table.get((self.TWITTER.address == address) &
                                                       (self.TWITTER.func_to_complete.func.fragment(
                                                          {'cls': cls,
                                                           'method': func}
                                                           ) &
                                                           (self.TWITTER.twitter_username == twitter_username)))

    async def bound_socials_insert_email(self, address, email):
        self.bound_socials_table.upsert({'address': address, 'email': email},
                                                   self.TWITTER.address == address)

    async def initialise_bound_socials_table(self, address):
        record = await self.get_bound_twitter_token(address)
        if not record:
            self.bound_socials_table.insert({'address': address,
                                             'email': None,
                                             'twitter': None,
                                             'twitter_username': None,
                                             'aptos_wallet': None})

    async def bound_socials_insert_twitter(self, address, twitter, twitter_username):
        self.bound_socials_table.upsert({'twitter': twitter,
                                                   'twitter_username': twitter_username},
                                                    self.TWITTER.address == address)

    async def bound_socials_insert_aptos_wallet(self, address, aptos_address):
        self.bound_socials_table.upsert({'address': address, 'aptos_address': aptos_address},
                                                   self.TWITTER.address == address)

    async def bound_socials_insert_sui_wallet(self, address, sui_address):
        self.bound_socials_table.upsert({'address': address, 'sui_address': sui_address},
                                                   self.TWITTER.address == address)

    async def get_bound_socials_all(self):
        return self.bound_socials_table.all()

    async def get_bound_twitter_token(self, address):
        return self.bound_socials_table.get(self.TWITTER.address == address)

    async def get_bound_token(self, token):
        return self.bound_socials_table.get(self.TWITTER.twitter == token)

    async def write_twitter_stat(self, address, token, status):
        async with global_lock:
            existing_user = self.twitter_stat_table.search(self.TWITTER.address == address)
            if not existing_user:
                self.twitter_stat_table.insert({'address': address, 'token': token, 'status': status})

    async def get_all_completed_tasks(self):
        return self.completed_twitter_tasks_table.all()

    async def get_twitter_stat(self):
        return self.twitter_stat_table.all()

    async def replace_bad_bound_db_token(self, address, old_db_token, new_db_token):
        self.bound_socials_table.update({'twitter': new_db_token},
                                        (self.TWITTER.address == address) & (self.TWITTER.twitter == old_db_token))

    async def delete_bound_twitter_from_db(self, address):
        self.bound_socials_table.update({'twitter': None,
                                         'twitter_username': None},
                                        self.TWITTER.address == address)

    async def delete_completed_twitter_tasks_with_bad_twitter(self, address):
        actual_twitter_username = self.bound_socials_table.get(self.TWITTER.address == address)
        if not actual_twitter_username:
            return
        twitter_username = actual_twitter_username.get('twitter_username')
        self.completed_twitter_tasks_table.remove((self.TWITTER.address == address) &
                                                  ~(self.TWITTER.twitter_username == twitter_username) &
                                                  (self.TWITTER.with_twitter == True))

    async def insert_completed_spartans_task(self, address, address_type, galxe_campaign):
        copied_completed_onchain_spartans_tasks_table = copy.copy(self.completed_onchain_spartans_tasks_table)
        existing_record = self.completed_onchain_spartans_tasks_table.search((self.TWITTER.address == address) &
                                                   (self.TWITTER.address_type == address_type) &
                                                   (self.TWITTER.galxe_campaign == galxe_campaign))
        if not existing_record:
            copied_completed_onchain_spartans_tasks_table.insert({'address': address,
                                                        'address_type': address_type,
                                                        'galxe_campaign': galxe_campaign})

    async def get_completed_spartans_task(self, address, address_type, galxe_campaign):
        return self.completed_onchain_spartans_tasks_table.get((self.TWITTER.address == address) &
                                                        (self.TWITTER.address_type == address_type) &
                                                        (self.TWITTER.galxe_campaign == galxe_campaign))

    async def insert_completed_galxe_spartans_task(self, address, galxe_campaign):
        copied_completed_galxe_spartans_tasks_table = copy.copy(self.completed_galxe_spartans_tasks_table)
        existing_record = self.completed_galxe_spartans_tasks_table.search((self.TWITTER.address == address) &
                                                   (self.TWITTER.galxe_campaign == galxe_campaign))
        if not existing_record:
            copied_completed_galxe_spartans_tasks_table.insert({'address': address,
                                                        'galxe_campaign': galxe_campaign})

    async def get_completed_galxe_spartans_task(self, address, galxe_campaign):
        return self.completed_galxe_spartans_tasks_table.get((self.TWITTER.address == address) &
                                                       (self.TWITTER.galxe_campaign == galxe_campaign))

    async def insert_spartans_faucet_status(self, address, status):
        self.spartans_faucet_table.upsert({'address': address,
                                           'status': status},
                                          (self.TWITTER.address == address) & (self.TWITTER.status == status))

    def get_spartans_faucet_all(self):
        return self.spartans_faucet_table.all()

    def get_completed_galxe_spartans_all(self):
        return self.completed_galxe_spartans_tasks_table.all()

    async def insert_completed_layer_hub_quests(self, address,
                                                last_updated,
                                                wallet_top,
                                                total,
                                                spartans,
                                                pathfinders,
                                                explorers,
                                                creators,
                                                scholars):
        existing_record = self.layer_hub_completed_table.search(self.TWITTER.address == address)
        if not existing_record:
            self.layer_hub_completed_table.insert({'address': address,
                                                   'last_updated': last_updated,
                                                   'wallet_top': wallet_top,
                                                   'total': total,
                                                   'spartans': spartans,
                                                   'pathfinders': pathfinders,
                                                   'explorers': explorers,
                                                   'creators': creators,
                                                   'scholars': scholars})

    async def get_completed_layer_hub_quests_all(self):
        return self.layer_hub_completed_table.all()

    async def truncate_completed_layer_hub_quests_table(self):
        self.layer_hub_completed_table.truncate()

    async def truncate_stat_table(self):
        self.twitter_stat_table.truncate()
