"""
Bridge between strategy positions and the Level 1 stream: subscribes an
account's option legs (Greeks) and underlyings (spot), and reads live values
back from the in-memory stream cache.
"""
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.account.models import Position
from app.streaming import manager
from app.streaming.state import stream_state

logger = logging.getLogger("app.strategy")


async def subscribe_account(account_hash: str, db: AsyncSession) -> dict:
    """Subscribe the stream to all option legs + underlyings for an account."""
    result = await db.execute(select(Position).where(Position.account_hash == account_hash))
    positions = list(result.scalars().all())

    option_symbols, underlyings = set(), set()
    for pos in positions:
        if (pos.asset_type or "").upper() == "OPTION":
            option_symbols.add(pos.symbol)
            # underlying via raw instrument when available
            inst = pos.raw.get("instrument", {}) if isinstance(pos.raw, dict) else {}
            u = inst.get("underlyingSymbol")
            if u:
                underlyings.add(u)
        else:
            underlyings.add(pos.symbol)

    if option_symbols:
        manager.subscribe_options(sorted(option_symbols))
    if underlyings:
        manager.subscribe_quotes(sorted(underlyings))

    logger.info(
        "Strategy stream: subscribed %d option(s) + %d underlying(s) for %s",
        len(option_symbols), len(underlyings), account_hash,
    )
    return {"options": len(option_symbols), "underlyings": len(underlyings)}


def get_live_greek(symbol: str, name: str = "delta") -> Decimal | None:
    """Read a named greek/price from the live stream cache, or None if absent."""
    data = stream_state.get_quote(symbol.upper())
    if not data:
        return None
    val = data.get(name)
    try:
        return Decimal(str(val)) if val is not None else None
    except Exception:
        return None
