from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class AccountResponse(BaseModel):
    id: int
    account_hash: str
    account_number: str | None
    account_type: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AccountSummaryResponse(BaseModel):
    account_hash: str
    cash_balance: Decimal | None
    equity_value: Decimal | None
    buying_power: Decimal | None
    long_market_value: Decimal | None
    short_market_value: Decimal | None
    day_pnl: Decimal | None
    snapshot_at: datetime

    model_config = {"from_attributes": True}


class PositionResponse(BaseModel):
    id: int
    account_hash: str
    symbol: str
    cusip: str | None
    asset_type: str | None
    quantity: Decimal
    average_price: Decimal | None
    current_value: Decimal | None
    unrealized_pnl: Decimal | None
    refreshed_at: datetime

    model_config = {"from_attributes": True}
