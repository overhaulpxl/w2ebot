from dataclasses import dataclass

import aiosqlite

from .constants import ECONOMY_FEE_BPS
from .database import configure_connection
from .ledger import AccountDelta, EconomyMutationError, EconomyResult, execute_transaction
from .transfers import apply_daily_usage, get_daily_usage


EXCHANGE_MULTIPLE_ETM = 200


@dataclass(frozen=True)
class ExchangeInfo:
    level: int
    daily_limit: int
    used_today: int
    remaining: int
    available: bool


def exchange_limit_for_level(level):
    level = int(level)
    if level < 10:
        return 0
    if level < 20:
        return 250_000
    if level < 40:
        return 500_000
    return 1_000_000


async def get_exchange_info(db_path, guild_id, user_id, *, enabled, now=None):
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            row = await db.fetchrow(
                "SELECT level FROM RpgProfile WHERE guildId=$1 AND userId=$2", str(guild_id), str(user_id),
            )
        level = int(row[0]) if row else 1
        usage = await get_daily_usage(db_path, guild_id, user_id, "EXCHANGE_ETM", now=now)
    except aiosqlite.OperationalError:
        level = 1
        usage = type("Usage", (), {"submitted_amount": 0})()
    limit = exchange_limit_for_level(level)
    used = usage.submitted_amount
    return ExchangeInfo(level, limit, used, max(0, limit - used), bool(enabled and limit > 0))


async def exchange_etm_to_ecy(
    db_path, *, guild_id, user_id, amount, request_id, now=None,
):
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        return EconomyResult(False, "invalid_amount", "Jumlah exchange harus lebih dari nol.")
    if amount % EXCHANGE_MULTIPLE_ETM != 0:
        return EconomyResult(False, "invalid_multiple", "Jumlah exchange wajib kelipatan 200 ETM.")
    fee = amount * ECONOMY_FEE_BPS // 10_000
    convertible = amount - fee
    if convertible % 10 != 0:
        return EconomyResult(False, "invalid_conversion", "Jumlah exchange tidak dapat dikonversi secara bulat.")
    ecy_received = convertible // 10
    general = fee * 80 // 100
    reserve = fee * 10 // 100
    fee_burn = fee - general - reserve
    burn = convertible + fee_burn

    async def state_extension(db, context):
        profile = await db.fetchrow(
            "SELECT level FROM RpgProfile WHERE guildId=$1 AND userId=$2", context.guild_id, str(user_id),
        )
        level = int(profile[0]) if profile else 1
        limit = exchange_limit_for_level(level)
        if limit <= 0:
            raise EconomyMutationError("level_locked", "Exchange terbuka mulai RPG Level 10.")
        before, after, period = await apply_daily_usage(
            db, context, user_id=user_id, usage_type="EXCHANGE_ETM", amount=amount, limit=limit,
        )
        return {
            "level": level, "daily_limit": limit, "usage_before": before,
            "usage_after": after, "period_date": period,
        }

    return await execute_transaction(
        db_path,
        guild_id=guild_id,
        idempotency_key=f"exchange:{guild_id}:{user_id}:{request_id}",
        operation="ETM_TO_ECY_EXCHANGE",
        source="ETERNAL_EXCHANGE",
        actor_id=user_id,
        reason="etm to ecy exchange",
        reason_code="etm_to_ecy",
        reference_id=request_id,
        feature="exchange",
        deltas=(
            AccountDelta("USER", str(user_id), "ETM", -amount, str(user_id)),
            AccountDelta("SYSTEM", "ETM_GENERAL", "ETM", general),
            AccountDelta("SYSTEM", "ETM_RESERVE", "ETM", reserve),
            AccountDelta("SYSTEM", "ETM_BURN", "ETM", burn),
            AccountDelta("SYSTEM", "ECY_ISSUANCE", "ECY", -ecy_received),
            AccountDelta("USER", str(user_id), "ECY", ecy_received, str(user_id)),
        ),
        success_code="exchanged",
        success_message=f"Exchange berhasil. Kamu menerima {ecy_received:,} ECY; fee {fee:,} ETM.",
        before_commit=state_extension,
        now_override=now,
    )
