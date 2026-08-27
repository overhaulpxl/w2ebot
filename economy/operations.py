"""Reservasi outcome acak Phase 3 yang idempotent."""

import json
import uuid

import aiosqlite

from .database import configure_connection
from .time_policy import utc_iso


async def reserve_operation(db_path, *, guild_id, user_id, operation_type, reservation_key,
                            source_resource_id, outcome, now=None):
    timestamp = utc_iso(now)
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                "SELECT operationId,status,outcomeJson FROM RpgOperation "
                "WHERE guildId=? AND reservationKey=? "
                "AND status IN ('RESERVED','AWAITING_FUNDS','REVIEW_REQUIRED')",
                (str(guild_id), str(reservation_key)),
            ) as cursor:
                existing = await cursor.fetchone()
            if existing:
                await db.rollback()
                return existing[0], existing[1], json.loads(existing[2]), True
            operation_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO RpgOperation "
                "(operationId,guildId,userId,operationType,reservationKey,status,sourceResourceId,outcomeJson,createdAt,updatedAt) "
                "VALUES (?,?,?,?,?,'RESERVED',?,?,?,?)",
                (operation_id, str(guild_id), str(user_id), str(operation_type),
                 str(reservation_key), str(source_resource_id) if source_resource_id else None,
                 json.dumps(outcome, sort_keys=True, separators=(",", ":")), timestamp, timestamp),
            )
            await db.commit()
            return operation_id, "RESERVED", outcome, False
        except aiosqlite.IntegrityError:
            await db.rollback()
            async with db.execute(
                "SELECT operationId,status,outcomeJson FROM RpgOperation "
                "WHERE guildId=? AND reservationKey=? "
                "AND status IN ('RESERVED','AWAITING_FUNDS','REVIEW_REQUIRED')",
                (str(guild_id), str(reservation_key)),
            ) as cursor:
                existing = await cursor.fetchone()
            if existing:
                return existing[0], existing[1], json.loads(existing[2]), True
            raise
        except Exception:
            await db.rollback()
            raise


async def get_operation(db_path, operation_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT operationId,guildId,userId,operationType,reservationKey,status,sourceResourceId,"
            "outcomeJson,resultJson,transactionId,createdAt,updatedAt,settledAt,"
            "retryCount,lastErrorCode,lastAttemptedAt,recoveryReviewJson "
            "FROM RpgOperation WHERE operationId=?", (str(operation_id),),
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    result = dict(row)
    result["outcome"] = json.loads(result.pop("outcomeJson"))
    result["result"] = json.loads(result.pop("resultJson")) if result.get("resultJson") else None
    return result


async def void_operation(db_path, *, operation_id, guild_id, user_id, now=None):
    timestamp = utc_iso(now)
    receipt = json.dumps(
        {"status": "VOID", "reason": "operation_voided"},
        sort_keys=True,
        separators=(",", ":"),
    )
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        cursor = await db.execute(
            "UPDATE RpgOperation SET status='VOID',reservationKey=NULL,resultJson=?,"
            "recoveryReviewJson=CASE WHEN status='REVIEW_REQUIRED' AND recoveryReviewJson='{}' "
            "THEN '{\"resolution\":\"authorized_void\"}' ELSE recoveryReviewJson END,"
            "updatedAt=?,settledAt=? WHERE operationId=? AND guildId=? AND userId=? "
            "AND status IN ('RESERVED','AWAITING_FUNDS','REVIEW_REQUIRED')",
            (receipt, timestamp, timestamp, str(operation_id), str(guild_id), str(user_id)),
        )
        await db.commit()
        return cursor.rowcount == 1


async def record_operation_retry(db_path, operation_id, *, error_code=None, review=None, now=None):
    """Catat metadata recovery tanpa menyentuh outcome atau reservation."""
    timestamp = utc_iso(now)
    review_json = json.dumps(review or {}, sort_keys=True, separators=(",", ":"))
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        cursor = await db.execute(
            "UPDATE RpgOperation SET retryCount=retryCount+1,lastErrorCode=?,"
            "lastAttemptedAt=?,recoveryReviewJson=CASE WHEN ?='{}' THEN recoveryReviewJson ELSE ? END,"
            "updatedAt=? WHERE operationId=? AND status IN "
            "('RESERVED','AWAITING_FUNDS','REVIEW_REQUIRED')",
            (error_code, timestamp, review_json, review_json, timestamp, str(operation_id)),
        )
        await db.commit()
        return cursor.rowcount == 1
