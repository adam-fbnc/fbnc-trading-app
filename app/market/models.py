from datetime import datetime, timezone, date
from decimal import Decimal
from sqlalchemy import String, DateTime, Date, Boolean, UniqueConstraint, Numeric, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MarketHours(Base):
    __tablename__ = "market_hours"

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String, nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False)
    session_hours: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("market", "date", name="uq_market_hours_market_date"),
    )


class QuoteSnapshot(Base):
    __tablename__ = "quote_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    asset_type: Mapped[str | None] = mapped_column(String, nullable=True)
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    bid_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    ask_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    open_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    high_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    low_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    volume: Mapped[int | None] = mapped_column(nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    quoted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )


class PriceBar(Base):
    __tablename__ = "price_bars"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # frequency_type: minute, daily, weekly, monthly
    frequency_type: Mapped[str] = mapped_column(String, nullable=False)
    # frequency: 1, 5, 10, 15, 30 (for minute); 1 (for daily/weekly/monthly)
    frequency: Mapped[int] = mapped_column(nullable=False)
    bar_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "frequency_type", "frequency", "bar_timestamp",
                         name="uq_price_bars_symbol_freq_ts"),
    )
