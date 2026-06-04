from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    account_number: Mapped[str | None] = mapped_column(String, nullable=True)
    account_type: Mapped[str | None] = mapped_column(String, nullable=True)
    # Human-friendly label, populated manually; never overwritten by sync.
    account_alias: Mapped[str | None] = mapped_column(String, nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_hash: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.account_hash", ondelete="CASCADE"), nullable=False, index=True
    )
    cash_balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    equity_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    buying_power: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    long_market_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    short_market_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    day_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_hash: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.account_hash", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    cusip: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    asset_type: Mapped[str | None] = mapped_column(String, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    average_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    account_hash: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.account_hash", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    asset_type: Mapped[str | None] = mapped_column(String, nullable=True)
    order_type: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    entered_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    close_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    account_hash: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.account_hash", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_type: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    symbol: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    cusip: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    fees: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    trade_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    settlement_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
