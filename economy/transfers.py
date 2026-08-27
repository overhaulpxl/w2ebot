from dataclasses import dataclass

import aiosqlite

from .constants import ECONOMY_FEE_BPS, TRANSFER_DAILY_LIMIT_ETM, TRANSFER_MIN_ETM
from .database import configure_connection
from .ledger import AccountDelta, EconomyMutationError, EconomyResult, execute_transaction
from .time_policy import jakarta_date


ALLOWED_USAGE_TYPES = ("TRANSFER_ETM", "EXCHANGE_ETM")


@dataclass(frozen=True)
class UsageSnapshot:
    period_date: str
    submitted_amount: int


async def get_daily_usage(db_path, guild_id, user_id, usage_type, *, now=None):
    if usage_type not in ALLOWED_USAGE_TYPES:
        raise ValueError("usageType tidak valid")
    period = jakarta_date(now)
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        row = await db.fetchrow(
            "SELECT submittedAmount FROM EconomyDailyUsage "
            "WHERE guildId=$1 AND userId=$2 AND periodDate=$3 AND usageType=$4", str(guild_id), str(user_id), period, usage_type),
        )
    return UsageSnapshot(period, int(row[0]) if row else 0)


async def apply_daily_usage(db, context, *, user_id, usage_type, amount, limit):
    if usage_type not in ALLOWED_USAGE_TYPES:
        raise EconomyMutationError("invalid_usage", "Usage ekonomi tidak valid.")
    period = jakarta_date(context.now)
    row = await db.fetchrow(
        "SELECT submittedAmount,version FROM EconomyDailyUsage "
        "WHERE guildId=$1 AND userId=$2 AND periodDate=$3 AND usageType=$4",
        (context.guild_id, str(user_id), period, usage_type),
    )
    before = int(row[0]) if row else 0
    after = before + int(amount)
    if after > int(limit):
        raise EconomyMutationError("daily_limit", "Batas transaksi harian terlampaui.")
    if row:
        cursor = await db.execute(
            "UPDATE EconomyDailyUsage SET submittedAmount=$1,version=version+1,updatedAt=$2 "
            "WHERE guildId=$1 AND userId=$2 AND periodDate=$3 AND usageType=$4 AND version=$5", after, context.now, context.guild_id, str(user_id), period, usage_type, int(row[1]),
        )
        if cursor.rowcount != 1:
            raise EconomyMutationError("stale", "Usage harian berubah saat diproses.")
    else:
        await db.execute(
            "INSERT INTO EconomyDailyUsage "
            "(guildId,userId,periodDate,usageType,submittedAmount,version,createdAt,updatedAt) "
            "VALUES ($1,$2,$3,$4,$5,0,$6,$7)", context.guild_id, str(user_id), period, usage_type, after, context.now, context.now),
        )
    return before, after, period


async def transfer_etm(
    db_path,
    *,
    guild_id,
    sender_id,
    recipient_id,
    amount,
    request_id,
    recipient_is_bot=False,
    now=None,
):
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < TRANSFER_MIN_ETM:
        return EconomyResult(False, "invalid_amount", f"Transfer minimal {TRANSFER_MIN_ETM:,} ETM.")
    if str(sender_id) == str(recipient_id):
        return EconomyResult(False, "self_transfer", "Kamu tidak dapat transfer ke diri sendiri.")
    if recipient_is_bot:
        return EconomyResult(False, "bot_recipient", "Transfer ke akun bot tidak diizinkan.")
    fee = amount * ECONOMY_FEE_BPS // 10_000
    general = fee * 80 // 100
    reserve = fee * 10 // 100
    burn = fee - general - reserve
    received = amount - fee

    async def state_extension(db, context):
        before, after, period = await apply_daily_usage(
            db, context, user_id=sender_id, usage_type="TRANSFER_ETM",
            amount=amount, limit=TRANSFER_DAILY_LIMIT_ETM,
        )
        return {"usage_before": before, "usage_after": after, "period_date": period}

    return await execute_transaction(
        db_path,
        guild_id=guild_id,
        idempotency_key=f"transfer:{guild_id}:{sender_id}:{request_id}",
        operation="PLAYER_TRANSFER_ETM",
        source="PLAYER_TRANSFER",
        actor_id=sender_id,
        reason="player transfer",
        reason_code="player_transfer",
        reference_id=request_id,
        feature="economy",
        deltas=(
            AccountDelta("USER", str(sender_id), "ETM", -amount, str(sender_id),
            AccountDelta("USER", str(recipient_id), "ETM", received, str(recipient_id),
            AccountDelta("SYSTEM", "ETM_GENERAL", "ETM", general),
            AccountDelta("SYSTEM", "ETM_RESERVE", "ETM", reserve),
            AccountDelta("SYSTEM", "ETM_BURN", "ETM", burn),
        ),
        success_code="transferred",
        success_message=f"Transfer berhasil. Penerima mendapat {received:,} ETM; fee {fee:,} ETM.",
        before_commit=state_extension,
        now_override=now,
    )
