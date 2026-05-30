from fastapi import APIRouter, Depends
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
