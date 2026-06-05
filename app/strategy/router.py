from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.strategy import service, scheduler
from app.strategy.aggregator import AccountDeltaSummary
from app.strategy.schemas import (
    AccountDeltaSummaryResponse, UnderlyingDeltaResponse, LegBreakdownResponse,
    SmoothedDeltaResponse, SnapshotRecordedResponse, SchedulerStatusResponse,
    TrackedAccountsResponse,
)
from app.strategy.moving_averages import MA_TYPES
from app.account import service as account_service
from app.core.database import get_db

router = APIRouter(prefix="/strategy", tags=["strategy"])


# ---------------------------------------------------------------------------
# Whole-account: per-underlying breakdown (one entry per ticker)
# ---------------------------------------------------------------------------

@router.get("/{account_hash}/delta-summary", response_model=AccountDeltaSummaryResponse)
async def get_delta_summary(account_hash: str, db: AsyncSession = Depends(get_db)):
    await _assert_account_exists(account_hash, db)
    summary = await service.build_delta_summary(account_hash, db)
    return _to_response(account_hash, summary)


@router.get("/by-alias/{account_alias}/delta-summary", response_model=AccountDeltaSummaryResponse)
async def get_delta_summary_by_alias(account_alias: str, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_alias(account_alias, db)
    summary = await service.build_delta_summary(account_hash, db)
    return _to_response(account_hash, summary)


# ---------------------------------------------------------------------------
# Single ticker: that underlying's shares + option legs and its net delta
# ---------------------------------------------------------------------------

@router.get("/{account_hash}/delta-summary/{underlying}", response_model=UnderlyingDeltaResponse)
async def get_delta_for_underlying(
    account_hash: str, underlying: str, db: AsyncSession = Depends(get_db)
):
    await _assert_account_exists(account_hash, db)
    summary = await service.build_delta_summary(account_hash, db, underlying_filter=underlying)
    return _single_underlying(summary, account_hash, underlying)


@router.get("/by-alias/{account_alias}/delta-summary/{underlying}", response_model=UnderlyingDeltaResponse)
async def get_delta_for_underlying_by_alias(
    account_alias: str, underlying: str, db: AsyncSession = Depends(get_db)
):
    account_hash = await _resolve_alias(account_alias, db)
    summary = await service.build_delta_summary(account_hash, db, underlying_filter=underlying)
    return _single_underlying(summary, account_hash, underlying)


# ---------------------------------------------------------------------------
# Delta history snapshots
# ---------------------------------------------------------------------------

@router.post("/{account_hash}/snapshots", response_model=SnapshotRecordedResponse)
async def record_snapshot(account_hash: str, db: AsyncSession = Depends(get_db)):
    await _assert_account_exists(account_hash, db)
    rows = await service.record_delta_snapshot(account_hash, db)
    return SnapshotRecordedResponse(account_hash=account_hash, underlyings_recorded=len(rows))


@router.post("/by-alias/{account_alias}/snapshots", response_model=SnapshotRecordedResponse)
async def record_snapshot_by_alias(account_alias: str, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_alias(account_alias, db)
    rows = await service.record_delta_snapshot(account_hash, db)
    return SnapshotRecordedResponse(account_hash=account_hash, underlyings_recorded=len(rows))


# ---------------------------------------------------------------------------
# Smoothed short-call delta (configurable MA type + time-based window)
# ---------------------------------------------------------------------------

@router.get("/{account_hash}/{underlying}/smoothed-delta", response_model=SmoothedDeltaResponse)
async def get_smoothed_delta(
    account_hash: str,
    underlying: str,
    ma_type: str = Query(default="ema", description=f"One of {MA_TYPES}"),
    window_minutes: float | None = Query(default=None, gt=0, description="Time length of the average"),
    timeframe_minutes: float | None = Query(default=None, gt=0, description="Resample bar size"),
    span: int = Query(default=10, ge=1, description="Samples (used if window_minutes omitted)"),
    lookback: int = Query(default=500, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
):
    _validate_ma_type(ma_type)
    await _assert_account_exists(account_hash, db)
    return SmoothedDeltaResponse(**await service.get_smoothed_delta(
        account_hash, underlying, db, ma_type, window_minutes, timeframe_minutes, span, lookback))


@router.get("/by-alias/{account_alias}/{underlying}/smoothed-delta", response_model=SmoothedDeltaResponse)
async def get_smoothed_delta_by_alias(
    account_alias: str,
    underlying: str,
    ma_type: str = Query(default="ema", description=f"One of {MA_TYPES}"),
    window_minutes: float | None = Query(default=None, gt=0),
    timeframe_minutes: float | None = Query(default=None, gt=0),
    span: int = Query(default=10, ge=1),
    lookback: int = Query(default=500, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
):
    _validate_ma_type(ma_type)
    account_hash = await _resolve_alias(account_alias, db)
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
    account_hash: str = Query(description="Account hash to track for delta snapshots"),
    db: AsyncSession = Depends(get_db),
):
    await _assert_account_exists(account_hash, db)
    scheduler.add_tracked_account(account_hash)
    return TrackedAccountsResponse(tracked_accounts=scheduler.get_tracked_accounts())


@router.delete("/tracked-accounts", response_model=TrackedAccountsResponse)
async def remove_tracked_account(
    account_hash: str = Query(description="Account hash to stop tracking"),
):
    scheduler.remove_tracked_account(account_hash)
    return TrackedAccountsResponse(tracked_accounts=scheduler.get_tracked_accounts())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_response(account_hash: str, summary: AccountDeltaSummary) -> AccountDeltaSummaryResponse:
    return AccountDeltaSummaryResponse(
        account_hash=account_hash,
        total_net_delta=summary.total_net_delta,
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
        short_call_delta=u.short_call_delta,
        long_put_delta=u.long_put_delta,
        incomplete=u.incomplete,
        legs=[
            LegBreakdownResponse(
                symbol=l.symbol, asset_type=l.asset_type, contract_type=l.contract_type,
                strike=l.strike, expiration=l.expiration, quantity=l.quantity,
                delta=l.delta, delta_contribution=l.delta_contribution,
                delta_source=l.delta_source,
            )
            for l in u.legs
        ],
    )


def _validate_ma_type(ma_type: str) -> None:
    if ma_type.lower() not in MA_TYPES:
        raise HTTPException(status_code=400, detail=f"ma_type must be one of {MA_TYPES}")


async def _assert_account_exists(account_hash: str, db: AsyncSession) -> None:
    accounts = await account_service.list_accounts(db)
    if not any(a.account_hash == account_hash for a in accounts):
        raise HTTPException(status_code=404, detail="Account not found")


async def _resolve_alias(account_alias: str, db: AsyncSession) -> str:
    try:
        account_hash = await account_service.get_account_hash_by_alias(account_alias, db)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if account_hash is None:
        raise HTTPException(status_code=404, detail=f"No account found with alias '{account_alias}'")
    return account_hash
