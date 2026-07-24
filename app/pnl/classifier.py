"""
Pure option-structure classification — no DB, no HTTP, no side effects.

Turns a set of option legs into a labelled structure (vertical, calendar,
diagonal, ratio, butterfly...), splits multi-leg orders into their constituent
spreads, and renders the readable structure key used to identify them.

Conventions (shared with app/strategy/aggregator.py):
  - Position quantity is signed: long > 0, short < 0.
  - OSI symbols are parsed right-to-left (6-char root is space-padded).

Structure key format:
    {order_id}-{leg}/{leg}/...
where each leg is {YYYYMMDD}{UNDERLYING}{QTY}{S|L}{C|P}{STRIKE}, e.g.

    1002345678-20260731TQQQ1SC65/20260806TQQQ1LC65

reads as a TQQQ spread: 7/31 expiry $65 strike 1 short call, against an 8/6
expiry $65 strike 1 long call. Legs are sorted so the same structure always
renders the same key regardless of the order the broker reported them in.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

SINGLE = "SINGLE"
CUSTOM = "CUSTOM"


@dataclass(frozen=True)
class Leg:
    symbol: str
    underlying: str
    contract_type: str          # "CALL" | "PUT"
    strike: Decimal
    expiration: date
    quantity: Decimal           # signed: long > 0, short < 0


def parse_osi(symbol: str) -> dict | None:
    """Parse an OSI option symbol (e.g. 'NVDA  260620C00130000') into metadata."""
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


def make_leg(symbol: str, quantity: Decimal) -> Leg | None:
    meta = parse_osi(symbol)
    if meta is None:
        return None
    return Leg(
        symbol=symbol.strip().upper(),
        underlying=meta["underlying"],
        contract_type=meta["contract_type"],
        strike=meta["strike"],
        expiration=meta["expiration"],
        quantity=quantity,
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify(legs: list[Leg]) -> str:
    """Label a leg set as-is. Does not split it — see decompose()."""
    if not legs:
        return CUSTOM
    if len(legs) == 1:
        return SINGLE

    calls = [l for l in legs if l.contract_type == "CALL"]
    puts = [l for l in legs if l.contract_type == "PUT"]

    if calls and puts:
        if len(legs) == 2:
            return "RISK_REVERSAL"
        if len(legs) == 4 and len(calls) == 2 and len(puts) == 2:
            return "IRON_CONDOR"
        return CUSTOM

    prefix = "CALL" if calls else "PUT"
    longs = [l for l in legs if l.quantity > 0]
    shorts = [l for l in legs if l.quantity < 0]
    if not longs or not shorts:
        return CUSTOM

    if len(legs) == 2:
        a, b = legs
        if abs(a.quantity) != abs(b.quantity):
            return f"{prefix}_RATIO"
        same_expiration = a.expiration == b.expiration
        same_strike = a.strike == b.strike
        if same_expiration and not same_strike:
            return f"{prefix}_VERTICAL"
        if same_strike and not same_expiration:
            return f"{prefix}_CALENDAR"
        if not same_strike and not same_expiration:
            return f"{prefix}_DIAGONAL"
        return CUSTOM

    if len(legs) == 3:
        if _is_butterfly(legs):
            return f"{prefix}_BUTTERFLY"
        return f"{prefix}_BACKSPREAD" if len(longs) > len(shorts) else f"{prefix}_RATIO"

    return CUSTOM


def _is_butterfly(legs: list[Leg]) -> bool:
    """1-2-1 across three strikes in a single expiration (wings need not be
    equidistant — a broken-wing butterfly is still a butterfly)."""
    if len({l.expiration for l in legs}) != 1:
        return False
    ordered = sorted(legs, key=lambda l: l.strike)
    if len({l.strike for l in ordered}) != 3:
        return False
    low, middle, high = ordered
    return low.quantity == high.quantity and middle.quantity == -2 * low.quantity


# ---------------------------------------------------------------------------
# Decomposition
# ---------------------------------------------------------------------------

def decompose(legs: list[Leg]) -> list[list[Leg]]:
    """
    Split a multi-leg order into its constituent spreads.

    Calls and puts separate first, so a condor falls out as one call spread plus
    one put spread. Within a same-type set of four, each short pairs with a long
    sharing its expiration (a vertical); whatever is left pairs by nearest strike
    (a calendar or diagonal).

    Leg sets that do not split cleanly are returned whole.
    """
    if len(legs) < 4:
        return [list(legs)]

    calls = [l for l in legs if l.contract_type == "CALL"]
    puts = [l for l in legs if l.contract_type == "PUT"]
    if calls and puts:
        return [group for side in (calls, puts) for group in decompose(side)]

    if len(legs) != 4:
        return [list(legs)]

    shorts = sorted([l for l in legs if l.quantity < 0], key=_sort_key)
    longs = sorted([l for l in legs if l.quantity > 0], key=_sort_key)
    if len(shorts) != 2 or len(longs) != 2:
        return [list(legs)]

    pairs: list[list[Leg]] = []
    unpaired: list[Leg] = []
    available = list(longs)

    for short in shorts:
        same_expiration = [l for l in available if l.expiration == short.expiration]
        if same_expiration:
            match = min(same_expiration, key=lambda l: (abs(l.strike - short.strike), l.strike))
            available.remove(match)
            pairs.append([short, match])
        else:
            unpaired.append(short)

    for short in unpaired:
        match = min(available, key=lambda l: (abs(l.strike - short.strike), l.strike))
        available.remove(match)
        pairs.append([short, match])

    return pairs


# ---------------------------------------------------------------------------
# Structure key
# ---------------------------------------------------------------------------

def build_structure_key(order_id: str | None, legs: list[Leg]) -> str:
    if len(legs) <= 1:
        return SINGLE
    tokens = "/".join(_leg_token(l) for l in sorted(legs, key=_sort_key))
    return f"{order_id}-{tokens}" if order_id else tokens


def _leg_token(leg: Leg) -> str:
    side = "S" if leg.quantity < 0 else "L"
    cp = "C" if leg.contract_type == "CALL" else "P"
    quantity = abs(int(leg.quantity))
    return (
        f"{leg.expiration:%Y%m%d}{leg.underlying}{quantity}{side}{cp}{_format_strike(leg.strike)}"
    )


def _format_strike(strike: Decimal) -> str:
    # normalize() drops trailing zeros but can yield exponent form (650 -> 6.5E+2),
    # so render through "f" to force plain notation.
    return format(strike.normalize(), "f")


def _sort_key(leg: Leg) -> tuple:
    return (leg.expiration, leg.strike, leg.contract_type, 0 if leg.quantity < 0 else 1)
