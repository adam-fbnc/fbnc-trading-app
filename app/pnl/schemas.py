from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class LegRequest(BaseModel):
    symbol: str        # OSI symbol, e.g. "NVDA  260620C00130000"
    quantity: Decimal  # signed: positive = long, negative = short
    entry_price: Decimal  # per-contract fill price, always positive


class AlertRequest(BaseModel):
    alert_type: str      # PROFIT_TARGET | STOP_LOSS
    threshold_pct: Decimal  # e.g. 100.0 for 100% profit, 30.0 for 30% loss


class CreateGroupRequest(BaseModel):
    underlying: str
    alias: str | None = None
    entry_date: datetime | None = None   # defaults to now
    legs: list[LegRequest]
    alerts: list[AlertRequest] = []
    group_type: str | None = None        # auto-detected if omitted


class LegResponse(BaseModel):
    id: int
    symbol: str
    underlying: str
    contract_type: str
    strike: Decimal
    expiration: date
    quantity: Decimal
    entry_price: Decimal
    current_mark: Decimal | None         # live mid from stream cache
    leg_pnl: Decimal | None             # (current_mark - entry_price) * quantity


class AlertResponse(BaseModel):
    id: int
    alert_type: str
    threshold_pct: Decimal
    is_active: bool
    triggered_at: datetime | None


class GroupPnLResponse(BaseModel):
    group_id: int
    account_hash: str
    underlying: str
    group_type: str
    alias: str | None
    status: str
    entry_date: datetime
    # entry_debit: net cost at entry — positive = debit paid, negative = credit received
    entry_debit: Decimal
    current_debit: Decimal | None        # current net mark (same sign convention)
    unrealized_pnl: Decimal | None       # current_debit - entry_debit
    pnl_pct: Decimal | None             # unrealized_pnl / |entry_debit| * 100
    net_delta: Decimal | None
    net_gamma: Decimal | None
    net_theta: Decimal | None
    net_vega: Decimal | None
    incomplete: bool                     # True if any leg mark is missing from stream
    legs: list[LegResponse]
    alerts: list[AlertResponse]


class ProposedLeg(BaseModel):
    symbol: str
    underlying: str
    contract_type: str
    strike: Decimal
    expiration: date
    quantity: Decimal
    entry_price: Decimal | None          # None if not found in transaction history


class ProposedGroup(BaseModel):
    order_id: str
    underlying: str
    group_type: str
    entry_date: datetime
    legs: list[ProposedLeg]


class AutoDetectResponse(BaseModel):
    proposed_groups: list[ProposedGroup]
    message: str
