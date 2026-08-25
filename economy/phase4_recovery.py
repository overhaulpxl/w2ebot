"""Recovery fail-closed untuk Eternal Marketplace Phase 4."""

import json
import uuid
from datetime import datetime, timezone


from .database import configure_connection
from .marketplace import (
    _LISTING_ESCROW_COLUMNS,
    _apply_quantity_mutation,
    _sale_receipts,
    mark_purchase_review,
    pending_watch_notifications,
    record_recovery_review,
    settle_pending_return,
    settle_purchase,
    utc_now,
)
from .phase4_schema import phase4_schema_capability


def _expected_ledger(sale):
    return {
        ("USER", str(sale["buyerId"]), str(sale["buyerId"])): -int(sale["grossEtm"]),
        ("USER", str(sale["sellerId"]), str(sale["sellerId"])): int(sale["sellerProceedsEtm"]),
        ("SYSTEM", "ETM_GENERAL", None): int(sale["treasuryEtm"]),
        ("SYSTEM", "ETM_RESERVE", None): int(sale["reserveEtm"]),
        ("SYSTEM", "ETM_BURN", None): int(sale["burnEtm"]),
    }


async def _prove_committed_sale(db, sale_id):
    db.row_factory = aiosqlite.Row
    sale = await db.fetchrow(
        "SELECT s.*,t.status AS transactionStatus,t.guildId AS transactionGuildId,"
        "t.idempotencyKey AS transactionIdempotencyKey,t.operation AS transactionOperation,"
        "t.source AS transactionSource,t.referenceId AS transactionReferenceId,"
        "t.actorId AS transactionActorId,t.metadataJson AS transactionMetadataJson,"
        "l.status AS listingStatus,"
        "l.remainingQuantity AS listingRemaining,l.version AS listingVersion,"
        "e.status AS escrowStatus,e.remainingQuantity AS escrowRemaining,e.version AS escrowVersion,"
        "e.authoritativeOwnerId,ev.quantityMutationId,ev.assetType AS evidenceAssetType,"
        "ev.equipmentInstanceId AS evidenceEquipmentId,ev.stackItemId AS evidenceStackItemId,"
        "ev.catalogVersion AS evidenceCatalogVersion,ev.stackBindingStatus AS evidenceBindingStatus,"
        "ev.quantity AS evidenceQuantity,ev.buyerId AS evidenceBuyerId,ev.sellerId AS evidenceSellerId,"
        "ev.buyerStackBefore,ev.buyerStackAfter,m.expectedOldQuantity,m.newQuantity,m.applied AS mutationApplied "
        "FROM MarketplaceSale s JOIN EconomyTransaction t ON t.transactionId=s.transactionId "
        "JOIN MarketplaceListing l ON l.listingId=s.listingId "
        "JOIN MarketplaceEscrow e ON e.escrowId=s.escrowId AND e.listingId=l.listingId "
        "LEFT JOIN MarketplaceSettlementEvidence ev ON ev.saleId=s.saleId "
        "LEFT JOIN MarketplaceQuantityMutation m ON m.mutationId=ev.quantityMutationId "
        "WHERE s.saleId=?",
        (str(sale_id),),
    )
    if not sale:
        return None, "missing_sale_pair"
    if sale["transactionStatus"] != "COMMITTED":
        return sale, "transaction_not_committed"
    try:
        transaction_metadata = json.loads(sale["transactionMetadataJson"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return sale, "transaction_identity_mismatch"
    extension = transaction_metadata.get("extension")
    balances = transaction_metadata.get("balances")
    transaction_checks = (
        sale["transactionGuildId"] == sale["guildId"],
        sale["transactionIdempotencyKey"] == sale["idempotencyKey"],
        sale["transactionOperation"] == "MARKETPLACE_PURCHASE",
        sale["transactionSource"] == "marketplace",
        sale["transactionReferenceId"] == sale["listingId"],
        sale["transactionActorId"] == sale["buyerId"],
        isinstance(extension, dict),
        extension.get("sale_id") == sale["saleId"] if isinstance(extension, dict) else False,
        extension.get("listing_id") == sale["listingId"] if isinstance(extension, dict) else False,
        transaction_metadata.get("result_code") == "marketplace_purchase_committed",
        isinstance(balances, dict),
    )
    if not all(transaction_checks):
        return sale, "transaction_identity_mismatch"
    if sale["quantityMutationId"] is None or int(sale["mutationApplied"] or 0) != 1:
        return sale, "missing_settlement_evidence"
    identity_checks = (
        sale["evidenceAssetType"] == sale["assetType"],
        sale["evidenceEquipmentId"] == sale["equipmentInstanceId"],
        sale["evidenceStackItemId"] == sale["stackItemId"],
        sale["evidenceCatalogVersion"] == sale["catalogVersion"],
        sale["evidenceBindingStatus"] == sale["stackBindingStatus"],
        int(sale["evidenceQuantity"]) == int(sale["quantity"]),
        sale["evidenceBuyerId"] == sale["buyerId"],
        sale["evidenceSellerId"] == sale["sellerId"],
        sale["authoritativeOwnerId"] == sale["sellerId"],
        int(sale["newQuantity"]) == int(sale["expectedOldQuantity"]) - int(sale["quantity"]),
        int(sale["listingRemaining"]) == int(sale["newQuantity"]),
        int(sale["escrowRemaining"]) == int(sale["newQuantity"]),
        int(sale["listingVersion"]) == int(sale["expectedListingVersion"]) + 1,
        int(sale["escrowVersion"]) == int(sale["expectedEscrowVersion"]) + 1,
    )
    if not all(identity_checks):
        return sale, "settlement_identity_mismatch"

    equipment = await db.fetchrow(
        "SELECT accountKind,accountId,userId,currency,amount,balanceBefore,balanceAfter "
        "FROM EconomyLedger WHERE transactionId=$1 ORDER BY sequence",
        (sale["transactionId"],),
    ) as cursor:
        ledger = await cursor.fetchall()
    expected = _expected_ledger(sale)
    actual = {}
    for row in ledger:
        key = (row[0], row[1], row[2])
        if row[3] != "ETM" or int(row[6]) - int(row[5]) != int(row[4]) or key in actual:
            return sale, "ledger_allocation_mismatch"
        balance_key = (
            f"USER:{row[1]}:{row[3]}" if row[0] == "USER"
            else f"SYSTEM:{row[1]}"
        )
        if balances.get(balance_key) != int(row[6]):
            return sale, "ledger_balance_evidence_mismatch"
        actual[key] = int(row[4])
    if actual != expected or sum(actual.values()) != 0:
        return sale, "ledger_allocation_mismatch"

    if sale["assetType"] == "EQUIPMENT":
        async with db.execute(
            "SELECT ownerId,status,catalogVersion FROM RpgEquipmentInstance "
            "WHERE guildId=? AND equipmentInstanceId=?",
            (sale["guildId"], sale["equipmentInstanceId"]),
        )
        if not equipment or equipment[0] != sale["buyerId"] or equipment[1] != "OWNED" or equipment[2] != sale["catalogVersion"]:
            return sale, "equipment_transfer_unproven"
        if sale["listingStatus"] != "SOLD" or sale["escrowStatus"] != "SOLD" or int(sale["listingRemaining"]) != 0:
            return sale, "equipment_escrow_unreleased"
        stack = await db.fetchrow(
            "SELECT 1 FROM MarketplaceEscrow WHERE equipmentInstanceId=$1 "
            "AND status IN ('HELD','PARTIAL','REVIEW_REQUIRED') LIMIT 1",
            (sale["equipmentInstanceId"],),
        ) as cursor:
            if await cursor.fetchone():
                return sale, "equipment_still_escrowed"
    else:
        if sale["buyerStackBefore"] is None or sale["buyerStackAfter"] is None:
            return sale, "stack_credit_unproven"
        if int(sale["buyerStackAfter"]) - int(sale["buyerStackBefore"]) != int(sale["quantity"]):
            return sale, "stack_credit_unproven"
        async with db.execute(
            "SELECT quantity,status FROM RpgInventoryStack WHERE guildId=$1 AND userId=$2 AND itemId=$3 "
            "AND catalogVersion=$1 AND bindingStatus=$2",
            (sale["guildId"], sale["buyerId"], sale["stackItemId"],
             sale["catalogVersion"], sale["stackBindingStatus"]),
        )
        if not stack or stack[1] != "ACTIVE" or int(stack[0]) < int(sale["buyerStackAfter"]):
            return sale, "stack_credit_unproven"
        expected_listing = "SOLD" if int(sale["newQuantity"]) == 0 else "PARTIALLY_FILLED"
        expected_escrow = "SOLD" if int(sale["newQuantity"]) == 0 else "PARTIAL"
        if sale["listingStatus"] != expected_listing or sale["escrowStatus"] != expected_escrow:
            return sale, "stack_escrow_state_mismatch"
    return sale, None


async def _finalize_committed_pair(db_path, sale_id):
    async with _pool.acquire() as db:
        
        async with db.transaction():
        try:
            sale, error = await _prove_committed_sale(db, sale_id)
            if error:
                await db.rollback()
                return False, error
            expected_buyer, expected_seller = _sale_receipts(sale)
            if sale["buyerReceiptJson"] not in (None, expected_buyer) or sale["sellerReceiptJson"] not in (None, expected_seller):
                await db.rollback()
                return False, "receipt_mismatch"
            if sale["status"] == "COMMITTED":
                await db.rollback()
                return True, None
            if sale["status"] != "PENDING":
                await db.rollback()
                return False, "sale_status_mismatch"
            cursor = await db.execute(
                "UPDATE MarketplaceSale SET status='COMMITTED',buyerReceiptJson=$1,sellerReceiptJson=$2,completedAt=$3 "
                "WHERE saleId=? AND status='PENDING'",
                (expected_buyer, expected_seller, utc_now(), sale["saleId"]),
            )
            if cursor.rowcount != 1:
                await db.rollback()
                return False, "sale_changed"
            await db.commit()
            return True, None
        except Exception:
            await db.rollback()
            raise


async def _record_entity_review(db_path, *, guild_id, entity_type, entity_id,
                                listing_id, error_code):
    async with _pool.acquire() as db:
        
        async with db.transaction():
        try:
            await record_recovery_review(
                db, guild_id=guild_id, entity_type=entity_type, entity_id=entity_id,
                listing_id=listing_id, error_code=error_code, now=utc_now(),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def _mark_sale_review_safely(db_path, *, guild_id, sale_id, listing_id, error_code):
    try:
        return await mark_purchase_review(
            db_path, guild_id=guild_id, sale_id=sale_id, reason_code=error_code,
        )
    except (aiosqlite.IntegrityError, ValueError):
        timestamp = utc_now()
        async with _pool.acquire() as db:
            
            async with db.transaction():
            try:
                await db.execute(
                    "UPDATE MarketplaceSale SET status='REVIEW_REQUIRED',reviewReasonCode=$1 "
                    "WHERE saleId=? AND status='PENDING'",
                    (str(error_code)[:100], str(sale_id)),
                )
                await record_recovery_review(
                    db, guild_id=guild_id, entity_type="SALE", entity_id=sale_id,
                    listing_id=listing_id, error_code=error_code, now=timestamp,
                    metadata={"listing_hold": "quantity_or_identity_mismatch"},
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        return None


async def _hold_listing_for_review(db_path, *, guild_id, listing_id, error_code):
    timestamp = utc_now()
    async with _pool.acquire() as db:
        
        db.row_factory = aiosqlite.Row
        async with db.transaction():
        try:
            listing = await db.fetchrow(
                "SELECT " + _LISTING_ESCROW_COLUMNS + " FROM MarketplaceListing l "
                "JOIN MarketplaceEscrow e ON e.escrowId=l.escrowId "
                "WHERE l.guildId=$1 AND l.listingId=$2",
                (str(guild_id), str(listing_id)),
            )
            if listing and listing["status"] not in ("SOLD", "RETURNED"):
                await _apply_quantity_mutation(
                    db, listing=listing, operation_type="RECOVERY",
                    new_quantity=int(listing["remainingQuantity"]),
                    new_listing_status="REVIEW_REQUIRED", new_escrow_status="REVIEW_REQUIRED",
                    now=timestamp, actor_id="phase4-recovery", authorization_source="INTERNAL_API",
                )
                await db.execute(
                    "UPDATE MarketplaceListing SET moderationCode='RECOVERY_REVIEW',"
                    "moderationReasonCode=$1,moderatedAt=$2 WHERE listingId=$3",
                    (str(error_code)[:100], timestamp, str(listing_id)),
                )
            await record_recovery_review(
                db, guild_id=guild_id, entity_type="LISTING", entity_id=listing_id,
                listing_id=listing_id, error_code=error_code, now=timestamp,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def _create_compatibility_return(db_path, listing_id, guild_id, owner_id):
    timestamp = utc_now()
    async with _pool.acquire() as db:
        
        db.row_factory = aiosqlite.Row
        async with db.transaction():
        try:
            row = await db.fetchrow(
                "SELECT l.listingId,e.escrowId,l.assetType,l.equipmentInstanceId,l.stackItemId,"
                "l.catalogVersion,l.stackBindingStatus,e.remainingQuantity,e.authoritativeOwnerId "
                "FROM MarketplaceListing l JOIN MarketplaceEscrow e ON e.escrowId=l.escrowId "
                "WHERE l.listingId=$4 AND l.guildId=$5 AND l.status IN ('CANCELLED','EXPIRED')",
                (str(listing_id), str(guild_id)),
            )
            if not row or row["authoritativeOwnerId"] != str(owner_id) or int(row["remainingQuantity"]) <= 0:
                await db.rollback()
                return None
            return_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"phase4-compat-return:{row['escrowId']}"))
            await db.execute(
                "INSERT OR IGNORE INTO MarketplaceReturn "
                "(returnId,listingId,escrowId,guildId,recipientId,assetType,equipmentInstanceId,stackItemId,"
                "catalogVersion,stackBindingStatus,quantity,reasonCode,initiatedById,authorizationSource,status,"
                "idempotencyKey,createdAt,lastAttemptedAt) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14, 'PENDING',?,?,?)",
                (return_id, row["listingId"], row["escrowId"], str(guild_id), row["authoritativeOwnerId"],
                 row["assetType"], row["equipmentInstanceId"], row["stackItemId"], row["catalogVersion"],
                 row["stackBindingStatus"], int(row["remainingQuantity"]), "compatibility_return",
                 "phase4-recovery", "INTERNAL_API", f"compat-return:{row['escrowId']}", timestamp, timestamp),
            )
            await db.commit()
            return return_id
        except Exception:
            await db.rollback()
            raise


async def recover_phase4_runtime(db_path, *, limit=100):
    limit = max(1, min(int(limit), 500))
    report = {
        "scanned": 0, "settled": 0, "replayed": 0, "review_required": 0,
        "returns_settled": 0, "notifications_pending": 0, "skipped": 0,
    }
    async with _pool.acquire() as db:
        
        if not await phase4_schema_capability(db):
            return report
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT s.saleId,s.transactionId,s.guildId,s.listingId,s.status,s.reviewReasonCode,t.status AS transactionStatus,"
            "(SELECT COUNT(*) FROM EconomyLedger le WHERE le.transactionId=s.transactionId) AS ledgerCount "
            "FROM MarketplaceSale s LEFT JOIN EconomyTransaction t ON t.transactionId=s.transactionId "
            "WHERE s.status IN ('PENDING','REVIEW_REQUIRED') ORDER BY s.createdAt LIMIT $1", (limit,),
        ) as cursor:
            sales = [dict(row) for row in await cursor.fetchall()]
        async with db.execute(
            "SELECT t.transactionId,t.guildId,t.referenceId FROM EconomyTransaction t "
            "LEFT JOIN MarketplaceSale s ON s.transactionId=t.transactionId "
            "WHERE t.operation='MARKETPLACE_PURCHASE' AND t.status='PENDING' AND s.saleId IS NULL LIMIT $1",
            (limit,),
        ) as cursor:
            orphans = [tuple(row) for row in await cursor.fetchall()]
        async with db.execute(
            "SELECT returnId,guildId,recipientId FROM MarketplaceReturn "
            "WHERE status IN ('PENDING','REVIEW_REQUIRED') ORDER BY createdAt LIMIT $1", (limit,),
        ) as cursor:
            returns = [tuple(row) for row in await cursor.fetchall()]
        async with db.execute(
            "SELECT l.listingId,l.guildId,e.authoritativeOwnerId FROM MarketplaceListing l "
            "JOIN MarketplaceEscrow e ON e.escrowId=l.escrowId WHERE l.status IN ('CANCELLED','EXPIRED') "
            "AND e.remainingQuantity>0 ORDER BY l.createdAt LIMIT $1", (limit,),
        ) as cursor:
            compatibility = [tuple(row) for row in await cursor.fetchall()]
        async with db.execute(
            "SELECT l.listingId,l.guildId,l.status,l.remainingQuantity,e.status,e.remainingQuantity "
            "FROM MarketplaceListing l JOIN MarketplaceEscrow e ON e.escrowId=l.escrowId "
            "WHERE l.remainingQuantity!=e.remainingQuantity OR "
            "(l.assetType='EQUIPMENT' AND e.status IN ('HELD','PARTIAL','REVIEW_REQUIRED') AND NOT EXISTS "
            "(SELECT 1 FROM RpgEquipmentInstance i WHERE i.equipmentInstanceId=l.equipmentInstanceId "
            "AND i.ownerId=e.authoritativeOwnerId AND i.status='ESCROWED')) LIMIT $1", (limit,),
        ) as cursor:
            mismatches = [tuple(row) for row in await cursor.fetchall()]
        timestamp = utc_now()
        cursor = await db.execute(
            "UPDATE MarketplaceNotificationOutbox SET status='PENDING',leaseOwner=NULL,leaseExpiresAt=NULL,"
            "lastAttemptedAt=?,lastErrorCode='lease_expired' "
            "WHERE status='SENDING' AND leaseExpiresAt<$1",
            (timestamp, timestamp),
        )
        expired_leases = max(0, cursor.rowcount)
        await db.commit()
        async with db.execute(
            "SELECT listingId,guildId,status FROM MarketplaceListing "
            "WHERE status IN ('PAUSED','REVIEW_REQUIRED') LIMIT $1", (limit,),
        ) as cursor:
            held_listings = [tuple(row) for row in await cursor.fetchall()]

    for transaction_id, guild_id, listing_id in orphans:
        report["scanned"] += 1
        await _record_entity_review(
            db_path, guild_id=guild_id, entity_type="TRANSACTION", entity_id=transaction_id,
            listing_id=listing_id, error_code="missing_sale_pair",
        )
        if listing_id:
            await _hold_listing_for_review(
                db_path, guild_id=guild_id, listing_id=listing_id, error_code="missing_sale_pair",
            )
        report["review_required"] += 1
    for sale in sales:
        report["scanned"] += 1
        if sale["status"] == "REVIEW_REQUIRED":
            await _record_entity_review(
                db_path, guild_id=sale["guildId"], entity_type="SALE", entity_id=sale["saleId"],
                listing_id=sale["listingId"], error_code=sale["reviewReasonCode"] or "sale_review_pending",
            )
            report["review_required"] += 1
            continue
        if sale["transactionStatus"] is None:
            await _mark_sale_review_safely(
                db_path, guild_id=sale["guildId"], sale_id=sale["saleId"],
                listing_id=sale["listingId"], error_code="missing_transaction_pair",
            )
            report["review_required"] += 1
        elif sale["transactionStatus"] == "COMMITTED":
            proven, error = await _finalize_committed_pair(db_path, sale["saleId"])
            if proven:
                report["replayed"] += 1
            else:
                await _mark_sale_review_safely(
                    db_path, guild_id=sale["guildId"], sale_id=sale["saleId"],
                    listing_id=sale["listingId"], error_code=error or "committed_state_ambiguous",
                )
                report["review_required"] += 1
        elif sale["transactionStatus"] == "PENDING" and not int(sale["ledgerCount"]):
            result = await settle_purchase(db_path, guild_id=sale["guildId"], sale_id=sale["saleId"])
            if result.ok:
                report["settled"] += 1
            elif result.code in ("paused", "insufficient_funds"):
                report["skipped"] += 1
            else:
                await _mark_sale_review_safely(
                    db_path, guild_id=sale["guildId"], sale_id=sale["saleId"],
                    listing_id=sale["listingId"], error_code=result.code,
                )
                report["review_required"] += 1
        else:
            await _mark_sale_review_safely(
                db_path, guild_id=sale["guildId"], sale_id=sale["saleId"],
                listing_id=sale["listingId"], error_code="pending_pair_ambiguous",
            )
            report["review_required"] += 1
    for return_id, guild_id, recipient_id in returns:
        report["scanned"] += 1
        try:
            result = await settle_pending_return(
                db_path, guild_id=guild_id, recipient_id=recipient_id, return_id=return_id,
            )
            report["returns_settled"] += int(result.ok)
        except Exception as exc:
            async with _pool.acquire() as db:
                
                await db.execute(
                    "UPDATE MarketplaceReturn SET status='REVIEW_REQUIRED',lastAttemptedAt=$1,lastErrorCode=$2 "
                    "WHERE returnId=? AND status IN ('PENDING','REVIEW_REQUIRED')",
                    (utc_now(), type(exc).__name__[:100], str(return_id)),
                )
                await db.commit()
            await _record_entity_review(
                db_path, guild_id=guild_id, entity_type="RETURN", entity_id=return_id,
                listing_id=None, error_code=type(exc).__name__,
            )
            report["review_required"] += 1
    for listing_id, guild_id, owner_id in compatibility:
        report["scanned"] += 1
        try:
            return_id = await _create_compatibility_return(db_path, listing_id, guild_id, owner_id)
            result = return_id and await settle_pending_return(
                db_path, guild_id=guild_id, recipient_id=owner_id, return_id=return_id,
            )
            report["returns_settled"] += int(bool(result and result.ok))
        except Exception as exc:
            await _record_entity_review(
                db_path, guild_id=guild_id, entity_type="LISTING", entity_id=listing_id,
                listing_id=listing_id, error_code=type(exc).__name__,
            )
            report["review_required"] += 1
    for listing_id, guild_id, *_state in mismatches:
        report["scanned"] += 1
        await _record_entity_review(
            db_path, guild_id=guild_id, entity_type="LISTING", entity_id=listing_id,
            listing_id=listing_id, error_code="listing_escrow_asset_mismatch",
        )
        report["review_required"] += 1
    for listing_id, guild_id, status in held_listings:
        report["scanned"] += 1
        if status == "PAUSED":
            report["skipped"] += 1
            continue
        await _record_entity_review(
            db_path, guild_id=guild_id, entity_type="LISTING", entity_id=listing_id,
            listing_id=listing_id, error_code="listing_review_pending",
        )
        report["review_required"] += 1
    report["notifications_pending"] = len(await pending_watch_notifications(db_path, limit=limit))
    report["notification_leases_recovered"] = expired_leases
    return report
