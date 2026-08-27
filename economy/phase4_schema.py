"""Schema dan migrasi eksplisit Eternal Marketplace Phase 4."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

import aiosqlite

from .catalog import catalog_hash
from .constants import ECONOMY_PHASE4_MIGRATION_VERSION, RPG_PHASE3_CATALOG_VERSION
from .database import configure_connection


STACK_MIGRATION_ALGORITHM = "phase4-stack-userId-v2-catalog-manifest-verified"
PHASE4_PRE_HARDENING_CHECKSUM = "37599e3b53560536c9aa6fc905cd7ce67f9caf887e0f864013a2b97368b9f86b"

PHASE4_SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS MarketplaceListing (
    listingId TEXT PRIMARY KEY, guildId TEXT NOT NULL, sellerId TEXT NOT NULL,
    assetType TEXT NOT NULL CHECK(assetType IN ('EQUIPMENT','STACK')),
    equipmentInstanceId TEXT, stackItemId TEXT, catalogVersion TEXT NOT NULL,
    stackBindingStatus TEXT, originalQuantity INTEGER NOT NULL CHECK(originalQuantity>0),
    remainingQuantity INTEGER NOT NULL CHECK(remainingQuantity>=0 AND remainingQuantity<=originalQuantity),
    unitPriceEtm INTEGER NOT NULL CHECK(unitPriceEtm>0),
    totalListingValue INTEGER NOT NULL CHECK(totalListingValue>0),
    assetSnapshotJson TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN
      ('ACTIVE','PARTIALLY_FILLED','PAUSED','REVIEW_REQUIRED','CANCELLED','EXPIRED','SOLD','RETURNED')),
    escrowId TEXT NOT NULL UNIQUE, idempotencyKey TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL, expiresAt TEXT,
    cancelledAt TEXT, completedAt TEXT, moderationCode TEXT, moderationActorId TEXT,
    moderationReasonCode TEXT, moderatedAt TEXT,
    UNIQUE(guildId,idempotencyKey),
    CHECK((assetType='EQUIPMENT' AND equipmentInstanceId IS NOT NULL AND stackItemId IS NULL
           AND stackBindingStatus IS NULL AND originalQuantity=1)
       OR (assetType='STACK' AND equipmentInstanceId IS NULL AND stackItemId IS NOT NULL
           AND stackBindingStatus IS NOT NULL)),
    FOREIGN KEY(escrowId) REFERENCES MarketplaceEscrow(escrowId) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE IF NOT EXISTS MarketplaceEscrow (
    escrowId TEXT PRIMARY KEY, listingId TEXT NOT NULL UNIQUE, guildId TEXT NOT NULL,
    authoritativeOwnerId TEXT NOT NULL, assetType TEXT NOT NULL CHECK(assetType IN ('EQUIPMENT','STACK')),
    equipmentInstanceId TEXT, stackItemId TEXT, catalogVersion TEXT NOT NULL,
    stackBindingStatus TEXT, originalQuantity INTEGER NOT NULL CHECK(originalQuantity>0),
    remainingQuantity INTEGER NOT NULL CHECK(remainingQuantity>=0 AND remainingQuantity<=originalQuantity),
    assetSnapshotJson TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('HELD','PARTIAL','SOLD','RETURNED','REVIEW_REQUIRED')),
    version INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL, releasedAt TEXT,
    CHECK((assetType='EQUIPMENT' AND equipmentInstanceId IS NOT NULL AND stackItemId IS NULL
           AND stackBindingStatus IS NULL AND originalQuantity=1)
       OR (assetType='STACK' AND equipmentInstanceId IS NULL AND stackItemId IS NOT NULL
           AND stackBindingStatus IS NOT NULL)),
    FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE IF NOT EXISTS MarketplaceSale (
    saleId TEXT PRIMARY KEY, transactionId TEXT NOT NULL UNIQUE, guildId TEXT NOT NULL,
    listingId TEXT NOT NULL, escrowId TEXT NOT NULL, sellerId TEXT NOT NULL, buyerId TEXT NOT NULL,
    assetType TEXT NOT NULL CHECK(assetType IN ('EQUIPMENT','STACK')),
    equipmentInstanceId TEXT, stackItemId TEXT, catalogVersion TEXT NOT NULL, stackBindingStatus TEXT,
    quantity INTEGER NOT NULL CHECK(quantity>0), unitPriceEtm INTEGER NOT NULL CHECK(unitPriceEtm>0),
    grossEtm INTEGER NOT NULL CHECK(grossEtm>0), feeEtm INTEGER NOT NULL CHECK(feeEtm>=0),
    sellerProceedsEtm INTEGER NOT NULL CHECK(sellerProceedsEtm>=0),
    treasuryEtm INTEGER NOT NULL CHECK(treasuryEtm>=0), reserveEtm INTEGER NOT NULL CHECK(reserveEtm>=0),
    burnEtm INTEGER NOT NULL CHECK(burnEtm>=0), expectedListingVersion INTEGER NOT NULL,
    expectedEscrowVersion INTEGER NOT NULL, idempotencyKey TEXT NOT NULL,
    authorizationSource TEXT NOT NULL DEFAULT 'DISCORD',
    status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','REVIEW_REQUIRED','VOID')),
    buyerReceiptJson TEXT, sellerReceiptJson TEXT, voidReasonCode TEXT, reviewReasonCode TEXT,
    createdAt TEXT NOT NULL, completedAt TEXT,
    UNIQUE(guildId,idempotencyKey),
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId),
    FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId),
    FOREIGN KEY(escrowId) REFERENCES MarketplaceEscrow(escrowId),
    CHECK((status='COMMITTED' AND buyerReceiptJson IS NOT NULL AND sellerReceiptJson IS NOT NULL
           AND voidReasonCode IS NULL)
       OR (status IN ('PENDING','REVIEW_REQUIRED') AND buyerReceiptJson IS NULL
           AND sellerReceiptJson IS NULL AND voidReasonCode IS NULL)
       OR (status='VOID' AND buyerReceiptJson IS NULL AND sellerReceiptJson IS NULL
           AND voidReasonCode IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS MarketplaceReturn (
    returnId TEXT PRIMARY KEY, listingId TEXT NOT NULL, escrowId TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL, recipientId TEXT NOT NULL,
    assetType TEXT NOT NULL CHECK(assetType IN ('EQUIPMENT','STACK')),
    equipmentInstanceId TEXT, stackItemId TEXT, catalogVersion TEXT NOT NULL, stackBindingStatus TEXT,
    quantity INTEGER NOT NULL CHECK(quantity>0), reasonCode TEXT NOT NULL,
    initiatedById TEXT, authorizationSource TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','REVIEW_REQUIRED')),
    idempotencyKey TEXT NOT NULL, receiptJson TEXT, createdAt TEXT NOT NULL,
    completedAt TEXT, lastAttemptedAt TEXT, lastErrorCode TEXT,
    UNIQUE(guildId,idempotencyKey),
    FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId),
    FOREIGN KEY(escrowId) REFERENCES MarketplaceEscrow(escrowId),
    CHECK((status='COMMITTED' AND receiptJson IS NOT NULL) OR
          (status!='COMMITTED' AND receiptJson IS NULL))
);
CREATE TABLE IF NOT EXISTS MarketplaceWatch (
    guildId TEXT NOT NULL, userId TEXT NOT NULL, listingId TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), createdAt TEXT NOT NULL,
    removedAt TEXT, lastObservedVersion INTEGER, pendingEventKey TEXT,
    notificationStatus TEXT CHECK(notificationStatus IS NULL OR notificationStatus IN ('PENDING','SENT','FAILED')),
    notificationMessageId TEXT, updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId,userId,listingId), FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId)
);
CREATE TABLE IF NOT EXISTS MarketplaceReport (
    reportId TEXT PRIMARY KEY, guildId TEXT NOT NULL, listingId TEXT NOT NULL,
    reporterId TEXT NOT NULL, reasonCategory TEXT NOT NULL, sanitizedDetails TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('OPEN','IN_REVIEW','RESOLVED','DISMISSED')),
    staffActorId TEXT, resolutionCode TEXT, resolutionMetadataJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL, reviewedAt TEXT, resolvedAt TEXT,
    FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId)
);
CREATE TABLE IF NOT EXISTS MarketplaceUserState (
    guildId TEXT NOT NULL, userId TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','RESTRICTED','FROZEN')),
    reasonCode TEXT, staffActorId TEXT, authorizationSource TEXT,
    version INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId,userId)
);
CREATE TABLE IF NOT EXISTS MarketplaceUserStateAudit (
    auditId TEXT PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    oldStatus TEXT, newStatus TEXT NOT NULL CHECK(newStatus IN ('ACTIVE','RESTRICTED','FROZEN')),
    actorId TEXT NOT NULL, authorizationSource TEXT NOT NULL, reasonCode TEXT NOT NULL,
    stateVersion INTEGER NOT NULL CHECK(stateVersion>=0), createdAt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS MarketplaceQuantityMutation (
    mutationId TEXT PRIMARY KEY, listingId TEXT NOT NULL, escrowId TEXT NOT NULL,
    operationType TEXT NOT NULL CHECK(operationType IN ('SALE','RETURN','MODERATION','RECOVERY','RECONCILIATION')),
    expectedListingVersion INTEGER NOT NULL, expectedEscrowVersion INTEGER NOT NULL,
    expectedOldQuantity INTEGER NOT NULL CHECK(expectedOldQuantity>=0),
    newQuantity INTEGER NOT NULL CHECK(newQuantity>=0),
    expectedListingStatus TEXT NOT NULL, expectedEscrowStatus TEXT NOT NULL,
    newListingStatus TEXT NOT NULL, newEscrowStatus TEXT NOT NULL,
    saleId TEXT, returnId TEXT, actorId TEXT, authorizationSource TEXT,
    createdAt TEXT NOT NULL, applied INTEGER NOT NULL DEFAULT 0 CHECK(applied IN (0,1)),
    FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId),
    FOREIGN KEY(escrowId) REFERENCES MarketplaceEscrow(escrowId),
    FOREIGN KEY(saleId) REFERENCES MarketplaceSale(saleId),
    FOREIGN KEY(returnId) REFERENCES MarketplaceReturn(returnId),
    CHECK((operationType='SALE' AND saleId IS NOT NULL AND returnId IS NULL)
       OR (operationType='RETURN' AND returnId IS NOT NULL AND saleId IS NULL)
       OR (operationType IN ('MODERATION','RECOVERY','RECONCILIATION') AND saleId IS NULL))
);
CREATE TABLE IF NOT EXISTS MarketplaceSettlementEvidence (
    saleId TEXT PRIMARY KEY, transactionId TEXT NOT NULL UNIQUE, guildId TEXT NOT NULL,
    listingId TEXT NOT NULL, escrowId TEXT NOT NULL, assetType TEXT NOT NULL,
    equipmentInstanceId TEXT, stackItemId TEXT, catalogVersion TEXT NOT NULL,
    stackBindingStatus TEXT, quantity INTEGER NOT NULL CHECK(quantity>0),
    buyerId TEXT NOT NULL, sellerId TEXT NOT NULL,
    buyerStackBefore INTEGER, buyerStackAfter INTEGER,
    quantityMutationId TEXT NOT NULL UNIQUE, createdAt TEXT NOT NULL,
    FOREIGN KEY(saleId) REFERENCES MarketplaceSale(saleId),
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId),
    FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId),
    FOREIGN KEY(escrowId) REFERENCES MarketplaceEscrow(escrowId),
    FOREIGN KEY(quantityMutationId) REFERENCES MarketplaceQuantityMutation(mutationId)
);
CREATE TABLE IF NOT EXISTS MarketplaceRecoveryReview (
    reviewId TEXT PRIMARY KEY, guildId TEXT NOT NULL, entityType TEXT NOT NULL,
    entityId TEXT NOT NULL, listingId TEXT, errorCode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','RESOLVED')),
    retryCount INTEGER NOT NULL DEFAULT 1 CHECK(retryCount>0),
    firstDetectedAt TEXT NOT NULL, lastAttemptedAt TEXT NOT NULL,
    sanitizedMetadataJson TEXT NOT NULL DEFAULT '{}', resolvedAt TEXT,
    UNIQUE(guildId,entityType,entityId,errorCode)
);
CREATE TABLE IF NOT EXISTS MarketplaceNotificationOutbox (
    eventId TEXT PRIMARY KEY, eventKey TEXT NOT NULL UNIQUE, guildId TEXT NOT NULL,
    userId TEXT NOT NULL, listingId TEXT NOT NULL, listingVersion INTEGER NOT NULL,
    eventType TEXT NOT NULL, sanitizedPayloadJson TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','SENDING','SENT','REVIEW_REQUIRED')),
    leaseOwner TEXT, leaseExpiresAt TEXT, attemptCount INTEGER NOT NULL DEFAULT 0 CHECK(attemptCount>=0),
    messageId TEXT, createdAt TEXT NOT NULL, sentAt TEXT, lastAttemptedAt TEXT, lastErrorCode TEXT,
    FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId)
);
CREATE INDEX IF NOT EXISTS idx_market_listing_browse ON MarketplaceListing(guildId,status,assetType,createdAt);
CREATE INDEX IF NOT EXISTS idx_market_listing_seller ON MarketplaceListing(guildId,sellerId,status,createdAt);
CREATE INDEX IF NOT EXISTS idx_market_listing_item ON MarketplaceListing(guildId,stackItemId,catalogVersion,status,unitPriceEtm);
CREATE UNIQUE INDEX IF NOT EXISTS idx_market_equipment_unresolved ON MarketplaceListing(guildId,equipmentInstanceId)
 WHERE equipmentInstanceId IS NOT NULL AND status IN ('ACTIVE','PARTIALLY_FILLED','PAUSED','REVIEW_REQUIRED','CANCELLED','EXPIRED');
CREATE INDEX IF NOT EXISTS idx_market_escrow_owner ON MarketplaceEscrow(guildId,authoritativeOwnerId,status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_market_sale_unresolved_buyer ON MarketplaceSale(guildId,buyerId,listingId)
 WHERE status IN ('PENDING','REVIEW_REQUIRED');
CREATE INDEX IF NOT EXISTS idx_market_sale_buyer ON MarketplaceSale(guildId,buyerId,completedAt);
CREATE INDEX IF NOT EXISTS idx_market_sale_seller ON MarketplaceSale(guildId,sellerId,completedAt);
CREATE INDEX IF NOT EXISTS idx_market_sale_price ON MarketplaceSale(guildId,assetType,stackItemId,equipmentInstanceId,catalogVersion,unitPriceEtm,completedAt);
CREATE INDEX IF NOT EXISTS idx_market_return_status ON MarketplaceReturn(guildId,status,lastAttemptedAt);
CREATE INDEX IF NOT EXISTS idx_market_watch_user ON MarketplaceWatch(guildId,userId,active);
CREATE INDEX IF NOT EXISTS idx_market_watch_notification ON MarketplaceWatch(notificationStatus,pendingEventKey);
CREATE INDEX IF NOT EXISTS idx_market_report_listing ON MarketplaceReport(guildId,listingId,status,createdAt);
CREATE INDEX IF NOT EXISTS idx_market_report_actor ON MarketplaceReport(guildId,reporterId,listingId,createdAt);
CREATE UNIQUE INDEX IF NOT EXISTS idx_market_report_unresolved ON MarketplaceReport(guildId,reporterId,listingId)
 WHERE status IN ('OPEN','IN_REVIEW');
CREATE INDEX IF NOT EXISTS idx_market_quantity_listing ON MarketplaceQuantityMutation(listingId,createdAt);
CREATE INDEX IF NOT EXISTS idx_market_recovery_open ON MarketplaceRecoveryReview(status,lastAttemptedAt);
CREATE INDEX IF NOT EXISTS idx_market_outbox_delivery ON MarketplaceNotificationOutbox(status,leaseExpiresAt,createdAt);
CREATE INDEX IF NOT EXISTS idx_market_outbox_listing ON MarketplaceNotificationOutbox(guildId,listingId,listingVersion,eventType);
CREATE INDEX IF NOT EXISTS idx_market_user_state_audit ON MarketplaceUserStateAudit(guildId,userId,createdAt);
"""

PHASE4_TRIGGER_SQL = (
    """CREATE TRIGGER IF NOT EXISTS trg_market_listing_identity_immutable BEFORE UPDATE ON MarketplaceListing
    WHEN NEW.listingId IS NOT OLD.listingId OR NEW.guildId IS NOT OLD.guildId OR NEW.sellerId IS NOT OLD.sellerId
      OR NEW.assetType IS NOT OLD.assetType OR NEW.equipmentInstanceId IS NOT OLD.equipmentInstanceId
      OR NEW.stackItemId IS NOT OLD.stackItemId OR NEW.catalogVersion IS NOT OLD.catalogVersion
      OR NEW.stackBindingStatus IS NOT OLD.stackBindingStatus OR NEW.originalQuantity IS NOT OLD.originalQuantity
      OR NEW.unitPriceEtm IS NOT OLD.unitPriceEtm OR NEW.totalListingValue IS NOT OLD.totalListingValue
      OR NEW.assetSnapshotJson IS NOT OLD.assetSnapshotJson OR NEW.escrowId IS NOT OLD.escrowId
      OR NEW.idempotencyKey IS NOT OLD.idempotencyKey OR NEW.remainingQuantity>OLD.remainingQuantity
    BEGIN SELECT RAISE(ABORT,'MarketplaceListing immutable identity changed'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_listing_transition BEFORE UPDATE OF status,remainingQuantity ON MarketplaceListing
    WHEN NOT (
      (NEW.status=OLD.status) OR
      (OLD.status='ACTIVE' AND NEW.status IN ('PARTIALLY_FILLED','PAUSED','REVIEW_REQUIRED','SOLD','RETURNED')) OR
      (OLD.status='PARTIALLY_FILLED' AND NEW.status IN ('PAUSED','REVIEW_REQUIRED','SOLD','RETURNED')) OR
      (OLD.status='PAUSED' AND NEW.status IN ('ACTIVE','PARTIALLY_FILLED','REVIEW_REQUIRED','RETURNED')) OR
      (OLD.status='REVIEW_REQUIRED' AND NEW.status IN ('ACTIVE','PARTIALLY_FILLED','RETURNED')) OR
      (OLD.status IN ('CANCELLED','EXPIRED') AND NEW.status IN ('REVIEW_REQUIRED','RETURNED'))
    ) OR (NEW.status IN ('SOLD','RETURNED') AND NEW.remainingQuantity!=0)
      OR (NEW.status IN ('ACTIVE','PARTIALLY_FILLED','PAUSED','CANCELLED','EXPIRED') AND NEW.remainingQuantity<=0)
    BEGIN SELECT RAISE(ABORT,'MarketplaceListing invalid transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_listing_no_delete BEFORE DELETE ON MarketplaceListing
    BEGIN SELECT RAISE(ABORT,'MarketplaceListing cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_listing_quantity_authoritative BEFORE UPDATE OF remainingQuantity,status,version ON MarketplaceListing
    WHEN NOT EXISTS (SELECT 1 FROM MarketplaceQuantityMutation m
      WHERE m.listingId=OLD.listingId AND m.escrowId=OLD.escrowId AND m.applied=0
      AND m.expectedListingVersion=OLD.version AND m.expectedOldQuantity=OLD.remainingQuantity
      AND m.expectedListingStatus=OLD.status AND m.newQuantity=NEW.remainingQuantity
      AND m.newListingStatus=NEW.status AND NEW.version=OLD.version+1)
    BEGIN SELECT RAISE(ABORT,'Marketplace listing mutation command required'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_escrow_identity_immutable BEFORE UPDATE ON MarketplaceEscrow
    WHEN NEW.escrowId IS NOT OLD.escrowId OR NEW.listingId IS NOT OLD.listingId
      OR NEW.guildId IS NOT OLD.guildId OR NEW.authoritativeOwnerId IS NOT OLD.authoritativeOwnerId
      OR NEW.assetType IS NOT OLD.assetType OR NEW.equipmentInstanceId IS NOT OLD.equipmentInstanceId
      OR NEW.stackItemId IS NOT OLD.stackItemId OR NEW.catalogVersion IS NOT OLD.catalogVersion
      OR NEW.stackBindingStatus IS NOT OLD.stackBindingStatus OR NEW.originalQuantity IS NOT OLD.originalQuantity
      OR NEW.assetSnapshotJson IS NOT OLD.assetSnapshotJson OR NEW.remainingQuantity>OLD.remainingQuantity
    BEGIN SELECT RAISE(ABORT,'MarketplaceEscrow immutable identity changed'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_escrow_transition BEFORE UPDATE OF status,remainingQuantity ON MarketplaceEscrow
    WHEN NOT ((NEW.status=OLD.status) OR
      (OLD.status='HELD' AND NEW.status IN ('PARTIAL','SOLD','RETURNED','REVIEW_REQUIRED')) OR
      (OLD.status='PARTIAL' AND NEW.status IN ('SOLD','RETURNED','REVIEW_REQUIRED')) OR
      (OLD.status='REVIEW_REQUIRED' AND NEW.status IN ('HELD','PARTIAL','SOLD','RETURNED')))
      OR (NEW.status IN ('SOLD','RETURNED') AND NEW.remainingQuantity!=0)
      OR (NEW.status IN ('HELD','PARTIAL') AND NEW.remainingQuantity<=0)
    BEGIN SELECT RAISE(ABORT,'MarketplaceEscrow invalid transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_escrow_no_delete BEFORE DELETE ON MarketplaceEscrow
    BEGIN SELECT RAISE(ABORT,'MarketplaceEscrow cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_escrow_quantity_authoritative BEFORE UPDATE OF remainingQuantity,status,version ON MarketplaceEscrow
    WHEN NOT EXISTS (SELECT 1 FROM MarketplaceQuantityMutation m
      WHERE m.listingId=OLD.listingId AND m.escrowId=OLD.escrowId AND m.applied=0
      AND m.expectedEscrowVersion=OLD.version AND m.expectedOldQuantity=OLD.remainingQuantity
      AND m.expectedEscrowStatus=OLD.status AND m.newQuantity=NEW.remainingQuantity
      AND m.newEscrowStatus=NEW.status AND NEW.version=OLD.version+1)
    BEGIN SELECT RAISE(ABORT,'Marketplace escrow mutation command required'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_sale_identity_immutable BEFORE UPDATE ON MarketplaceSale
    WHEN NEW.saleId IS NOT OLD.saleId OR NEW.transactionId IS NOT OLD.transactionId
      OR NEW.guildId IS NOT OLD.guildId OR NEW.listingId IS NOT OLD.listingId OR NEW.escrowId IS NOT OLD.escrowId
      OR NEW.sellerId IS NOT OLD.sellerId OR NEW.buyerId IS NOT OLD.buyerId OR NEW.assetType IS NOT OLD.assetType
      OR NEW.equipmentInstanceId IS NOT OLD.equipmentInstanceId OR NEW.stackItemId IS NOT OLD.stackItemId
      OR NEW.catalogVersion IS NOT OLD.catalogVersion OR NEW.stackBindingStatus IS NOT OLD.stackBindingStatus
      OR NEW.quantity IS NOT OLD.quantity OR NEW.unitPriceEtm IS NOT OLD.unitPriceEtm OR NEW.grossEtm IS NOT OLD.grossEtm
      OR NEW.feeEtm IS NOT OLD.feeEtm OR NEW.sellerProceedsEtm IS NOT OLD.sellerProceedsEtm
      OR NEW.treasuryEtm IS NOT OLD.treasuryEtm OR NEW.reserveEtm IS NOT OLD.reserveEtm OR NEW.burnEtm IS NOT OLD.burnEtm
      OR NEW.expectedListingVersion IS NOT OLD.expectedListingVersion OR NEW.expectedEscrowVersion IS NOT OLD.expectedEscrowVersion
      OR NEW.idempotencyKey IS NOT OLD.idempotencyKey OR NEW.authorizationSource IS NOT OLD.authorizationSource
    BEGIN SELECT RAISE(ABORT,'MarketplaceSale immutable identity changed'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_sale_transition BEFORE UPDATE ON MarketplaceSale
    WHEN NOT ((OLD.status='PENDING' AND NEW.status IN ('PENDING','COMMITTED','REVIEW_REQUIRED','VOID')) OR
              (OLD.status='REVIEW_REQUIRED' AND NEW.status IN ('REVIEW_REQUIRED','COMMITTED','VOID')) OR
              (OLD.status=NEW.status AND OLD.status IN ('COMMITTED','VOID')))
      OR (OLD.buyerReceiptJson IS NOT NULL AND NEW.buyerReceiptJson IS NOT OLD.buyerReceiptJson)
      OR (OLD.sellerReceiptJson IS NOT NULL AND NEW.sellerReceiptJson IS NOT OLD.sellerReceiptJson)
      OR (OLD.voidReasonCode IS NOT NULL AND NEW.voidReasonCode IS NOT OLD.voidReasonCode)
      OR (NEW.status='COMMITTED' AND (NEW.buyerReceiptJson IS NULL OR NEW.sellerReceiptJson IS NULL OR NEW.voidReasonCode IS NOT NULL))
      OR (NEW.status IN ('PENDING','REVIEW_REQUIRED') AND (NEW.buyerReceiptJson IS NOT NULL OR NEW.sellerReceiptJson IS NOT NULL OR NEW.voidReasonCode IS NOT NULL))
      OR (NEW.status='VOID' AND (NEW.buyerReceiptJson IS NOT NULL OR NEW.sellerReceiptJson IS NOT NULL OR NEW.voidReasonCode IS NULL))
    BEGIN SELECT RAISE(ABORT,'MarketplaceSale invalid transition or receipt'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_sale_no_delete BEFORE DELETE ON MarketplaceSale
    BEGIN SELECT RAISE(ABORT,'MarketplaceSale cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_return_identity_immutable BEFORE UPDATE ON MarketplaceReturn
    WHEN NEW.returnId IS NOT OLD.returnId OR NEW.listingId IS NOT OLD.listingId OR NEW.escrowId IS NOT OLD.escrowId
      OR NEW.guildId IS NOT OLD.guildId OR NEW.recipientId IS NOT OLD.recipientId OR NEW.assetType IS NOT OLD.assetType
      OR NEW.equipmentInstanceId IS NOT OLD.equipmentInstanceId OR NEW.stackItemId IS NOT OLD.stackItemId
      OR NEW.catalogVersion IS NOT OLD.catalogVersion OR NEW.stackBindingStatus IS NOT OLD.stackBindingStatus
      OR NEW.quantity IS NOT OLD.quantity OR NEW.reasonCode IS NOT OLD.reasonCode OR NEW.idempotencyKey IS NOT OLD.idempotencyKey
    BEGIN SELECT RAISE(ABORT,'MarketplaceReturn immutable identity changed'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_return_transition BEFORE UPDATE ON MarketplaceReturn
    WHEN NOT ((OLD.status='PENDING' AND NEW.status IN ('PENDING','COMMITTED','REVIEW_REQUIRED')) OR
              (OLD.status='REVIEW_REQUIRED' AND NEW.status IN ('REVIEW_REQUIRED','COMMITTED')) OR
              (OLD.status='COMMITTED' AND NEW.status='COMMITTED'))
      OR (OLD.receiptJson IS NOT NULL AND NEW.receiptJson IS NOT OLD.receiptJson)
      OR (NEW.status='COMMITTED' AND NEW.receiptJson IS NULL)
      OR (NEW.status!='COMMITTED' AND NEW.receiptJson IS NOT NULL)
    BEGIN SELECT RAISE(ABORT,'MarketplaceReturn invalid transition or receipt'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_return_no_delete BEFORE DELETE ON MarketplaceReturn
    BEGIN SELECT RAISE(ABORT,'MarketplaceReturn cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_report_no_delete BEFORE DELETE ON MarketplaceReport
    BEGIN SELECT RAISE(ABORT,'MarketplaceReport cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_quantity_validate BEFORE INSERT ON MarketplaceQuantityMutation
    WHEN NOT EXISTS (SELECT 1 FROM MarketplaceListing l JOIN MarketplaceEscrow e ON e.escrowId=l.escrowId
      WHERE l.listingId=NEW.listingId AND e.escrowId=NEW.escrowId AND e.listingId=l.listingId
      AND l.version=NEW.expectedListingVersion AND e.version=NEW.expectedEscrowVersion
      AND l.remainingQuantity=NEW.expectedOldQuantity AND e.remainingQuantity=NEW.expectedOldQuantity
      AND l.status=NEW.expectedListingStatus AND e.status=NEW.expectedEscrowStatus)
      OR NEW.newQuantity>NEW.expectedOldQuantity
      OR (NEW.operationType='SALE' AND NOT EXISTS (SELECT 1 FROM MarketplaceSale s
          WHERE s.saleId=NEW.saleId AND s.listingId=NEW.listingId AND s.escrowId=NEW.escrowId
          AND s.quantity=NEW.expectedOldQuantity-NEW.newQuantity))
      OR (NEW.operationType='RETURN' AND NOT EXISTS (SELECT 1 FROM MarketplaceReturn r
          WHERE r.returnId=NEW.returnId AND r.listingId=NEW.listingId AND r.escrowId=NEW.escrowId
          AND r.quantity=NEW.expectedOldQuantity-NEW.newQuantity))
      OR (NEW.newListingStatus='SOLD' AND (NEW.newQuantity!=0 OR NEW.newEscrowStatus!='SOLD'))
      OR (NEW.newListingStatus='RETURNED' AND (NEW.newQuantity!=0 OR NEW.newEscrowStatus!='RETURNED'))
      OR (NEW.newListingStatus='PARTIALLY_FILLED' AND (NEW.newQuantity<=0 OR NEW.newEscrowStatus!='PARTIAL'))
    BEGIN SELECT RAISE(ABORT,'Marketplace quantity mutation validation failed'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_quantity_apply AFTER INSERT ON MarketplaceQuantityMutation
    BEGIN
      UPDATE MarketplaceListing SET remainingQuantity=NEW.newQuantity,status=NEW.newListingStatus,version=version+1
       WHERE listingId=NEW.listingId AND version=NEW.expectedListingVersion;
      UPDATE MarketplaceEscrow SET remainingQuantity=NEW.newQuantity,status=NEW.newEscrowStatus,version=version+1,updatedAt=NEW.createdAt,
       releasedAt=CASE WHEN NEW.newEscrowStatus IN ('SOLD','RETURNED') THEN NEW.createdAt ELSE releasedAt END
       WHERE escrowId=NEW.escrowId AND version=NEW.expectedEscrowVersion;
      UPDATE MarketplaceQuantityMutation SET applied=1 WHERE mutationId=NEW.mutationId;
    END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_quantity_immutable BEFORE UPDATE ON MarketplaceQuantityMutation
    WHEN NOT (OLD.applied=0 AND NEW.applied=1 AND NEW.mutationId=OLD.mutationId
      AND NEW.listingId=OLD.listingId AND NEW.escrowId=OLD.escrowId
      AND NEW.operationType=OLD.operationType AND NEW.expectedListingVersion=OLD.expectedListingVersion
      AND NEW.expectedEscrowVersion=OLD.expectedEscrowVersion AND NEW.expectedOldQuantity=OLD.expectedOldQuantity
      AND NEW.newQuantity=OLD.newQuantity AND NEW.expectedListingStatus=OLD.expectedListingStatus
      AND NEW.expectedEscrowStatus=OLD.expectedEscrowStatus AND NEW.newListingStatus=OLD.newListingStatus
      AND NEW.newEscrowStatus=OLD.newEscrowStatus AND NEW.saleId IS OLD.saleId AND NEW.returnId IS OLD.returnId
      AND NEW.actorId IS OLD.actorId AND NEW.authorizationSource IS OLD.authorizationSource
      AND NEW.createdAt=OLD.createdAt)
    BEGIN SELECT RAISE(ABORT,'MarketplaceQuantityMutation immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_quantity_no_delete BEFORE DELETE ON MarketplaceQuantityMutation
    BEGIN SELECT RAISE(ABORT,'MarketplaceQuantityMutation cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_settlement_evidence_immutable BEFORE UPDATE ON MarketplaceSettlementEvidence
    BEGIN SELECT RAISE(ABORT,'MarketplaceSettlementEvidence immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_settlement_evidence_no_delete BEFORE DELETE ON MarketplaceSettlementEvidence
    BEGIN SELECT RAISE(ABORT,'MarketplaceSettlementEvidence cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_user_state_insert_guard BEFORE INSERT ON MarketplaceUserState
    WHEN NEW.staffActorId IS NULL OR NEW.authorizationSource IS NULL OR NEW.reasonCode IS NULL
    BEGIN SELECT RAISE(ABORT,'MarketplaceUserState authorization required'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_user_state_update_guard BEFORE UPDATE ON MarketplaceUserState
    WHEN NEW.status NOT IN ('ACTIVE','RESTRICTED','FROZEN') OR NEW.version!=OLD.version+1
      OR NEW.staffActorId IS NULL OR NEW.authorizationSource IS NULL OR NEW.reasonCode IS NULL
      OR NEW.updatedAt<=OLD.updatedAt
    BEGIN SELECT RAISE(ABORT,'MarketplaceUserState invalid transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_user_state_no_delete BEFORE DELETE ON MarketplaceUserState
    BEGIN SELECT RAISE(ABORT,'MarketplaceUserState cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_user_state_audit_insert AFTER INSERT ON MarketplaceUserState
    BEGIN INSERT INTO MarketplaceUserStateAudit
      (auditId,guildId,userId,oldStatus,newStatus,actorId,authorizationSource,reasonCode,stateVersion,createdAt)
      VALUES (lower(hex(randomblob(16))),NEW.guildId,NEW.userId,NULL,NEW.status,NEW.staffActorId,NEW.authorizationSource,NEW.reasonCode,NEW.version,NEW.updatedAt); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_user_state_audit_update AFTER UPDATE ON MarketplaceUserState
    BEGIN INSERT INTO MarketplaceUserStateAudit
      (auditId,guildId,userId,oldStatus,newStatus,actorId,authorizationSource,reasonCode,stateVersion,createdAt)
      VALUES (lower(hex(randomblob(16))),NEW.guildId,NEW.userId,OLD.status,NEW.status,NEW.staffActorId,NEW.authorizationSource,NEW.reasonCode,NEW.version,NEW.updatedAt); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_user_state_audit_immutable BEFORE UPDATE ON MarketplaceUserStateAudit
    BEGIN SELECT RAISE(ABORT,'MarketplaceUserStateAudit immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_user_state_audit_no_delete BEFORE DELETE ON MarketplaceUserStateAudit
    BEGIN SELECT RAISE(ABORT,'MarketplaceUserStateAudit cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_outbox_immutable BEFORE UPDATE ON MarketplaceNotificationOutbox
    WHEN NEW.eventId!=OLD.eventId OR NEW.eventKey!=OLD.eventKey OR NEW.guildId!=OLD.guildId
      OR NEW.userId!=OLD.userId OR NEW.listingId!=OLD.listingId OR NEW.listingVersion!=OLD.listingVersion
      OR NEW.eventType!=OLD.eventType OR NEW.sanitizedPayloadJson!=OLD.sanitizedPayloadJson
      OR NOT ((OLD.status='PENDING' AND NEW.status IN ('SENDING','REVIEW_REQUIRED'))
          OR (OLD.status='SENDING' AND NEW.status IN ('SENDING','PENDING','SENT','REVIEW_REQUIRED'))
          OR (OLD.status=NEW.status AND OLD.status IN ('SENT','REVIEW_REQUIRED')))
    BEGIN SELECT RAISE(ABORT,'MarketplaceNotificationOutbox invalid mutation'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_outbox_no_delete BEFORE DELETE ON MarketplaceNotificationOutbox
    BEGIN SELECT RAISE(ABORT,'MarketplaceNotificationOutbox cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_equipment_enter_escrow BEFORE UPDATE OF status ON RpgEquipmentInstance
    WHEN OLD.status='OWNED' AND NEW.status='ESCROWED' AND NOT EXISTS (
      SELECT 1 FROM MarketplaceEscrow e WHERE e.equipmentInstanceId=OLD.equipmentInstanceId
      AND e.guildId=OLD.guildId AND e.authoritativeOwnerId=OLD.ownerId AND e.status='HELD')
    BEGIN SELECT RAISE(ABORT,'Equipment escrow record required'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_equipment_leave_escrow BEFORE UPDATE ON RpgEquipmentInstance
    WHEN OLD.status='ESCROWED' AND (NEW.status!='OWNED' OR NOT EXISTS (
      SELECT 1 FROM MarketplaceEscrow e WHERE e.equipmentInstanceId=OLD.equipmentInstanceId
      AND e.guildId=OLD.guildId AND e.status IN ('SOLD','RETURNED')))
    BEGIN SELECT RAISE(ABORT,'Escrowed equipment cannot be mutated'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_equipment_protected_fields BEFORE UPDATE ON RpgEquipmentInstance
    WHEN OLD.status='ESCROWED' AND (NEW.itemId IS NOT OLD.itemId OR NEW.catalogVersion IS NOT OLD.catalogVersion
      OR NEW.slot IS NOT OLD.slot OR NEW.enhancementLevel IS NOT OLD.enhancementLevel OR NEW.pityBps IS NOT OLD.pityBps
      OR NEW.bindingStatus IS NOT OLD.bindingStatus OR NEW.acquiredSource IS NOT OLD.acquiredSource)
    BEGIN SELECT RAISE(ABORT,'Escrowed equipment fields are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_equipment_no_delete BEFORE DELETE ON RpgEquipmentInstance
    WHEN OLD.status='ESCROWED' BEGIN SELECT RAISE(ABORT,'Escrowed equipment cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_market_profile_no_escrow_equip BEFORE UPDATE ON RpgProfile
    WHEN EXISTS (SELECT 1 FROM RpgEquipmentInstance e WHERE e.status='ESCROWED' AND e.guildId=NEW.guildId
      AND e.ownerId=NEW.userId AND e.equipmentInstanceId IN
      (NEW.activeWeaponInstanceId,NEW.activeArmorInstanceId,NEW.activeAccessoryInstanceId))
    BEGIN SELECT RAISE(ABORT,'Escrowed equipment cannot be equipped'); END""",
)

REQUIRED_TABLES = {
    "MarketplaceListing", "MarketplaceEscrow", "MarketplaceSale", "MarketplaceReturn",
    "MarketplaceWatch", "MarketplaceReport", "MarketplaceUserState", "MarketplaceUserStateAudit",
    "MarketplaceQuantityMutation", "MarketplaceSettlementEvidence", "MarketplaceRecoveryReview",
    "MarketplaceNotificationOutbox",
}
REQUIRED_INDEXES = {
    "idx_market_listing_browse", "idx_market_listing_seller", "idx_market_listing_item",
    "idx_market_equipment_unresolved", "idx_market_escrow_owner", "idx_market_sale_unresolved_buyer",
    "idx_market_sale_buyer", "idx_market_sale_seller", "idx_market_sale_price",
    "idx_market_return_status", "idx_market_watch_user", "idx_market_watch_notification",
    "idx_market_report_listing", "idx_market_report_actor", "idx_rpg_inventory_user",
    "idx_market_report_unresolved", "idx_market_quantity_listing", "idx_market_recovery_open",
    "idx_market_outbox_delivery", "idx_market_outbox_listing", "idx_market_user_state_audit",
}
REQUIRED_TRIGGERS = {
    statement.split("TRIGGER IF NOT EXISTS ", 1)[1].split()[0] for statement in PHASE4_TRIGGER_SQL
}

PHASE4_MIGRATION_CHECKSUM = hashlib.sha256(
    (STACK_MIGRATION_ALGORITHM + "\n" + PHASE4_SCHEMA_SQL + "\n" + "\n".join(PHASE4_TRIGGER_SQL)).encode("utf-8")
).hexdigest()


def _split_sql(script):
    statements, buffer = [], ""
    for line in script.splitlines():
        buffer += line + "\n"
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        raise ValueError("Schema Phase 4 tidak lengkap.")
    return statements


async def _columns(db, table):
    marker = await db.fetchrow(f'PRAGMA table_info("{table}")') as cursor:
        return {row[1]: row for row in await cursor.fetchall()}


async def _object_names(db, object_type):
    row = await db.fetchrow("SELECT name FROM sqlite_master WHERE type=$1", object_type) as cursor:
        return {row[0] for row in await cursor.fetchall()}


async def phase4_schema_capability(db):
    try:
        stack_columns = await _columns(db, "RpgInventoryStack")
        sale_columns = await _columns(db, "MarketplaceSale")
        required_stack = {"guildId", "userId", "itemId", "catalogVersion", "bindingStatus", "status", "quantity", "version"}
        pk_order = [row[1] for row in sorted(stack_columns.values(), key=lambda row: row[5]) if row[5] > 0]
        async with db.execute(
            "SELECT checksum,status FROM EconomySchemaMigration WHERE version=$1", ECONOMY_PHASE4_MIGRATION_VERSION,),
        )
        tables = await _object_names(db, "table")
        indexes = await _object_names(db, "index")
        triggers = await _object_names(db, "trigger")
        return bool(
            marker and marker[1] == "COMPLETED" and marker[0] == PHASE4_MIGRATION_CHECKSUM
            and required_stack.issubset(stack_columns)
            and "authorizationSource" in sale_columns
            and pk_order == ["guildId", "userId", "itemId", "catalogVersion", "bindingStatus"]
            and REQUIRED_TABLES.issubset(tables)
            and REQUIRED_INDEXES.issubset(indexes)
            and REQUIRED_TRIGGERS.issubset(triggers)
    except aiosqlite.Error:
        return False


def _rows_checksum(rows):
    return hashlib.sha256(json.dumps(rows, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


async def _rebuild_stack(db, now, *, failure_stage=None):
    columns = await _columns(db, "RpgInventoryStack")
    if {"catalogVersion", "bindingStatus", "status"}.issubset(columns):
        pk_order = [row[1] for row in sorted(columns.values(), key=lambda row: row[5]) if row[5] > 0]
        if pk_order != ["guildId", "userId", "itemId", "catalogVersion", "bindingStatus"]:
            raise ValueError("Primary key RpgInventoryStack Phase 4 tidak cocok.")
        return
    required_legacy = {"guildId", "userId", "itemId", "quantity", "version", "createdAt", "updatedAt"}
    if not required_legacy.issubset(columns):
        raise ValueError("Schema RpgInventoryStack legacy tidak dikenali.")
    manifest = await db.fetchrow(
        "SELECT guildId,userId,itemId,quantity,version,createdAt,updatedAt "
        "FROM RpgInventoryStack ORDER BY guildId,userId,itemId"
        source = [tuple(row) for row in await cursor.fetchall()]
    expected_hash = catalog_hash()
    async with db.execute(
        "SELECT catalogHash FROM RpgCatalogManifest WHERE catalogVersion=$1", RPG_PHASE3_CATALOG_VERSION,),
    )
    provenance_valid = bool(manifest and manifest[0] == expected_hash)
    marker = await db.fetchrow(
        "SELECT itemId FROM RpgCatalogItem WHERE catalogVersion=$1", RPG_PHASE3_CATALOG_VERSION,),
        known_items = {row[0] for row in await cursor.fetchall()} if provenance_valid else set()
    await db.execute("""CREATE TABLE RpgInventoryStack_phase4 (
        guildId TEXT NOT NULL, userId TEXT NOT NULL, itemId TEXT NOT NULL,
        catalogVersion TEXT NOT NULL, bindingStatus TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVIEW_REQUIRED'),
        quantity INTEGER NOT NULL CHECK(quantity>=0), version INTEGER NOT NULL DEFAULT 0,
        createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
        PRIMARY KEY(guildId,userId,itemId,catalogVersion,bindingStatus)""")
    if failure_stage == "after_stack_create":
        raise RuntimeError("Injected Phase 4 migration failure")


    target = []
    for row in source:
        proven = provenance_valid and row[2] in known_items
        migrated = (
            row[0], row[1], row[2], RPG_PHASE3_CATALOG_VERSION if proven else "UNRESOLVED",
            "UNBOUND" if proven else "LEGACY_BOUND", "ACTIVE" if proven else "REVIEW_REQUIRED",
            row[3], row[4], row[5], row[6],
        )
        target.append(migrated)
        await db.execute(
            "INSERT INTO RpgInventoryStack_phase4 "
            "(guildId,userId,itemId,catalogVersion,bindingStatus,status,quantity,version,createdAt,updatedAt) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)", migrated,
        )
    if failure_stage == "after_stack_copy":
        raise RuntimeError("Injected Phase 4 migration failure")
    async with db.execute(
        "SELECT guildId,userId,itemId,catalogVersion,bindingStatus,status,quantity,version,createdAt,updatedAt "
        "FROM RpgInventoryStack_phase4 ORDER BY guildId,userId,itemId,catalogVersion,bindingStatus"
        copied = [tuple(row) for row in await cursor.fetchall()]
    expected_target = sorted(target)
    if copied != expected_target or _rows_checksum(copied) != _rows_checksum(expected_target):
        raise ValueError("Rekonsiliasi key/checksum stack Phase 4 gagal.")
    if sum(row[3] for row in source) != sum(row[6] for row in copied) or len(source) != len(copied):
        raise ValueError("Rekonsiliasi quantity stack Phase 4 gagal.")
    await db.execute("DROP INDEX IF EXISTS idx_rpg_inventory_user")
    await db.execute("ALTER TABLE RpgInventoryStack RENAME TO RpgInventoryStack_phase3_old")
    await db.execute("ALTER TABLE RpgInventoryStack_phase4 RENAME TO RpgInventoryStack")
    await db.execute("DROP TABLE RpgInventoryStack_phase3_old")
    await db.execute(
        "CREATE INDEX idx_rpg_inventory_user ON RpgInventoryStack(guildId,userId,itemId,catalogVersion,bindingStatus)"
    if failure_stage == "after_stack_swap":
        raise RuntimeError("Injected Phase 4 migration failure")


async def _ensure_hardening_columns(db):
    tables = await _object_names(db, "table")
    if "MarketplaceSale" in tables:
        columns = await _columns(db, "MarketplaceSale")
        if "authorizationSource" not in columns:
            await db.execute(
                "ALTER TABLE MarketplaceSale ADD COLUMN authorizationSource TEXT NOT NULL DEFAULT 'DISCORD'"


async def migrate_phase4_schema(db_path, *, failure_stage=None):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                "SELECT checksum,status FROM EconomySchemaMigration WHERE version=$1", ECONOMY_PHASE4_MIGRATION_VERSION,),
            )
            if marker and marker[1] == "COMPLETED":
                if marker[0] not in (PHASE4_MIGRATION_CHECKSUM, PHASE4_PRE_HARDENING_CHECKSUM):
                    raise ValueError("Checksum migration Phase 4 tidak cocok.")
                if marker[0] == PHASE4_MIGRATION_CHECKSUM and not await phase4_schema_capability(db):
                    raise ValueError("Marker Phase 4 tidak cocok dengan schema aktual.")
                if marker[0] == PHASE4_MIGRATION_CHECKSUM:
                    await db.rollback()
                    return {"applied": False, "idempotent": True, "checksum": PHASE4_MIGRATION_CHECKSUM}
            now = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "INSERT OR REPLACE INTO EconomySchemaMigration "
                "(version,name,checksum,status,startedAt,detailsJson) VALUES ($1,$2,$3,$4,$5,$6)",
                (ECONOMY_PHASE4_MIGRATION_VERSION, "phase4-marketplace", PHASE4_MIGRATION_CHECKSUM,
                 "RUNNING", now, json.dumps({"stack_algorithm": STACK_MIGRATION_ALGORITHM}, separators=(",", ":")),
            )
            if failure_stage == "after_marker":
                raise RuntimeError("Injected Phase 4 migration failure")
            await _rebuild_stack(db, now, failure_stage=failure_stage)
            await _ensure_hardening_columns(db)
            if "MarketplaceReport" in await _object_names(db, "table"):
                async with db.execute(
                    "SELECT guildId,reporterId,listingId,COUNT(*) FROM MarketplaceReport "
                    "WHERE status IN ('OPEN','IN_REVIEW') GROUP BY guildId,reporterId,listingId HAVING COUNT(*)>1 LIMIT 1"
                        if row:
                        raise ValueError("Report unresolved duplikat wajib direkonsiliasi sebelum hardening.")
            await db.execute("DROP TRIGGER IF EXISTS trg_market_listing_escrow_quantity")
            for index, statement in enumerate(_split_sql(PHASE4_SCHEMA_SQL)):
                await db.execute(statement)
                if failure_stage == "after_listing" and "CREATE TABLE IF NOT EXISTS MarketplaceListing" in statement:
                    raise RuntimeError("Injected Phase 4 migration failure")
                if failure_stage == "after_escrow" and "CREATE TABLE IF NOT EXISTS MarketplaceEscrow" in statement:
                    raise RuntimeError("Injected Phase 4 migration failure")
            for trigger in PHASE4_TRIGGER_SQL:
                await db.execute(trigger)
            if failure_stage == "after_triggers":
                raise RuntimeError("Injected Phase 4 migration failure")
            async with db.execute("PRAGMA foreign_key_check") as cursor:
                if await cursor.fetchall():
                    raise ValueError("foreign_key_check gagal setelah migration Phase 4.")
            async with db.execute("PRAGMA integrity_check") as cursor:
                if (await cursor.fetchone())[0] != "ok":
                    raise ValueError("integrity_check gagal setelah migration Phase 4.")
            await db.execute(
                "UPDATE EconomySchemaMigration SET status='COMPLETED',completedAt=$1 WHERE version=$2",
                (now, ECONOMY_PHASE4_MIGRATION_VERSION),
            )
            if failure_stage == "after_marker_complete":
                raise RuntimeError("Injected Phase 4 migration failure")
            if not await phase4_schema_capability(db):
                raise ValueError("Capability schema Phase 4 gagal setelah migration.")
            if failure_stage == "before_commit":
                raise RuntimeError("Injected Phase 4 migration failure")
            await db.commit()
            return {"applied": True, "idempotent": False, "checksum": PHASE4_MIGRATION_CHECKSUM}
        except Exception:
            await db.rollback()
            raise
