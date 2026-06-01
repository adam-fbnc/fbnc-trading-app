import logging
from datetime import datetime, timezone, date as date_type
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import MarketHours, QuoteSnapshot, PriceBar
from app.core.schwab_client import get_schwab_client

logger = logging.getLogger(__name__)

VALID_MARKETS = {"equity", "option", "bond", "future", "forex"}


# ---------------------------------------------------------------------------
# Market Hours
# ---------------------------------------------------------------------------

async def get_market_hours(
    market: str,
    db: AsyncSession,
    date: date_type | None = None,
) -> MarketHours:
    target_date = date or datetime.now(timezone.utc).date()

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


# ---------------------------------------------------------------------------
# Quotes
# ---------------------------------------------------------------------------

async def get_quotes(symbols: list[str], db: AsyncSession) -> list[QuoteSnapshot]:
    client = get_schwab_client()
    response = client.quotes(symbols, fields="all")
    response.raise_for_status()
    raw_data = response.json()

    snapshots = []
    now = datetime.now(timezone.utc)

    for symbol, quote_data in raw_data.items():
        quote = quote_data.get("quote", {})
        reference = quote_data.get("reference", {})

        snapshot = QuoteSnapshot(
            symbol=symbol,
            asset_type=quote_data.get("assetMainType") or reference.get("assetType"),
            last_price=_d(quote.get("lastPrice") or quote.get("mark")),
            bid_price=_d(quote.get("bidPrice")),
            ask_price=_d(quote.get("askPrice")),
            open_price=_d(quote.get("openPrice")),
            high_price=_d(quote.get("highPrice")),
            low_price=_d(quote.get("lowPrice")),
            close_price=_d(quote.get("closePrice")),
            volume=quote.get("totalVolume") or quote.get("volume"),
            raw=quote_data,
            quoted_at=now,
        )
        db.add(snapshot)
        snapshots.append(snapshot)

    await db.commit()
    logger.info("Fetched and persisted quotes for %d symbol(s)", len(snapshots))
    return snapshots


async def get_quote(symbol: str, db: AsyncSession) -> QuoteSnapshot:
    results = await get_quotes([symbol], db)
    return results[0]


# ---------------------------------------------------------------------------
# Price History
# ---------------------------------------------------------------------------

async def get_price_history(
    symbol: str,
    db: AsyncSession,
    period_type: str = "day",
    period: int | None = None,
    frequency_type: str = "minute",
    frequency: int = 1,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    need_extended_hours: bool = False,
) -> list[PriceBar]:
    client = get_schwab_client()
    response = client.price_history(
        symbol,
        periodType=period_type,
        period=period,
        frequencyType=frequency_type,
        frequency=frequency,
        startDate=start_date,
        endDate=end_date,
        needExtendedHoursData=need_extended_hours,
    )
    response.raise_for_status()
    data = response.json()

    candles = data.get("candles", [])
    if not candles:
        logger.info("No price bars returned for %s", symbol)
        return []

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    import datetime as dt_module

    rows = []
    for candle in candles:
        # Schwab returns epoch milliseconds
        ts = datetime.fromtimestamp(candle["datetime"] / 1000, tz=timezone.utc)
        rows.append({
            "symbol": symbol.upper(),
            "frequency_type": frequency_type,
            "frequency": frequency,
            "bar_timestamp": ts,
            "open": _d(candle["open"]),
            "high": _d(candle["high"]),
            "low": _d(candle["low"]),
            "close": _d(candle["close"]),
            "volume": int(candle.get("volume", 0)),
        })

    stmt = pg_insert(PriceBar).values(rows).on_conflict_do_nothing(
        constraint="uq_price_bars_symbol_freq_ts"
    )
    await db.execute(stmt)
    await db.commit()
    logger.info("Upserted %d price bar(s) for %s (%s/%s)", len(rows), symbol, frequency_type, frequency)

    result = await db.execute(
        select(PriceBar)
        .where(
            PriceBar.symbol == symbol.upper(),
            PriceBar.frequency_type == frequency_type,
            PriceBar.frequency == frequency,
        )
        .order_by(PriceBar.bar_timestamp)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_hours(raw: dict, market: str) -> tuple[bool, dict | None]:
    try:
        market_data = raw.get(market, {})
        if not market_data:
            return False, None
        inner = next(iter(market_data.values()), {})
        return inner.get("isOpen", False), inner.get("sessionHours")
    except Exception as e:
        logger.warning("Could not parse market hours response: %s", e)
        return False, None


def _d(value) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None
