import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.account.models import Position
from app.core.config import settings
from app.core.schwab_client import get_schwab_client
from app.strategy.aggregator import LegInput, AccountDeltaSummary, aggregate
from app.strategy.moving_averages import compute_ma
from app.strategy.models import DeltaSnapshot

logger = logging.getLogger("app.strategy")

_EQUITY_TYPES = {"EQUITY", "ETF", "COLLECTIVE_INVESTMENT", "INDEX"}


async def build_delta_summary(
    account_hash: str,
    db: AsyncSession,
    underlying_filter: str | None = None,
) -> AccountDeltaSummary:
    """
    Build per-underlying delta breakdown for an account.

    If underlying_filter is given (e.g. "NVDA"), only that ticker's legs are
    included and only its symbols are quoted.
    """
    # Structure comes from the already-synced positions table.
    result = await db.execute(
        select(Position).where(Position.account_hash == account_hash)
    )
    positions = list(result.scalars().all())
    if not positions:
        logger.info("No positions for account %s; returning empty delta summary", account_hash)
        return AccountDeltaSummary(underlyings=[], total_net_delta=Decimal("0"))

    target = underlying_filter.upper() if underlying_filter else None

    # Build leg metadata, then optionally filter to one underlying.
    legs_meta: list[dict] = []
    for pos in positions:
        asset_type = (pos.asset_type or "").upper()
        if asset_type == "OPTION":
            meta = _parse_option(pos)
            if meta is None:
                logger.warning("Could not parse option position %s; skipping", pos.symbol)
                continue
            legs_meta.append(meta)
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

    if target is not None:
        legs_meta = [m for m in legs_meta if m["underlying"].upper() == target]

    option_symbols = {m["symbol"] for m in legs_meta if m["contract_type"] is not None}
    underlyings = {m["underlying"] for m in legs_meta}

    # One live quotes call for the (possibly filtered) option legs + underlyings.
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
# Delta history (snapshots)
# ---------------------------------------------------------------------------

async def record_delta_snapshot(account_hash: str, db: AsyncSession) -> list[DeltaSnapshot]:
    """
    Compute the current delta summary and persist one row per underlying.
    Returns the rows written.
    """
    summary = await build_delta_summary(account_hash, db)
    now = datetime.now(timezone.utc)
    rows: list[DeltaSnapshot] = []

    for u in summary.underlyings:
        short_call_symbol = None
        for leg in u.legs:
            if leg.contract_type == "CALL" and leg.quantity < 0 and leg.delta is not None:
                # Track the short call with the highest |delta| (most ITM)
                if short_call_symbol is None or (
                    u.short_call_delta is not None and leg.delta == u.short_call_delta
                ):
                    short_call_symbol = leg.symbol

        row = DeltaSnapshot(
            account_hash=account_hash,
            underlying=u.underlying,
            spot=u.spot,
            net_delta=u.net_delta,
            short_call_symbol=short_call_symbol,
            short_call_delta=u.short_call_delta,
            long_put_delta=u.long_put_delta,
            recorded_at=now,
        )
        db.add(row)
        rows.append(row)

    await db.commit()
    logger.info("Recorded %d delta snapshot row(s) for account %s", len(rows), account_hash)
    return rows


async def get_smoothed_delta(
    account_hash: str,
    underlying: str,
    db: AsyncSession,
    ma_type: str = "ema",
    window_minutes: float | None = None,
    timeframe_minutes: float | None = None,
    span: int = 10,
    lookback: int = 500,
) -> dict:
    """
    Smoothed short-call delta for one (account, underlying), using a configurable
    moving average over the *current* short-call contract's recent run (so a roll
    starts a fresh window).

    Parameters
    ----------
    ma_type            : "ema" | "hma" | "kama"
    timeframe_minutes  : resample snapshots into bars of this size (last value per
                         bar). Defaults to the snapshot interval (no resampling).
    window_minutes     : time length of the average; converted to bars/samples via
                         the timeframe. If omitted, `span` (in samples) is used.
    """
    underlying = underlying.upper()
    result = await db.execute(
        select(DeltaSnapshot)
        .where(
            DeltaSnapshot.account_hash == account_hash,
            DeltaSnapshot.underlying == underlying,
        )
        .order_by(DeltaSnapshot.recorded_at.desc())
        .limit(lookback)
    )
    rows = list(result.scalars().all())  # newest first

    interval_min = max(5, settings.strategy_snapshot_interval_seconds) / 60.0
    bar_min = timeframe_minutes if timeframe_minutes and timeframe_minutes > 0 else interval_min

    base = {
        "underlying": underlying, "short_call_symbol": None,
        "ma_type": ma_type.lower(), "window_minutes": window_minutes,
        "timeframe_minutes": bar_min, "period": None,
        "current_delta": None, "smoothed_delta": None, "samples": 0,
    }
    if not rows:
        return base

    current_symbol = rows[0].short_call_symbol
    # Contiguous newest run for the current short-call contract, oldest -> newest
    run = []
    for r in rows:
        if r.short_call_symbol != current_symbol:
            break
        if r.short_call_delta is not None:
            run.append((r.recorded_at, r.short_call_delta))
    run.reverse()

    series = _resample_last(run, bar_min) if (timeframe_minutes and timeframe_minutes > 0) else [d for _, d in run]

    if window_minutes and window_minutes > 0:
        period = max(1, round(window_minutes / bar_min))
    else:
        period = span

    smoothed = compute_ma(series, period, ma_type)
    current = series[-1] if series else None

    base.update({
        "short_call_symbol": current_symbol,
        "period": period,
        "current_delta": current,
        "smoothed_delta": smoothed,
        "samples": len(series),
    })
    return base


def _resample_last(points: list[tuple], bar_minutes: float) -> list:
    """Bucket (timestamp, value) points into bars of bar_minutes; keep the last
    value in each bar. Input ordered oldest -> newest; output ordered the same."""
    if not points:
        return []
    bucket_secs = bar_minutes * 60.0
    buckets: dict[int, object] = {}
    order: list[int] = []
    for ts, val in points:
        key = int(ts.timestamp() // bucket_secs)
        if key not in buckets:
            order.append(key)
        buckets[key] = val  # last wins
    return [buckets[k] for k in order]


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
