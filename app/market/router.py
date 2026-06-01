from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.market import schemas, service
from app.core.database import get_db

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/hours", response_model=schemas.MarketHoursResponse)
async def get_market_hours(
    market: str = Query(description="Market type: equity, option, bond, future, forex"),
    date: date | None = Query(default=None, description="Date (YYYY-MM-DD), defaults to today"),
    db: AsyncSession = Depends(get_db),
):
    if market not in service.VALID_MARKETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid market '{market}'. Must be one of: {sorted(service.VALID_MARKETS)}",
        )
    return await service.get_market_hours(market, db, date)


@router.get("/quotes", response_model=list[schemas.QuoteResponse])
async def get_quotes(
    symbols: str = Query(description="Comma-separated symbols, e.g. AAPL,MSFT,SPY"),
    db: AsyncSession = Depends(get_db),
):
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(status_code=400, detail="At least one symbol is required")
    return await service.get_quotes(symbol_list, db)


@router.get("/quotes/{symbol}", response_model=schemas.QuoteResponse)
async def get_quote(
    symbol: str,
    db: AsyncSession = Depends(get_db),
):
    return await service.get_quote(symbol.upper(), db)


@router.get("/{symbol}/history", response_model=list[schemas.PriceBarResponse])
async def get_price_history(
    symbol: str,
    period_type: str = Query(default="day", description="day, month, year, ytd"),
    period: int | None = Query(default=None, description="Number of periods"),
    frequency_type: str = Query(default="minute", description="minute, daily, weekly, monthly"),
    frequency: int = Query(default=1, description="Frequency within frequency_type"),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    need_extended_hours: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    valid_period_types = {"day", "month", "year", "ytd"}
    valid_frequency_types = {"minute", "daily", "weekly", "monthly"}
    if period_type not in valid_period_types:
        raise HTTPException(status_code=400, detail=f"period_type must be one of {valid_period_types}")
    if frequency_type not in valid_frequency_types:
        raise HTTPException(status_code=400, detail=f"frequency_type must be one of {valid_frequency_types}")
    return await service.get_price_history(
        symbol.upper(), db, period_type, period, frequency_type, frequency,
        start_date, end_date, need_extended_hours,
    )
