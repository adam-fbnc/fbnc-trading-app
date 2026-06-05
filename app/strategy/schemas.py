from datetime import date, datetime
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


class SmoothedDeltaResponse(BaseModel):
    underlying: str
    short_call_symbol: str | None
    ma_type: str
    window_minutes: float | None
    timeframe_minutes: float | None
    period: int | None
    current_delta: Decimal | None
    smoothed_delta: Decimal | None
    samples: int


class SnapshotRecordedResponse(BaseModel):
    account_hash: str
    underlyings_recorded: int


class SchedulerStatusResponse(BaseModel):
    tracked_accounts: list[str]
    interval_seconds: int
    next_run: datetime | None
    last_run: datetime | None
    job_running: bool


class TrackedAccountsResponse(BaseModel):
    tracked_accounts: list[str]
