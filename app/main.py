import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.logging_config import setup_logging
from app.core.middleware import register_observability
from app.account.router import router as account_router
from app.market.router import router as market_router
from app.orders.router import router as orders_router
from app.streaming.router import router as stream_router
from app.gex.router import router as gex_router
from app.strategy.router import router as strategy_router

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    from app.streaming.manager import start_stream, subscribe_account_activity
    from app.streaming.db_worker import start_db_worker
    from app.gex.scheduler import start_scheduler
    try:
        start_db_worker()
        start_stream()
        subscribe_account_activity()
        logger.info("Stream and DB worker started on boot")
    except Exception as e:
        logger.warning("Could not auto-start stream on boot: %s", e)
    try:
        start_scheduler()
        logger.info("OI snapshot scheduler started on boot")
    except Exception as e:
        logger.warning("Could not start OI scheduler: %s", e)

    yield

    # Shutdown
    from app.streaming.manager import stop_stream
    from app.streaming.db_worker import stop_db_worker
    from app.gex.scheduler import stop_scheduler
    stop_stream()
    stop_db_worker()
    stop_scheduler()
    logger.info("Stream, DB worker, and scheduler stopped on shutdown")


app = FastAPI(title="Schwab Trading API", version="0.1.0", lifespan=lifespan)

register_observability(app)

app.include_router(account_router)
app.include_router(market_router)
app.include_router(orders_router)
app.include_router(stream_router)
app.include_router(gex_router)
app.include_router(strategy_router)


@app.get("/health")
async def health():
    from app.streaming.state import stream_state
    return {"status": "ok", "stream_running": stream_state.is_running}
