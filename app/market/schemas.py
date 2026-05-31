from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class MarketHoursResponse(BaseModel):
    market: str
    date: date
    is_open: bool
    session_hours: dict | None
    fetched_at: datetime

    model_config = {"from_attributes": True}


class QuoteResponse(BaseModel):
    symbol: str
    asset_type: str | None
    last_price: Decimal | None
    bid_price: Decimal | None
    ask_price: Decimal | None
    open_price: Decimal | None
    high_price: Decimal | None
    low_price: Decimal | None
    close_price: Decimal | None
    volume: int | None
    quoted_at: datetime

    model_config = {"from_attributes": True}
