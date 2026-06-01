import logging
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.account.models import Order
from app.orders.builder import build_order
from app.orders.schemas import (
    OrderRequest, PlaceOrderResponse, PreviewResponse,
    OrderStatusResponse, ReplaceOrderResponse,
)
from app.core.schwab_client import get_schwab_client

logger = logging.getLogger(__name__)


async def place_order(
    account_hash: str,
    req: OrderRequest,
    db: AsyncSession,
) -> PlaceOrderResponse:
    client = get_schwab_client()
    order_dict = build_order(req)

    response = client.place_order(account_hash, order_dict)
    response.raise_for_status()

    # Order ID is in the Location header: .../orders/{orderId}
    location = response.headers.get("Location", "")
    order_id = location.rstrip("/").split("/")[-1]

    await _upsert_order(account_hash, order_id, req.symbol, "WORKING", order_dict, db)
    logger.info("Placed order %s for %s x%s %s", order_id, req.instruction.value, req.quantity, req.symbol)
    return PlaceOrderResponse(order_id=order_id)


async def preview_order(
    account_hash: str,
    req: OrderRequest,
) -> PreviewResponse:
    client = get_schwab_client()
    order_dict = build_order(req)

    response = client.preview_order(account_hash, order_dict)
    response.raise_for_status()
    data = response.json()

    return PreviewResponse(
        estimated_order_value=_d(data.get("orderValue") or data.get("estimatedOrderValue")),
        estimated_commission=_d(data.get("commissionAndFee") or data.get("estimatedCommission")),
        buying_power_effect=_d(data.get("buyingPowerEffect")),
        raw=data,
    )


async def get_order(
    account_hash: str,
    order_id: str,
    db: AsyncSession,
) -> OrderStatusResponse:
    client = get_schwab_client()
    response = client.order_details(account_hash, order_id)
    response.raise_for_status()
    data = response.json()

    legs = data.get("orderLegCollection", [{}])
    instrument = legs[0].get("instrument", {}) if legs else {}

    await _upsert_order(account_hash, order_id, instrument.get("symbol"), data.get("status"), data, db)

    return OrderStatusResponse(
        order_id=str(data.get("orderId", order_id)),
        account_hash=account_hash,
        status=data.get("status"),
        symbol=instrument.get("symbol"),
        asset_type=instrument.get("assetType"),
        order_type=data.get("orderType"),
        quantity=_d(data.get("quantity")),
        filled_quantity=_d(data.get("filledQuantity")),
        remaining_quantity=_d(data.get("remainingQuantity")),
        price=_d(data.get("price")),
        average_fill_price=_d(data.get("orderActivityCollection", [{}])[0].get("executionLegs", [{}])[0].get("price")) if data.get("orderActivityCollection") else None,
        entered_time=_parse_dt(data.get("enteredTime")),
        close_time=_parse_dt(data.get("closeTime")),
    )


async def cancel_order(
    account_hash: str,
    order_id: str,
    db: AsyncSession,
) -> None:
    client = get_schwab_client()
    response = client.cancel_order(account_hash, order_id)
    response.raise_for_status()

    # Update status in DB
    stmt = insert(Order).values(
        order_id=order_id,
        account_hash=account_hash,
        symbol=None,
        asset_type=None,
        order_type=None,
        status="CANCELLED",
        quantity=None,
        price=None,
        entered_time=None,
        close_time=datetime.now(timezone.utc),
        raw={},
    ).on_conflict_do_update(
        index_elements=["order_id"],
        set_={"status": "CANCELLED", "close_time": datetime.now(timezone.utc)},
    )
    await db.execute(stmt)
    await db.commit()
    logger.info("Cancelled order %s", order_id)


async def replace_order(
    account_hash: str,
    order_id: str,
    req: OrderRequest,
    db: AsyncSession,
) -> ReplaceOrderResponse:
    client = get_schwab_client()
    order_dict = build_order(req)

    response = client.replace_order(account_hash, order_id, order_dict)
    response.raise_for_status()

    location = response.headers.get("Location", "")
    new_order_id = location.rstrip("/").split("/")[-1]

    # Mark old order as replaced
    stmt = insert(Order).values(
        order_id=order_id,
        account_hash=account_hash,
        symbol=None, asset_type=None, order_type=None,
        status="REPLACED", quantity=None, price=None,
        entered_time=None, close_time=datetime.now(timezone.utc), raw={},
    ).on_conflict_do_update(
        index_elements=["order_id"],
        set_={"status": "REPLACED", "close_time": datetime.now(timezone.utc)},
    )
    await db.execute(stmt)

    # Persist new order
    await _upsert_order(account_hash, new_order_id, req.symbol, "WORKING", order_dict, db)
    logger.info("Replaced order %s with %s", order_id, new_order_id)
    return ReplaceOrderResponse(new_order_id=new_order_id, old_order_id=order_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _upsert_order(
    account_hash: str,
    order_id: str,
    symbol: str | None,
    status: str | None,
    raw: dict,
    db: AsyncSession,
) -> None:
    stmt = insert(Order).values(
        order_id=order_id,
        account_hash=account_hash,
        symbol=symbol,
        asset_type=raw.get("orderLegCollection", [{}])[0].get("instrument", {}).get("assetType") if isinstance(raw.get("orderLegCollection"), list) else None,
        order_type=raw.get("orderType"),
        status=status,
        quantity=_d(raw.get("quantity")),
        price=_d(raw.get("price")),
        entered_time=_parse_dt(raw.get("enteredTime")),
        close_time=_parse_dt(raw.get("closeTime")),
        raw=raw,
    ).on_conflict_do_update(
        index_elements=["order_id"],
        set_={
            "status": status,
            "close_time": _parse_dt(raw.get("closeTime")),
            "raw": raw,
        },
    )
    await db.execute(stmt)
    await db.commit()


def _d(value) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
