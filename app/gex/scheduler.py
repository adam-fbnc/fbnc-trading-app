"""
APScheduler job — fetches option chains for tracked symbols every 30 minutes
during market hours. Runs as a background thread alongside the FastAPI app.
"""
import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.gex.service import get_tracked_symbols

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_last_run: datetime | None = None
_job_running: bool = False


def start_scheduler() -> None:
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _snapshot_job,
        trigger=IntervalTrigger(minutes=30),
        id="oi_snapshot",
        name="OI Snapshot",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("OI snapshot scheduler started (every 30 min)")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("OI snapshot scheduler stopped")


def get_scheduler_status() -> dict:
    next_run = None
    if _scheduler and _scheduler.running:
        job = _scheduler.get_job("oi_snapshot")
        if job:
            next_run = job.next_run_time
    return {
        "tracked_symbols": get_tracked_symbols(),
        "next_run": next_run,
        "last_run": _last_run,
        "job_running": _job_running,
    }


def _snapshot_job() -> None:
    """
    Called by APScheduler in a thread. Creates a new event loop to run
    the async snapshot coroutine.
    """
    global _last_run, _job_running
    symbols = get_tracked_symbols()
    if not symbols:
        logger.debug("No tracked symbols — skipping OI snapshot")
        return

    _job_running = True
    try:
        asyncio.run(_fetch_snapshots(symbols))
        _last_run = datetime.now(timezone.utc)
        logger.info("OI snapshot completed for: %s", symbols)
    except Exception as e:
        logger.error("OI snapshot job failed: %s", e)
    finally:
        _job_running = False


async def _fetch_snapshots(symbols: list[str]) -> None:
    from app.core.database import AsyncSessionLocal
    from app.market.service import get_option_chain, is_market_open

    async with AsyncSessionLocal() as db:
        try:
            open_ = await is_market_open("option", db)
            if not open_:
                logger.info("Option market closed — skipping snapshot")
                return
        except Exception:
            pass  # If market hours check fails, proceed anyway

        for symbol in symbols:
            try:
                await get_option_chain(symbol, db)
                logger.info("Snapped option chain for %s", symbol)
            except Exception as e:
                logger.warning("Failed to snap option chain for %s: %s", symbol, e)
