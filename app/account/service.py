import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.account.models import Account, AccountSnapshot
from app.core.schwab_client import get_schwab_client

logger = logging.getLogger(__name__)


async def sync_linked_accounts(db: AsyncSession) -> list[Account]:
    client = get_schwab_client()
    response = client.linked_accounts()
    response.raise_for_status()
    data = response.json()

    if not data:
        logger.error("No linked Schwab accounts found.")
        raise RuntimeError("No linked Schwab accounts returned. Check credentials and account linkage.")

    for entry in data:
        account_hash = entry.get("hashValue")
        account_info = entry.get("securitiesAccount", {})

        stmt = insert(Account).values(
            account_hash=account_hash,
            account_number=_mask(account_info.get("accountNumber")),
            account_type=account_info.get("type"),
            raw=entry,
        ).on_conflict_do_update(
            index_elements=["account_hash"],
            set_={
                "account_number": _mask(account_info.get("accountNumber")),
                "account_type": account_info.get("type"),
                "raw": entry,
            },
        )
        await db.execute(stmt)

    await db.commit()
    logger.info("Synced %d linked account(s).", len(data))

    result = await db.execute(select(Account))
    return list(result.scalars().all())


async def list_accounts(db: AsyncSession) -> list[Account]:
    result = await db.execute(select(Account))
    return list(result.scalars().all())


async def get_account_summary(account_hash: str, db: AsyncSession) -> AccountSnapshot:
    client = get_schwab_client()
    response = client.account_details(account_hash, fields="positions")
    response.raise_for_status()
    data = response.json()

    securities = data.get("securitiesAccount", {})
    current = securities.get("currentBalances", {})
    initial = securities.get("initialBalances", {})

    day_pnl = _safe_decimal(current.get("totalMarketValue")) and (
        _safe_decimal(current.get("totalMarketValue")) - _safe_decimal(initial.get("totalMarketValue"))
    )

    snapshot = AccountSnapshot(
        account_hash=account_hash,
        cash_balance=_safe_decimal(current.get("cashBalance") or current.get("availableFunds")),
        equity_value=_safe_decimal(current.get("liquidationValue") or current.get("equity")),
        buying_power=_safe_decimal(current.get("buyingPower") or current.get("availableFundsNonMarginableTrade")),
        long_market_value=_safe_decimal(current.get("longMarketValue")),
        short_market_value=_safe_decimal(current.get("shortMarketValue")),
        day_pnl=day_pnl,
        raw=data,
        snapshot_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    logger.info("Snapshot recorded for account %s", account_hash)
    return snapshot


async def get_latest_snapshot(account_hash: str, db: AsyncSession) -> AccountSnapshot | None:
    result = await db.execute(
        select(AccountSnapshot)
        .where(AccountSnapshot.account_hash == account_hash)
        .order_by(AccountSnapshot.snapshot_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _safe_decimal(value):
    from decimal import Decimal
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None


def _mask(account_number: str | None) -> str | None:
    if not account_number or len(account_number) < 4:
        return account_number
    return "****" + account_number[-4:]
