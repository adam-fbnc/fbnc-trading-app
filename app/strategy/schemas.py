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
    gamma: Decimal | None
    theta: Decimal | None
    delta_contribution: Decimal | None
    gamma_contribution: Decimal | None
    theta_contribution: Decimal | None
    delta_source: str


class UnderlyingDeltaResponse(BaseModel):
    underlying: str
    spot: Decimal | None
    shares: Decimal
    net_delta: Decimal | None
    net_gamma: Decimal | None
    net_theta: Decimal | None
    short_call_delta: Decimal | None
    short_call_theta: Decimal | None
    long_put_delta: Decimal | None
    long_put_theta: Decimal | None
    incomplete: bool
    legs: list[LegBreakdownResponse]


class AccountDeltaSummaryResponse(BaseModel):
    account_hash: str
    total_net_delta: Decimal | None
    total_net_gamma: Decimal | None
    total_net_theta: Decimal | None
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


class StructureGreeksResponse(BaseModel):
    group_id: int
    structure_key: str | None            # e.g. "1002345678-20260731TQQQ1SC65/20260806TQQQ1LC65"
    structure_type: str                  # CALL_DIAGONAL | CALL_VERTICAL | SINGLE | ...
    underlying: str
    source_order_id: str | None
    entry_date: datetime
    spot: Decimal | None
    net_delta: Decimal | None
    net_gamma: Decimal | None
    net_theta: Decimal | None
    incomplete: bool                     # True if any needed greek was missing
    legs: list[LegBreakdownResponse]


class AccountStructuresResponse(BaseModel):
    account_hash: str
    structures: list[StructureGreeksResponse]


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
