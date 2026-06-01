"""
Pure GEX calculation functions — no DB, no HTTP, no side effects.
Designed to be called identically by FastAPI, Streamlit, or Dash.

Formula:
  Call GEX at strike = +gamma × open_interest × 100 × spot_price
  Put GEX  at strike = -gamma × open_interest × 100 × spot_price
  Net GEX  at strike = call_gex + put_gex

Gamma flip: the strike where cumulative net GEX (sorted by strike) crosses zero.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence


@dataclass
class ContractInput:
    strike: Decimal
    contract_type: str          # "CALL" or "PUT"
    gamma: Decimal | None
    open_interest: int | None


@dataclass
class GEXByStrike:
    strike: Decimal
    call_gex: Decimal
    put_gex: Decimal
    net_gex: Decimal
    call_oi: int
    put_oi: int


@dataclass
class GEXResult:
    symbol: str
    spot_price: Decimal
    strikes: list[GEXByStrike]
    total_gex: Decimal
    gamma_flip: Decimal | None          # strike where net GEX crosses zero
    largest_call_strike: Decimal | None # strike with highest call GEX
    largest_put_strike: Decimal | None  # strike with highest (absolute) put GEX


_MULTIPLIER = Decimal("100")


def calculate_gex(
    symbol: str,
    contracts: Sequence[ContractInput],
    spot_price: Decimal,
) -> GEXResult:
    # Aggregate by strike
    by_strike: dict[Decimal, dict] = {}
    for c in contracts:
        if c.gamma is None or c.open_interest is None:
            continue
        strike = c.strike
        if strike not in by_strike:
            by_strike[strike] = {
                "call_gex": Decimal("0"), "put_gex": Decimal("0"),
                "call_oi": 0, "put_oi": 0,
            }
        gex = c.gamma * Decimal(str(c.open_interest)) * _MULTIPLIER * spot_price
        if c.contract_type == "CALL":
            by_strike[strike]["call_gex"] += gex
            by_strike[strike]["call_oi"] += c.open_interest
        else:
            by_strike[strike]["put_gex"] -= gex       # dealers short put gamma
            by_strike[strike]["put_oi"] += c.open_interest

    strikes = sorted(by_strike.keys())
    rows = [
        GEXByStrike(
            strike=s,
            call_gex=by_strike[s]["call_gex"],
            put_gex=by_strike[s]["put_gex"],
            net_gex=by_strike[s]["call_gex"] + by_strike[s]["put_gex"],
            call_oi=by_strike[s]["call_oi"],
            put_oi=by_strike[s]["put_oi"],
        )
        for s in strikes
    ]

    total_gex = sum(r.net_gex for r in rows)
    gamma_flip = _find_gamma_flip(rows)
    largest_call = max(rows, key=lambda r: r.call_gex, default=None)
    largest_put = min(rows, key=lambda r: r.put_gex, default=None)

    return GEXResult(
        symbol=symbol,
        spot_price=spot_price,
        strikes=rows,
        total_gex=total_gex,
        gamma_flip=gamma_flip,
        largest_call_strike=largest_call.strike if largest_call else None,
        largest_put_strike=largest_put.strike if largest_put else None,
    )


def _find_gamma_flip(rows: list[GEXByStrike]) -> Decimal | None:
    """
    Return the strike where cumulative net GEX transitions from positive to negative
    (or vice versa) as we walk from low to high strike.
    """
    cumulative = Decimal("0")
    prev_cumulative = Decimal("0")
    for i, row in enumerate(rows):
        prev_cumulative = cumulative
        cumulative += row.net_gex
        if i > 0 and (
            (prev_cumulative >= 0 and cumulative < 0) or
            (prev_cumulative <= 0 and cumulative > 0)
        ):
            return row.strike
    return None
