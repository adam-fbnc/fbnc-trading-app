from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.account import schemas, service
from app.core.database import get_db

router = APIRouter(prefix="/accounts", tags=["accounts"])

ACCOUNT_IDENTIFIER = Path(
    ...,
    description=(
        "Account hash or account alias identifying the account. "
        "account_hash is checked first; if no account_hash matches, the value "
        "is looked up as an account_alias."
    ),
)


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
# By account_identifier (account_hash or account_alias)
# ---------------------------------------------------------------------------

@router.get("/{account_identifier}/summary", response_model=schemas.AccountSummaryResponse)
async def get_account_summary(account_identifier: str = ACCOUNT_IDENTIFIER, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    return await service.get_account_summary(account_hash, db)


@router.post("/{account_identifier}/summary/refresh", response_model=schemas.AccountSummaryResponse)
async def refresh_account_summary(account_identifier: str = ACCOUNT_IDENTIFIER, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    return await service.get_account_summary(account_hash, db)


@router.get("/{account_identifier}/positions", response_model=list[schemas.PositionResponse])
async def get_positions(account_identifier: str = ACCOUNT_IDENTIFIER, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    return await service.list_positions(account_hash, db)


@router.post("/{account_identifier}/positions/sync", response_model=list[schemas.PositionResponse])
async def sync_positions(account_identifier: str = ACCOUNT_IDENTIFIER, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    return await service.sync_positions(account_hash, db)


@router.get("/{account_identifier}/orders", response_model=list[schemas.OrderResponse])
async def get_orders(
    account_identifier: str = ACCOUNT_IDENTIFIER,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    return await service.list_orders(account_hash, db, from_date, to_date, status)


@router.post("/{account_identifier}/orders/sync", response_model=list[schemas.OrderResponse])
async def sync_orders(
    account_identifier: str = ACCOUNT_IDENTIFIER,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    return await service.sync_orders(account_hash, db, from_date, to_date, status)


@router.get("/{account_identifier}/transactions", response_model=list[schemas.TransactionResponse])
async def get_transactions(
    account_identifier: str = ACCOUNT_IDENTIFIER,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    return await service.list_transactions(account_hash, db, from_date, to_date, type)


@router.post("/{account_identifier}/transactions/sync", response_model=list[schemas.TransactionResponse])
async def sync_transactions(
    account_identifier: str = ACCOUNT_IDENTIFIER,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    types: str = Query(default="TRADE"),
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    return await service.sync_transactions(account_hash, db, from_date, to_date, types)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_account_identifier(account_identifier: str, db: AsyncSession) -> str:
    """Resolve account_identifier to an account_hash, trying account_hash first
    and falling back to account_alias."""
    try:
        account_hash = await service.resolve_account_identifier(account_identifier, db)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if account_hash is None:
        raise HTTPException(
            status_code=404,
            detail=f"No account found with hash or alias '{account_identifier}'",
        )
    return account_hash
