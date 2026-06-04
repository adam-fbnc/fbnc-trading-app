from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.orders import schemas, service
from app.account import service as account_service
from app.core.database import get_db

router = APIRouter(prefix="/orders", tags=["orders"])


# ---------------------------------------------------------------------------
# By account_hash
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# By account_alias — resolve alias to hash, then delegate to the same services
# ---------------------------------------------------------------------------

@router.post("/by-alias/{account_alias}/place", response_model=schemas.PlaceOrderResponse, status_code=201)
async def place_order_by_alias(
    account_alias: str,
    req: schemas.OrderRequest,
    db: AsyncSession = Depends(get_db),
):
    _validate_price(req)
    account_hash = await _resolve_alias(account_alias, db)
    return await service.place_order(account_hash, req, db)


@router.post("/by-alias/{account_alias}/preview", response_model=schemas.PreviewResponse)
async def preview_order_by_alias(
    account_alias: str,
    req: schemas.OrderRequest,
    db: AsyncSession = Depends(get_db),
):
    _validate_price(req)
    account_hash = await _resolve_alias(account_alias, db)
    return await service.preview_order(account_hash, req)


@router.get("/by-alias/{account_alias}/{order_id}", response_model=schemas.OrderStatusResponse)
async def get_order_by_alias(
    account_alias: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_alias(account_alias, db)
    return await service.get_order(account_hash, order_id, db)


@router.delete("/by-alias/{account_alias}/{order_id}", status_code=200)
async def cancel_order_by_alias(
    account_alias: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
):
    account_hash = await _resolve_alias(account_alias, db)
    await service.cancel_order(account_hash, order_id, db)
    return {"message": f"Order {order_id} cancelled successfully"}


@router.put("/by-alias/{account_alias}/{order_id}", response_model=schemas.ReplaceOrderResponse)
async def replace_order_by_alias(
    account_alias: str,
    order_id: str,
    req: schemas.OrderRequest,
    db: AsyncSession = Depends(get_db),
):
    _validate_price(req)
    account_hash = await _resolve_alias(account_alias, db)
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


async def _resolve_alias(account_alias: str, db: AsyncSession) -> str:
    try:
        account_hash = await account_service.get_account_hash_by_alias(account_alias, db)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if account_hash is None:
        raise HTTPException(status_code=404, detail=f"No account found with alias '{account_alias}'")
    return account_hash
