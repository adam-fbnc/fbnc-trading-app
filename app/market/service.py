import logging
from datetime import datetime, timezone, date as date_type
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import MarketHours, QuoteSnapshot, PriceBar, OptionContract
from app.core.schwab_client import get_schwab_client

logger = logging.getLogger(__name__)

VALID_MARKETS = {"equity", "option", "bond", "future", "forex"}

# Number of columns inserted per option_contracts row — used to size insert
# batches under asyncpg's bind-parameter limit.
OPTION_INSERT_COLS = 18

# asyncpg caps bind parameters per statement at 32767 (Postgres protocol int16).
# Stay well under it with a safety margin.
MAX_BIND_PARAMS = 30000


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
# Option Chains
# ---------------------------------------------------------------------------

async def get_option_chain(
    symbol: str,
    db: AsyncSession,
    contract_type: str = "ALL",
    strike_count: int | None = None,
    from_date: date_type | None = None,
    to_date: date_type | None = None,
    include_underlying_quote: bool = True,
) -> list[OptionContract]:
    client = get_schwab_client()
    response = client.option_chains(
        symbol,
        contractType=contract_type,
        strikeCount=strike_count,
        fromDate=from_date,
        toDate=to_date,
        includeUnderlyingQuote=include_underlying_quote,
    )
    response.raise_for_status()
    data = response.json()

    snapped_at = datetime.now(timezone.utc)
    contracts = _parse_option_chain(symbol.upper(), data, snapped_at)
    logger.info("Parsed %d option contract(s) for %s", len(contracts), symbol)

    if not contracts:
        logger.info("No option contracts returned for %s", symbol)
        return []

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    # asyncpg caps bind parameters at 32767 per statement. With
    # OPTION_INSERT_COLS columns per row, batch to stay under MAX_BIND_PARAMS.
    # NVDA's full chain alone is ~4,300 rows × 18 cols ≈ 77k params in one shot.
    batch_size = MAX_BIND_PARAMS // OPTION_INSERT_COLS  # ~1666 rows/batch
    total = len(contracts)
    for start in range(0, total, batch_size):
        chunk = contracts[start:start + batch_size]
        stmt = pg_insert(OptionContract).values(chunk).on_conflict_do_update(
            constraint="uq_option_contracts_key",
            set_={
                "open_interest": pg_insert(OptionContract).excluded.open_interest,
                "volume": pg_insert(OptionContract).excluded.volume,
                "implied_volatility": pg_insert(OptionContract).excluded.implied_volatility,
                "delta": pg_insert(OptionContract).excluded.delta,
                "gamma": pg_insert(OptionContract).excluded.gamma,
                "theta": pg_insert(OptionContract).excluded.theta,
                "vega": pg_insert(OptionContract).excluded.vega,
                "last_price": pg_insert(OptionContract).excluded.last_price,
                "bid": pg_insert(OptionContract).excluded.bid,
                "ask": pg_insert(OptionContract).excluded.ask,
                "raw": pg_insert(OptionContract).excluded.raw,
            },
        )
        try:
            await db.execute(stmt)
        except SQLAlchemyError as e:
            # Surface the concise underlying driver error (asyncpg), not the
            # 30k-parameter statement dump. e.orig is the real DBAPI exception.
            orig = getattr(e, "orig", None)
            logger.error(
                "DB insert failed for %s batch rows %d-%d: %s: %s",
                symbol, start, start + len(chunk),
                type(orig).__name__ if orig else type(e).__name__,
                orig if orig else e,
            )
            await db.rollback()
            raise
        logger.debug("Inserted batch %d-%d of %d for %s", start, start + len(chunk), total, symbol)

    await db.commit()
    logger.info("Upserted %d option contract(s) for %s in %d batch(es)",
                total, symbol, (total + batch_size - 1) // batch_size)

    result = await db.execute(
        select(OptionContract)
        .where(OptionContract.underlying_symbol == symbol.upper())
        .order_by(OptionContract.expiration_date, OptionContract.strike, OptionContract.contract_type)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Instrument Search
# ---------------------------------------------------------------------------

async def search_instruments(symbol: str, projection: str = "symbol-search") -> list[dict]:
    client = get_schwab_client()
    response = client.instruments(symbol, projection=projection)
    response.raise_for_status()
    data = response.json()
    instruments = data.get("instruments", data) if isinstance(data, dict) else data
    return instruments if isinstance(instruments, list) else list(instruments.values())


async def get_instrument_by_cusip(cusip: str) -> dict:
    client = get_schwab_client()
    response = client.instrument_cusip(cusip)
    response.raise_for_status()
    return response.json()


def _parse_option_chain(
    underlying: str, data: dict, snapped_at: datetime
) -> list[dict]:
    # Keyed by the DB unique constraint (expiration, strike, contract_type) so we
    # never emit two rows that collide on ON CONFLICT in a single INSERT. Some
    # underlyings (e.g. post-split NVDA) return both standard and adjusted/
    # non-standard contracts at the same strike+expiration; we keep the one with
    # the highest open interest (the standard, liquid contract).
    by_key: dict[tuple, dict] = {}

    for contract_type_key in ("callExpDateMap", "putExpDateMap"):
        contract_type = "CALL" if contract_type_key == "callExpDateMap" else "PUT"
        for exp_key, strikes in data.get(contract_type_key, {}).items():
            # exp_key format: "2026-01-17:30" (date:daysToExpiration)
            exp_date_str = exp_key.split(":")[0]
            try:
                from datetime import date as dt_date
                exp_date = dt_date.fromisoformat(exp_date_str)
            except ValueError:
                continue

            for strike_str, contracts in strikes.items():
                strike = _d(strike_str)
                for contract in contracts:
                    key = (exp_date, strike, contract_type)
                    row = {
                        "underlying_symbol": underlying,
                        "symbol": contract.get("symbol", ""),
                        "cusip": contract.get("cusip"),
                        "contract_type": contract_type,
                        "expiration_date": exp_date,
                        "strike": strike,
                        "open_interest": contract.get("openInterest"),
                        "volume": contract.get("totalVolume"),
                        "implied_volatility": _d(contract.get("volatility")),
                        "delta": _d(contract.get("delta")),
                        "gamma": _d(contract.get("gamma")),
                        "theta": _d(contract.get("theta")),
                        "vega": _d(contract.get("vega")),
                        "last_price": _d(contract.get("last")),
                        "bid": _d(contract.get("bid")),
                        "ask": _d(contract.get("ask")),
                        "raw": contract,
                        "snapped_at": snapped_at,
                    }
                    existing = by_key.get(key)
                    if existing is None or _oi(row) > _oi(existing):
                        by_key[key] = row

    return list(by_key.values())


def _oi(row: dict) -> int:
    return row.get("open_interest") or 0


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
