from dataclasses import dataclass
from datetime import timedelta
import secrets
import uuid

import aiosqlite

from .activity import append_activity_event
from .constants import (
    DAILY_REWARD_ECY,
    DAILY_REWARD_ETM,
    WEEKLY_REWARD_ECY,
    WEEKLY_REWARD_ETM,
    WORK_COOLDOWN_SECONDS,
    WORK_DAILY_LIMIT,
    WORK_REWARD_MAX_ETM,
    WORK_REWARD_MIN_ETM,
    WORK_ROLL_STALE_SECONDS,
)
from .database import configure_connection
from .ledger import AccountDelta, EconomyMutationError, EconomyResult, execute_transaction
from .time_policy import jakarta_date, remaining_seconds, utc_datetime, utc_iso


CLAIM_CONFIG = {
    "DAILY": (DAILY_REWARD_ETM, DAILY_REWARD_ECY, 24 * 60 * 60, 2),
    "WEEKLY": (WEEKLY_REWARD_ETM, WEEKLY_REWARD_ECY, 7 * 24 * 60 * 60, 0),
}


@dataclass(frozen=True)
class RewardRollResult:
    ok: bool
    code: str
    message: str
    roll_id: str | None = None
    amount: int | None = None
    reused: bool = False


async def claim_reward(db_path, *, guild_id, user_id, claim_type, request_id, now=None):
    claim_type = str(claim_type).upper()
    if claim_type not in CLAIM_CONFIG:
        return EconomyResult(False, "invalid_claim", "Jenis claim tidak valid.")
    etm, ecy, cooldown, points = CLAIM_CONFIG[claim_type]

    async def state_extension(db, context):
        async with db.execute(
            "SELECT nextEligibleAt,version FROM EconomyClaimState "
            "WHERE guildId=? AND userId=? AND claimType=?",
            (context.guild_id, str(user_id), claim_type),
        ) as cursor:
            state = await cursor.fetchone()
        if state and state[0]:
            try:
                remaining = remaining_seconds(state[0], context.now)
            except (TypeError, ValueError):
                raise EconomyMutationError("invalid_state", "State cooldown claim tidak valid.")
            if remaining > 0:
                raise EconomyMutationError("cooldown", f"Claim belum tersedia. Tunggu {remaining} detik lagi.")
        next_eligible = utc_iso(utc_datetime(context.now) + timedelta(seconds=cooldown))
        if state:
            cursor = await db.execute(
                "UPDATE EconomyClaimState SET lastClaimAt=?,nextEligibleAt=?,lastTransactionId=?,"
                "version=version+1,updatedAt=? WHERE guildId=? AND userId=? AND claimType=? AND version=?",
                (context.now, next_eligible, context.transaction_id, context.now,
                 context.guild_id, str(user_id), claim_type, int(state[1])),
            )
            if cursor.rowcount != 1:
                raise EconomyMutationError("stale", "Claim berubah saat diproses.")
        else:
            await db.execute(
                "INSERT INTO EconomyClaimState "
                "(guildId,userId,claimType,lastClaimAt,nextEligibleAt,lastTransactionId,version,createdAt,updatedAt) "
                "VALUES (?,?,?,?,?,?,0,?,?)",
                (context.guild_id, str(user_id), claim_type, context.now, next_eligible,
                 context.transaction_id, context.now, context.now),
            )
        await append_activity_event(
            db, guild_id=context.guild_id, user_id=user_id,
            event_type=f"{claim_type}_CLAIM", event_key=f"{claim_type.lower()}:{context.transaction_id}",
            points=points, occurred_at=context.now, transaction_id=context.transaction_id,
            reference_id=request_id,
        )
        return {"claim_type": claim_type, "next_eligible_at": next_eligible}

    return await execute_transaction(
        db_path,
        guild_id=guild_id,
        idempotency_key=f"{claim_type.lower()}:{guild_id}:{user_id}:{request_id}",
        operation=f"{claim_type}_REWARD",
        source=f"{claim_type}_REWARD",
        actor_id=user_id,
        reason=f"{claim_type.lower()} reward",
        reason_code=f"{claim_type.lower()}_reward",
        reference_id=request_id,
        feature="economy",
        deltas=(
            AccountDelta("SYSTEM", "ETM_ISSUANCE", "ETM", -etm),
            AccountDelta("USER", str(user_id), "ETM", etm, str(user_id)),
            AccountDelta("SYSTEM", "ECY_ISSUANCE", "ECY", -ecy),
            AccountDelta("USER", str(user_id), "ECY", ecy, str(user_id)),
        ),
        success_code=f"{claim_type.lower()}_claimed",
        success_message=(
            f"{claim_type.title()} berhasil diklaim: {etm:,} ETM dan {ecy:,} ECY."
        ),
        before_commit=state_extension,
        now_override=now,
    )


async def _ensure_work_state(db, guild_id, user_id, now):
    await db.execute(
        "INSERT OR IGNORE INTO EconomyWorkState "
        "(guildId,userId,periodDate,successCount,lastSuccessAt,pendingRollId,version,createdAt,updatedAt) "
        "VALUES (?,?,NULL,0,NULL,NULL,0,?,?)",
        (str(guild_id), str(user_id), now, now),
    )


async def reserve_work_roll(db_path, *, guild_id, user_id, now=None):
    current = utc_datetime(now)
    now_iso = utc_iso(current)
    today = jakarta_date(current)
    cutoff = current - timedelta(seconds=WORK_ROLL_STALE_SECONDS)
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        try:
            await _ensure_work_state(db, guild_id, user_id, now_iso)
            async with db.execute(
                "SELECT periodDate,successCount,lastSuccessAt,pendingRollId,version "
                "FROM EconomyWorkState WHERE guildId=? AND userId=?",
                (str(guild_id), str(user_id)),
            ) as cursor:
                state = await cursor.fetchone()
            period_date, count, last_success, pending_roll, _ = state
            effective_count = int(count) if period_date == today else 0
            if pending_roll:
                async with db.execute(
                    "SELECT amount,status,createdAt FROM EconomyRewardRoll WHERE rollId=? AND guildId=? AND userId=?",
                    (pending_roll, str(guild_id), str(user_id)),
                ) as cursor:
                    roll = await cursor.fetchone()
                if not roll:
                    raise EconomyMutationError("invalid_state", "Pending Work roll tidak ditemukan.")
                amount, status, created_at = int(roll[0]), roll[1], utc_datetime(roll[2])
                if status == "RESERVED" and created_at <= cutoff:
                    await db.execute(
                        "UPDATE EconomyRewardRoll SET status='VOID',voidedAt=? WHERE rollId=? AND status='RESERVED'",
                        (now_iso, pending_roll),
                    )
                    await db.execute(
                        "UPDATE EconomyWorkState SET pendingRollId=NULL,version=version+1,updatedAt=? "
                        "WHERE guildId=? AND userId=? AND pendingRollId=?",
                        (now_iso, str(guild_id), str(user_id), pending_roll),
                    )
                    await db.commit()
                    return RewardRollResult(False, "roll_expired", "Work roll lama sudah kedaluwarsa dan dibatalkan.")
                if status == "RESERVED":
                    await db.rollback()
                    return RewardRollResult(True, "roll_reused", "Work roll lama dilanjutkan.", pending_roll, amount, True)
                await db.rollback()
                return RewardRollResult(False, "invalid_roll", "Work roll ini tidak dapat digunakan lagi.")
            if last_success:
                remaining = WORK_COOLDOWN_SECONDS - int((current - utc_datetime(last_success)).total_seconds())
                if remaining > 0:
                    await db.rollback()
                    return RewardRollResult(False, "cooldown", f"Work tersedia lagi dalam {remaining} detik.")
            if effective_count >= WORK_DAILY_LIMIT:
                await db.rollback()
                return RewardRollResult(False, "daily_limit", "Batas Work harian sudah tercapai.")
            roll_id = str(uuid.uuid4())
            amount = secrets.randbelow(WORK_REWARD_MAX_ETM - WORK_REWARD_MIN_ETM + 1) + WORK_REWARD_MIN_ETM
            await db.execute(
                "INSERT INTO EconomyRewardRoll "
                "(rollId,guildId,userId,rewardType,currency,amount,status,createdAt) "
                "VALUES (?,?,?,'WORK','ETM',?,'RESERVED',?)",
                (roll_id, str(guild_id), str(user_id), amount, now_iso),
            )
            cursor = await db.execute(
                "UPDATE EconomyWorkState SET pendingRollId=?,version=version+1,updatedAt=? "
                "WHERE guildId=? AND userId=? AND pendingRollId IS NULL",
                (roll_id, now_iso, str(guild_id), str(user_id)),
            )
            if cursor.rowcount != 1:
                raise EconomyMutationError("stale", "Work state berubah saat roll dibuat.")
            await db.commit()
            return RewardRollResult(True, "roll_reserved", "Work reward berhasil disiapkan.", roll_id, amount)
        except EconomyMutationError as exc:
            await db.rollback()
            return RewardRollResult(False, exc.code, exc.message)
        except Exception:
            await db.rollback()
            raise


async def settle_work_roll(db_path, *, guild_id, user_id, roll_id, now=None):
    current = utc_datetime(now)
    cutoff = current - timedelta(seconds=WORK_ROLL_STALE_SECONDS)
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                "SELECT amount,status,createdAt,transactionId FROM EconomyRewardRoll "
                "WHERE rollId=? AND guildId=? AND userId=?",
                (str(roll_id), str(guild_id), str(user_id)),
            ) as cursor:
                roll = await cursor.fetchone()
            if not roll:
                await db.rollback()
                return EconomyResult(False, "not_found", "Work roll tidak ditemukan.")
            amount, status, created_at, transaction_id = int(roll[0]), roll[1], utc_datetime(roll[2]), roll[3]
            if status == "VOID":
                await db.rollback()
                return EconomyResult(False, "void_roll", "Work roll ini sudah dibatalkan.")
            if status == "COMMITTED":
                await db.rollback()
                return EconomyResult(True, "work_paid", "Work reward ini sudah dibayar.", transaction_id, replayed=True)
            if created_at <= cutoff:
                now_iso = utc_iso(current)
                await db.execute(
                    "UPDATE EconomyRewardRoll SET status='VOID',voidedAt=? WHERE rollId=? AND status='RESERVED'",
                    (now_iso, str(roll_id)),
                )
                await db.execute(
                    "UPDATE EconomyWorkState SET pendingRollId=NULL,version=version+1,updatedAt=? "
                    "WHERE guildId=? AND userId=? AND pendingRollId=?",
                    (now_iso, str(guild_id), str(user_id), str(roll_id)),
                )
                await db.commit()
                return EconomyResult(False, "roll_expired", "Work roll sudah kedaluwarsa dan dibatalkan.")
            await db.rollback()
        except Exception:
            await db.rollback()
            raise

    async def state_extension(db, context):
        async with db.execute(
            "SELECT amount,status,createdAt FROM EconomyRewardRoll WHERE rollId=? AND guildId=? AND userId=?",
            (str(roll_id), context.guild_id, str(user_id)),
        ) as cursor:
            latest_roll = await cursor.fetchone()
        if not latest_roll or latest_roll[1] != "RESERVED":
            raise EconomyMutationError("invalid_roll", "Work roll tidak lagi dapat diproses.")
        if utc_datetime(latest_roll[2]) <= utc_datetime(context.now) - timedelta(seconds=WORK_ROLL_STALE_SECONDS):
            raise EconomyMutationError("roll_expired", "Work roll sudah kedaluwarsa.")
        async with db.execute(
            "SELECT periodDate,successCount,lastSuccessAt,pendingRollId,version FROM EconomyWorkState "
            "WHERE guildId=? AND userId=?",
            (context.guild_id, str(user_id)),
        ) as cursor:
            state = await cursor.fetchone()
        if not state or state[3] != str(roll_id):
            raise EconomyMutationError("stale", "Pending Work roll berubah.")
        period_date, count, last_success, _, version = state
        today = jakarta_date(context.now)
        effective_count = int(count) if period_date == today else 0
        if last_success and remaining_seconds(
            utc_iso(utc_datetime(last_success) + timedelta(seconds=WORK_COOLDOWN_SECONDS)), context.now
        ) > 0:
            raise EconomyMutationError("cooldown", "Work masih dalam cooldown.")
        if effective_count >= WORK_DAILY_LIMIT:
            raise EconomyMutationError("daily_limit", "Batas Work harian sudah tercapai.")
        cursor = await db.execute(
            "UPDATE EconomyWorkState SET periodDate=?,successCount=?,lastSuccessAt=?,pendingRollId=NULL,"
            "version=version+1,updatedAt=? WHERE guildId=? AND userId=? AND version=? AND pendingRollId=?",
            (today, effective_count + 1, context.now, context.now, context.guild_id,
             str(user_id), int(version), str(roll_id)),
        )
        if cursor.rowcount != 1:
            raise EconomyMutationError("stale", "Work state berubah saat pembayaran.")
        cursor = await db.execute(
            "UPDATE EconomyRewardRoll SET status='COMMITTED',transactionId=?,settledAt=? "
            "WHERE rollId=? AND status='RESERVED'",
            (context.transaction_id, context.now, str(roll_id)),
        )
        if cursor.rowcount != 1:
            raise EconomyMutationError("stale", "Work roll berubah saat pembayaran.")
        await append_activity_event(
            db, guild_id=context.guild_id, user_id=user_id, event_type="WORK_SUCCESS",
            event_key=f"work:{context.transaction_id}", points=0, metric_value=1,
            occurred_at=context.now,
            transaction_id=context.transaction_id, reference_id=roll_id,
        )
        return {"roll_id": str(roll_id), "reward": amount, "period_date": today}

    return await execute_transaction(
        db_path,
        guild_id=guild_id,
        idempotency_key=f"work:{guild_id}:{user_id}:{roll_id}",
        operation="WORK_REWARD",
        source="WORK_REWARD",
        actor_id=user_id,
        reason="work reward",
        reason_code="work_reward",
        reference_id=roll_id,
        feature="economy",
        deltas=(
            AccountDelta("SYSTEM", "ETM_ISSUANCE", "ETM", -amount),
            AccountDelta("USER", str(user_id), "ETM", amount, str(user_id)),
        ),
        success_code="work_paid",
        success_message=f"Work selesai. Kamu mendapatkan {amount:,} ETM.",
        before_commit=state_extension,
        now_override=current,
    )


async def recover_stale_work_rolls(db_path, *, now=None):
    current = utc_datetime(now)
    cutoff = utc_iso(current - timedelta(seconds=WORK_ROLL_STALE_SECONDS))
    now_iso = utc_iso(current)
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                "SELECT rollId FROM EconomyRewardRoll WHERE status='RESERVED' AND createdAt<=? ORDER BY createdAt",
                (cutoff,),
            ) as cursor:
                roll_ids = [row[0] for row in await cursor.fetchall()]
            voided = 0
            for roll_id in roll_ids:
                cursor = await db.execute(
                    "UPDATE EconomyRewardRoll SET status='VOID',voidedAt=? "
                    "WHERE rollId=? AND status='RESERVED' AND createdAt<=?",
                    (now_iso, roll_id, cutoff),
                )
                if cursor.rowcount != 1:
                    continue
                await db.execute(
                    "UPDATE EconomyWorkState SET pendingRollId=NULL,version=version+1,updatedAt=? "
                    "WHERE pendingRollId=?",
                    (now_iso, roll_id),
                )
                voided += 1
            await db.commit()
            return {"scanned": len(roll_ids), "voided": voided}
        except Exception:
            await db.rollback()
            raise
