"""
Background DB worker — drains the handler's queue and writes events to PostgreSQL.
Runs in its own thread so the stream handler never blocks on DB I/O.
"""
import json
import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal

import psycopg2

from app.core.config import settings
from app.streaming.handler import db_write_queue

logger = logging.getLogger(__name__)
_worker_thread: threading.Thread | None = None
_stop_event = threading.Event()


def start_db_worker() -> None:
    global _worker_thread
    _stop_event.clear()
    _worker_thread = threading.Thread(target=_run, daemon=True, name="stream-db-worker")
    _worker_thread.start()
    logger.info("Stream DB worker started")


def stop_db_worker() -> None:
    _stop_event.set()
    logger.info("Stream DB worker stopping")


def _run() -> None:
    # Use a synchronous psycopg2 connection — avoids asyncio complexity in a thread
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = None
    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        cur = conn.cursor()
        while not _stop_event.is_set():
            try:
                event_type, payload = db_write_queue.get(timeout=1.0)
                if event_type != "PNL_ALERT":
                    _persist_event(cur, event_type, payload)
                if event_type == "ACCT_ACTIVITY":
                    _process_account_activity(cur, payload)
                elif event_type == "PNL_ALERT":
                    _process_pnl_alert(cur, payload)
            except Exception:
                pass  # timeout or empty queue — loop again
    except Exception as e:
        logger.error("Stream DB worker fatal error: %s", e)
    finally:
        if conn:
            conn.close()


def _persist_event(cur, event_type: str, payload: dict) -> None:
    cur.execute(
        """
        INSERT INTO stream_events (event_type, payload, received_at)
        VALUES (%s, %s, %s)
        """,
        (event_type, json.dumps(payload), datetime.now(timezone.utc)),
    )


def _process_account_activity(cur, payload: dict) -> None:
    """Parse account activity messages and update the orders table on fills."""
    try:
        msg_type = payload.get("2")           # field 2 = message type
        msg_data_raw = payload.get("3", "{}")  # field 3 = message data JSON string

        if not msg_type or msg_type not in ("OrderFill", "OrderPartialFill", "OrderCancellation"):
            return

        msg_data = json.loads(msg_data_raw) if isinstance(msg_data_raw, str) else msg_data_raw
        order_id = str(msg_data.get("OrderId") or msg_data.get("orderId", ""))
        if not order_id:
            return

        status_map = {
            "OrderFill": "FILLED",
            "OrderPartialFill": "PARTIALLY_FILLED",
            "OrderCancellation": "CANCELLED",
        }
        new_status = status_map.get(msg_type, msg_type)

        cur.execute(
            """
            UPDATE orders
            SET status = %s,
                close_time = CASE WHEN %s IN ('FILLED','CANCELLED') THEN %s ELSE close_time END,
                raw = raw || %s::jsonb
            WHERE order_id = %s
            """,
            (
                new_status,
                new_status,
                datetime.now(timezone.utc),
                json.dumps({"last_activity": payload}),
                order_id,
            ),
        )
        logger.info("Account activity: %s order %s → %s", msg_type, order_id, new_status)
    except Exception as e:
        logger.warning("Failed to process account activity event: %s", e)


def _process_pnl_alert(cur, payload: dict) -> None:
    """Persist a triggered P&L alert: stamp triggered_at, deactivate, and log."""
    try:
        alert_id = payload["alert_id"]
        group_id = payload["group_id"]
        alert_type = payload["alert_type"]
        pnl_pct = float(payload["pnl_pct"])
        symbol = payload["symbol"]
        now = datetime.now(timezone.utc)

        cur.execute(
            """
            UPDATE group_alerts
            SET triggered_at = %s, is_active = false
            WHERE id = %s AND triggered_at IS NULL
            """,
            (now, alert_id),
        )
        logger.warning(
            "P&L ALERT | group=%d alert=%d type=%s pnl=%.2f%% symbol=%s",
            group_id, alert_id, alert_type, pnl_pct, symbol,
        )
    except Exception as e:
        logger.warning("Failed to process PNL_ALERT event: %s", e)
