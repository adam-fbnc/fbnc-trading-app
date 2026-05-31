from datetime import datetime, timezone, date
from sqlalchemy import String, DateTime, Date, Boolean, UniqueConstraint
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
