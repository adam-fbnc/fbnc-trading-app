from datetime import datetime, date, timezone
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, ForeignKey, Boolean, Date, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PositionGroup(Base):
    """A multi-leg option position tracked as a single P&L unit (spread, condor, ratio, etc.)."""
    __tablename__ = "position_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    underlying: Mapped[str] = mapped_column(String, nullable=False, index=True)
    group_type: Mapped[str] = mapped_column(String, nullable=False)
    alias: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="OPEN")  # OPEN | CLOSED
    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    legs: Mapped[list["PositionGroupLeg"]] = relationship(
        "PositionGroupLeg", back_populates="group", lazy="selectin", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["GroupAlert"]] = relationship(
        "GroupAlert", back_populates="group", lazy="selectin", cascade="all, delete-orphan"
    )


class PositionGroupLeg(Base):
    """One option leg within a position group."""
    __tablename__ = "position_group_legs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("position_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)  # OSI symbol
    underlying: Mapped[str] = mapped_column(String, nullable=False)
    contract_type: Mapped[str] = mapped_column(String, nullable=False)  # CALL | PUT
    strike: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    expiration: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)  # signed: + long, - short
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)  # per-contract, always positive

    group: Mapped["PositionGroup"] = relationship("PositionGroup", back_populates="legs")


class GroupAlert(Base):
    """A P&L threshold alert attached to a position group."""
    __tablename__ = "group_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("position_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_type: Mapped[str] = mapped_column(String, nullable=False)  # PROFIT_TARGET | STOP_LOSS
    threshold_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    group: Mapped["PositionGroup"] = relationship("PositionGroup", back_populates="alerts")
