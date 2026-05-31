from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.market import schemas, service
from app.core.database import get_db

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/hours", response_model=schemas.MarketHoursResponse)
async def get_market_hours(
    market: str = Query(description="Market type: equity, option, bond, future, forex"),
    date: date | None = Query(default=None, description="Date (YYYY-MM-DD), defaults to today"),
    refresh: bool = Query(default=False, description="Force re-fetch even if cached"),
    db: AsyncSession = Depends(get_db),
):
    if market not in service.VALID_MARKETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid market '{market}'. Must be one of: {sorted(service.VALID_MARKETS)}",
        )
    return await service.get_market_hours(market, db, date)
