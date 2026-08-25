"""Recovery restart-safe untuk operasi dan outbox Mining Phase 7."""

from datetime import datetime, timezone
import json
import uuid


from .database import configure_connection
from .mining import settle_operation
from .phase7_schema import phase7_capability


def _now():
    return datetime.now(timezone.utc).isoformat()


async def recover_phase7(db_path, *, limit=100):
    report = {"inspected": 0, "committed": 0, "reviewRequired": 0,
              "failed": 0, "outboxLeasesReclaimed": 0}
    try:
        async with _pool.acquire() as db:
            
            if not await phase7_capability(db):
                return {**report, "ready": False, "code": "schema_unavailable"}
            async with db.execute(
                "SELECT operationId FROM MiningOperation WHERE status IN ('RESERVED','REVIEW_REQUIRED') "
                "ORDER BY createdAt LIMIT $1", (max(1, min(int(limit), 500)),),
            ) as cursor:
                operation_ids = [row[0] for row in await cursor.fetchall()]
        for operation_id in operation_ids:
            report["inspected"] += 1
            result = await settle_operation(db_path, operation_id, recovery=True)
            if result.ok:
                report["committed"] += 1
            elif result.code == "review_required":
                report["reviewRequired"] += 1
            else:
                report["failed"] += 1
        async with _pool.acquire() as db:
            
            async with db.transaction():
            now = _now()
            cursor = await db.execute(
                "UPDATE MiningNotificationOutbox SET status='FAILED',leaseOwner=NULL,leaseExpiresAt=NULL,"
                "attemptCount=attemptCount+1,lastErrorCode='lease_expired' "
                "WHERE status='CLAIMED' AND leaseExpiresAt IS NOT NULL AND leaseExpiresAt<=$1", (now,),
            )
            report["outboxLeasesReclaimed"] = max(0, cursor.rowcount)
            await db.commit()
        return {**report, "ready": True, "code": "complete"}
    except aiosqlite.Error as exc:
        return {**report, "ready": False, "code": "database_error", "errorType": type(exc).__name__}


async def mark_mining_review(db_path, *, guild_id, entity_type, entity_id, error_code,
                             metadata=None):
    now = _now()
    sanitized = json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    async with _pool.acquire() as db:
        
        async with db.transaction():
        await db.execute(
            "INSERT INTO MiningRecoveryReview "
            "(reviewId,guildId,entityType,entityId,errorCode,status,sanitizedMetadataJson,firstDetectedAt,lastAttemptedAt) "
            "VALUES ($1,$2,$3,$4,$5,'OPEN',$6,$7,$8) ON CONFLICT(guildId,entityType,entityId,errorCode) DO UPDATE SET "
            "lastAttemptedAt=excluded.lastAttemptedAt,sanitizedMetadataJson=excluded.sanitizedMetadataJson",
            (str(uuid.uuid4()), str(guild_id), str(entity_type), str(entity_id), str(error_code),
             sanitized, now, now),
        )
        await db.commit()
