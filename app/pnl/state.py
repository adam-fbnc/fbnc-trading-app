"""
In-memory index of open position groups for fast stream-tick P&L alert checks.
Avoids DB round-trips on every incoming option tick.

Lifecycle:
  - Populated at app startup from DB (via service.load_open_groups).
  - Updated synchronously whenever groups/alerts are created or closed via the API.
  - Read from the stream handler thread — all access is lock-protected.
"""
import threading
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class _LegState:
    symbol: str
    quantity: Decimal
    entry_price: Decimal


@dataclass
class _AlertState:
    alert_id: int
    alert_type: str       # PROFIT_TARGET | STOP_LOSS
    threshold_pct: Decimal
    triggered: bool = False  # in-memory dedup — prevents re-queuing on every tick


@dataclass
class _GroupState:
    group_id: int
    account_hash: str
    underlying: str
    legs: list[_LegState] = field(default_factory=list)
    alerts: list[_AlertState] = field(default_factory=list)


class PnLState:
    def __init__(self):
        self._lock = threading.Lock()
        self._symbol_index: dict[str, set[int]] = {}   # symbol -> {group_id, ...}
        self._groups: dict[int, _GroupState] = {}       # group_id -> state

    def register_group(
        self,
        group_id: int,
        account_hash: str,
        underlying: str,
        legs: list[dict],
        alerts: list[dict],
    ) -> None:
        leg_states = [
            _LegState(l["symbol"].upper(), Decimal(str(l["quantity"])), Decimal(str(l["entry_price"])))
            for l in legs
        ]
        alert_states = [
            _AlertState(a["id"], a["alert_type"], Decimal(str(a["threshold_pct"])))
            for a in alerts
        ]
        state = _GroupState(group_id, account_hash, underlying, leg_states, alert_states)
        with self._lock:
            self._groups[group_id] = state
            for leg in leg_states:
                self._symbol_index.setdefault(leg.symbol, set()).add(group_id)

    def deregister_group(self, group_id: int) -> None:
        with self._lock:
            state = self._groups.pop(group_id, None)
            if state:
                for leg in state.legs:
                    bucket = self._symbol_index.get(leg.symbol)
                    if bucket:
                        bucket.discard(group_id)

    def add_alert(self, group_id: int, alert_id: int, alert_type: str, threshold_pct: Decimal) -> None:
        with self._lock:
            state = self._groups.get(group_id)
            if state:
                state.alerts.append(_AlertState(alert_id, alert_type, threshold_pct))

    def remove_alert(self, group_id: int, alert_id: int) -> None:
        with self._lock:
            state = self._groups.get(group_id)
            if state:
                state.alerts = [a for a in state.alerts if a.alert_id != alert_id]

    def get_groups_for_symbol(self, symbol: str) -> list[int]:
        with self._lock:
            return list(self._symbol_index.get(symbol.upper(), set()))

    def get_group_state(self, group_id: int) -> _GroupState | None:
        with self._lock:
            return self._groups.get(group_id)

    def mark_alert_triggered(self, group_id: int, alert_id: int) -> None:
        with self._lock:
            state = self._groups.get(group_id)
            if state:
                for a in state.alerts:
                    if a.alert_id == alert_id:
                        a.triggered = True


pnl_state = PnLState()
