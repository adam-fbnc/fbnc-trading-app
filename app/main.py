import logging
import logging.config

from fastapi import FastAPI

from app.account.router import router as account_router
from app.market.router import router as market_router
from app.orders.router import router as orders_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Schwab Trading API", version="0.1.0")

app.include_router(account_router)
app.include_router(market_router)
app.include_router(orders_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
