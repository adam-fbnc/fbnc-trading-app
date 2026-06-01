from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.orders import schemas, service
from app.core.database import get_db

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/{account_hash}/place", response_model=schemas.PlaceOrderResponse, status_code=201)
async def place_order(
    account_hash: str,
    req: schemas.OrderRequest,
    db: AsyncSession = Depends(get_db),
):
    _validate_price(req)
    return await service.place_order(account_hash, req, db)


@router.post("/{account_hash}/preview", response_model=schemas.PreviewResponse)
async def preview_order(
    account_hash: str,
    req: schemas.OrderRequest,
):
    _validate_price(req)
    return await service.preview_order(account_hash, req)


@router.get("/{account_hash}/{order_id}", response_model=schemas.OrderStatusResponse)
async def get_order(
    account_hash: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await service.get_order(account_hash, order_id, db)


@router.delete("/{account_hash}/{order_id}", status_code=200)
async def cancel_order(
    account_hash: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
):
    await service.cancel_order(account_hash, order_id, db)
    return {"message": f"Order {order_id} cancelled successfully"}


@router.put("/{account_hash}/{order_id}", response_model=schemas.ReplaceOrderResponse)
async def replace_order(
    account_hash: str,
    order_id: str,
    req: schemas.OrderRequest,
    db: AsyncSession = Depends(get_db),
):
    _validate_price(req)
    return await service.replace_order(account_hash, order_id, req, db)


def _validate_price(req: schemas.OrderRequest) -> None:
    if req.order_type in (schemas.OrderType.limit, schemas.OrderType.stop_limit) and req.price is None:
        raise HTTPException(
            status_code=400,
            detail=f"price is required for {req.order_type.value} orders",
        )
