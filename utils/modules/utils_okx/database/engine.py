from database.engine import DbManager
from sqlalchemy import select


class OKXDbManager(DbManager):
    def __init__(self, db_path, base):
        super().__init__(db_path, base)

    async def get_note(self, subaccount):
        async with self.session.begin():
            result = await self.session.execute(
                select(self.base).where(self.base.subaccount_name == subaccount)
            )
            return result.scalar_one_or_none()

    async def write_prop(self, subaccount, prop, value):
        async with self.session.begin():
            result = await self.session.execute(
                select(self.base).where(self.base.subaccount_name == subaccount)
            )
            obj = result.scalar_one_or_none()
            setattr(obj, prop, value)

    async def create_note(self, subaccount):
        async with self.session.begin():
            result = await self.session.execute(
                select(self.base).where(self.base.subaccount_name == subaccount)
            )
            existing_note = result.scalar_one_or_none()
            if existing_note:
                return existing_note
            note = self.base(subaccount_name=subaccount)
            self.session.add(note)

    async def write_config(self, config):
        async with self.session.begin():
            result = await self.session.execute(
                select(self.base).where(self.base.config == config)
            )
            existing_note = result.scalar_one_or_none()
            if existing_note:
                return existing_note
            note = self.base(config=config)
            self.session.add(note)

    async def get_config(self):
        async with self.session.begin():
            result = await self.session.execute(select(self.base))
            config_obj = result.scalar_one_or_none()
            return config_obj

    async def get_all_notes(self):
        async with self.session.begin():
            result = await self.session.execute(select(self.base))
            notes = result.scalars().all()
            return notes

class OKXWithdrawManager(OKXDbManager):
    async def create_note(self, to_pk):
        async with self.session.begin():
            result = await self.session.execute(
                select(self.base).where(self.base.to_pk == to_pk)
            )
            existing_note = result.scalar_one_or_none()
            if existing_note:
                return existing_note
            note = self.base(to_pk=to_pk)
            self.session.add(note)

    async def write_prop(self, to_pk, prop, value):
        async with self.session.begin():
            result = await self.session.execute(
                select(self.base).where(self.base.to_pk == to_pk)
            )
            obj = result.scalar_one_or_none()
            setattr(obj, prop, value)

    async def bulk_write_prop(self, to_pk, data):
        async with self.session.begin():
            result = await self.session.execute(
                select(self.base).where(self.base.to_pk == to_pk)
            )
            obj = result.scalar_one_or_none()
            for prop, value in data.items():
                setattr(obj, prop, value)

class OKXWalletWithdrawManager(OKXDbManager):
    async def create_note(self, from_pk):
        async with self.session.begin():
            result = await self.session.execute(
                select(self.base).where(self.base.from_pk == from_pk)
            )
            existing_note = result.scalar_one_or_none()
            if existing_note:
                return existing_note
            note = self.base(from_pk=from_pk)
            self.session.add(note)

    async def bulk_write_prop(self, from_pk, data):
        async with self.session.begin():
            result = await self.session.execute(
                select(self.base).where(self.base.from_pk == from_pk)
            )
            obj = result.scalar_one_or_none()
            for prop, value in data.items():
                setattr(obj, prop, value)
