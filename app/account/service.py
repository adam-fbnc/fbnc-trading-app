import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.account.models import Account, AccountSnapshot, Position, Order, Transaction
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

        # account_number is at the top level of the linked_accounts() response
        account_number = _mask(entry.get("accountNumber"))

        # account_type is not in linked_accounts() — enrich with a details call
        account_type = _fetch_account_type(client, account_hash)

        stmt = insert(Account).values(
            account_hash=account_hash,
            account_number=account_number,
            account_type=account_type,
            raw=entry,
        ).on_conflict_do_update(
            index_elements=["account_hash"],
            set_={
                "account_number": account_number,
                "account_type": account_type,
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


async def get_account_hash_by_alias(account_alias: str, db: AsyncSession) -> str | None:
    """
    Resolve a human-friendly account_alias to its account_hash.

    Returns None if no account has the alias. Raises ValueError if more than
    one account shares the alias (aliases are populated manually and are not
    DB-enforced unique).
    """
    result = await db.execute(
        select(Account).where(Account.account_alias == account_alias)
    )
    accounts = list(result.scalars().all())
    if len(accounts) > 1:
        raise ValueError(f"Multiple accounts share alias '{account_alias}'; aliases must be unique")
    return accounts[0].account_hash if accounts else None


async def get_account_summary(account_hash: str, db: AsyncSession) -> AccountSnapshot:
    client = get_schwab_client()
    response = client.account_details(account_hash, fields="positions")
    response.raise_for_status()
    data = response.json()

    securities = data.get("securitiesAccount", {})
    current = securities.get("currentBalances", {})
    initial = securities.get("initialBalances", {})

    current_mv = _safe_decimal(current.get("totalMarketValue"))
    initial_mv = _safe_decimal(initial.get("totalMarketValue"))
    day_pnl = (current_mv - initial_mv) if current_mv is not None and initial_mv is not None else None

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


async def sync_positions(account_hash: str, db: AsyncSession) -> list[Position]:
    client = get_schwab_client()
    response = client.account_details(account_hash, fields="positions")
    response.raise_for_status()
    data = response.json()

    raw_positions = data.get("securitiesAccount", {}).get("positions", [])

    await db.execute(delete(Position).where(Position.account_hash == account_hash))

    positions = []
    for pos in raw_positions:
        instrument = pos.get("instrument", {})
        market_value = _safe_decimal(pos.get("marketValue"))
        avg_price = _safe_decimal(pos.get("averagePrice"))
        quantity = _safe_decimal(pos.get("longQuantity", 0)) - _safe_decimal(pos.get("shortQuantity", 0))
        cost_basis = _safe_decimal(pos.get("averageLongPrice") or pos.get("averagePrice"))
        unrealized_pnl = (
            (market_value - (quantity * cost_basis))
            if market_value is not None and quantity is not None and cost_basis is not None
            else _safe_decimal(pos.get("currentDayProfitLoss"))
        )

        position = Position(
            account_hash=account_hash,
            symbol=instrument.get("symbol", ""),
            cusip=instrument.get("cusip"),
            asset_type=instrument.get("assetType"),
            quantity=quantity or Decimal("0"),
            average_price=avg_price,
            current_value=market_value,
            unrealized_pnl=unrealized_pnl,
            raw=pos,
            refreshed_at=datetime.now(timezone.utc),
        )
        db.add(position)
        positions.append(position)

    await db.commit()
    logger.info("Synced %d position(s) for account %s", len(positions), account_hash)
    return positions


async def list_positions(account_hash: str, db: AsyncSession) -> list[Position]:
    result = await db.execute(
        select(Position).where(Position.account_hash == account_hash)
    )
    return list(result.scalars().all())


async def sync_orders(
    account_hash: str,
    db: AsyncSession,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    status: str | None = None,
) -> list[Order]:
    client = get_schwab_client()

    now = datetime.now(timezone.utc)
    from_dt = from_date or (now - timedelta(days=30))
    to_dt = to_date or now

    response = client.account_orders(
        account_hash,
        fromEnteredTime=from_dt,
        toEnteredTime=to_dt,
        status=status,
    )
    response.raise_for_status()
    data = response.json()

    for order_data in data:
        order_id = str(order_data.get("orderId", ""))
        legs = order_data.get("orderLegCollection", [{}])
        first_leg = legs[0] if legs else {}
        instrument = first_leg.get("instrument", {})

        stmt = insert(Order).values(
            order_id=order_id,
            account_hash=account_hash,
            symbol=instrument.get("symbol"),
            asset_type=instrument.get("assetType"),
            order_type=order_data.get("orderType"),
            status=order_data.get("status"),
            quantity=_safe_decimal(order_data.get("quantity")),
            price=_safe_decimal(order_data.get("price")),
            entered_time=_parse_dt(order_data.get("enteredTime")),
            close_time=_parse_dt(order_data.get("closeTime")),
            raw=order_data,
        ).on_conflict_do_update(
            index_elements=["order_id"],
            set_={
                "status": order_data.get("status"),
                "close_time": _parse_dt(order_data.get("closeTime")),
                "raw": order_data,
            },
        )
        await db.execute(stmt)

    await db.commit()
    logger.info("Upserted %d order(s) for account %s", len(data), account_hash)

    result = await db.execute(
        select(Order).where(Order.account_hash == account_hash).order_by(Order.entered_time.desc())
    )
    return list(result.scalars().all())


async def list_orders(
    account_hash: str,
    db: AsyncSession,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    status: str | None = None,
) -> list[Order]:
    q = select(Order).where(Order.account_hash == account_hash)
    if from_date:
        q = q.where(Order.entered_time >= from_date)
    if to_date:
        q = q.where(Order.entered_time <= to_date)
    if status:
        q = q.where(Order.status == status)
    result = await db.execute(q.order_by(Order.entered_time.desc()))
    return list(result.scalars().all())


async def sync_transactions(
    account_hash: str,
    db: AsyncSession,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    types: str = "TRADE",
) -> list[Transaction]:
    client = get_schwab_client()

    now = datetime.now(timezone.utc)
    from_dt = from_date or (now - timedelta(days=90))
    to_dt = to_date or now

    response = client.transactions(
        account_hash,
        startDate=from_dt,
        endDate=to_dt,
        types=types,
    )
    response.raise_for_status()
    data = response.json()

    for txn in data:
        transaction_id = str(txn.get("activityId") or txn.get("transactionId", ""))
        transfer_items = txn.get("transferItems", [{}])
        first_item = transfer_items[0] if transfer_items else {}
        instrument = first_item.get("instrument", {})
        fees_detail = txn.get("fees", {})
        total_fees = sum(
            _safe_decimal(v) or Decimal("0")
            for v in fees_detail.values()
            if isinstance(v, (int, float, str))
        )

        stmt = insert(Transaction).values(
            transaction_id=transaction_id,
            account_hash=account_hash,
            transaction_type=txn.get("type"),
            symbol=instrument.get("symbol"),
            cusip=instrument.get("cusip"),
            amount=_safe_decimal(txn.get("netAmount")),
            fees=total_fees if total_fees else None,
            trade_date=_parse_dt(txn.get("tradeDate")),
            settlement_date=_parse_dt(txn.get("settlementDate")),
            raw=txn,
        ).on_conflict_do_update(
            index_elements=["transaction_id"],
            set_={"raw": txn},
        )
        await db.execute(stmt)

    await db.commit()
    logger.info("Upserted %d transaction(s) for account %s", len(data), account_hash)

    result = await db.execute(
        select(Transaction)
        .where(Transaction.account_hash == account_hash)
        .order_by(Transaction.trade_date.desc())
    )
    return list(result.scalars().all())


async def list_transactions(
    account_hash: str,
    db: AsyncSession,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    transaction_type: str | None = None,
) -> list[Transaction]:
    q = select(Transaction).where(Transaction.account_hash == account_hash)
    if from_date:
        q = q.where(Transaction.trade_date >= from_date)
    if to_date:
        q = q.where(Transaction.trade_date <= to_date)
    if transaction_type:
        q = q.where(Transaction.transaction_type == transaction_type)
    result = await db.execute(q.order_by(Transaction.trade_date.desc()))
    return list(result.scalars().all())


def _fetch_account_type(client, account_hash: str) -> str | None:
    """Fetch account type from account_details (not available in linked_accounts)."""
    try:
        resp = client.account_details(account_hash)
        resp.raise_for_status()
        return resp.json().get("securitiesAccount", {}).get("type")
    except Exception as e:
        logger.warning("Could not fetch account type for %s: %s", account_hash, e)
        return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _safe_decimal(value) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None


def _mask(account_number: str | None) -> str | None:
    if not account_number or len(account_number) < 4:
        return account_number
    return "****" + account_number[-4:]
