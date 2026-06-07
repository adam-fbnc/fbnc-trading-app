import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.account.models import Order, Transaction
from app.pnl.models import GroupAlert, PositionGroup, PositionGroupLeg
from app.pnl.schemas import (
    AlertResponse, CreateGroupRequest, GroupPnLResponse, LegResponse,
)
from app.pnl.state import pnl_state
from app.streaming.state import stream_state

logger = logging.getLogger("app.pnl")

_MULTIPLIER = Decimal("100")
_VALID_ALERT_TYPES = {"PROFIT_TARGET", "STOP_LOSS"}


# ---------------------------------------------------------------------------
# Group CRUD
# ---------------------------------------------------------------------------

async def create_group(account_hash: str, req: CreateGroupRequest, db: AsyncSession) -> PositionGroup:
    if not req.legs:
        raise ValueError("At least one leg is required")

    legs_meta = [_parse_osi(leg.symbol) for leg in req.legs]
    for i, meta in enumerate(legs_meta):
        if meta is None:
            raise ValueError(f"Cannot parse OSI symbol: {req.legs[i].symbol!r}")

    group_type = req.group_type or _recognize_type(req.legs, legs_meta)
    entry_date = req.entry_date or datetime.now(timezone.utc)

    group = PositionGroup(
        account_hash=account_hash,
        underlying=req.underlying.upper(),
        group_type=group_type,
        alias=req.alias,
        status="OPEN",
        entry_date=entry_date,
    )
    db.add(group)
    await db.flush()  # get group.id

    for leg_req, meta in zip(req.legs, legs_meta):
        db.add(PositionGroupLeg(
            group_id=group.id,
            symbol=leg_req.symbol.upper().strip(),
            underlying=meta["underlying"],
            contract_type=meta["contract_type"],
            strike=meta["strike"],
            expiration=meta["expiration"],
            quantity=leg_req.quantity,
            entry_price=abs(leg_req.entry_price),
        ))

    for alert_req in req.alerts:
        _validate_alert_type(alert_req.alert_type)
        db.add(GroupAlert(
            group_id=group.id,
            alert_type=alert_req.alert_type.upper(),
            threshold_pct=alert_req.threshold_pct,
            is_active=True,
        ))

    await db.commit()
    await db.refresh(group)

    pnl_state.register_group(
        group_id=group.id,
        account_hash=account_hash,
        underlying=group.underlying,
        legs=[{"symbol": l.symbol, "quantity": l.quantity, "entry_price": l.entry_price} for l in group.legs],
        alerts=[{"id": a.id, "alert_type": a.alert_type, "threshold_pct": a.threshold_pct} for a in group.alerts],
    )
    logger.info("Created position group %d (%s %s) for %s", group.id, group_type, group.underlying, account_hash)
    return group


async def close_group(group_id: int, db: AsyncSession) -> PositionGroup:
    group = await _get_group_or_raise(group_id, db)
    group.status = "CLOSED"
    await db.commit()
    pnl_state.deregister_group(group_id)
    logger.info("Closed position group %d", group_id)
    return group


async def delete_group(group_id: int, db: AsyncSession) -> None:
    group = await _get_group_or_raise(group_id, db)
    await db.delete(group)
    await db.commit()
    pnl_state.deregister_group(group_id)
    logger.info("Deleted position group %d", group_id)


async def list_groups(
    account_hash: str, db: AsyncSession, status: str | None = None
) -> list[PositionGroup]:
    q = select(PositionGroup).where(PositionGroup.account_hash == account_hash)
    if status:
        q = q.where(PositionGroup.status == status.upper())
    result = await db.execute(q)
    return list(result.scalars().all())


async def add_alert(
    group_id: int, alert_type: str, threshold_pct: Decimal, db: AsyncSession
) -> GroupAlert:
    _validate_alert_type(alert_type)
    await _get_group_or_raise(group_id, db)
    alert = GroupAlert(
        group_id=group_id,
        alert_type=alert_type.upper(),
        threshold_pct=threshold_pct,
        is_active=True,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    pnl_state.add_alert(group_id, alert.id, alert.alert_type, alert.threshold_pct)
    logger.info("Added %s alert (%.1f%%) to group %d", alert_type, threshold_pct, group_id)
    return alert


async def remove_alert(group_id: int, alert_id: int, db: AsyncSession) -> None:
    result = await db.execute(
        select(GroupAlert).where(GroupAlert.id == alert_id, GroupAlert.group_id == group_id)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise ValueError(f"Alert {alert_id} not found in group {group_id}")
    await db.delete(alert)
    await db.commit()
    pnl_state.remove_alert(group_id, alert_id)


# ---------------------------------------------------------------------------
# P&L computation (on-demand, uses stream cache)
# ---------------------------------------------------------------------------

def compute_group_pnl(group: PositionGroup) -> GroupPnLResponse:
    """
    Compute live P&L for a group from the stream cache.
    P&L convention:
      entry_debit = sum(qty * entry_price)  — positive = debit paid, negative = credit received
      current_debit = sum(qty * mark)       — same sign convention
      unrealized_pnl = current_debit - entry_debit
      pnl_pct = unrealized_pnl / |entry_debit| * 100
    """
    entry_debit = sum(leg.quantity * leg.entry_price for leg in group.legs)

    legs_resp: list[LegResponse] = []
    current_debit = Decimal("0")
    incomplete = False
    net_delta = net_gamma = net_theta = net_vega = Decimal("0")

    for leg in group.legs:
        cache = stream_state.get_quote(leg.symbol)
        mark = _d(cache.get("mark")) if cache else None
        leg_pnl = (mark - leg.entry_price) * leg.quantity if mark is not None else None

        if mark is None:
            incomplete = True
        else:
            current_debit += leg.quantity * mark

        if cache:
            mult = leg.quantity * _MULTIPLIER
            if (v := _d(cache.get("delta"))) is not None:
                net_delta += v * mult
            if (v := _d(cache.get("gamma"))) is not None:
                net_gamma += v * mult
            if (v := _d(cache.get("theta"))) is not None:
                net_theta += v * mult
            if (v := _d(cache.get("vega"))) is not None:
                net_vega += v * mult

        legs_resp.append(LegResponse(
            id=leg.id,
            symbol=leg.symbol,
            underlying=leg.underlying,
            contract_type=leg.contract_type,
            strike=leg.strike,
            expiration=leg.expiration,
            quantity=leg.quantity,
            entry_price=leg.entry_price,
            current_mark=mark,
            leg_pnl=leg_pnl,
        ))

    unrealized_pnl = (current_debit - entry_debit) if not incomplete else None
    pnl_pct = None
    if unrealized_pnl is not None and entry_debit != 0:
        pnl_pct = (unrealized_pnl / abs(entry_debit) * Decimal("100")).quantize(Decimal("0.01"))

    return GroupPnLResponse(
        group_id=group.id,
        account_hash=group.account_hash,
        underlying=group.underlying,
        group_type=group.group_type,
        alias=group.alias,
        status=group.status,
        entry_date=group.entry_date,
        entry_debit=entry_debit,
        current_debit=current_debit if not incomplete else None,
        unrealized_pnl=unrealized_pnl,
        pnl_pct=pnl_pct,
        net_delta=net_delta,
        net_gamma=net_gamma,
        net_theta=net_theta,
        net_vega=net_vega,
        incomplete=incomplete,
        legs=legs_resp,
        alerts=[
            AlertResponse(
                id=a.id,
                alert_type=a.alert_type,
                threshold_pct=a.threshold_pct,
                is_active=a.is_active,
                triggered_at=a.triggered_at,
            )
            for a in group.alerts
        ],
    )


# ---------------------------------------------------------------------------
# Stream-tick alert check (called from stream handler thread — no DB, no async)
# ---------------------------------------------------------------------------

def check_alerts_for_symbol(symbol: str) -> list[tuple[int, int, str, Decimal]]:
    """
    Called on every LEVELONE_OPTIONS tick. Returns (group_id, alert_id, alert_type, pnl_pct)
    for any alerts whose threshold is newly crossed. Sets in-memory triggered flag to
    prevent duplicate events on subsequent ticks. Thread-safe, no DB I/O.
    """
    triggered: list[tuple[int, int, str, Decimal]] = []

    for group_id in pnl_state.get_groups_for_symbol(symbol):
        state = pnl_state.get_group_state(group_id)
        if state is None or not state.alerts:
            continue

        entry_debit = sum(l.quantity * l.entry_price for l in state.legs)
        if entry_debit == 0:
            continue

        current_debit = Decimal("0")
        for leg in state.legs:
            cache = stream_state.get_quote(leg.symbol)
            mark = _d(cache.get("mark")) if cache else None
            if mark is None:
                current_debit = None
                break
            current_debit += leg.quantity * mark

        if current_debit is None:
            continue  # incomplete — skip until all legs are cached

        pnl_pct = (current_debit - entry_debit) / abs(entry_debit) * Decimal("100")

        for alert in state.alerts:
            if alert.triggered:
                continue
            hit = (
                alert.alert_type == "PROFIT_TARGET" and pnl_pct >= alert.threshold_pct
            ) or (
                alert.alert_type == "STOP_LOSS" and pnl_pct <= -alert.threshold_pct
            )
            if hit:
                pnl_state.mark_alert_triggered(group_id, alert.alert_id)
                triggered.append((group_id, alert.alert_id, alert.alert_type, pnl_pct))

    return triggered


# ---------------------------------------------------------------------------
# Auto-detect groups from filled Schwab orders
# ---------------------------------------------------------------------------

async def auto_detect_groups(account_hash: str, db: AsyncSession) -> list[dict]:
    """
    Scan filled orders for multi-leg option positions and propose groups.
    Entry prices are pulled from transaction history where available.
    """
    orders_result = await db.execute(
        select(Order).where(Order.account_hash == account_hash, Order.status == "FILLED")
    )
    orders = list(orders_result.scalars().all())

    txn_result = await db.execute(
        select(Transaction).where(Transaction.account_hash == account_hash)
    )
    txns_by_symbol: dict[str, list[Transaction]] = {}
    for t in txn_result.scalars().all():
        key = (t.symbol or "").upper().strip()
        if key:
            txns_by_symbol.setdefault(key, []).append(t)

    proposed: list[dict] = []
    seen_order_ids: set[str] = set()

    for order in orders:
        raw = order.raw or {}
        order_id = str(order.order_id)
        if order_id in seen_order_ids:
            continue

        leg_collection = raw.get("orderLegCollection", [])
        if len(leg_collection) < 2:
            continue
        if not all(l.get("orderLegType") == "OPTION" for l in leg_collection):
            continue

        legs: list[dict] = []
        underlying: str | None = None
        valid = True

        for leg_raw in leg_collection:
            instrument = leg_raw.get("instrument", {})
            symbol = (instrument.get("symbol") or "").upper().strip()
            meta = _parse_osi(symbol)
            if meta is None:
                valid = False
                break
            underlying = underlying or meta["underlying"]
            instruction = leg_raw.get("instruction", "")
            raw_qty = Decimal(str(leg_raw.get("quantity", 1)))
            quantity = -raw_qty if "SELL" in instruction else raw_qty
            entry_price = _find_fill_price(symbol, order, txns_by_symbol.get(symbol, []))
            legs.append({
                "symbol": symbol,
                "underlying": meta["underlying"],
                "contract_type": meta["contract_type"],
                "strike": meta["strike"],
                "expiration": meta["expiration"],
                "quantity": quantity,
                "entry_price": entry_price,
            })

        if not valid or not legs or not underlying:
            continue

        class _L:
            def __init__(self, d: dict):
                self.symbol = d["symbol"]
                self.quantity = d["quantity"]

        group_type = _recognize_type([_L(l) for l in legs], [_parse_osi(l["symbol"]) for l in legs])
        seen_order_ids.add(order_id)
        proposed.append({
            "order_id": order_id,
            "underlying": underlying,
            "group_type": group_type,
            "entry_date": order.entered_time or datetime.now(timezone.utc),
            "legs": legs,
        })

    logger.info("Auto-detected %d candidate group(s) for %s", len(proposed), account_hash)
    return proposed


def _find_fill_price(symbol: str, order: Order, txns: list[Transaction]) -> Decimal | None:
    """Best-effort per-contract fill price from transaction history."""
    for txn in txns:
        items = (txn.raw or {}).get("transferItems", [])
        for item in items:
            item_symbol = (item.get("instrument", {}).get("symbol") or "").upper().strip()
            if item_symbol == symbol:
                price = _d(item.get("price"))
                if price is not None and price > 0:
                    return price
        # Fallback: derive from transaction amount + quantity
        raw_qty = abs(_d((txn.raw or {}).get("transferItems", [{}])[0].get("amount", None)) or Decimal("0"))
        if txn.amount is not None and raw_qty > 0:
            return abs(txn.amount / raw_qty / _MULTIPLIER)

    # Last resort: net order price divided by leg count
    net_price = _d((order.raw or {}).get("price"))
    leg_count = len((order.raw or {}).get("orderLegCollection", [])) or 1
    if net_price is not None:
        return abs(net_price / leg_count)

    return None


# ---------------------------------------------------------------------------
# Startup: restore open groups into in-memory state
# ---------------------------------------------------------------------------

async def load_open_groups(db: AsyncSession) -> int:
    """Called at app startup to rebuild the in-memory index from DB."""
    result = await db.execute(select(PositionGroup).where(PositionGroup.status == "OPEN"))
    groups = list(result.scalars().all())
    for group in groups:
        pnl_state.register_group(
            group_id=group.id,
            account_hash=group.account_hash,
            underlying=group.underlying,
            legs=[
                {"symbol": l.symbol, "quantity": l.quantity, "entry_price": l.entry_price}
                for l in group.legs
            ],
            alerts=[
                {"id": a.id, "alert_type": a.alert_type, "threshold_pct": a.threshold_pct}
                for a in group.alerts
                if a.is_active and a.triggered_at is None
            ],
        )
    logger.info("Loaded %d open position group(s) into PnL state", len(groups))
    return len(groups)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_group_or_raise(group_id: int, db: AsyncSession) -> PositionGroup:
    result = await db.execute(select(PositionGroup).where(PositionGroup.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise ValueError(f"Position group {group_id} not found")
    return group


def _validate_alert_type(alert_type: str) -> None:
    if alert_type.upper() not in _VALID_ALERT_TYPES:
        raise ValueError(f"alert_type must be one of {_VALID_ALERT_TYPES}, got: {alert_type!r}")


def _parse_osi(symbol: str) -> dict | None:
    """Parse OSI option symbol (e.g. 'NVDA  260620C00130000') into metadata."""
    s = symbol.strip()
    if len(s) < 15 or s[-9] not in ("C", "P"):
        return None
    try:
        strike = Decimal(s[-8:]) / Decimal("1000")
        cp = s[-9]
        yymmdd = s[-15:-9]
        root = s[:-15].strip()
        expiration = date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))
    except (ValueError, ArithmeticError):
        return None
    if not root:
        return None
    return {
        "underlying": root,
        "contract_type": "CALL" if cp == "C" else "PUT",
        "strike": strike,
        "expiration": expiration,
    }


def _recognize_type(legs: list, legs_meta: list[dict | None]) -> str:
    """Best-effort spread type label from leg count and call/put/long/short breakdown."""
    calls = [l for l, m in zip(legs, legs_meta) if m and m["contract_type"] == "CALL"]
    puts = [l for l, m in zip(legs, legs_meta) if m and m["contract_type"] == "PUT"]
    longs = [l for l in legs if l.quantity > 0]
    shorts = [l for l in legs if l.quantity < 0]
    n = len(legs)

    if n == 2:
        if len(calls) == 2 and len(longs) == 1 and len(shorts) == 1:
            return "CALL_SPREAD"
        if len(puts) == 2 and len(longs) == 1 and len(shorts) == 1:
            return "PUT_SPREAD"
        if len(calls) == 1 and len(puts) == 1:
            return "RISK_REVERSAL"
    if n == 3:
        if len(calls) == 3:
            return "CALL_BACKSPREAD" if len(longs) > len(shorts) else "CALL_RATIO"
        if len(puts) == 3:
            return "PUT_BACKSPREAD" if len(longs) > len(shorts) else "PUT_RATIO"
    if n == 4:
        if len(calls) == 2 and len(puts) == 2:
            return "IRON_CONDOR"
        if len(calls) == 4:
            return "CALL_BUTTERFLY"
        if len(puts) == 4:
            return "PUT_BUTTERFLY"

    return "CUSTOM"


def _d(value) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None
