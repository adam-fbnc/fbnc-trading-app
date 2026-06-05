"""
Pure EMA helpers — no DB, no side effects.

Exponential moving average over an ordered series (oldest → newest):
    alpha = 2 / (span + 1)
    ema_t = alpha * value_t + (1 - alpha) * ema_{t-1}

Span is in *samples*. With a roughly fixed polling interval, the effective
time window ≈ span × interval. The roll engine evaluates the EMA rather than
the raw delta so a single spike can't trigger a roll.
"""
from decimal import Decimal


def compute_ema(values: list[Decimal | float], span: int) -> Decimal | None:
    """Return the EMA of the final point given the ordered series, or None if empty."""
    if not values or span < 1:
        return None
    alpha = Decimal(2) / Decimal(span + 1)
    ema: Decimal | None = None
    for v in values:
        d = Decimal(str(v))
        ema = d if ema is None else (alpha * d + (Decimal(1) - alpha) * ema)
    return ema
