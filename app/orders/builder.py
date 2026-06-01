"""
Builds Schwab-compatible order dicts from OrderRequest objects.
Reference: https://developer.schwab.com/products/trader-api--individual-/details/specifications/Retail%20Trader%20API%20Production
"""
from app.orders.schemas import OrderRequest, AssetType


def build_order(req: OrderRequest) -> dict:
    order = {
        "orderType": req.order_type.value,
        "session": req.session.value,
        "duration": req.duration.value,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": req.instruction.value,
                "quantity": float(req.quantity),
                "instrument": _build_instrument(req),
            }
        ],
    }

    if req.price is not None:
        order["price"] = float(req.price)

    if req.stop_price is not None:
        order["stopPrice"] = float(req.stop_price)

    return order


def _build_instrument(req: OrderRequest) -> dict:
    if req.asset_type == AssetType.option:
        return {
            "symbol": req.symbol,
            "assetType": "OPTION",
        }
    return {
        "symbol": req.symbol,
        "assetType": "EQUITY",
    }
