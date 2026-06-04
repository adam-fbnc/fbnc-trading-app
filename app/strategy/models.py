from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DeltaSnapshot(Base):
    """
    Time series of per-(account, underlying) position deltas, captured on a
    schedule. Feeds EMA smoothing for the roll engine's whipsaw guard.
    """
    __tablename__ = "delta_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    underlying: Mapped[str] = mapped_column(String, nullable=False, index=True)
    spot: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    net_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    short_call_symbol: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    short_call_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    long_put_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
