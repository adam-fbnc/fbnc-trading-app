from datetime import date
from decimal import Decimal
from pydantic import BaseModel


class LegBreakdownResponse(BaseModel):
    symbol: str
    asset_type: str
    contract_type: str | None
    strike: Decimal | None
    expiration: date | None
    quantity: Decimal
    delta: Decimal | None
    delta_contribution: Decimal | None
    delta_source: str


class UnderlyingDeltaResponse(BaseModel):
    underlying: str
    spot: Decimal | None
    shares: Decimal
    net_delta: Decimal | None
    short_call_delta: Decimal | None
    long_put_delta: Decimal | None
    incomplete: bool
    legs: list[LegBreakdownResponse]


class AccountDeltaSummaryResponse(BaseModel):
    account_hash: str
    total_net_delta: Decimal | None
    underlyings: list[UnderlyingDeltaResponse]
