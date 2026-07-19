"""
Pure position-Greek aggregation — no DB, no HTTP, no side effects.

Combines an account's equity and option legs into net delta, gamma and theta
per underlying, plus per-leg detail. Called identically by the on-demand API
today and by the streaming monitor later.

Conventions (Schwab):
  - Equity: delta = 1.0/share; gamma = theta = 0.
  - Call delta positive (0..1); put delta negative (-1..0).
  - Gamma is positive per contract; theta is negative per contract (decay).
  - Position quantity is signed: long > 0, short < 0.
  - Contribution to a net Greek, in share-equivalents:
        equity delta:  quantity * 1.0
        option greek:  quantity * greek * 100   (100 = contract multiplier)

  Sign intuition for a covered call + protective put:
    short call theta:  (-qty) * (-theta) > 0   -> you COLLECT decay
    long  put  theta:  (+qty) * (-theta) < 0   -> you PAY decay
  so net theta flipping negative means the structure now bleeds time value.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

CONTRACT_MULTIPLIER = Decimal("100")
_EQUITY_TYPES = ("EQUITY", "ETF", "COLLECTIVE_INVESTMENT", "INDEX")


@dataclass
class LegInput:
    symbol: str
    asset_type: str
    underlying: str
    quantity: Decimal                   # signed: long > 0, short < 0
    contract_type: str | None = None    # "CALL" / "PUT" / None for equity
    strike: Decimal | None = None
    expiration: date | None = None
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    delta_source: str = "none"          # provenance of the greeks: quote|stream|none|equity


@dataclass
class LegBreakdown:
    symbol: str
    asset_type: str
    contract_type: str | None
    strike: Decimal | None
    expiration: date | None
    quantity: Decimal
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    delta_contribution: Decimal | None
    gamma_contribution: Decimal | None
    theta_contribution: Decimal | None
    delta_source: str


@dataclass
class UnderlyingBreakdown:
    underlying: str
    spot: Decimal | None
    shares: Decimal
    net_delta: Decimal | None
    net_gamma: Decimal | None
    net_theta: Decimal | None
    short_call_delta: Decimal | None
    short_call_theta: Decimal | None
    long_put_delta: Decimal | None
    long_put_theta: Decimal | None
    legs: list[LegBreakdown] = field(default_factory=list)
    incomplete: bool = False            # True if any needed greek was missing


@dataclass
class AccountGreekSummary:
    underlyings: list[UnderlyingBreakdown]
    total_net_delta: Decimal | None
    total_net_gamma: Decimal | None
    total_net_theta: Decimal | None


# Back-compat alias (older imports referenced AccountDeltaSummary)
AccountDeltaSummary = AccountGreekSummary


def aggregate(legs: list[LegInput], spots: dict[str, Decimal | None]) -> AccountGreekSummary:
    by_underlying: dict[str, list[LegInput]] = {}
    for leg in legs:
        by_underlying.setdefault(leg.underlying, []).append(leg)

    underlyings: list[UnderlyingBreakdown] = []
    tot_delta, tot_gamma, tot_theta = Decimal("0"), Decimal("0"), Decimal("0")
    tot_ok_delta = tot_ok_gamma = tot_ok_theta = True

    for underlying in sorted(by_underlying):
        group = by_underlying[underlying]
        breakdowns: list[LegBreakdown] = []
        shares = Decimal("0")
        sum_delta, sum_gamma, sum_theta = Decimal("0"), Decimal("0"), Decimal("0")
        miss_delta = miss_gamma = miss_theta = False
        short_call_delta = short_call_theta = None
        long_put_delta = long_put_theta = None

        for leg in group:
            if leg.asset_type in _EQUITY_TYPES:
                d_contrib = leg.quantity * Decimal("1")
                shares += leg.quantity
                sum_delta += d_contrib
                sum_gamma += Decimal("0")
                sum_theta += Decimal("0")
                breakdowns.append(LegBreakdown(
                    symbol=leg.symbol, asset_type=leg.asset_type, contract_type=None,
                    strike=None, expiration=None, quantity=leg.quantity,
                    delta=Decimal("1"), gamma=Decimal("0"), theta=Decimal("0"),
                    delta_contribution=d_contrib, gamma_contribution=Decimal("0"),
                    theta_contribution=Decimal("0"), delta_source="equity",
                ))
                continue

            # Option leg — each greek contributes independently; a missing greek
            # only invalidates that one net (not the others).
            d_contrib = g_contrib = t_contrib = None
            if leg.delta is None:
                miss_delta = True
            else:
                d_contrib = leg.quantity * leg.delta * CONTRACT_MULTIPLIER
                sum_delta += d_contrib
            if leg.gamma is None:
                miss_gamma = True
            else:
                g_contrib = leg.quantity * leg.gamma * CONTRACT_MULTIPLIER
                sum_gamma += g_contrib
            if leg.theta is None:
                miss_theta = True
            else:
                t_contrib = leg.quantity * leg.theta * CONTRACT_MULTIPLIER
                sum_theta += t_contrib

            breakdowns.append(LegBreakdown(
                symbol=leg.symbol, asset_type=leg.asset_type, contract_type=leg.contract_type,
                strike=leg.strike, expiration=leg.expiration, quantity=leg.quantity,
                delta=leg.delta, gamma=leg.gamma, theta=leg.theta,
                delta_contribution=d_contrib, gamma_contribution=g_contrib,
                theta_contribution=t_contrib, delta_source=leg.delta_source,
            ))

            # Representative short-call / long-put greeks for the rule engine
            if leg.contract_type == "CALL" and leg.quantity < 0 and leg.delta is not None:
                if short_call_delta is None or abs(leg.delta) > abs(short_call_delta):
                    short_call_delta = leg.delta
                    short_call_theta = leg.theta
            elif leg.contract_type == "PUT" and leg.quantity > 0 and leg.delta is not None:
                long_put_delta = leg.delta
                long_put_theta = leg.theta

        net_delta = None if miss_delta else sum_delta
        net_gamma = None if miss_gamma else sum_gamma
        net_theta = None if miss_theta else sum_theta

        if miss_delta: tot_ok_delta = False
        else: tot_delta += sum_delta
        if miss_gamma: tot_ok_gamma = False
        else: tot_gamma += sum_gamma
        if miss_theta: tot_ok_theta = False
        else: tot_theta += sum_theta

        underlyings.append(UnderlyingBreakdown(
            underlying=underlying, spot=spots.get(underlying), shares=shares,
            net_delta=net_delta, net_gamma=net_gamma, net_theta=net_theta,
            short_call_delta=short_call_delta, short_call_theta=short_call_theta,
            long_put_delta=long_put_delta, long_put_theta=long_put_theta,
            legs=breakdowns, incomplete=(miss_delta or miss_gamma or miss_theta),
        ))

    return AccountGreekSummary(
        underlyings=underlyings,
        total_net_delta=tot_delta if tot_ok_delta else None,
        total_net_gamma=tot_gamma if tot_ok_gamma else None,
        total_net_theta=tot_theta if tot_ok_theta else None,
    )
