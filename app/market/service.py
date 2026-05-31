import logging
from datetime import datetime, timezone, date as date_type
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import MarketHours
from app.core.schwab_client import get_schwab_client

logger = logging.getLogger(__name__)

VALID_MARKETS = {"equity", "option", "bond", "future", "forex"}


async def get_market_hours(
    market: str,
    db: AsyncSession,
    date: date_type | None = None,
) -> MarketHours:
    target_date = date or datetime.now(timezone.utc).date()

    # Return cached result if already fetched today
    existing = await db.execute(
        select(MarketHours).where(
            MarketHours.market == market,
            MarketHours.date == target_date,
        )
    )
    cached = existing.scalar_one_or_none()
    if cached:
        logger.debug("Returning cached market hours for %s on %s", market, target_date)
        return cached

    client = get_schwab_client()
    response = client.market_hour(market, date=target_date)
    response.raise_for_status()
    raw = response.json()

    is_open, session_hours = _parse_hours(raw, market)

    stmt = insert(MarketHours).values(
        market=market,
        date=target_date,
        is_open=is_open,
        session_hours=session_hours,
        raw=raw,
        fetched_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        constraint="uq_market_hours_market_date",
        set_={
            "is_open": is_open,
            "session_hours": session_hours,
            "raw": raw,
            "fetched_at": datetime.now(timezone.utc),
        },
    )
    await db.execute(stmt)
    await db.commit()

    result = await db.execute(
        select(MarketHours).where(
            MarketHours.market == market,
            MarketHours.date == target_date,
        )
    )
    record = result.scalar_one()
    logger.info("Fetched market hours for %s on %s — isOpen=%s", market, target_date, is_open)
    return record


async def is_market_open(market: str, db: AsyncSession) -> bool:
    record = await get_market_hours(market, db)
    return record.is_open


def _parse_hours(raw: dict, market: str) -> tuple[bool, dict | None]:
    """
    Schwab returns nested: { "equity": { "EQ": { "isOpen": bool, "sessionHours": {...} } } }
    Walk the response to find the first market entry regardless of the inner key.
    """
    try:
        market_data = raw.get(market, {})
        if not market_data:
            return False, None
        inner = next(iter(market_data.values()), {})
        is_open = inner.get("isOpen", False)
        session_hours = inner.get("sessionHours")
        return is_open, session_hours
    except Exception as e:
        logger.warning("Could not parse market hours response: %s", e)
        return False, None
