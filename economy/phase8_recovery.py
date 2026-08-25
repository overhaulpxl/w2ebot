"""Recovery restart-safe Phase 8 tanpa reroll atau penggantian identitas."""

from datetime import datetime, timedelta, timezone
import json
import uuid


from .database import configure_connection
from .eternal_options import settle_option
from .phase8_schema import phase8_capability
from .phase8_voice import close_voice_segments_on_restart


def _now():
    return datetime.now(timezone.utc).isoformat()


async def recover_phase8(db_path, *, limit=200, now=None):
    report = {"ready": False, "voiceClosed": 0, "voiceAwarded": 0, "optionsInspected": 0,
              "optionsSettled": 0, "optionsPending": 0, "expiredClaims": 0,
              "outboxLeasesReclaimed": 0, "reviewRequired": 0}
    try:
        voice = await close_voice_segments_on_restart(db_path)
        report["voiceClosed"] = voice.get("closed", 0)
        report["voiceAwarded"] = voice.get("awarded", 0)
        async with _pool.acquire() as db:
            
            if not await phase8_capability(db):
                return report
            now = str(now) if now is not None else _now()
            rows = await db.fetch(
                "SELECT positionId FROM EternalOptionPosition WHERE status IN ('ACTIVE','SETTLEMENT_PENDING') "
                "AND expiresAt<=$1 ORDER BY expiresAt LIMIT $2", (now, max(1, min(int(limit), 1000))),
            ) as cursor:
                positions = [row[0] for row in await cursor.fetchall()]
        for position_id in positions:
            report["optionsInspected"] += 1
            result = await settle_option(db_path, position_id, now=now)
            if result.ok:
                report["optionsSettled"] += 1
            elif result.code == "expiry_price_pending":
                report["optionsPending"] += 1
            else:
                report["reviewRequired"] += 1
        async with _pool.acquire() as db:
            
            async with db.transaction():
            expired = await (await db.execute(
                "SELECT g.giveawayId,w.winnerId FROM GiveawayV1 g JOIN GiveawayWinner w "
                "ON w.giveawayId=g.giveawayId AND w.userId=g.currentWinnerId "
                "WHERE g.status='AWAITING_CLAIM' AND w.status='AWAITING_CLAIM' AND w.claimDeadline<=$1",
                (now,),
            )).fetchall()
            for giveaway_id, winner_id in expired:
                await db.execute(
                    "INSERT OR IGNORE INTO Phase8RecoveryReview "
                    "(reviewId,guildId,entityType,entityId,errorCode,status,sanitizedMetadataJson,firstDetectedAt,lastAttemptedAt) "
                    "SELECT $1,guildId,'GIVEAWAY_WINNER',$2,'CLAIM_EXPIRED','OPEN',$3, $4, $5 FROM GiveawayV1 WHERE giveawayId=$6",
                    (str(uuid.uuid4()), winner_id, json.dumps({"giveawayId": giveaway_id}, separators=(",", ":")),
                     now, now, giveaway_id),
                )
                report["expiredClaims"] += 1
            cursor = await db.execute(
                "UPDATE Phase8NotificationOutbox SET status='FAILED',leaseOwner=NULL,leaseExpiresAt=NULL,"
                "attemptCount=attemptCount+1,lastErrorCode='lease_expired' "
                "WHERE status='CLAIMED' AND leaseExpiresAt IS NOT NULL AND leaseExpiresAt<=$1", (now,),
            )
            report["outboxLeasesReclaimed"] = max(0, cursor.rowcount)
            await db.commit()
        report["ready"] = True
        return report
    except aiosqlite.Error:
        return report


async def claim_phase8_outbox(db_path, *, lease_owner, limit=100, now=None):
    timestamp = now or datetime.now(timezone.utc)
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)
    lease_until = (timestamp + timedelta(minutes=2)).isoformat()
    async with _pool.acquire() as db:
        
        async with db.transaction():
        async with db.execute(
            "SELECT outboxId FROM Phase8NotificationOutbox "
            "WHERE status IN ('PENDING','FAILED') "
            "AND (leaseExpiresAt IS NULL OR leaseExpiresAt<$1) "
            "ORDER BY createdAt,outboxId LIMIT $2",
            (timestamp.isoformat(), max(1, min(int(limit), 1000))),
        ) as cursor:
            outbox_ids = [row[0] for row in await cursor.fetchall()]
        for outbox_id in outbox_ids:
            await db.execute(
                "UPDATE Phase8NotificationOutbox SET status='CLAIMED',leaseOwner=$1,leaseExpiresAt=$2,"
                "attemptCount=attemptCount+1,lastErrorCode=NULL "
                "WHERE outboxId=? AND status IN ('PENDING','FAILED')",
                (str(lease_owner), lease_until, outbox_id),
            )
        rows = []
        if outbox_ids:
            placeholders = ",".join("$1" for _ in outbox_ids)
            async with db.execute(
                f"SELECT outboxId,eventKey,guildId,channelId,userId,entityType,entityId,payloadJson "
                f"FROM Phase8NotificationOutbox WHERE outboxId IN ({placeholders}) "
                "AND status='CLAIMED' AND leaseOwner=$1 ORDER BY createdAt,outboxId",
                (*outbox_ids, str(lease_owner)),
            )
        await db.commit()
    columns = ("outboxId", "eventKey", "guildId", "channelId", "userId",
               "entityType", "entityId", "payloadJson")
    return [dict(zip(columns, row)) for row in rows]


async def finalize_phase8_outbox(db_path, *, outbox_id, lease_owner, sent,
                                 message_id=None, error_code=None):
    timestamp = _now()
    async with _pool.acquire() as db:
        
        cursor = await db.execute(
            "UPDATE Phase8NotificationOutbox SET status=$1,messageId=COALESCE($2,messageId),"
            "lastErrorCode=$2,sentAt=$3,leaseOwner=NULL,leaseExpiresAt=NULL "
            "WHERE outboxId=$4 AND status='CLAIMED' AND leaseOwner=?",
            ("SENT" if sent else "FAILED", str(message_id) if message_id else None,
             str(error_code) if error_code else None, timestamp if sent else None,
             str(outbox_id), str(lease_owner)),
        )
        await db.commit()
        return cursor.rowcount == 1
