from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class GEXByStrikeResponse(BaseModel):
    strike: Decimal
    call_gex: Decimal
    put_gex: Decimal
    net_gex: Decimal
    call_oi: int
    put_oi: int


class GEXResponse(BaseModel):
    symbol: str
    spot_price: Decimal
    total_gex: Decimal
    gamma_flip: Decimal | None
    largest_call_strike: Decimal | None
    largest_put_strike: Decimal | None
    strikes: list[GEXByStrikeResponse]


class OIChangeResponse(BaseModel):
    strike: float
    contract_type: str
    prev_oi: int
    current_oi: int
    oi_delta: int


class SchedulerStatusResponse(BaseModel):
    tracked_symbols: list[str]
    next_run: datetime | None
    last_run: datetime | None
    job_running: bool
