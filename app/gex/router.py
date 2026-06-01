from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.gex import service, scheduler
from app.gex.charts import build_gex_chart
from app.gex.schemas import GEXResponse, GEXByStrikeResponse, OIChangeResponse, SchedulerStatusResponse
from app.core.database import get_db

router = APIRouter(prefix="/gex", tags=["gex"])


# ---------------------------------------------------------------------------
# GEX data endpoints (SCRUM-29, SCRUM-30)
# ---------------------------------------------------------------------------

@router.get("/{symbol}", response_model=GEXResponse)
async def get_gex(symbol: str, db: AsyncSession = Depends(get_db)):
    try:
        result = await service.build_gex(symbol, db)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No option chain data for {symbol.upper()}. Fetch a chain first via GET /market/{symbol.upper()}/option-chain.",
        )
    return GEXResponse(
        symbol=result.symbol,
        spot_price=result.spot_price,
        total_gex=result.total_gex,
        gamma_flip=result.gamma_flip,
        largest_call_strike=result.largest_call_strike,
        largest_put_strike=result.largest_put_strike,
        strikes=[
            GEXByStrikeResponse(
                strike=r.strike, call_gex=r.call_gex, put_gex=r.put_gex,
                net_gex=r.net_gex, call_oi=r.call_oi, put_oi=r.put_oi,
            )
            for r in result.strikes
        ],
    )


@router.get("/{symbol}/oi-changes", response_model=list[OIChangeResponse])
async def get_oi_changes(symbol: str, db: AsyncSession = Depends(get_db)):
    changes = await service.get_oi_changes(symbol, db)
    if not changes:
        raise HTTPException(status_code=404, detail="Need at least two snapshots to compute OI changes.")
    return [OIChangeResponse(**c) for c in changes]


# ---------------------------------------------------------------------------
# Chart endpoint (SCRUM-31) — isolated in charts.py for future C/D upgrade
# ---------------------------------------------------------------------------

@router.get("/{symbol}/chart", response_class=HTMLResponse)
async def get_gex_chart(symbol: str, db: AsyncSession = Depends(get_db)):
    try:
        result = await service.build_gex(symbol, db)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No option chain data for {symbol.upper()}.",
        )
    html = build_gex_chart(result)
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Scheduler / symbol management (SCRUM-28)
# ---------------------------------------------------------------------------

@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
async def scheduler_status():
    return SchedulerStatusResponse(**scheduler.get_scheduler_status())


@router.post("/symbols")
async def add_symbol(symbol: str = Query(description="Symbol to track for OI snapshots")):
    service.add_tracked_symbol(symbol)
    return {"tracked_symbols": service.get_tracked_symbols()}


@router.delete("/symbols")
async def remove_symbol(symbol: str = Query(description="Symbol to stop tracking")):
    service.remove_tracked_symbol(symbol)
    return {"tracked_symbols": service.get_tracked_symbols()}


@router.get("/symbols", response_model=list[str])
async def list_symbols():
    return service.get_tracked_symbols()


@router.post("/scheduler/run-now")
async def run_snapshot_now():
    """Trigger an immediate OI snapshot outside the 30-min schedule."""
    symbols = service.get_tracked_symbols()
    if not symbols:
        raise HTTPException(status_code=400, detail="No tracked symbols. Add symbols first via POST /gex/symbols.")
    scheduler._snapshot_job()
    return {"message": f"Snapshot triggered for {symbols}"}
