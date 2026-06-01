"""
StreamManager — owns the schwabdev Stream instance and controls its lifecycle.
"""
import logging
import threading

import schwabdev

from app.core.schwab_client import get_schwab_client
from app.streaming.handler import handle_message
from app.streaming.state import stream_state

logger = logging.getLogger(__name__)

_stream: schwabdev.Stream | None = None
_stream_lock = threading.Lock()


def get_stream() -> schwabdev.Stream | None:
    return _stream


def start_stream() -> None:
    global _stream
    with _stream_lock:
        if stream_state.is_running:
            logger.info("Stream already running — skipping start")
            return

        client = get_schwab_client()
        _stream = schwabdev.Stream(client)
        _stream.start(receiver=handle_message, daemon=True)
        stream_state.mark_started()
        logger.info("Stream started")


def stop_stream() -> None:
    global _stream
    with _stream_lock:
        if _stream is not None:
            _stream.stop(clear_subscriptions=True)
            _stream = None
        stream_state.mark_stopped()
        logger.info("Stream stopped")


def subscribe_quotes(symbols: list[str], fields: str = "0,1,2,3,4,5,6,7,8") -> None:
    """Subscribe to Level 1 equity quotes."""
    _require_running()
    keys = ",".join(s.upper() for s in symbols)
    _stream.send(_stream.level_one_equities(keys, fields))
    stream_state.add_subscription("LEVELONE_EQUITIES", symbols)
    logger.info("Subscribed to equity quotes: %s", keys)


def unsubscribe_quotes(symbols: list[str]) -> None:
    _require_running()
    keys = ",".join(s.upper() for s in symbols)
    _stream.send(_stream.level_one_equities(keys, "0", command="UNSUBS"))
    stream_state.remove_subscription("LEVELONE_EQUITIES", symbols)
    logger.info("Unsubscribed from equity quotes: %s", keys)


def subscribe_options(symbols: list[str], fields: str = "0,1,2,3,4,5,6,7,8,9,10,11,12,13") -> None:
    """Subscribe to Level 1 option quotes."""
    _require_running()
    keys = ",".join(s.upper() for s in symbols)
    _stream.send(_stream.level_one_options(keys, fields))
    stream_state.add_subscription("LEVELONE_OPTIONS", symbols)
    logger.info("Subscribed to option quotes: %s", keys)


def unsubscribe_options(symbols: list[str]) -> None:
    _require_running()
    keys = ",".join(s.upper() for s in symbols)
    _stream.send(_stream.level_one_options(keys, "0", command="UNSUBS"))
    stream_state.remove_subscription("LEVELONE_OPTIONS", symbols)


def subscribe_account_activity() -> None:
    """Subscribe to account activity (fills, order updates)."""
    _require_running()
    _stream.send(_stream.account_activity())
    stream_state.add_subscription("ACCT_ACTIVITY", ["Account Activity"])
    logger.info("Subscribed to account activity")


def _require_running() -> None:
    if not stream_state.is_running or _stream is None:
        raise RuntimeError("Stream is not running. Call POST /stream/start first.")
