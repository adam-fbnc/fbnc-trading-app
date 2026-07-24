import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.account import service as account_service
from app.core.database import get_db
from app.pnl import service
from app.pnl.schemas import (
    AlertRequest, AlertResponse, AutoDetectResponse,
    CreateGroupRequest, GroupPnLResponse, ProposedGroup, ProposedLeg,
    StructureSyncResponse, StructureReconcileResponse,
)

ACCOUNT_IDENTIFIER = Path(
    ...,
    description=(
        "Account hash or account alias identifying the account. "
        "account_hash is checked first; if no account_hash matches, the value "
        "is looked up as an account_alias."
    ),
)

logger = logging.getLogger("app.pnl")
router = APIRouter(prefix="/pnl", tags=["pnl"])


# ---------------------------------------------------------------------------
# Complex position structures
# ---------------------------------------------------------------------------

@router.post("/{account_identifier}/structures/sync", response_model=StructureSyncResponse)
async def sync_structures(
    account_identifier: str = ACCOUNT_IDENTIFIER,
    db: AsyncSession = Depends(get_db),
):
    """
    Detect complex positions (spreads, ratios, butterflies) from filled orders
    and persist them as auto-managed structures.

    A multi-leg order is split into its constituent spreads — a 4-leg order that
    combines a roll-up with a new diagonal becomes two structures, and a condor
    becomes a call spread plus a put spread. Legs that hold nothing (the
    buy-to-close side of a roll) are dropped. Sync positions first.

    Manually created groups are never touched.
    """
    account_hash = await _resolve_account_identifier(account_identifier, db)
    result = await service.sync_structures(account_hash, db)
    return StructureSyncResponse(**result)


@router.post("/{account_identifier}/structures/reconcile", response_model=StructureReconcileResponse)
async def reconcile_structures(
    account_identifier: str = ACCOUNT_IDENTIFIER,
    db: AsyncSession = Depends(get_db),
):
    """
    Re-classify structures against currently-held positions after a leg is
    closed or partially closed. A 1:2 ratio that loses one long becomes a
    vertical; a spread that loses a leg becomes SINGLE; a structure with nothing
    left is closed. Sync positions first.
    """
    account_hash = await _resolve_account_identifier(account_identifier, db)
    result = await service.reconcile_structures(account_hash, db)
    return StructureReconcileResponse(**result)


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


async def _get_group(account_hash: str, group_id: int, db: AsyncSession):
    try:
        group = await service._get_group_or_raise(group_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if group.account_hash != account_hash:
        raise HTTPException(status_code=404, detail=f"Group {group_id} not found")
    return group
