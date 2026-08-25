"""Recovery restart Casino V1 tanpa reroll atau identity replacement."""

from datetime import datetime, timedelta, timezone
import json
import uuid


from .casino import blackjack_action, settle_session, utc_now
from .casino_games import blackjack_allowed_actions
from .database import configure_connection
from .phase5_schema import phase5_capability


async def _record_review(db, *, guild_id, entity_type, entity_id, code, metadata=None):
    now = utc_now()
    await db.execute(
        "INSERT INTO CasinoRecoveryReview "
        "(reviewId,guildId,entityType,entityId,errorCode,status,retryCount,sanitizedMetadataJson,firstDetectedAt,lastAttemptedAt) "
        "VALUES ($1,$2,$3,$4,$5,'OPEN',1,$6,$7,$8) ON CONFLICT(guildId,entityType,entityId,errorCode) DO UPDATE SET "
        "retryCount=CasinoRecoveryReview.retryCount+1,lastAttemptedAt=excluded.lastAttemptedAt",
        (str(uuid.uuid4()), str(guild_id), str(entity_type), str(entity_id), str(code),
         json.dumps(metadata or {}, sort_keys=True, separators=(",", ":")), now, now),
    )


async def recover_phase5_runtime(db_path, *, guild_id=None, now=None, limit=100):
    current = now or datetime.now(timezone.utc)
    cutoff = (current - timedelta(minutes=10)).isoformat()
    result = {"scanned": 0, "settled": 0, "active": 0, "reviewRequired": 0,
              "blackjackAutoStand": 0, "outboxPending": 0}
    async with _pool.acquire() as db:
        
        if not await phase5_capability(db):
            return {**result, "schemaUnavailable": True}
        query = (
            "SELECT s.sessionId,s.guildId,s.userId,s.gameType,s.status,s.stateJson,s.createdAt "
            "FROM CasinoSession s WHERE s.status IN ('RESERVED','ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED')"
        )
        params = []
        if guild_id is not None:
            query += " AND s.guildId=$1"
            params.append(str(guild_id))
        query += " ORDER BY s.createdAt LIMIT $2"
        params.append(int(limit))
        rows = await db.fetch(query, tuple(params))
        rows = await db.fetch("SELECT COUNT(*) FROM CasinoNotificationOutbox WHERE status IN ('PENDING','FAILED')") as cursor:
            result["outboxPending"] = int((await cursor.fetchone())[0])
    for session_id, row_guild, user_id, game, status, state_raw, created_at in rows:
        result["scanned"] += 1
        if status == "REVIEW_REQUIRED":
            result["reviewRequired"] += 1
            continue
        if game == "BLACKJACK" and status == "ACTIVE":
            if created_at > cutoff:
                result["active"] += 1
                continue
            state = json.loads(state_raw)
            action_index = 0
            while state.get("state") == "PLAYER_TURN":
                response = await blackjack_action(
                    db_path, session_id=session_id, user_id=user_id, action="STAND",
                    action_request_id=f"recovery-timeout:{session_id}:{action_index}", now=current.isoformat(),
                )
                action_index += 1
                if not response.ok:
                    async with _pool.acquire() as db:
                        
                        async with db.transaction():
                        await _record_review(db, guild_id=row_guild, entity_type="SESSION",
                                             entity_id=session_id, code=response.code)
                        await db.execute(
                            "UPDATE CasinoSession SET status='REVIEW_REQUIRED',lastErrorCode=$1,lastAttemptedAt=$2 "
                            "WHERE sessionId=? AND status NOT IN ('COMMITTED','VOID')",
                            (response.code, current.isoformat(), session_id),
                        )
                        await db.execute(
                            "UPDATE CasinoSettlement SET status='REVIEW_REQUIRED' WHERE sessionId=$1 AND status='PENDING'",
                            (session_id,),
                        )
                        await db.execute(
                            "UPDATE CasinoBankrollReservation SET status='REVIEW_REQUIRED' WHERE sessionId=$1 AND status='ACTIVE'",
                            (session_id,),
                        )
                        await db.commit()
                    result["reviewRequired"] += 1
                    break
                if response.code == "committed":
                    result["settled"] += 1
                    result["blackjackAutoStand"] += 1
                    break
                async with _pool.acquire() as db:
                    
                    async with db.execute("SELECT stateJson FROM CasinoSession WHERE sessionId=$1", session_id) as cursor:
                        state = json.loads((await cursor.fetchone())[0])
            continue
        response = await settle_session(db_path, session_id=session_id)
        if response.ok and response.code == "committed":
            result["settled"] += 1
        elif response.code == "active":
            result["active"] += 1
        else:
            async with _pool.acquire() as db:
                
                async with db.transaction():
                await _record_review(
                    db, guild_id=row_guild, entity_type="SESSION", entity_id=session_id,
                    code=response.code, metadata={"game": game},
                )
                await db.execute(
                    "UPDATE CasinoSession SET status='REVIEW_REQUIRED',lastErrorCode=$1,lastAttemptedAt=$2 "
                    "WHERE sessionId=? AND status IN ('RESERVED','ACTIVE','SETTLEMENT_PENDING')",
                    (response.code, current.isoformat(), session_id),
                )
                await db.execute(
                    "UPDATE CasinoSettlement SET status='REVIEW_REQUIRED' WHERE sessionId=$1 AND status='PENDING'",
                    (session_id,),
                )
                await db.execute(
                    "UPDATE CasinoBankrollReservation SET status='REVIEW_REQUIRED' WHERE sessionId=$1 AND status='ACTIVE'",
                    (session_id,),
                )
                await db.commit()
            result["reviewRequired"] += 1
    return result


async def claim_casino_outbox(db_path, *, lease_owner, limit=100, now=None):
    timestamp = now or datetime.now(timezone.utc)
    lease_until = (timestamp + timedelta(minutes=2)).isoformat()
    async with _pool.acquire() as db:
        
        async with db.transaction():
        async with db.execute(
            "SELECT eventId FROM CasinoNotificationOutbox WHERE status IN ('PENDING','FAILED') "
            "AND (leaseExpiresAt IS NULL OR leaseExpiresAt<$1) ORDER BY createdAt LIMIT $2",
            (timestamp.isoformat(), int(limit)),
        ) as cursor:
            ids = [row[0] for row in await cursor.fetchall()]
        for event_id in ids:
            await db.execute(
                "UPDATE CasinoNotificationOutbox SET status='CLAIMED',leaseOwner=$1,leaseExpiresAt=$2,attemptCount=attemptCount+1 "
                "WHERE eventId=? AND status IN ('PENDING','FAILED')",
                (str(lease_owner), lease_until, event_id),
            )
        rows = []
        if ids:
            placeholders = ",".join("$1" for _ in ids)
            async with db.execute(
                f"SELECT eventId,eventKey,guildId,userId,sessionId,payloadJson FROM CasinoNotificationOutbox WHERE eventId IN ({placeholders})",
                tuple(ids),
            )
        await db.commit()
    return [dict(zip(("eventId", "eventKey", "guildId", "userId", "sessionId", "payloadJson"), row)) for row in rows]


async def finalize_casino_outbox(db_path, *, event_id, lease_owner, sent, message_id=None, error_code=None):
    async with _pool.acquire() as db:
        
        cursor = await db.execute(
            "UPDATE CasinoNotificationOutbox SET status=$1,messageId=$2,lastErrorCode=$3,sentAt=$4,leaseOwner=NULL,leaseExpiresAt=NULL "
            "WHERE eventId=$2 AND status='CLAIMED' AND leaseOwner=?",
            ("SENT" if sent else "FAILED", str(message_id) if message_id else None,
             str(error_code) if error_code else None, utc_now() if sent else None,
             str(event_id), str(lease_owner)),
        )
        await db.commit()
        return cursor.rowcount == 1
