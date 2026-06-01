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


class PriceBarResponse(BaseModel):
    symbol: str
    frequency_type: str
    frequency: int
    bar_timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    model_config = {"from_attributes": True}


class OptionContractResponse(BaseModel):
    underlying_symbol: str
    symbol: str
    cusip: str | None
    contract_type: str
    expiration_date: date
    strike: Decimal
    open_interest: int | None
    volume: int | None
    implied_volatility: Decimal | None
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None
    last_price: Decimal | None
    bid: Decimal | None
    ask: Decimal | None
    snapped_at: datetime

    model_config = {"from_attributes": True}
