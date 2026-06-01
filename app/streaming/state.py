"""
Global streaming state — shared between the stream thread and FastAPI request handlers.
All mutations go through StreamState methods to keep locking consistent.
"""
import threading
from datetime import datetime, timezone
from typing import Any


class StreamState:
    def __init__(self):
        self._lock = threading.Lock()
        self._running: bool = False
        self._started_at: datetime | None = None
        self._last_message_at: datetime | None = None
        self._subscriptions: dict[str, set[str]] = {}   # service -> set of symbols
        self._quote_cache: dict[str, dict] = {}          # symbol -> latest quote fields

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def mark_started(self) -> None:
        with self._lock:
            self._running = True
            self._started_at = datetime.now(timezone.utc)

    def mark_stopped(self) -> None:
        with self._lock:
            self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def started_at(self) -> datetime | None:
        return self._started_at

    @property
    def last_message_at(self) -> datetime | None:
        return self._last_message_at

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def add_subscription(self, service: str, symbols: list[str]) -> None:
        with self._lock:
            if service not in self._subscriptions:
                self._subscriptions[service] = set()
            self._subscriptions[service].update(s.upper() for s in symbols)

    def remove_subscription(self, service: str, symbols: list[str]) -> None:
        with self._lock:
            if service in self._subscriptions:
                for s in symbols:
                    self._subscriptions[service].discard(s.upper())

    def get_subscriptions(self) -> dict[str, list[str]]:
        with self._lock:
            return {k: sorted(v) for k, v in self._subscriptions.items()}

    # ------------------------------------------------------------------
    # Quote cache
    # ------------------------------------------------------------------

    def update_quote(self, symbol: str, fields: dict) -> None:
        with self._lock:
            self._last_message_at = datetime.now(timezone.utc)
            if symbol not in self._quote_cache:
                self._quote_cache[symbol] = {}
            self._quote_cache[symbol].update(fields)
            self._quote_cache[symbol]["_updated_at"] = datetime.now(timezone.utc).isoformat()

    def get_quote(self, symbol: str) -> dict | None:
        return self._quote_cache.get(symbol.upper())

    def get_all_quotes(self) -> dict[str, dict]:
        return dict(self._quote_cache)

    def touch(self) -> None:
        with self._lock:
            self._last_message_at = datetime.now(timezone.utc)


# Singleton shared across the app
stream_state = StreamState()
