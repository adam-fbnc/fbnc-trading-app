import logging
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.gex.calculator import calculate_gex, ContractInput, GEXResult
from app.market.models import OptionContract, QuoteSnapshot
from app.core.schwab_client import get_schwab_client

logger = logging.getLogger(__name__)

# In-memory registry of symbols to track
_tracked_symbols: set[str] = set()


def get_tracked_symbols() -> list[str]:
    return sorted(_tracked_symbols)


def add_tracked_symbol(symbol: str) -> None:
    _tracked_symbols.add(symbol.upper())


def remove_tracked_symbol(symbol: str) -> None:
    _tracked_symbols.discard(symbol.upper())


async def build_gex(
    symbol: str,
    db: AsyncSession,
    snapshot_time: datetime | None = None,
    spot_price: Decimal | None = None,
) -> GEXResult | None:
    symbol = symbol.upper()

    # Get the latest snapshot time if not specified
    if snapshot_time is None:
        result = await db.execute(
            select(func.max(OptionContract.snapped_at))
            .where(OptionContract.underlying_symbol == symbol)
        )
        snapshot_time = result.scalar_one_or_none()
        if snapshot_time is None:
            logger.warning("No option chain data found for %s", symbol)
            return None

    # Fetch contracts from that snapshot
    result = await db.execute(
        select(OptionContract).where(
            OptionContract.underlying_symbol == symbol,
            OptionContract.snapped_at == snapshot_time,
        )
    )
    contracts = result.scalars().all()
    if not contracts:
        return None

    # Get spot price — DB cache first, live API only as fallback
    if spot_price is None:
        spot_price = await _get_spot_price(symbol, db)
    if spot_price is None:
        raise ValueError(
            f"Cannot compute GEX for {symbol}: no spot price available. "
            f"Run GET /market/quotes/{symbol} to fetch a current quote first."
        )

    inputs = [
        ContractInput(
            strike=c.strike,
            contract_type=c.contract_type,
            gamma=c.gamma,
            open_interest=c.open_interest,
        )
        for c in contracts
    ]

    return calculate_gex(symbol, inputs, spot_price)


async def _get_spot_price(symbol: str, db: AsyncSession) -> Decimal | None:
    """
    Read latest cached quote from DB. Falls back to a live Schwab API call
    only if no cached quote exists. Never raises — returns None on failure.
    """
    # Try DB cache first (no side effects, no API call)
    result = await db.execute(
        select(QuoteSnapshot.last_price)
        .where(QuoteSnapshot.symbol == symbol, QuoteSnapshot.last_price.is_not(None))
        .order_by(QuoteSnapshot.quoted_at.desc())
        .limit(1)
    )
    cached = result.scalar_one_or_none()
    if cached is not None:
        return cached

    # Fall back to live API
    try:
        client = get_schwab_client()
        response = client.quotes([symbol], fields="quote")
        response.raise_for_status()
        data = response.json()
        quote = data.get(symbol, {}).get("quote", {})
        price = quote.get("lastPrice") or quote.get("mark")
        return Decimal(str(price)) if price is not None else None
    except Exception as e:
        logger.warning("Could not fetch live spot price for %s: %s", symbol, e)
        return None


async def get_oi_changes(
    symbol: str,
    db: AsyncSession,
) -> list[dict]:
    """Compare OI between the two most recent snapshots."""
    symbol = symbol.upper()

    # Get two most recent distinct snapshot times
    result = await db.execute(
        select(OptionContract.snapped_at)
        .where(OptionContract.underlying_symbol == symbol)
        .distinct()
        .order_by(OptionContract.snapped_at.desc())
        .limit(2)
    )
    times = [row[0] for row in result.fetchall()]
    if len(times) < 2:
        return []

    latest_t, prev_t = times[0], times[1]

    # Fetch both snapshots
    def fetch_oi(snap_time):
        return select(
            OptionContract.strike,
            OptionContract.contract_type,
            OptionContract.open_interest,
        ).where(
            OptionContract.underlying_symbol == symbol,
            OptionContract.snapped_at == snap_time,
        )

    latest_res = await db.execute(fetch_oi(latest_t))
    prev_res = await db.execute(fetch_oi(prev_t))

    latest = {(r.strike, r.contract_type): r.open_interest for r in latest_res}
    prev = {(r.strike, r.contract_type): r.open_interest for r in prev_res}

    changes = []
    for (strike, ct), oi in latest.items():
        prev_oi = prev.get((strike, ct), 0) or 0
        delta = (oi or 0) - prev_oi
        if delta != 0:
            changes.append({
                "strike": float(strike),
                "contract_type": ct,
                "prev_oi": prev_oi,
                "current_oi": oi or 0,
                "oi_delta": delta,
            })

    return sorted(changes, key=lambda x: abs(x["oi_delta"]), reverse=True)
