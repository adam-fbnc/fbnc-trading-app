from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.strategy import service, scheduler
from app.strategy.aggregator import AccountDeltaSummary
from app.strategy.schemas import (
    AccountDeltaSummaryResponse, UnderlyingDeltaResponse, LegBreakdownResponse,
    SmoothedDeltaResponse, SnapshotRecordedResponse, SchedulerStatusResponse,
    TrackedAccountsResponse,
)
from app.strategy.moving_averages import MA_TYPES
from app.strategy import streaming as strategy_streaming
from app.streaming.state import stream_state
from app.account import service as account_service
from app.core.database import get_db

router = APIRouter(prefix="/strategy", tags=["strategy"])

ACCOUNT_IDENTIFIER = Path(
    ...,
    description=(
        "Account hash or account alias identifying the account. "
        "account_hash is checked first; if no account_hash matches, the value "
        "is looked up as an account_alias."
    ),
)


# ---------------------------------------------------------------------------
# Whole-account: per-underlying breakdown (one entry per ticker)
# ---------------------------------------------------------------------------

@router.get("/{account_identifier}/delta-summary", response_model=AccountDeltaSummaryResponse)
async def get_delta_summary(account_identifier: str = ACCOUNT_IDENTIFIER, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    summary = await service.build_delta_summary(account_hash, db)
    return _to_response(account_hash, summary)


# ---------------------------------------------------------------------------
# Single ticker: that underlying's shares + option legs and its net delta
# ---------------------------------------------------------------------------

@router.get("/{account_identifier}/delta-summary/{underlying}", response_model=UnderlyingDeltaResponse)
async def get_delta_for_underlying(
    underlying: str, account_identifier: str = ACCOUNT_IDENTIFIER, db: AsyncSession = Depends(get_db)
):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    summary = await service.build_delta_summary(account_hash, db, underlying_filter=underlying)
    return _single_underlying(summary, account_hash, underlying)


# ---------------------------------------------------------------------------
# Delta history snapshots
# ---------------------------------------------------------------------------

@router.post("/{account_identifier}/snapshots", response_model=SnapshotRecordedResponse)
async def record_snapshot(account_identifier: str = ACCOUNT_IDENTIFIER, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    rows = await service.record_delta_snapshot(account_hash, db)
    return SnapshotRecordedResponse(account_hash=account_hash, underlyings_recorded=len(rows))


# ---------------------------------------------------------------------------
# Smoothed short-call delta (configurable MA type + time-based window)
# ---------------------------------------------------------------------------

@router.get("/{account_identifier}/{underlying}/smoothed-delta", response_model=SmoothedDeltaResponse)
async def get_smoothed_delta(
    underlying: str,
    account_identifier: str = ACCOUNT_IDENTIFIER,
    ma_type: str = Query(default="ema", description=f"One of {MA_TYPES}"),
    window_minutes: float | None = Query(default=None, gt=0, description="Time length of the average"),
    timeframe_minutes: float | None = Query(default=None, gt=0, description="Resample bar size"),
    span: int = Query(default=10, ge=1, description="Samples (used if window_minutes omitted)"),
    lookback: int = Query(default=500, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
):
    _validate_ma_type(ma_type)
    account_hash = await _resolve_account_identifier(account_identifier, db)
    return SmoothedDeltaResponse(**await service.get_smoothed_delta(
        account_hash, underlying, db, ma_type, window_minutes, timeframe_minutes, span, lookback))


# ---------------------------------------------------------------------------
# Snapshot scheduler / tracked accounts
# ---------------------------------------------------------------------------

@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
async def scheduler_status():
    return SchedulerStatusResponse(**scheduler.get_scheduler_status())


@router.post("/scheduler/run-now")
async def run_snapshot_now(db: AsyncSession = Depends(get_db)):
    accounts = scheduler.get_tracked_accounts()
    if not accounts:
        raise HTTPException(status_code=400, detail="No tracked accounts. Add one via POST /strategy/tracked-accounts.")
    total = 0
    for h in accounts:
        rows = await service.record_delta_snapshot(h, db)
        total += len(rows)
    return {"accounts": accounts, "underlyings_recorded": total}


@router.get("/tracked-accounts", response_model=TrackedAccountsResponse)
async def list_tracked_accounts():
    return TrackedAccountsResponse(tracked_accounts=scheduler.get_tracked_accounts())


@router.post("/tracked-accounts", response_model=TrackedAccountsResponse)
async def add_tracked_account(
    account_identifier: str = Query(description="Account hash or account alias to track for delta snapshots"),
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    scheduler.add_tracked_account(account_hash)
    return TrackedAccountsResponse(tracked_accounts=scheduler.get_tracked_accounts())


@router.delete("/tracked-accounts", response_model=TrackedAccountsResponse)
async def remove_tracked_account(
    account_identifier: str = Query(description="Account hash or account alias to stop tracking"),
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    scheduler.remove_tracked_account(account_hash)
    return TrackedAccountsResponse(tracked_accounts=scheduler.get_tracked_accounts())


# ---------------------------------------------------------------------------
# Streaming (live Greeks)
# ---------------------------------------------------------------------------

@router.post("/{account_identifier}/stream/subscribe")
async def subscribe_account_stream(account_identifier: str = ACCOUNT_IDENTIFIER, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    try:
        counts = await strategy_streaming.subscribe_account(account_hash, db)
    except RuntimeError as e:  # stream not running
        raise HTTPException(status_code=409, detail=str(e))
    return {"account_hash": account_hash, "subscribed": counts}


@router.get("/stream/quote/{symbol}")
async def inspect_stream_quote(symbol: str):
    """Dump the latest live-streamed fields for a symbol (named greeks + raw
    f_* numeric fields) to verify Schwab field mappings empirically."""
    data = stream_state.get_quote(symbol.upper())
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No streamed data for '{symbol.upper()}'. Subscribe first and wait for a tick during market hours.",
        )
    return {"symbol": symbol.upper(), "data": data}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_response(account_hash: str, summary: AccountDeltaSummary) -> AccountDeltaSummaryResponse:
    return AccountDeltaSummaryResponse(
        account_hash=account_hash,
        total_net_delta=summary.total_net_delta,
        total_net_gamma=summary.total_net_gamma,
        total_net_theta=summary.total_net_theta,
        underlyings=[_underlying_to_response(u) for u in summary.underlyings],
    )


def _single_underlying(
    summary: AccountDeltaSummary, account_hash: str, underlying: str
) -> UnderlyingDeltaResponse:
    for u in summary.underlyings:
        if u.underlying.upper() == underlying.upper():
            return _underlying_to_response(u)
    raise HTTPException(
        status_code=404,
        detail=f"No position for '{underlying.upper()}' in account. "
               f"Sync positions first, or check the ticker.",
    )


def _underlying_to_response(u) -> UnderlyingDeltaResponse:
    return UnderlyingDeltaResponse(
        underlying=u.underlying,
        spot=u.spot,
        shares=u.shares,
        net_delta=u.net_delta,
        net_gamma=u.net_gamma,
        net_theta=u.net_theta,
        short_call_delta=u.short_call_delta,
        short_call_theta=u.short_call_theta,
        long_put_delta=u.long_put_delta,
        long_put_theta=u.long_put_theta,
        incomplete=u.incomplete,
        legs=[
            LegBreakdownResponse(
                symbol=l.symbol, asset_type=l.asset_type, contract_type=l.contract_type,
                strike=l.strike, expiration=l.expiration, quantity=l.quantity,
                delta=l.delta, gamma=l.gamma, theta=l.theta,
                delta_contribution=l.delta_contribution,
                gamma_contribution=l.gamma_contribution,
                theta_contribution=l.theta_contribution,
                delta_source=l.delta_source,
            )
            for l in u.legs
        ],
    )


def _validate_ma_type(ma_type: str) -> None:
    if ma_type.lower() not in MA_TYPES:
        raise HTTPException(status_code=400, detail=f"ma_type must be one of {MA_TYPES}")


async def _resolve_account_identifier(account_identifier: str, db: AsyncSession) -> str:
    """Resolve account_identifier to an account_hash, trying account_hash first
    and falling back to account_alias."""
    try:
        account_hash = await account_service.resolve_account_identifier(account_identifier, db)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if account_hash is None:
        raise HTTPException(
            status_code=404,
            detail=f"No account found with hash or alias '{account_identifier}'",
        )
    return account_hash
