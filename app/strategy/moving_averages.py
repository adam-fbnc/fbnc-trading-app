"""
Pure moving-average estimators over an ordered series (oldest -> newest).
Each compute_* returns the smoothed value at the final point, or None.

Available types:
  ema  - exponential MA. Simple, predictable lag; default.
  hma  - Hull MA. Very low lag; reacts fast but can overshoot at turns.
  kama - Kaufman Adaptive MA. Smooths in chop, speeds up in trend.

EMA is computed in Decimal; HMA/KAMA use float internally (nested WMAs /
adaptive constants) and return Decimal.
"""
from decimal import Decimal
from math import isqrt

MA_TYPES = ("ema", "hma", "kama")


def compute_ma(values: list, period: int, ma_type: str = "ema"):
    ma_type = (ma_type or "ema").lower()
    if ma_type == "ema":
        return compute_ema(values, period)
    if ma_type == "hma":
        return compute_hma(values, period)
    if ma_type == "kama":
        return compute_kama(values, period)
    raise ValueError(f"Unknown ma_type '{ma_type}'. Use one of {MA_TYPES}.")


def compute_ema(values: list, span: int) -> Decimal | None:
    if not values or span < 1:
        return None
    alpha = Decimal(2) / Decimal(span + 1)
    ema: Decimal | None = None
    for v in values:
        d = Decimal(str(v))
        ema = d if ema is None else (alpha * d + (Decimal(1) - alpha) * ema)
    return ema


def compute_hma(values: list, period: int) -> Decimal | None:
    """
    HMA(n) = WMA( 2*WMA(n/2) - WMA(n), round(sqrt(n)) )
    Needs ~ n + sqrt(n) samples to be valid.
    """
    if period < 2:
        return None
    fvals = [float(v) for v in values]
    n = period
    half = max(1, n // 2)
    sqrt_n = max(1, isqrt(n))
    if len(fvals) < n + sqrt_n:
        return None

    wma_half = _rolling_wma(fvals, half)
    wma_full = _rolling_wma(fvals, n)
    raw = [
        2 * h - f
        for h, f in zip(wma_half, wma_full)
        if h is not None and f is not None
    ]
    if len(raw) < sqrt_n:
        return None
    hma_series = _rolling_wma(raw, sqrt_n)
    last = next((x for x in reversed(hma_series) if x is not None), None)
    return Decimal(str(last)) if last is not None else None


def compute_kama(values: list, period: int, fast: int = 2, slow: int = 30) -> Decimal | None:
    """
    Kaufman Adaptive MA. period = efficiency-ratio lookback.
    SC = (ER*(fast_sc - slow_sc) + slow_sc)^2
    """
    if period < 1:
        return None
    fvals = [float(v) for v in values]
    if len(fvals) < period + 1:
        return None

    fast_sc = 2.0 / (fast + 1)
    slow_sc = 2.0 / (slow + 1)
    kama = fvals[0]
    for i in range(1, len(fvals)):
        if i < period:
            # warm up with the price itself until we have a full ER window
            kama = fvals[i]
            continue
        change = abs(fvals[i] - fvals[i - period])
        volatility = sum(abs(fvals[j] - fvals[j - 1]) for j in range(i - period + 1, i + 1))
        er = (change / volatility) if volatility != 0 else 0.0
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        kama = kama + sc * (fvals[i] - kama)
    return Decimal(str(kama))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rolling_wma(values: list[float], period: int) -> list:
    """Rolling weighted MA (weights 1..period); None until the window fills."""
    out: list = []
    denom = period * (period + 1) / 2
    for i in range(len(values)):
        if i + 1 < period:
            out.append(None)
            continue
        window = values[i - period + 1: i + 1]
        wsum = sum(w * x for w, x in enumerate(window, start=1))
        out.append(wsum / denom)
    return out
