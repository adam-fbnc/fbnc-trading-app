import logging
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.account.models import Account
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


def _mask(account_number: str | None) -> str | None:
    if not account_number or len(account_number) < 4:
        return account_number
    return "****" + account_number[-4:]
