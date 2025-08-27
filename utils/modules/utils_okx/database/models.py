from sqlalchemy import String, Boolean, Float
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy import Integer, Text, DateTime
from datetime import datetime


class Base(DeclarativeBase):
    pass


class OkxSubMainModel(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subaccount_name: Mapped[str] = mapped_column(String, nullable=False)
    balance_before_transfer: Mapped[float] = mapped_column(Float, nullable=True)
    balance_after_transfer: Mapped[float] = mapped_column(Float, nullable=True)
    transferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transferred_amount: Mapped[float] = mapped_column(Float, nullable=True)
    transferred_currency: Mapped[str] = mapped_column(String, nullable=True)

class OkxMainSubModel(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subaccount_name: Mapped[str] = mapped_column(String, nullable=False)
    balance_before_transfer: Mapped[float] = mapped_column(Float, nullable=True)
    balance_after_transfer: Mapped[float] = mapped_column(Float, nullable=True)
    transferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transferred_amount: Mapped[float] = mapped_column(Float, nullable=True)
    transferred_currency: Mapped[str] = mapped_column(String, nullable=True)


class WithdrawOkxWalletModel(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    to: Mapped[str] = mapped_column(String, nullable=True)
    to_pk: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=True)
    fee: Mapped[float] = mapped_column(Float, nullable=True)
    tx_id: Mapped[str] = mapped_column(String, nullable=True)
    chain: Mapped[str] = mapped_column(String, nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=True)
    withdrawn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    withdraw_order: Mapped[str] = mapped_column(String, nullable=True)
    withdraw_status: Mapped[str] = mapped_column(String, nullable=True)
    human_like_withdraw_status: Mapped[str] = mapped_column(String, nullable=True)
    withdraw_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    balance_before_withdraw: Mapped[float] = mapped_column(Float, nullable=True)
    balance_after_withdraw: Mapped[float] = mapped_column(Float, nullable=True)


class WithdrawWalletOkxModel(Base):
    __tablename__ = "withdraw_wallet_to_okx_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    to: Mapped[str] = mapped_column(String, nullable=True)
    from_: Mapped[str] = mapped_column(String, nullable=True)
    from_pk: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=True)
    chain: Mapped[str] = mapped_column(String, nullable=True)
    currency_contract_address: Mapped[str] = mapped_column(String, nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=True)
    withdrawn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    withdraw_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    balance_before_withdraw: Mapped[float] = mapped_column(Float, nullable=True)
    balance_after_withdraw: Mapped[float] = mapped_column(Float, nullable=True)


class OkxConfigAbstractModel(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config: Mapped[str] = mapped_column(Text, nullable=False)

class OkxConfigModel(Base):
    __tablename__ = "okx_config_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config: Mapped[str] = mapped_column(Text, nullable=False)