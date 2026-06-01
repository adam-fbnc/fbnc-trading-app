import logging
from fastapi import APIRouter, HTTPException

from app.streaming import manager
from app.streaming.schemas import StreamStatusResponse, SymbolsRequest, QuoteCacheResponse
from app.streaming.state import stream_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stream", tags=["streaming"])


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@router.post("/start", response_model=StreamStatusResponse)
async def start_stream():
    try:
        manager.start_stream()
        manager.subscribe_account_activity()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return _status()


@router.post("/stop", response_model=StreamStatusResponse)
async def stop_stream():
    manager.stop_stream()
    return _status()


@router.get("/status", response_model=StreamStatusResponse)
async def stream_status():
    return _status()


# ---------------------------------------------------------------------------
# Equity quotes
# ---------------------------------------------------------------------------

@router.post("/subscribe/quotes", response_model=StreamStatusResponse)
async def subscribe_quotes(req: SymbolsRequest):
    try:
        manager.subscribe_quotes(req.symbols)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _status()


@router.post("/unsubscribe/quotes", response_model=StreamStatusResponse)
async def unsubscribe_quotes(req: SymbolsRequest):
    try:
        manager.unsubscribe_quotes(req.symbols)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _status()


# ---------------------------------------------------------------------------
# Option quotes
# ---------------------------------------------------------------------------

@router.post("/subscribe/options", response_model=StreamStatusResponse)
async def subscribe_options(req: SymbolsRequest):
    try:
        manager.subscribe_options(req.symbols)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _status()


@router.post("/unsubscribe/options", response_model=StreamStatusResponse)
async def unsubscribe_options(req: SymbolsRequest):
    try:
        manager.unsubscribe_options(req.symbols)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _status()


# ---------------------------------------------------------------------------
# Quote cache reads
# ---------------------------------------------------------------------------

@router.get("/quotes", response_model=list[QuoteCacheResponse])
async def get_all_cached_quotes():
    return [
        QuoteCacheResponse(symbol=sym, data=data)
        for sym, data in stream_state.get_all_quotes().items()
    ]


@router.get("/quotes/{symbol}", response_model=QuoteCacheResponse)
async def get_cached_quote(symbol: str):
    data = stream_state.get_quote(symbol.upper())
    if data is None:
        raise HTTPException(status_code=404, detail=f"No cached quote for {symbol}. Is it subscribed?")
    return QuoteCacheResponse(symbol=symbol.upper(), data=data)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _status() -> StreamStatusResponse:
    return StreamStatusResponse(
        running=stream_state.is_running,
        started_at=stream_state.started_at,
        last_message_at=stream_state.last_message_at,
        subscriptions=stream_state.get_subscriptions(),
    )
