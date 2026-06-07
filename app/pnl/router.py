import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.account import service as account_service
from app.core.database import get_db
from app.pnl import service
from app.pnl.schemas import (
    AlertRequest, AlertResponse, AutoDetectResponse,
    CreateGroupRequest, GroupPnLResponse, ProposedGroup, ProposedLeg,
)

logger = logging.getLogger("app.pnl")
router = APIRouter(prefix="/pnl", tags=["pnl"])


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

@router.post("/{account_hash}/groups", response_model=GroupPnLResponse, status_code=201)
async def create_group(
    account_hash: str,
    req: CreateGroupRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a position group from a list of option legs.
    Set entry_price per leg (always positive); quantity is signed (negative = short).
    Optionally attach initial alerts (e.g. 100% profit target, 30% stop loss).
    group_type is auto-detected if omitted.
    """
    await _assert_account(account_hash, db)
    try:
        group = await service.create_group(account_hash, req, db)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return service.compute_group_pnl(group)


@router.get("/{account_hash}/groups", response_model=list[GroupPnLResponse])
async def list_groups(
    account_hash: str,
    status: str | None = Query(default=None, description="Filter: OPEN or CLOSED"),
    db: AsyncSession = Depends(get_db),
):
    await _assert_account(account_hash, db)
    groups = await service.list_groups(account_hash, db, status=status)
    return [service.compute_group_pnl(g) for g in groups]


@router.get("/{account_hash}/groups/{group_id}", response_model=GroupPnLResponse)
async def get_group(
    account_hash: str,
    group_id: int,
    db: AsyncSession = Depends(get_db),
):
    await _assert_account(account_hash, db)
    group = await _get_group(account_hash, group_id, db)
    return service.compute_group_pnl(group)


@router.post("/{account_hash}/groups/{group_id}/close", response_model=GroupPnLResponse)
async def close_group(
    account_hash: str,
    group_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Mark a group as CLOSED and remove it from the live alert index."""
    await _assert_account(account_hash, db)
    await _get_group(account_hash, group_id, db)  # ownership check
    try:
        group = await service.close_group(group_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return service.compute_group_pnl(group)


@router.delete("/{account_hash}/groups/{group_id}", status_code=204)
async def delete_group(
    account_hash: str,
    group_id: int,
    db: AsyncSession = Depends(get_db),
):
    await _assert_account(account_hash, db)
    await _get_group(account_hash, group_id, db)  # ownership check
    try:
        await service.delete_group(group_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@router.post("/{account_hash}/groups/{group_id}/alerts", response_model=AlertResponse, status_code=201)
async def add_alert(
    account_hash: str,
    group_id: int,
    req: AlertRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Add a P&L threshold alert to an existing group.
    alert_type: PROFIT_TARGET or STOP_LOSS
    threshold_pct: e.g. 100.0 triggers when unrealized P&L >= 100% of entry cost;
                        30.0 (STOP_LOSS) triggers when loss >= 30% of entry cost.
    """
    await _assert_account(account_hash, db)
    await _get_group(account_hash, group_id, db)
    try:
        alert = await service.add_alert(group_id, req.alert_type, req.threshold_pct, db)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return AlertResponse(
        id=alert.id,
        alert_type=alert.alert_type,
        threshold_pct=alert.threshold_pct,
        is_active=alert.is_active,
        triggered_at=alert.triggered_at,
    )


@router.delete("/{account_hash}/groups/{group_id}/alerts/{alert_id}", status_code=204)
async def remove_alert(
    account_hash: str,
    group_id: int,
    alert_id: int,
    db: AsyncSession = Depends(get_db),
):
    await _assert_account(account_hash, db)
    await _get_group(account_hash, group_id, db)
    try:
        await service.remove_alert(group_id, alert_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Auto-detect
# ---------------------------------------------------------------------------

@router.post("/{account_hash}/groups/auto-detect", response_model=AutoDetectResponse)
async def auto_detect(
    account_hash: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Scan filled orders for multi-leg option positions and propose position groups.
    Returns proposals with legs and best-effort entry prices from transaction history.
    Confirm each via POST /pnl/{account_hash}/groups.
    """
    await _assert_account(account_hash, db)
    raw_proposals = await service.auto_detect_groups(account_hash, db)
    proposed = [
        ProposedGroup(
            order_id=p["order_id"],
            underlying=p["underlying"],
            group_type=p["group_type"],
            entry_date=p["entry_date"],
            legs=[ProposedLeg(**leg) for leg in p["legs"]],
        )
        for p in raw_proposals
    ]
    return AutoDetectResponse(
        proposed_groups=proposed,
        message=(
            f"Found {len(proposed)} candidate group(s). "
            "Review entry prices then confirm each via POST /pnl/{account_hash}/groups."
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _assert_account(account_hash: str, db: AsyncSession) -> None:
    accounts = await account_service.list_accounts(db)
    if not any(a.account_hash == account_hash for a in accounts):
        raise HTTPException(status_code=404, detail="Account not found")


async def _get_group(account_hash: str, group_id: int, db: AsyncSession):
    try:
        group = await service._get_group_or_raise(group_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if group.account_hash != account_hash:
        raise HTTPException(status_code=404, detail=f"Group {group_id} not found")
    return group
