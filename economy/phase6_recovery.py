"""Restart recovery untuk Crypto Phase 6 tanpa mengganti identitas atau outcome."""

from datetime import datetime, timedelta, timezone
import json
import uuid


from .crypto_market import commit_market_tick, utc_now
from .database import configure_connection
from .phase6_schema import phase6_capability


async def _review_trade(db, row, error_code, now):
    trade_id, guild_id, user_id = row[0], row[1], row[2]
    await db.execute(
        "UPDATE CryptoTrade SET status='REVIEW_REQUIRED',retryCount=retryCount+1,"
        "lastErrorCode=? WHERE tradeId=? AND status='PENDING'",
        (error_code, trade_id),
    )
    await db.execute(
        "INSERT OR IGNORE INTO CryptoRecoveryReview "
        "(reviewId,guildId,entityType,entityId,errorCode,status,sanitizedMetadataJson,firstDetectedAt,lastAttemptedAt) "
        "VALUES ($1,$2,$3,$4,$5,'OPEN',$1,$2,$3)",
        (str(uuid.uuid4()), guild_id, "TRADE", trade_id, error_code,
         json.dumps({"userId": user_id}, sort_keys=True, separators=(",", ":")), now, now),
    )


async def recover_pending_trades(db_path):
    counts = {"committed_receipts_adopted": 0, "review_required": 0}
    async with _pool.acquire() as db:
        
        async with db.transaction():
        if not await phase6_capability(db):
            await db.rollback()
            return counts
        rows = await db.fetch(
            "SELECT c.tradeId,c.guildId,c.userId,c.transactionId,t.status,t.metadataJson,"
            "(SELECT COUNT(*) FROM EconomyLedger l WHERE l.transactionId=c.transactionId),"
            "(SELECT COALESCE(SUM(amount),0) FROM EconomyLedger l WHERE l.transactionId=c.transactionId) "
            "FROM CryptoTrade c LEFT JOIN EconomyTransaction t ON t.transactionId=c.transactionId "
            "WHERE c.status='PENDING' ORDER BY c.createdAt"
        )
        now = utc_now()
        for row in rows:
            transaction_status, metadata_text, ledger_count, ledger_sum = row[4:]
            receipt = None
            if transaction_status == "COMMITTED" and ledger_count and ledger_sum == 0:
                try:
                    receipt = json.loads(metadata_text or "{}").get("receipt")
                except (TypeError, json.JSONDecodeError):
                    receipt = None
            if isinstance(receipt, dict) and receipt.get("tradeId") == row[0]:
                updated = await db.execute(
                    "UPDATE CryptoTrade SET status='COMMITTED',receiptJson=$1,settledAt=$2,"
                    "retryCount=retryCount+1,lastErrorCode=NULL WHERE tradeId=? AND status='PENDING'",
                    (json.dumps(receipt, sort_keys=True, separators=(",", ":")), now, row[0]),
                )
                counts["committed_receipts_adopted"] += int(updated.rowcount == 1)
                continue
            if transaction_status == "PENDING" and not ledger_count:
                error = "mutation_free_pending_requires_review"
            elif transaction_status is None:
                error = "missing_transaction_header"
            else:
                error = "ambiguous_trade_state"
            await _review_trade(db, row, error, now)
            counts["review_required"] += 1
        await db.commit()
    return counts


async def claim_crypto_news_outbox(db_path, *, lease_owner, limit=100, lease_seconds=120):
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    expires = (now_dt + timedelta(seconds=int(lease_seconds))).isoformat()
    async with _pool.acquire() as db:
        
        async with db.transaction():
        if not await phase6_capability(db):
            await db.rollback()
            return []
        await db.execute(
            "UPDATE CryptoNewsOutbox SET status='FAILED',leaseOwner=NULL,leaseExpiresAt=NULL,"
            "lastErrorCode='expired_lease' WHERE status='CLAIMED' AND leaseExpiresAt<$1", (now,),
        )
        rows = await db.fetch(
            "SELECT o.outboxId,o.newsId,o.guildId,n.eventKey,n.symbol,n.previousPriceEcy,"
            "n.currentPriceEcy,n.changeBps,n.newsType FROM CryptoNewsOutbox o "
            "JOIN CryptoNewsEvent n ON n.newsId=o.newsId "
            "WHERE o.status IN ('PENDING','FAILED') ORDER BY o.createdAt LIMIT $1", (int(limit),),
        )
        claimed = []
        for row in rows:
            updated = await db.execute(
                "UPDATE CryptoNewsOutbox SET status='CLAIMED',leaseOwner=$1,leaseExpiresAt=$2,"
                "attemptCount=attemptCount+1 WHERE outboxId=? AND status IN ('PENDING','FAILED')",
                (str(lease_owner), expires, row[0]),
            )
            if updated.rowcount == 1:
                claimed.append({
                    "outboxId": row[0], "newsId": row[1], "guildId": row[2],
                    "eventKey": row[3], "symbol": row[4], "previousPriceEcy": int(row[5]),
                    "currentPriceEcy": int(row[6]), "changeBps": int(row[7]), "newsType": row[8],
                })
        await db.commit()
        return claimed


async def finalize_crypto_news_outbox(db_path, *, outbox_id, lease_owner, sent,
                                      message_id=None, error_code=None, review_required=False):
    async with _pool.acquire() as db:
        
        async with db.transaction():
        status = "SENT" if sent else ("REVIEW_REQUIRED" if review_required else "FAILED")
        updated = await db.execute(
            "UPDATE CryptoNewsOutbox SET status=$1,messageId=$2,lastErrorCode=$3,sentAt=$4,"
            "leaseOwner=NULL,leaseExpiresAt=NULL WHERE outboxId=$1 AND status='CLAIMED' AND leaseOwner=$1",
            (status, str(message_id) if message_id is not None else None,
             None if sent else str(error_code or "delivery_failed"), utc_now() if sent else None,
             str(outbox_id), str(lease_owner)),
        )
        await db.commit()
        return updated.rowcount == 1


async def recover_phase6_runtime(db_path):
    result = {"ticks_committed": 0, "ticks_failed": 0}
    try:
        async with _pool.acquire() as db:
            
            if not await phase6_capability(db):
                return {**result, "schema_ready": False}
            async with db.execute(
                "SELECT tickId FROM CryptoMarketTick WHERE status IN ('RESERVED','REVIEW_REQUIRED') "
                "ORDER BY scheduledAt"
            ) as cursor:
                tick_ids = [row[0] for row in await cursor.fetchall()]
        for tick_id in tick_ids:
            try:
                await commit_market_tick(db_path, tick_id)
                result["ticks_committed"] += 1
            except (RuntimeError, ValueError, aiosqlite.Error):
                result["ticks_failed"] += 1
        result.update(await recover_pending_trades(db_path))
        result["schema_ready"] = True
        return result
    except aiosqlite.OperationalError:
        return {**result, "schema_ready": False}
