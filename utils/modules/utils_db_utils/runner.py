from .router import DbUtilsRouter, ProjectSelectRouter, ProjectDbSelectRouter
import asyncio
from loguru import logger
from database.engine import DbManager
from utils.utils import build_db_path
import os
from utils.run_config import ROOT_DIR
from datetime import datetime
import importlib
from sqlalchemy.orm import class_mapper
from sqlalchemy import select
import traceback


class BitQuantDbManager(DbManager):
    def __init__(self, db_path, base):
        super().__init__(db_path, base)

class UtilsDbRunner:
    def __init__(self):
        self.router = DbUtilsRouter()

    def get_action(self):
        action = self.router.get_action()
        return action

    async def merge(self):
        current_project = self.current_project
        try:
            first_db = ProjectDbSelectRouter(current_project).get_action()
        except KeyError:
            logger.error("This project has 0 or 1 db. Add more dbs if you want to merge.")
            return
        second_db = ProjectDbSelectRouter(current_project, excludes=[first_db]).get_action()
        logger.info(f"Starting merging {first_db} and {second_db}...")

        first_db_path = os.path.join(ROOT_DIR, current_project, 'data', 'database', first_db)
        second_db_path = os.path.join(ROOT_DIR, current_project, 'data', 'database', second_db)
        db_path = os.path.join(ROOT_DIR, current_project, 'data', 'database')
        dbs_names = [f for f in os.listdir(db_path) if f.endswith(".db")]
        while True:
            creation_date = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            new_db_name = f"{current_project[4:]}-merged-{creation_date}.db"
            if new_db_name in dbs_names:
                continue
            merged_db_path = os.path.join(db_path, new_db_name)
            break
        module = importlib.import_module(f"{current_project}.database")
        base_project_model = getattr(module, "base_project_model")

        column_keys = [prop.key for prop in class_mapper(base_project_model).iterate_properties if hasattr(prop, 'columns')]
        first_db_manager = DbManager(first_db_path, base_project_model)
        second_db_manager = DbManager(second_db_path, base_project_model)
        dbs_records = []
        for manager in [first_db_manager, second_db_manager]:
            async with manager as dbm:
                async with dbm.session.begin():
                    result = await dbm.session.execute(select(dbm.base))
                    dbs_records.append(result.scalars().all())
        first_db_all_records, second_db_all_records = dbs_records
        unique_records = []
        address_set = set()
        for all_records in [first_db_all_records, second_db_all_records]:
            for record in all_records:
                address = record.address
                if address not in address_set:
                    unique_records.append(record)
                    address_set.add(address)
                else:
                    existing_index = None
                    for i, e_r in enumerate(unique_records):
                        if e_r.address == address:
                            existing_record = e_r
                            existing_index = i
                            break
                    existing_score = 0
                    new_score = 0
                    for key in column_keys:
                        if key == 'id':
                            continue
                        existing_value = getattr(existing_record, key)
                        new_value = getattr(record, key)
                        if existing_value and not new_value:
                            existing_score += 1
                        elif new_value and not existing_value:
                            new_score += 1
                    if new_score > existing_score:
                        unique_records.pop(existing_index)
                        unique_records.append(record)
        async with DbManager(merged_db_path, base_project_model) as dbm:
            await dbm.create_tables()
            try:
                for record in unique_records:
                    note = dbm.base(**{key: getattr(record, key) for key in column_keys if key != 'id'})
                    dbm.session.add(note)
                    await dbm.session.commit()
            except Exception as e:
                logger.error(f"{e}\n[{traceback.format_exc()}]")
                os.remove(merged_db_path)
        logger.success(f"Successfully merged! Created db `{new_db_name}`")

    def run(self):
        action = self.get_action()
        if action == "merge":
            asyncio.run(self.merge())

    @property
    def current_project(self):
        current_project = ProjectSelectRouter().get_action()
        return 'run_' + current_project.split()[-1].lower()