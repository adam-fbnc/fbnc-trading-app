from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.account import schemas, service
from app.core.database import get_db

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[schemas.AccountResponse])
async def get_accounts(db: AsyncSession = Depends(get_db)):
    return await service.list_accounts(db)


@router.post("/sync", response_model=list[schemas.AccountResponse])
async def sync_accounts(db: AsyncSession = Depends(get_db)):
    return await service.sync_linked_accounts(db)


@router.get("/{account_hash}/summary", response_model=schemas.AccountSummaryResponse)
async def get_account_summary(account_hash: str, db: AsyncSession = Depends(get_db)):
    accounts = await service.list_accounts(db)
    if not any(a.account_hash == account_hash for a in accounts):
        raise HTTPException(status_code=404, detail="Account not found")
    return await service.get_account_summary(account_hash, db)


@router.post("/{account_hash}/summary/refresh", response_model=schemas.AccountSummaryResponse)
async def refresh_account_summary(account_hash: str, db: AsyncSession = Depends(get_db)):
    accounts = await service.list_accounts(db)
    if not any(a.account_hash == account_hash for a in accounts):
        raise HTTPException(status_code=404, detail="Account not found")
    return await service.get_account_summary(account_hash, db)
