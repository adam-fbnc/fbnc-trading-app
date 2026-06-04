from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.account import schemas, service
from app.core.database import get_db

router = APIRouter(prefix="/accounts", tags=["accounts"])


# ---------------------------------------------------------------------------
# Account listing
# ---------------------------------------------------------------------------

@router.get("", response_model=list[schemas.AccountResponse])
async def get_accounts(db: AsyncSession = Depends(get_db)):
    return await service.list_accounts(db)


@router.post("/sync", response_model=list[schemas.AccountResponse])
async def sync_accounts(db: AsyncSession = Depends(get_db)):
    return await service.sync_linked_accounts(db)


# ---------------------------------------------------------------------------
# By account_hash
# ---------------------------------------------------------------------------

@router.get("/{account_hash}/summary", response_model=schemas.AccountSummaryResponse)
async def get_account_summary(account_hash: str, db: AsyncSession = Depends(get_db)):
    await _assert_account_exists(account_hash, db)
    return await service.get_account_summary(account_hash, db)


@router.post("/{account_hash}/summary/refresh", response_model=schemas.AccountSummaryResponse)
async def refresh_account_summary(account_hash: str, db: AsyncSession = Depends(get_db)):
    await _assert_account_exists(account_hash, db)
    return await service.get_account_summary(account_hash, db)


@router.get("/{account_hash}/positions", response_model=list[schemas.PositionResponse])
async def get_positions(account_hash: str, db: AsyncSession = Depends(get_db)):
    await _assert_account_exists(account_hash, db)
    return await service.list_positions(account_hash, db)


@router.post("/{account_hash}/positions/sync", response_model=list[schemas.PositionResponse])
async def sync_positions(account_hash: str, db: AsyncSession = Depends(get_db)):
    await _assert_account_exists(account_hash, db)
    return await service.sync_positions(account_hash, db)


@router.get("/{account_hash}/orders", response_model=list[schemas.OrderResponse])
async def get_orders(
    account_hash: str,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    await _assert_account_exists(account_hash, db)
    return await service.list_orders(account_hash, db, from_date, to_date, status)


@router.post("/{account_hash}/orders/sync", response_model=list[schemas.OrderResponse])
async def sync_orders(
    account_hash: str,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    await _assert_account_exists(account_hash, db)
    return await service.sync_orders(account_hash, db, from_date, to_date, status)


@router.get("/{account_hash}/transactions", response_model=list[schemas.TransactionResponse])
async def get_transactions(
    account_hash: str,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    await _assert_account_exists(account_hash, db)
    return await service.list_transactions(account_hash, db, from_date, to_date, type)


@router.post("/{account_hash}/transactions/sync", response_model=list[schemas.TransactionResponse])
async def sync_transactions(
    account_hash: str,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    types: str = Query(default="TRADE"),
    db: AsyncSession = Depends(get_db),
):
    await _assert_account_exists(account_hash, db)
    return await service.sync_transactions(account_hash, db, from_date, to_date, types)


# ---------------------------------------------------------------------------
# By account_alias — resolve alias to hash, then delegate to the same services
# ---------------------------------------------------------------------------

@router.get("/by-alias/{account_alias}/summary", response_model=schemas.AccountSummaryResponse)
async def get_account_summary_by_alias(account_alias: str, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_alias(account_alias, db)
    return await service.get_account_summary(account_hash, db)


@router.post("/by-alias/{account_alias}/summary/refresh", response_model=schemas.AccountSummaryResponse)
async def refresh_account_summary_by_alias(account_alias: str, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_alias(account_alias, db)
    return await service.get_account_summary(account_hash, db)


@router.get("/by-alias/{account_alias}/positions", response_model=list[schemas.PositionResponse])
async def get_positions_by_alias(account_alias: str, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_alias(account_alias, db)
    return await service.list_positions(account_hash, db)


@router.post("/by-alias/{account_alias}/positions/sync", response_model=list[schemas.PositionResponse])
async def sync_positions_by_alias(account_alias: str, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_alias(account_alias, db)
    return await service.sync_positions(account_hash, db)


@router.get("/by-alias/{account_alias}/orders", response_model=list[schemas.OrderResponse])
async def get_orders_by_alias(
    account_alias: str,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_alias(account_alias, db)
    return await service.list_orders(account_hash, db, from_date, to_date, status)


@router.post("/by-alias/{account_alias}/orders/sync", response_model=list[schemas.OrderResponse])
async def sync_orders_by_alias(
    account_alias: str,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_alias(account_alias, db)
    return await service.sync_orders(account_hash, db, from_date, to_date, status)


@router.get("/by-alias/{account_alias}/transactions", response_model=list[schemas.TransactionResponse])
async def get_transactions_by_alias(
    account_alias: str,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_alias(account_alias, db)
    return await service.list_transactions(account_hash, db, from_date, to_date, type)


@router.post("/by-alias/{account_alias}/transactions/sync", response_model=list[schemas.TransactionResponse])
async def sync_transactions_by_alias(
    account_alias: str,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    types: str = Query(default="TRADE"),
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_alias(account_alias, db)
    return await service.sync_transactions(account_hash, db, from_date, to_date, types)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _assert_account_exists(account_hash: str, db: AsyncSession) -> None:
    accounts = await service.list_accounts(db)
    if not any(a.account_hash == account_hash for a in accounts):
        raise HTTPException(status_code=404, detail="Account not found")


async def _resolve_alias(account_alias: str, db: AsyncSession) -> str:
    try:
        account_hash = await service.get_account_hash_by_alias(account_alias, db)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if account_hash is None:
        raise HTTPException(status_code=404, detail=f"No account found with alias '{account_alias}'")
    return account_hash
