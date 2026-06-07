"""
Schwab streamer field maps.

Schwab's LEVELONE_* services deliver numeric field keys. These maps translate
them to named fields so the rest of the app reads `delta`/`gamma`/... instead
of "28"/"29". The numbers follow Schwab's published LEVELONE spec (TDA-derived).

NOTE: verify empirically once subscribed — the handler also keeps the raw
numeric fields, and GET /strategy/stream/quote/{symbol} dumps them. If a number
is off, fix it here in one place.
"""

# field number (str) -> name
LEVELONE_OPTIONS_FIELD_MAP: dict[str, str] = {
    "0": "symbol",
    "2": "bid",
    "3": "ask",
    "4": "last",
    "8": "total_volume",
    "9": "open_interest",
    "10": "volatility",
    "28": "delta",
    "29": "gamma",
    "30": "theta",
    "31": "vega",
    "32": "rho",
    "35": "underlying_price",
    "37": "mark",
}

LEVELONE_EQUITIES_FIELD_MAP: dict[str, str] = {
    "0": "symbol",
    "1": "bid",
    "2": "ask",
    "3": "last",
    "8": "total_volume",
}

# Comma-separated field lists to request on subscribe
OPTION_STREAM_FIELDS = ",".join(LEVELONE_OPTIONS_FIELD_MAP.keys())
EQUITY_STREAM_FIELDS = ",".join(LEVELONE_EQUITIES_FIELD_MAP.keys())


def translate(service: str, fields: dict) -> dict:
    """Return a dict with both named greeks/prices (when known) and the raw
    numeric fields preserved (prefixed 'f_') for debugging/verification."""
    if service == "LEVELONE_OPTIONS":
        fmap = LEVELONE_OPTIONS_FIELD_MAP
    elif service == "LEVELONE_EQUITIES":
        fmap = LEVELONE_EQUITIES_FIELD_MAP
    else:
        fmap = {}

    named: dict = {}
    for k, v in fields.items():
        name = fmap.get(str(k))
        if name:
            named[name] = v
        named[f"f_{k}"] = v
    return named
