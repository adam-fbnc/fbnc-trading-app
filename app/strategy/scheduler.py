"""
Delta-snapshot scheduler — records per-underlying delta snapshots on a fixed
interval for tracked accounts, gated to equity market hours. Mirrors the GEX
snapshotter's pattern.

Tracked accounts are held in memory for now; a persistent strategy-config
table (account allowlist + mode) is a later story.
"""
import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings

logger = logging.getLogger("app.strategy")

_scheduler: BackgroundScheduler | None = None
_tracked_accounts: set[str] = set()
_last_run: datetime | None = None
_job_running: bool = False


def get_tracked_accounts() -> list[str]:
    return sorted(_tracked_accounts)


def add_tracked_account(account_hash: str) -> None:
    _tracked_accounts.add(account_hash)


def remove_tracked_account(account_hash: str) -> None:
    _tracked_accounts.discard(account_hash)


def start_scheduler() -> None:
    global _scheduler
    interval = max(5, settings.strategy_snapshot_interval_seconds)
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _snapshot_job,
        trigger=IntervalTrigger(seconds=interval),
        id="delta_snapshot",
        name="Delta Snapshot",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Delta-snapshot scheduler started (every %ds)", interval)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Delta-snapshot scheduler stopped")


def get_scheduler_status() -> dict:
    next_run = None
    if _scheduler and _scheduler.running:
        job = _scheduler.get_job("delta_snapshot")
        if job:
            next_run = job.next_run_time
    return {
        "tracked_accounts": get_tracked_accounts(),
        "interval_seconds": max(5, settings.strategy_snapshot_interval_seconds),
        "next_run": next_run,
        "last_run": _last_run,
        "job_running": _job_running,
    }


def _snapshot_job() -> None:
    global _last_run, _job_running
    accounts = get_tracked_accounts()
    if not accounts:
        return
    _job_running = True
    try:
        asyncio.run(_record_all(accounts))
        _last_run = datetime.now(timezone.utc)
    except Exception as e:
        logger.error("Delta-snapshot job failed: %s", e)
    finally:
        _job_running = False


async def _record_all(accounts: list[str]) -> None:
    from app.core.database import AsyncSessionLocal
    from app.market.service import is_market_open
    from app.strategy.service import record_delta_snapshot

    async with AsyncSessionLocal() as db:
        try:
            if not await is_market_open("equity", db):
                logger.debug("Equity market closed — skipping delta snapshot")
                return
        except Exception:
            pass  # if the market-hours check fails, proceed rather than miss data

        for account_hash in accounts:
            try:
                await record_delta_snapshot(account_hash, db)
            except Exception as e:
                logger.warning("Snapshot failed for account %s: %s", account_hash, e)
