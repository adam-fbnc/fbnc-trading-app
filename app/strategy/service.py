import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.account.models import Position
from app.core.schwab_client import get_schwab_client
from app.strategy.aggregator import LegInput, AccountDeltaSummary, aggregate

logger = logging.getLogger("app.strategy")

_EQUITY_TYPES = {"EQUITY", "ETF", "COLLECTIVE_INVESTMENT", "INDEX"}


async def build_delta_summary(account_hash: str, db: AsyncSession) -> AccountDeltaSummary:
    # Structure comes from the already-synced positions table.
    result = await db.execute(
        select(Position).where(Position.account_hash == account_hash)
    )
    positions = list(result.scalars().all())
    if not positions:
        logger.info("No positions for account %s; returning empty delta summary", account_hash)
        return AccountDeltaSummary(underlyings=[], total_net_delta=Decimal("0"))

    # Build leg metadata and collect symbols needing live quotes.
    legs_meta: list[dict] = []
    option_symbols: set[str] = set()
    underlyings: set[str] = set()

    for pos in positions:
        asset_type = (pos.asset_type or "").upper()
        if asset_type == "OPTION":
            meta = _parse_option(pos)
            if meta is None:
                logger.warning("Could not parse option position %s; skipping", pos.symbol)
                continue
            legs_meta.append(meta)
            option_symbols.add(pos.symbol)
            underlyings.add(meta["underlying"])
        else:
            legs_meta.append({
                "symbol": pos.symbol,
                "asset_type": asset_type or "EQUITY",
                "underlying": pos.symbol,
                "quantity": pos.quantity,
                "contract_type": None,
                "strike": None,
                "expiration": None,
            })
            underlyings.add(pos.symbol)

    # One live quotes call for all option legs + underlyings (Greeks + spot).
    quote_symbols = sorted(option_symbols | underlyings)
    quotes = _fetch_quotes(quote_symbols)

    spots: dict[str, Decimal | None] = {
        u: _spot_from_quote(quotes.get(u)) for u in underlyings
    }

    legs: list[LegInput] = []
    for m in legs_meta:
        delta = None
        source = "none"
        if m["contract_type"] is not None:  # option
            q = quotes.get(m["symbol"])
            delta = _delta_from_quote(q)
            source = "quote" if delta is not None else "none"
        legs.append(LegInput(
            symbol=m["symbol"],
            asset_type=m["asset_type"],
            underlying=m["underlying"],
            quantity=m["quantity"],
            contract_type=m["contract_type"],
            strike=m["strike"],
            expiration=m["expiration"],
            delta=delta,
            delta_source=source if m["contract_type"] else "equity",
        ))

    summary = aggregate(legs, spots)
    logger.info(
        "Delta summary for %s: %d underlying(s), total_net_delta=%s",
        account_hash, len(summary.underlyings), summary.total_net_delta,
    )
    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_quotes(symbols: list[str]) -> dict:
    if not symbols:
        return {}
    client = get_schwab_client()
    try:
        resp = client.quotes(symbols, fields="all")
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("Failed to fetch quotes for delta summary: %s", e)
        return {}


def _parse_option(pos: Position) -> dict | None:
    """
    Resolve option metadata, preferring the stored raw instrument payload and
    falling back to OSI symbol parsing.
    """
    instrument = {}
    if isinstance(pos.raw, dict):
        instrument = pos.raw.get("instrument", {}) or {}

    underlying = instrument.get("underlyingSymbol")
    put_call = instrument.get("putCall")
    contract_type = put_call.upper() if put_call else None

    osi = _parse_osi(pos.symbol)
    if osi:
        underlying = underlying or osi["underlying"]
        contract_type = contract_type or osi["contract_type"]
        strike = osi["strike"]
        expiration = osi["expiration"]
    else:
        strike = None
        expiration = None

    if not underlying or contract_type not in ("CALL", "PUT"):
        return None

    return {
        "symbol": pos.symbol,
        "asset_type": "OPTION",
        "underlying": underlying,
        "quantity": pos.quantity,
        "contract_type": contract_type,
        "strike": strike,
        "expiration": expiration,
    }


def _parse_osi(symbol: str) -> dict | None:
    """
    Parse an OSI option symbol (21 chars: 6 root + 6 YYMMDD + C/P + 8 strike*1000).
    Schwab pads the root with spaces, e.g. 'NVDA  260605C00130000'.
    Parses from the right to tolerate variable root length.
    """
    s = symbol.strip()
    if len(s) < 15 or s[-9] not in ("C", "P"):
        return None
    try:
        strike = Decimal(s[-8:]) / Decimal("1000")
        cp = s[-9]
        yymmdd = s[-15:-9]
        root = s[:-15].strip()
        expiration = date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))
    except (ValueError, ArithmeticError):
        return None
    if not root:
        return None
    return {
        "underlying": root,
        "contract_type": "CALL" if cp == "C" else "PUT",
        "strike": strike,
        "expiration": expiration,
    }


def _delta_from_quote(q: dict | None) -> Decimal | None:
    if not q:
        return None
    quote = q.get("quote", {}) if isinstance(q, dict) else {}
    return _d(quote.get("delta"))


def _spot_from_quote(q: dict | None) -> Decimal | None:
    if not q:
        return None
    quote = q.get("quote", {}) if isinstance(q, dict) else {}
    return _d(quote.get("lastPrice") or quote.get("mark") or quote.get("closePrice"))


def _d(value) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None
