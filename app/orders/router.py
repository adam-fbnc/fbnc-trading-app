from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.orders import schemas, service
from app.account import service as account_service
from app.core.database import get_db

router = APIRouter(prefix="/orders", tags=["orders"])

ACCOUNT_IDENTIFIER = Path(
    ...,
    description=(
        "Account hash or account alias identifying the account. "
        "account_hash is checked first; if no account_hash matches, the value "
        "is looked up as an account_alias."
    ),
)


# ---------------------------------------------------------------------------
# By account_identifier (account_hash or account_alias)
# ---------------------------------------------------------------------------

@router.post("/{account_identifier}/place", response_model=schemas.PlaceOrderResponse, status_code=201)
async def place_order(
    req: schemas.OrderRequest,
    account_identifier: str = ACCOUNT_IDENTIFIER,
    db: AsyncSession = Depends(get_db),
):
    _validate_price(req)
    account_hash = await _resolve_account_identifier(account_identifier, db)
    return await service.place_order(account_hash, req, db)


@router.post("/{account_identifier}/preview", response_model=schemas.PreviewResponse)
async def preview_order(
    req: schemas.OrderRequest,
    account_identifier: str = ACCOUNT_IDENTIFIER,
    db: AsyncSession = Depends(get_db),
):
    _validate_price(req)
    account_hash = await _resolve_account_identifier(account_identifier, db)
    return await service.preview_order(account_hash, req)


@router.get("/{account_identifier}/{order_id}", response_model=schemas.OrderStatusResponse)
async def get_order(
    order_id: str,
    account_identifier: str = ACCOUNT_IDENTIFIER,
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    return await service.get_order(account_hash, order_id, db)


@router.delete("/{account_identifier}/{order_id}", status_code=200)
async def cancel_order(
    order_id: str,
    account_identifier: str = ACCOUNT_IDENTIFIER,
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_account_identifier(account_identifier, db)
    await service.cancel_order(account_hash, order_id, db)
    return {"message": f"Order {order_id} cancelled successfully"}


@router.put("/{account_identifier}/{order_id}", response_model=schemas.ReplaceOrderResponse)
async def replace_order(
    order_id: str,
    req: schemas.OrderRequest,
    account_identifier: str = ACCOUNT_IDENTIFIER,
    db: AsyncSession = Depends(get_db),
):
    _validate_price(req)
    account_hash = await _resolve_account_identifier(account_identifier, db)
    return await service.replace_order(account_hash, order_id, req, db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_price(req: schemas.OrderRequest) -> None:
    if req.order_type in (schemas.OrderType.limit, schemas.OrderType.stop_limit) and req.price is None:
        raise HTTPException(
            status_code=400,
            detail=f"price is required for {req.order_type.value} orders",
        )


async def _resolve_account_identifier(account_identifier: str, db: AsyncSession) -> str:
    """Resolve account_identifier to an account_hash, trying account_hash first
    and falling back to account_alias."""
    try:
        account_hash = await account_service.resolve_account_identifier(account_identifier, db)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if account_hash is None:
        raise HTTPException(
            status_code=404,
            detail=f"No account found with hash or alias '{account_identifier}'",
        )
    return account_hash
