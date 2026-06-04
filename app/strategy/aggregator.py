"""
Pure position-delta aggregation — no DB, no HTTP, no side effects.

Combines an account's equity and option legs into a net position delta per
underlying, plus per-leg detail. Designed to be called identically by the
on-demand API today and by the streaming monitor later.

Delta conventions (Schwab):
  - Equity: delta = 1.0 per share.
  - Call delta is positive (0..1); put delta is negative (-1..0).
  - Position quantity is signed: long > 0, short < 0.
  - Contribution to net delta, in share-equivalents:
        equity:  quantity * 1.0
        option:  quantity * delta * 100   (100 = contract multiplier)
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

CONTRACT_MULTIPLIER = Decimal("100")


@dataclass
class LegInput:
    symbol: str
    asset_type: str                 # "EQUITY", "ETF", "OPTION", ...
    underlying: str
    quantity: Decimal               # signed: long > 0, short < 0
    contract_type: str | None = None    # "CALL" / "PUT" / None for equity
    strike: Decimal | None = None
    expiration: date | None = None
    delta: Decimal | None = None        # per-contract (option) signed; None if unavailable
    delta_source: str = "none"          # "quote", "snapshot", "none"


@dataclass
class LegBreakdown:
    symbol: str
    asset_type: str
    contract_type: str | None
    strike: Decimal | None
    expiration: date | None
    quantity: Decimal
    delta: Decimal | None               # per-contract / per-share
    delta_contribution: Decimal | None  # share-equivalent delta this leg adds
    delta_source: str


@dataclass
class UnderlyingBreakdown:
    underlying: str
    spot: Decimal | None
    shares: Decimal                     # net equity shares
    net_delta: Decimal | None           # share-equivalent; None if any option delta missing
    short_call_delta: Decimal | None    # highest |delta| short-call per-contract delta
    long_put_delta: Decimal | None      # long-put per-contract delta
    legs: list[LegBreakdown] = field(default_factory=list)
    incomplete: bool = False            # True if a needed delta was missing


@dataclass
class AccountDeltaSummary:
    underlyings: list[UnderlyingBreakdown]
    total_net_delta: Decimal | None     # sum of per-underlying net deltas


def aggregate(legs: list[LegInput], spots: dict[str, Decimal | None]) -> AccountDeltaSummary:
    by_underlying: dict[str, list[LegInput]] = {}
    for leg in legs:
        by_underlying.setdefault(leg.underlying, []).append(leg)

    underlyings: list[UnderlyingBreakdown] = []
    total_net = Decimal("0")
    total_complete = True

    for underlying in sorted(by_underlying):
        group = by_underlying[underlying]
        breakdowns: list[LegBreakdown] = []
        shares = Decimal("0")
        net = Decimal("0")
        incomplete = False
        short_call_delta: Decimal | None = None
        long_put_delta: Decimal | None = None

        for leg in group:
            if leg.asset_type in ("EQUITY", "ETF", "COLLECTIVE_INVESTMENT", "INDEX"):
                contribution = leg.quantity * Decimal("1")
                shares += leg.quantity
                net += contribution
                breakdowns.append(LegBreakdown(
                    symbol=leg.symbol, asset_type=leg.asset_type, contract_type=None,
                    strike=None, expiration=None, quantity=leg.quantity,
                    delta=Decimal("1"), delta_contribution=contribution, delta_source="equity",
                ))
                continue

            # Option leg
            if leg.delta is None:
                incomplete = True
                contribution = None
            else:
                contribution = leg.quantity * leg.delta * CONTRACT_MULTIPLIER
                net += contribution

            breakdowns.append(LegBreakdown(
                symbol=leg.symbol, asset_type=leg.asset_type, contract_type=leg.contract_type,
                strike=leg.strike, expiration=leg.expiration, quantity=leg.quantity,
                delta=leg.delta, delta_contribution=contribution, delta_source=leg.delta_source,
            ))

            # Surface representative leg deltas for the rule engine
            if leg.delta is not None:
                if leg.contract_type == "CALL" and leg.quantity < 0:
                    if short_call_delta is None or abs(leg.delta) > abs(short_call_delta):
                        short_call_delta = leg.delta
                elif leg.contract_type == "PUT" and leg.quantity > 0:
                    long_put_delta = leg.delta

        net_delta = None if incomplete else net
        if incomplete:
            total_complete = False
        else:
            total_net += net

        underlyings.append(UnderlyingBreakdown(
            underlying=underlying,
            spot=spots.get(underlying),
            shares=shares,
            net_delta=net_delta,
            short_call_delta=short_call_delta,
            long_put_delta=long_put_delta,
            legs=breakdowns,
            incomplete=incomplete,
        ))

    return AccountDeltaSummary(
        underlyings=underlyings,
        total_net_delta=total_net if total_complete else None,
    )
