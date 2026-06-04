from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.strategy import service
from app.strategy.aggregator import AccountDeltaSummary
from app.strategy.schemas import (
    AccountDeltaSummaryResponse, UnderlyingDeltaResponse, LegBreakdownResponse,
)
from app.account import service as account_service
from app.core.database import get_db

router = APIRouter(prefix="/strategy", tags=["strategy"])


@router.get("/{account_hash}/delta-summary", response_model=AccountDeltaSummaryResponse)
async def get_delta_summary(account_hash: str, db: AsyncSession = Depends(get_db)):
    await _assert_account_exists(account_hash, db)
    summary = await service.build_delta_summary(account_hash, db)
    return _to_response(account_hash, summary)


@router.get("/by-alias/{account_alias}/delta-summary", response_model=AccountDeltaSummaryResponse)
async def get_delta_summary_by_alias(account_alias: str, db: AsyncSession = Depends(get_db)):
    account_hash = await _resolve_alias(account_alias, db)
    summary = await service.build_delta_summary(account_hash, db)
    return _to_response(account_hash, summary)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_response(account_hash: str, summary: AccountDeltaSummary) -> AccountDeltaSummaryResponse:
    return AccountDeltaSummaryResponse(
        account_hash=account_hash,
        total_net_delta=summary.total_net_delta,
        underlyings=[
            UnderlyingDeltaResponse(
                underlying=u.underlying,
                spot=u.spot,
                shares=u.shares,
                net_delta=u.net_delta,
                short_call_delta=u.short_call_delta,
                long_put_delta=u.long_put_delta,
                incomplete=u.incomplete,
                legs=[
                    LegBreakdownResponse(
                        symbol=l.symbol, asset_type=l.asset_type, contract_type=l.contract_type,
                        strike=l.strike, expiration=l.expiration, quantity=l.quantity,
                        delta=l.delta, delta_contribution=l.delta_contribution,
                        delta_source=l.delta_source,
                    )
                    for l in u.legs
                ],
            )
            for u in summary.underlyings
        ],
    )


async def _assert_account_exists(account_hash: str, db: AsyncSession) -> None:
    accounts = await account_service.list_accounts(db)
    if not any(a.account_hash == account_hash for a in accounts):
        raise HTTPException(status_code=404, detail="Account not found")


async def _resolve_alias(account_alias: str, db: AsyncSession) -> str:
    try:
        account_hash = await account_service.get_account_hash_by_alias(account_alias, db)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if account_hash is None:
        raise HTTPException(status_code=404, detail=f"No account found with alias '{account_alias}'")
    return account_hash
