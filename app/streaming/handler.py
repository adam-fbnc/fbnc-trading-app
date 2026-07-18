"""
Message handler — called by the schwabdev Stream thread for every incoming message.
Must be fast and non-blocking; heavy work (DB writes) is deferred via a queue.
"""
import json
import logging
import queue
from typing import Any

from app.streaming.state import stream_state

logger = logging.getLogger(__name__)

# DB write queue: tuples of (event_type, payload_dict)
db_write_queue: queue.Queue = queue.Queue(maxsize=10_000)


def handle_message(message: Any) -> None:
    """Entry point called by schwabdev Stream for every message."""
    try:
        if isinstance(message, str):
            data = json.loads(message)
        elif isinstance(message, dict):
            data = message
        else:
            return

        stream_state.touch()

        for response in data.get("data", []):
            service = response.get("service", "")
            contents = response.get("content", [])
            _route(service, contents)

    except Exception as e:
        logger.warning("Stream handler error: %s", e)


def _route(service: str, contents: list[dict]) -> None:
    if service in ("LEVELONE_EQUITIES", "LEVELONE_OPTIONS"):
        _handle_quotes(service, contents)
    elif service == "ACCT_ACTIVITY":
        _handle_account_activity(contents)
    elif service == "CHART_EQUITY":
        _handle_chart(service, contents)


def _handle_quotes(service: str, contents: list[dict]) -> None:
    from app.streaming.fields import translate
    for item in contents:
        symbol = item.get("key", "")
        if not symbol:
            continue
        raw = {k: v for k, v in item.items() if k != "key"}
        # Map numeric Schwab fields to named greeks/prices (raw kept as f_*).
        stream_state.update_quote(symbol, translate(service, raw))
        if service == "LEVELONE_OPTIONS":
            _check_pnl_alerts(symbol)


def _check_pnl_alerts(symbol: str) -> None:
    """Check P&L thresholds for any groups containing this symbol. Non-blocking."""
    try:
        from app.pnl.service import check_alerts_for_symbol
        triggered = check_alerts_for_symbol(symbol)
        for group_id, alert_id, alert_type, pnl_pct in triggered:
            try:
                db_write_queue.put_nowait(("PNL_ALERT", {
                    "group_id": group_id,
                    "alert_id": alert_id,
                    "alert_type": alert_type,
                    "pnl_pct": str(pnl_pct),
                    "symbol": symbol,
                }))
            except queue.Full:
                logger.warning("DB write queue full — dropping PNL_ALERT for group %d", group_id)
    except Exception as e:
        logger.warning("PnL alert check error for %s: %s", symbol, e)


def _handle_account_activity(contents: list[dict]) -> None:
    for item in contents:
        try:
            db_write_queue.put_nowait(("ACCT_ACTIVITY", item))
        except queue.Full:
            logger.warning("DB write queue full — dropping account activity event")


def _handle_chart(service: str, contents: list[dict]) -> None:
    for item in contents:
        try:
            db_write_queue.put_nowait((service, item))
        except queue.Full:
            pass
