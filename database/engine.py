from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from eth_account import Account
from sqlalchemy import select, inspect
from utils.client import Client
from utils.models import Proxy


class DbManager:
    def __init__(self, db_path, base):
        self.db_path = db_path
        self.base = base
        self._engine = None
        self._sessionmaker = None
        self.session = None

    def get_engine(self):
        if self._engine is None:
            db_url = f"sqlite+aiosqlite:///{self.db_path}"
            self._engine = create_async_engine(db_url, echo=False)
        return self._engine

    def get_sessionmaker(self):
        if self._sessionmaker is None:
            engine = self.get_engine()
            self._sessionmaker = sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
        return self._sessionmaker

    async def __aenter__(self):
        session_factory = self.get_sessionmaker()
        self.session = session_factory()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.session.rollback()
        await self.session.close()

    async def create_tables(self):
        engine = self.get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(self.base.metadata.create_all)

    async def drop_tables(self):
        engine = self.get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(self.base.metadata.drop_all)

    async def create_base_note(self, pk, proxy, **kwargs):
        result = await self.session.execute(
            select(self.base).where(self.base.private_key == pk)
        )
        existing_note = result.scalar_one_or_none()
        if existing_note:
            return existing_note
        note = self.base(address=Account.from_key(pk).address, private_key=pk, proxy=proxy, **kwargs)
        self.session.add(note)

    async def get_run_data(self):
        async with self.session.begin():
            result = await self.session.execute(select(self.base))
            users = result.scalars().all()
            return [{'client': Client(user.private_key),
                     'proxy': Proxy(user.proxy)}
                    for user in users]

    async def insert_column(self, pk, name, value):
        async with self.session.begin():
            result = await self.session.execute(
                select(self.base).where(self.base.private_key == pk)
            )
            obj = result.scalar_one_or_none()
            setattr(obj, name, value)

    async def get_column(self, pk, column_name):
        async with self.session.begin():
            result = await self.session.execute(
                select(self.base).where(self.base.private_key == pk)
            )
            obj = result.scalar_one_or_none()
            return getattr(obj, column_name)

    async def update_proxy_by_private_key(self, pk, new_proxy):
        async with self.session.begin():
            result = await self.session.execute(
                select(self.base).where(self.base.private_key == pk)
            )
            obj = result.scalar_one_or_none()
            if not obj:
                return None
            obj.proxy = new_proxy

    async def get_all_tables(self):
        engine = self.get_engine()
        async with engine.connect() as conn:
            def sync_get_tables(conn):
                inspector = inspect(conn)
                return inspector.get_table_names()
            return await conn.run_sync(sync_get_tables)