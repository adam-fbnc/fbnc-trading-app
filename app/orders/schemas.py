from decimal import Decimal
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class AssetType(str, Enum):
    equity = "EQUITY"
    option = "OPTION"
    etf = "ETF"


class Instruction(str, Enum):
    buy = "BUY"
    sell = "SELL"
    buy_to_open = "BUY_TO_OPEN"
    buy_to_close = "BUY_TO_CLOSE"
    sell_to_open = "SELL_TO_OPEN"
    sell_to_close = "SELL_TO_CLOSE"


class OrderType(str, Enum):
    market = "MARKET"
    limit = "LIMIT"
    stop = "STOP"
    stop_limit = "STOP_LIMIT"
    trailing_stop = "TRAILING_STOP"


class Session(str, Enum):
    normal = "NORMAL"
    am = "AM"
    pm = "PM"
    seamless = "SEAMLESS"


class Duration(str, Enum):
    day = "DAY"
    good_till_cancel = "GOOD_TILL_CANCEL"
    fill_or_kill = "FILL_OR_KILL"


class OrderRequest(BaseModel):
    symbol: str
    asset_type: AssetType = AssetType.equity
    instruction: Instruction = Instruction.buy
    quantity: Decimal = Field(gt=0)
    order_type: OrderType = OrderType.limit
    price: Decimal | None = Field(default=None, description="Required for LIMIT and STOP_LIMIT orders")
    stop_price: Decimal | None = None
    duration: Duration = Duration.day
    session: Session = Session.normal


class PlaceOrderResponse(BaseModel):
    order_id: str
    message: str = "Order placed successfully"


class PreviewResponse(BaseModel):
    estimated_order_value: Decimal | None
    estimated_commission: Decimal | None
    buying_power_effect: Decimal | None
    raw: dict


class OrderStatusResponse(BaseModel):
    order_id: str
    account_hash: str
    status: str | None
    symbol: str | None
    asset_type: str | None
    order_type: str | None
    quantity: Decimal | None
    filled_quantity: Decimal | None
    remaining_quantity: Decimal | None
    price: Decimal | None
    average_fill_price: Decimal | None
    entered_time: datetime | None
    close_time: datetime | None


class ReplaceOrderResponse(BaseModel):
    new_order_id: str
    old_order_id: str
    message: str = "Order replaced successfully"
