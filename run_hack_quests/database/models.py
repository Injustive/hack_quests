from database.base_models import BaseModel
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, JSON, func
from sqlalchemy.ext.hybrid import hybrid_property


class Base(DeclarativeBase):
    pass


class HackQuestsBaseModel(BaseModel):
    __tablename__ = "hack_quests_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    own_referral_code: Mapped[str] = mapped_column(String, nullable=True)
    applied_referral_code: Mapped[str] = mapped_column(String, nullable=True)
    max_pet_lvl: Mapped[int] = mapped_column(Integer, nullable=True)
    need_to_recomplete: Mapped[bool] = mapped_column(Boolean, default=True)
