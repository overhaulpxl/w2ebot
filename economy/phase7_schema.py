"""Schema Mining Phase 7 yang hanya dipasang oleh migrasi eksplisit."""

import hashlib
import re

from .constants import ECONOMY_PHASE7_MIGRATION_VERSION, MINING_RIG_CATALOG
from .phase3_schema import PHASE3_HARDENING_CHECKSUM, PHASE3_HARDENING_VERSION
from .phase6_schema import phase6_capability, phase6_capability_sync


PHASE7_MIGRATION_NAME = "phase7-mining"
PHASE7_CATALOG_VERSION = "mining-v1.0.0"

PHASE7_TABLE_SQL = r"""
CREATE TABLE IF NOT EXISTS MiningRigCatalog (
    rigDefinitionId TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    purchasePriceEcy INTEGER NOT NULL CHECK(purchasePriceEcy>0),
    grossEquivalentPerDay INTEGER NOT NULL CHECK(grossEquivalentPerDay>0),
    maintenancePriceEcy INTEGER NOT NULL CHECK(maintenancePriceEcy>0),
    catalogVersion TEXT NOT NULL,
    createdAt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS MiningRigInstance (
    rigInstanceId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    rigDefinitionId TEXT NOT NULL,
    catalogVersion TEXT NOT NULL,
    targetSymbol TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','MAINTENANCE_DUE','REVIEW_REQUIRED')),
    durabilityBps INTEGER NOT NULL DEFAULT 10000 CHECK(durabilityBps=10000),
    paidThrough TEXT,
    accruedThrough TEXT NOT NULL,
    migrationSourceHash TEXT,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    FOREIGN KEY(rigDefinitionId) REFERENCES MiningRigCatalog(rigDefinitionId),
    FOREIGN KEY(targetSymbol) REFERENCES CryptoAssetDefinition(symbol)
);
CREATE TABLE IF NOT EXISTS MiningPendingAsset (
    rigInstanceId TEXT NOT NULL,
    symbol TEXT NOT NULL,
    pendingUnits INTEGER NOT NULL DEFAULT 0 CHECK(pendingUnits>=0),
    fractionalBillionths INTEGER NOT NULL DEFAULT 0 CHECK(fractionalBillionths BETWEEN 0 AND 999999999),
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    updatedAt TEXT NOT NULL,
    PRIMARY KEY(rigInstanceId,symbol),
    FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId),
    FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol)
);
CREATE TABLE IF NOT EXISTS MiningOperation (
    operationId TEXT PRIMARY KEY,
    requestId TEXT NOT NULL,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    operationType TEXT NOT NULL CHECK(operationType IN ('PURCHASE','MAINTENANCE','TARGET_CHANGE','ACCRUAL','CLAIM')),
    rigInstanceId TEXT,
    reservationKey TEXT,
    outcomeJson TEXT NOT NULL,
    resultJson TEXT,
    transactionId TEXT,
    status TEXT NOT NULL CHECK(status IN ('RESERVED','COMMITTED','VOID','REVIEW_REQUIRED')),
    retryCount INTEGER NOT NULL DEFAULT 0 CHECK(retryCount>=0),
    lastErrorCode TEXT,
    lastAttemptedAt TEXT,
    reviewMetadataJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL,
    settledAt TEXT,
    UNIQUE(guildId,requestId),
    FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId),
    CHECK((status IN ('RESERVED','REVIEW_REQUIRED') AND reservationKey IS NOT NULL AND resultJson IS NULL AND settledAt IS NULL)
       OR (status IN ('COMMITTED','VOID') AND reservationKey IS NULL AND resultJson IS NOT NULL AND settledAt IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS MiningPurchase (
    purchaseId TEXT PRIMARY KEY,
    operationId TEXT NOT NULL UNIQUE,
    rigInstanceId TEXT NOT NULL UNIQUE,
    priceEcy INTEGER NOT NULL CHECK(priceEcy>0),
    miningEcy INTEGER NOT NULL CHECK(miningEcy>=0),
    reserveEcy INTEGER NOT NULL CHECK(reserveEcy>=0),
    burnEcy INTEGER NOT NULL CHECK(burnEcy>=0),
    transactionId TEXT NOT NULL UNIQUE,
    createdAt TEXT NOT NULL,
    FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId),
    FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId),
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId),
    CHECK(miningEcy+reserveEcy+burnEcy=priceEcy)
);
CREATE TABLE IF NOT EXISTS MiningMaintenancePayment (
    paymentId TEXT PRIMARY KEY,
    operationId TEXT NOT NULL UNIQUE,
    rigInstanceId TEXT NOT NULL,
    periodStart TEXT NOT NULL,
    periodEnd TEXT NOT NULL,
    priceEcy INTEGER NOT NULL CHECK(priceEcy>0),
    miningEcy INTEGER NOT NULL CHECK(miningEcy>=0),
    reserveEcy INTEGER NOT NULL CHECK(reserveEcy>=0),
    burnEcy INTEGER NOT NULL CHECK(burnEcy>=0),
    transactionId TEXT NOT NULL UNIQUE,
    createdAt TEXT NOT NULL,
    FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId),
    FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId),
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId),
    CHECK(miningEcy+reserveEcy+burnEcy=priceEcy)
);
CREATE TABLE IF NOT EXISTS MiningTargetChange (
    changeId TEXT PRIMARY KEY,
    operationId TEXT NOT NULL UNIQUE,
    rigInstanceId TEXT NOT NULL,
    previousSymbol TEXT NOT NULL,
    targetSymbol TEXT NOT NULL,
    changedAt TEXT NOT NULL,
    FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId),
    FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId)
);
CREATE TABLE IF NOT EXISTS MiningAccrualCheckpoint (
    checkpointId TEXT PRIMARY KEY,
    operationId TEXT NOT NULL UNIQUE,
    rigInstanceId TEXT NOT NULL,
    symbol TEXT NOT NULL,
    observedAt TEXT NOT NULL,
    previousAccruedThrough TEXT NOT NULL,
    rewardedSeconds INTEGER NOT NULL CHECK(rewardedSeconds BETWEEN 0 AND 86400),
    discardedSeconds INTEGER NOT NULL CHECK(discardedSeconds>=0),
    windowStart TEXT,
    windowEnd TEXT,
    sampleCount INTEGER NOT NULL CHECK(sampleCount>=0),
    priceSum INTEGER NOT NULL CHECK(priceSum>=0),
    averagePriceEcy INTEGER CHECK(averagePriceEcy>0),
    latestHistoryId TEXT,
    priceReferenceHash TEXT,
    numeratorText TEXT NOT NULL,
    denominatorText TEXT NOT NULL,
    calculationHash TEXT NOT NULL,
    creditedUnits INTEGER NOT NULL CHECK(creditedUnits>=0),
    previousCarry INTEGER NOT NULL CHECK(previousCarry BETWEEN 0 AND 999999999),
    resultingCarry INTEGER NOT NULL CHECK(resultingCarry BETWEEN 0 AND 999999999),
    createdAt TEXT NOT NULL,
    FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId),
    FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId),
    FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol)
);
CREATE TABLE IF NOT EXISTS MiningClaim (
    claimId TEXT PRIMARY KEY,
    operationId TEXT NOT NULL UNIQUE,
    requestId TEXT NOT NULL,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    rigInstanceId TEXT NOT NULL,
    outcomeJson TEXT NOT NULL,
    receiptJson TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status='COMMITTED'),
    createdAt TEXT NOT NULL,
    settledAt TEXT NOT NULL,
    UNIQUE(guildId,requestId),
    FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId),
    FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId)
);
CREATE TABLE IF NOT EXISTS MiningClaimAsset (
    claimId TEXT NOT NULL,
    symbol TEXT NOT NULL,
    units INTEGER NOT NULL CHECK(units>0),
    pendingBefore INTEGER NOT NULL CHECK(pendingBefore>=units),
    pendingAfter INTEGER NOT NULL CHECK(pendingAfter>=0),
    holdingBefore INTEGER NOT NULL CHECK(holdingBefore>=0),
    holdingAfter INTEGER NOT NULL CHECK(holdingAfter>=units),
    PRIMARY KEY(claimId,symbol),
    FOREIGN KEY(claimId) REFERENCES MiningClaim(claimId),
    FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol)
);
CREATE TABLE IF NOT EXISTS MiningAssetLedger (
    entryId TEXT PRIMARY KEY,
    claimId TEXT NOT NULL,
    operationId TEXT NOT NULL,
    symbol TEXT NOT NULL,
    accountType TEXT NOT NULL CHECK(accountType IN ('RIG_PENDING','USER_HOLDING')),
    accountId TEXT NOT NULL,
    unitsDelta INTEGER NOT NULL CHECK(unitsDelta<>0),
    createdAt TEXT NOT NULL,
    UNIQUE(claimId,symbol,accountType),
    FOREIGN KEY(claimId) REFERENCES MiningClaim(claimId),
    FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId)
);
CREATE TABLE IF NOT EXISTS MiningNotificationOutbox (
    outboxId TEXT PRIMARY KEY,
    operationId TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    eventType TEXT NOT NULL,
    payloadJson TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','CLAIMED','SENT','FAILED','REVIEW_REQUIRED')),
    leaseOwner TEXT,
    leaseExpiresAt TEXT,
    attemptCount INTEGER NOT NULL DEFAULT 0 CHECK(attemptCount>=0),
    messageId TEXT,
    lastErrorCode TEXT,
    createdAt TEXT NOT NULL,
    sentAt TEXT,
    FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId)
);
CREATE TABLE IF NOT EXISTS MiningRecoveryReview (
    reviewId TEXT PRIMARY KEY,
    guildId TEXT,
    entityType TEXT NOT NULL,
    entityId TEXT NOT NULL,
    errorCode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','RESOLVED')),
    sanitizedMetadataJson TEXT NOT NULL DEFAULT '{}',
    firstDetectedAt TEXT NOT NULL,
    lastAttemptedAt TEXT NOT NULL,
    resolvedAt TEXT,
    UNIQUE(guildId,entityType,entityId,errorCode)
);
CREATE TABLE IF NOT EXISTS MiningLegacyRigMigration (
    sourceUserId TEXT NOT NULL,
    sourceSymbol TEXT NOT NULL,
    sourceTierText TEXT NOT NULL,
    sourceOrdinal INTEGER NOT NULL CHECK(sourceOrdinal>0),
    sourceHash TEXT NOT NULL,
    targetGuildId TEXT,
    rigInstanceId TEXT,
    status TEXT NOT NULL CHECK(status IN ('MIGRATED','REVIEW_REQUIRED')),
    errorCode TEXT,
    rawSourceJson TEXT NOT NULL,
    sanitizedMetadataJson TEXT NOT NULL DEFAULT '{}',
    migratedAt TEXT NOT NULL,
    PRIMARY KEY(sourceUserId,sourceSymbol,sourceTierText,sourceOrdinal)
);
CREATE TABLE IF NOT EXISTS MiningAuthorization (
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    permissionClass TEXT NOT NULL CHECK(permissionClass IN ('MINING_CONTROL','MINING_RECOVERY')),
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    grantedById TEXT NOT NULL,
    reason TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId,userId,permissionClass)
);
CREATE TABLE IF NOT EXISTS MiningAuthorizationAudit (
    auditId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    actorId TEXT NOT NULL,
    subjectId TEXT NOT NULL,
    permissionClass TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    reason TEXT NOT NULL,
    createdAt TEXT NOT NULL
);
"""

PHASE7_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_mining_rig_owner ON MiningRigInstance(guildId,userId,status,createdAt)",
    "CREATE INDEX IF NOT EXISTS idx_mining_operation_status ON MiningOperation(status,lastAttemptedAt,createdAt)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_mining_operation_reservation ON MiningOperation(reservationKey) WHERE status IN ('RESERVED','REVIEW_REQUIRED')",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_mining_purchase_user ON MiningOperation(guildId,userId) WHERE operationType='PURCHASE' AND status IN ('RESERVED','REVIEW_REQUIRED')",
    "CREATE INDEX IF NOT EXISTS idx_mining_checkpoint_rig ON MiningAccrualCheckpoint(rigInstanceId,observedAt DESC)",
    "CREATE INDEX IF NOT EXISTS idx_mining_claim_user ON MiningClaim(guildId,userId,createdAt DESC)",
    "CREATE INDEX IF NOT EXISTS idx_mining_outbox_status ON MiningNotificationOutbox(status,leaseExpiresAt,createdAt)",
    "CREATE INDEX IF NOT EXISTS idx_mining_review_status ON MiningRecoveryReview(status,lastAttemptedAt)",
    "CREATE INDEX IF NOT EXISTS idx_mining_auth_user ON MiningAuthorization(guildId,userId,enabled)",
)

PHASE7_TRIGGER_SQL = (
    """CREATE TRIGGER IF NOT EXISTS trg_mining_catalog_no_update BEFORE UPDATE ON MiningRigCatalog BEGIN SELECT RAISE(ABORT,'mining catalog is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_catalog_no_delete BEFORE DELETE ON MiningRigCatalog BEGIN SELECT RAISE(ABORT,'mining catalog cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_operation_plan_immutable BEFORE UPDATE ON MiningOperation WHEN NEW.requestId<>OLD.requestId OR NEW.guildId<>OLD.guildId OR NEW.userId<>OLD.userId OR NEW.operationType<>OLD.operationType OR NEW.rigInstanceId IS NOT OLD.rigInstanceId OR NEW.outcomeJson<>OLD.outcomeJson OR NEW.transactionId IS NOT OLD.transactionId BEGIN SELECT RAISE(ABORT,'mining operation plan is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_operation_transition BEFORE UPDATE OF status ON MiningOperation WHEN NOT ((OLD.status='RESERVED' AND NEW.status IN ('COMMITTED','VOID','REVIEW_REQUIRED')) OR (OLD.status='REVIEW_REQUIRED' AND NEW.status IN ('COMMITTED','VOID')) OR OLD.status=NEW.status) BEGIN SELECT RAISE(ABORT,'invalid mining operation transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_operation_receipt BEFORE UPDATE ON MiningOperation WHEN (OLD.resultJson IS NOT NULL AND NEW.resultJson IS NOT OLD.resultJson) OR (OLD.resultJson IS NULL AND NEW.resultJson IS NOT NULL AND NEW.status NOT IN ('COMMITTED','VOID')) OR OLD.status IN ('COMMITTED','VOID') BEGIN SELECT RAISE(ABORT,'mining operation receipt is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_operation_reservation BEFORE UPDATE ON MiningOperation WHEN (NEW.status IN ('RESERVED','REVIEW_REQUIRED') AND (NEW.reservationKey IS NULL OR NEW.reservationKey<>OLD.reservationKey)) OR (NEW.status IN ('COMMITTED','VOID') AND NEW.reservationKey IS NOT NULL) BEGIN SELECT RAISE(ABORT,'invalid mining reservation transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_operation_no_delete BEFORE DELETE ON MiningOperation BEGIN SELECT RAISE(ABORT,'mining operations cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_rig_no_delete BEFORE DELETE ON MiningRigInstance BEGIN SELECT RAISE(ABORT,'mining rigs cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_rig_identity_immutable BEFORE UPDATE ON MiningRigInstance WHEN NEW.rigInstanceId<>OLD.rigInstanceId OR NEW.guildId<>OLD.guildId OR NEW.userId<>OLD.userId OR NEW.rigDefinitionId<>OLD.rigDefinitionId OR NEW.catalogVersion<>OLD.catalogVersion OR NEW.createdAt<>OLD.createdAt BEGIN SELECT RAISE(ABORT,'mining rig identity is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_purchase_no_update BEFORE UPDATE ON MiningPurchase BEGIN SELECT RAISE(ABORT,'mining purchases are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_purchase_no_delete BEFORE DELETE ON MiningPurchase BEGIN SELECT RAISE(ABORT,'mining purchases cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_maintenance_no_update BEFORE UPDATE ON MiningMaintenancePayment BEGIN SELECT RAISE(ABORT,'mining maintenance history is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_maintenance_no_delete BEFORE DELETE ON MiningMaintenancePayment BEGIN SELECT RAISE(ABORT,'mining maintenance history cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_target_no_update BEFORE UPDATE ON MiningTargetChange BEGIN SELECT RAISE(ABORT,'mining target history is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_target_no_delete BEFORE DELETE ON MiningTargetChange BEGIN SELECT RAISE(ABORT,'mining target history cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_claim_no_update BEFORE UPDATE ON MiningClaim BEGIN SELECT RAISE(ABORT,'mining claims are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_claim_no_delete BEFORE DELETE ON MiningClaim BEGIN SELECT RAISE(ABORT,'mining claims cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_claim_asset_no_update BEFORE UPDATE ON MiningClaimAsset BEGIN SELECT RAISE(ABORT,'mining claim assets are append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_claim_asset_no_delete BEFORE DELETE ON MiningClaimAsset BEGIN SELECT RAISE(ABORT,'mining claim assets cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_asset_ledger_no_update BEFORE UPDATE ON MiningAssetLedger BEGIN SELECT RAISE(ABORT,'mining asset ledger is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_asset_ledger_no_delete BEFORE DELETE ON MiningAssetLedger BEGIN SELECT RAISE(ABORT,'mining asset ledger cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_checkpoint_no_update BEFORE UPDATE ON MiningAccrualCheckpoint BEGIN SELECT RAISE(ABORT,'mining checkpoints are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_checkpoint_no_delete BEFORE DELETE ON MiningAccrualCheckpoint BEGIN SELECT RAISE(ABORT,'mining checkpoints cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_outbox_transition BEFORE UPDATE OF status ON MiningNotificationOutbox WHEN NOT ((OLD.status IN ('PENDING','FAILED') AND NEW.status IN ('CLAIMED','REVIEW_REQUIRED')) OR (OLD.status='CLAIMED' AND NEW.status IN ('SENT','FAILED','REVIEW_REQUIRED')) OR OLD.status=NEW.status) BEGIN SELECT RAISE(ABORT,'invalid mining outbox transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_outbox_no_delete BEFORE DELETE ON MiningNotificationOutbox BEGIN SELECT RAISE(ABORT,'mining outbox cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_review_no_delete BEFORE DELETE ON MiningRecoveryReview BEGIN SELECT RAISE(ABORT,'mining recovery review cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_legacy_no_update BEFORE UPDATE ON MiningLegacyRigMigration BEGIN SELECT RAISE(ABORT,'mining legacy rows are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_legacy_no_delete BEFORE DELETE ON MiningLegacyRigMigration BEGIN SELECT RAISE(ABORT,'mining legacy rows cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_auth_audit_no_update BEFORE UPDATE ON MiningAuthorizationAudit BEGIN SELECT RAISE(ABORT,'mining authorization audit is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_mining_auth_audit_no_delete BEFORE DELETE ON MiningAuthorizationAudit BEGIN SELECT RAISE(ABORT,'mining authorization audit cannot be deleted'); END""",
)


def _canonical(value):
    return " ".join(str(value).split())


PHASE7_SCHEMA_CHECKSUM = hashlib.sha256(
    (PHASE7_MIGRATION_NAME + "\n" + _canonical(PHASE7_TABLE_SQL) + "\n" +
     "\n".join(_canonical(value) for value in PHASE7_INDEX_SQL + PHASE7_TRIGGER_SQL)).encode("utf-8")
).hexdigest()

REQUIRED_PHASE7_TABLES = {
    "MiningRigCatalog", "MiningRigInstance", "MiningPendingAsset", "MiningOperation",
    "MiningPurchase", "MiningMaintenancePayment", "MiningTargetChange",
    "MiningAccrualCheckpoint", "MiningClaim", "MiningClaimAsset", "MiningAssetLedger",
    "MiningNotificationOutbox", "MiningRecoveryReview", "MiningLegacyRigMigration",
    "MiningAuthorization", "MiningAuthorizationAudit",
}
REQUIRED_PHASE7_INDEXES = {re.search(r"INDEX IF NOT EXISTS (\w+)", value).group(1) for value in PHASE7_INDEX_SQL}
REQUIRED_PHASE7_TRIGGERS = {re.search(r"TRIGGER IF NOT EXISTS (\w+)", value).group(1) for value in PHASE7_TRIGGER_SQL}


def phase3_profile_capability_sync(connection):
    migrations = dict(connection.execute(
        "SELECT version,checksum FROM EconomySchemaMigration WHERE status='COMPLETED' AND version IN (300,?)",
        (PHASE3_HARDENING_VERSION,),
    ).fetchall())
    if 300 not in migrations or migrations.get(PHASE3_HARDENING_VERSION) != PHASE3_HARDENING_CHECKSUM:
        return False
    row = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='RpgProfile'").fetchone()
    if not row:
        return False
    sql = " ".join(row[0].lower().split())
    required = {"guildId", "userId", "level", "currentHp", "maxHp"}
    info = connection.execute('PRAGMA table_info("RpgProfile")').fetchall()
    columns = {item[1] for item in info}
    pk = [item[1] for item in sorted(info, key=lambda value: value[5]) if item[5]]
    indexes = {item[1] for item in connection.execute('PRAGMA index_list("RpgProfile")').fetchall()}
    return (required.issubset(columns) and pk == ["guildId", "userId"]
            and "level between 1 and 100" in sql and "currenthp >= 0" in sql
            and "currenthp <= maxhp" not in sql
            and {"idx_rpg_profile_level", "idx_rpg_profile_user"}.issubset(indexes))


async def phase3_profile_capability(db):
    async with db.execute(
        "SELECT version,checksum FROM EconomySchemaMigration WHERE status='COMPLETED' AND version IN (300,?)",
        (PHASE3_HARDENING_VERSION,),
    ) as cursor:
        migrations = dict(await cursor.fetchall())
    if 300 not in migrations or migrations.get(PHASE3_HARDENING_VERSION) != PHASE3_HARDENING_CHECKSUM:
        return False
    async with db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='RpgProfile'") as cursor:
        row = await cursor.fetchone()
    if not row:
        return False
    sql = " ".join(row[0].lower().split())
    async with db.execute('PRAGMA table_info("RpgProfile")') as cursor:
        info = await cursor.fetchall()
    async with db.execute('PRAGMA index_list("RpgProfile")') as cursor:
        indexes = {item[1] for item in await cursor.fetchall()}
    columns = {item[1] for item in info}
    pk = [item[1] for item in sorted(info, key=lambda value: value[5]) if item[5]]
    return ({"guildId", "userId", "level", "currentHp", "maxHp"}.issubset(columns)
            and pk == ["guildId", "userId"] and "level between 1 and 100" in sql
            and "currenthp >= 0" in sql and "currenthp <= maxhp" not in sql
            and {"idx_rpg_profile_level", "idx_rpg_profile_user"}.issubset(indexes))


def phase7_capability_sync(connection):
    if not phase3_profile_capability_sync(connection) or not phase6_capability_sync(connection):
        return False
    marker = connection.execute(
        "SELECT checksum,status FROM EconomySchemaMigration WHERE version=?",
        (ECONOMY_PHASE7_MIGRATION_VERSION,),
    ).fetchone()
    if marker != (PHASE7_SCHEMA_CHECKSUM, "COMPLETED"):
        return False
    objects = dict(connection.execute(
        "SELECT name,type FROM sqlite_master WHERE name LIKE 'Mining%' OR name LIKE 'idx_mining_%' OR name LIKE 'uq_mining_%' OR name LIKE 'trg_mining_%'"
    ).fetchall())
    if not all(objects.get(name) == "table" for name in REQUIRED_PHASE7_TABLES):
        return False
    if not all(objects.get(name) == "index" for name in REQUIRED_PHASE7_INDEXES):
        return False
    if not all(objects.get(name) == "trigger" for name in REQUIRED_PHASE7_TRIGGERS):
        return False
    definitions = connection.execute(
        "SELECT rigDefinitionId,name,purchasePriceEcy,grossEquivalentPerDay,maintenancePriceEcy FROM MiningRigCatalog ORDER BY rigDefinitionId"
    ).fetchall()
    return definitions == sorted((key, *value) for key, value in MINING_RIG_CATALOG.items())


async def phase7_capability(db):
    if not await phase3_profile_capability(db) or not await phase6_capability(db):
        return False
    async with db.execute(
        "SELECT checksum,status FROM EconomySchemaMigration WHERE version=?",
        (ECONOMY_PHASE7_MIGRATION_VERSION,),
    ) as cursor:
        marker = await cursor.fetchone()
    if not marker or tuple(marker) != (PHASE7_SCHEMA_CHECKSUM, "COMPLETED"):
        return False
    async with db.execute(
        "SELECT name,type FROM sqlite_master WHERE name LIKE 'Mining%' OR name LIKE 'idx_mining_%' OR name LIKE 'uq_mining_%' OR name LIKE 'trg_mining_%'"
    ) as cursor:
        objects = dict(await cursor.fetchall())
    if not all(objects.get(name) == "table" for name in REQUIRED_PHASE7_TABLES):
        return False
    if not all(objects.get(name) == "index" for name in REQUIRED_PHASE7_INDEXES):
        return False
    if not all(objects.get(name) == "trigger" for name in REQUIRED_PHASE7_TRIGGERS):
        return False
    async with db.execute(
        "SELECT rigDefinitionId,name,purchasePriceEcy,grossEquivalentPerDay,maintenancePriceEcy FROM MiningRigCatalog ORDER BY rigDefinitionId"
    ) as cursor:
        definitions = await cursor.fetchall()
    return definitions == sorted((key, *value) for key, value in MINING_RIG_CATALOG.items())
