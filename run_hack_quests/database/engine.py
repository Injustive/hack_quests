from database.engine import DbManager
from sqlalchemy import select, Boolean
from utils.client import Client
from utils.models import Proxy
from sqlalchemy import String


class HackQuestsDbManager(DbManager):
    async def add_register_columns(self, table_name="hack_quests_base"):
        from sqlalchemy import MetaData, Table
        from sqlalchemy.sql import text
        from sqlalchemy.exc import SQLAlchemyError
        try:
            engine = self.get_engine()
            async with engine.begin() as conn:
                metadata = MetaData()
                await conn.run_sync(lambda sync_conn: Table(
                    table_name,
                    metadata,
                    autoload_with=sync_conn
                ))
                await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN need_to_recomplete BOOLEAN DEFAULT TRUE"))
                await conn.commit()
        except SQLAlchemyError as e:
            await conn.rollback()