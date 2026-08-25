from core import _pool
"""Schema eksplisit Casino V1 Phase 5; tidak dijalankan saat startup."""

import hashlib
import re
import sqlite3


from .constants import ECONOMY_PHASE5_MIGRATION_VERSION


PHASE5_MIGRATION_NAME = "phase5-casino"

PHASE5_TABLE_SQL = r"""
CREATE TABLE IF NOT EXISTS CasinoSession (
    sessionId TEXT PRIMARY KEY,
    requestId TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    gameType TEXT NOT NULL CHECK(gameType IN ('BLACKJACK','SLOT','COINFLIP','RPS','NUMBER','GACHA','BOX')),
    stakeEcy INTEGER NOT NULL CHECK(stakeEcy>=0),
    maximumGrossLiabilityEcy INTEGER NOT NULL CHECK(maximumGrossLiabilityEcy>=0),
    outcomeJson TEXT NOT NULL,
    stateJson TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK(status IN ('RESERVED','ACTIVE','SETTLEMENT_PENDING','COMMITTED','VOID','REVIEW_REQUIRED')),
    reservationKey TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    retryCount INTEGER NOT NULL DEFAULT 0 CHECK(retryCount>=0),
    lastErrorCode TEXT,
    lastAttemptedAt TEXT,
    reviewMetadataJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL,
    expiresAt TEXT,
    settledAt TEXT,
    CHECK((status IN ('RESERVED','ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED') AND reservationKey IS NOT NULL)
       OR (status IN ('COMMITTED','VOID') AND reservationKey IS NULL))
);
CREATE TABLE IF NOT EXISTS CasinoSettlement (
    settlementId TEXT PRIMARY KEY,
    sessionId TEXT NOT NULL UNIQUE,
    transactionId TEXT UNIQUE,
    stakeEcy INTEGER NOT NULL CHECK(stakeEcy>=0),
    grossPayoutEcy INTEGER NOT NULL CHECK(grossPayoutEcy>=0),
    status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','VOID','REVIEW_REQUIRED')),
    receiptJson TEXT,
    voidReasonCode TEXT,
    createdAt TEXT NOT NULL,
    settledAt TEXT,
    FOREIGN KEY(sessionId) REFERENCES CasinoSession(sessionId),
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId),
    CHECK((status='COMMITTED' AND transactionId IS NOT NULL AND receiptJson IS NOT NULL AND voidReasonCode IS NULL)
       OR (status='VOID' AND receiptJson IS NULL AND voidReasonCode IS NOT NULL)
       OR (status IN ('PENDING','REVIEW_REQUIRED') AND receiptJson IS NULL AND voidReasonCode IS NULL))
);
CREATE TABLE IF NOT EXISTS CasinoBankrollReservation (
    reservationId TEXT PRIMARY KEY,
    sessionId TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    liabilityEcy INTEGER NOT NULL CHECK(liabilityEcy>=0),
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','RELEASED','REVIEW_REQUIRED')),
    createdAt TEXT NOT NULL,
    releasedAt TEXT,
    FOREIGN KEY(sessionId) REFERENCES CasinoSession(sessionId),
    CHECK((status='RELEASED' AND releasedAt IS NOT NULL) OR (status!='RELEASED' AND releasedAt IS NULL))
);
CREATE TABLE IF NOT EXISTS CasinoSessionAction (
    actionId TEXT PRIMARY KEY,
    sessionId TEXT NOT NULL,
    requestId TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence>=1),
    actorId TEXT NOT NULL,
    actionType TEXT NOT NULL,
    actionJson TEXT NOT NULL,
    resultJson TEXT NOT NULL,
    transactionId TEXT UNIQUE,
    createdAt TEXT NOT NULL,
    UNIQUE(sessionId,requestId),
    UNIQUE(sessionId,sequence),
    FOREIGN KEY(sessionId) REFERENCES CasinoSession(sessionId),
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId)
);
CREATE TABLE IF NOT EXISTS CasinoBankrollDistribution (
    distributionId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    transactionId TEXT NOT NULL UNIQUE,
    operationType TEXT NOT NULL CHECK(operationType IN ('ADJUST_TOP_UP','ADJUST_WITHDRAW','EXCESS_DISTRIBUTION','INITIAL_SEED')),
    amountEcy INTEGER NOT NULL CHECK(amountEcy>0),
    generalEcy INTEGER NOT NULL DEFAULT 0 CHECK(generalEcy>=0),
    reserveEcy INTEGER NOT NULL DEFAULT 0 CHECK(reserveEcy>=0),
    burnEcy INTEGER NOT NULL DEFAULT 0 CHECK(burnEcy>=0),
    actorId TEXT,
    reasonCode TEXT NOT NULL,
    receiptJson TEXT NOT NULL,
    createdAt TEXT NOT NULL,
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId)
);
CREATE TABLE IF NOT EXISTS CasinoNotificationOutbox (
    eventId TEXT PRIMARY KEY,
    eventKey TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    sessionId TEXT NOT NULL,
    payloadJson TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','CLAIMED','SENT','FAILED','REVIEW_REQUIRED')),
    leaseOwner TEXT,
    leaseExpiresAt TEXT,
    attemptCount INTEGER NOT NULL DEFAULT 0 CHECK(attemptCount>=0),
    messageId TEXT,
    lastErrorCode TEXT,
    createdAt TEXT NOT NULL,
    sentAt TEXT,
    FOREIGN KEY(sessionId) REFERENCES CasinoSession(sessionId)
);
CREATE TABLE IF NOT EXISTS CasinoRecoveryReview (
    reviewId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    entityType TEXT NOT NULL,
    entityId TEXT NOT NULL,
    errorCode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','RESOLVED')),
    retryCount INTEGER NOT NULL DEFAULT 1 CHECK(retryCount>0),
    sanitizedMetadataJson TEXT NOT NULL DEFAULT '{}',
    firstDetectedAt TEXT NOT NULL,
    lastAttemptedAt TEXT NOT NULL,
    resolvedAt TEXT,
    UNIQUE(guildId,entityType,entityId,errorCode)
);
CREATE TABLE IF NOT EXISTS CasinoLegacyStatistic (
    snapshotId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    sourceKey TEXT NOT NULL,
    sourceHash TEXT NOT NULL,
    sanitizedSnapshotJson TEXT NOT NULL,
    migrationStatus TEXT NOT NULL CHECK(migrationStatus IN ('SNAPSHOT','REVIEW_REQUIRED')),
    createdAt TEXT NOT NULL,
    UNIQUE(guildId,userId,sourceKey)
);
CREATE TABLE IF NOT EXISTS CasinoAuthorization (
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    permissionClass TEXT NOT NULL CHECK(permissionClass IN ('CASINO_CONTROL','CASINO_FINANCIAL','CASINO_RECOVERY')),
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    grantedById TEXT NOT NULL,
    reasonCode TEXT NOT NULL,
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId,userId,permissionClass)
);
CREATE TABLE IF NOT EXISTS CasinoAuthorizationAudit (
    auditId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    permissionClass TEXT NOT NULL,
    oldEnabled INTEGER,
    newEnabled INTEGER NOT NULL CHECK(newEnabled IN (0,1)),
    actionType TEXT NOT NULL CHECK(actionType IN ('GRANT','REVOKE','OWNER_OVERRIDE','USE')),
    actorId TEXT NOT NULL,
    reasonCode TEXT NOT NULL,
    createdAt TEXT NOT NULL
);
"""

PHASE5_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_casino_user_unresolved ON CasinoSession(guildId,userId) WHERE status IN ('RESERVED','ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED')",
    "CREATE INDEX IF NOT EXISTS idx_casino_guild_unresolved ON CasinoSession(guildId,status,createdAt)",
    "CREATE INDEX IF NOT EXISTS idx_casino_reservation_exposure ON CasinoBankrollReservation(guildId,status,liabilityEcy)",
    "CREATE INDEX IF NOT EXISTS idx_casino_recovery_status ON CasinoRecoveryReview(guildId,status,lastAttemptedAt)",
    "CREATE INDEX IF NOT EXISTS idx_casino_outbox_status ON CasinoNotificationOutbox(status,leaseExpiresAt,createdAt)",
    "CREATE INDEX IF NOT EXISTS idx_casino_auth_lookup ON CasinoAuthorization(guildId,userId,permissionClass,enabled)",
)

PHASE5_TRIGGER_SQL = (
    """CREATE TRIGGER IF NOT EXISTS trg_casino_session_outcome_immutable BEFORE UPDATE ON CasinoSession
       WHEN NEW.outcomeJson<>OLD.outcomeJson OR NEW.requestId<>OLD.requestId OR NEW.guildId<>OLD.guildId
         OR NEW.userId<>OLD.userId OR NEW.gameType<>OLD.gameType OR NEW.stakeEcy<>OLD.stakeEcy
         OR NEW.maximumGrossLiabilityEcy<>OLD.maximumGrossLiabilityEcy
       BEGIN SELECT RAISE(ABORT,'casino planned outcome is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_session_transition BEFORE UPDATE OF status ON CasinoSession
       WHEN NOT ((OLD.status='RESERVED' AND NEW.status IN ('ACTIVE','SETTLEMENT_PENDING','COMMITTED','VOID','REVIEW_REQUIRED'))
              OR (OLD.status='ACTIVE' AND NEW.status IN ('SETTLEMENT_PENDING','COMMITTED','VOID','REVIEW_REQUIRED'))
              OR (OLD.status='SETTLEMENT_PENDING' AND NEW.status IN ('COMMITTED','VOID','REVIEW_REQUIRED'))
              OR (OLD.status='REVIEW_REQUIRED' AND NEW.status IN ('COMMITTED','VOID'))
              OR OLD.status=NEW.status)
       BEGIN SELECT RAISE(ABORT,'invalid casino session transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_session_terminal BEFORE UPDATE ON CasinoSession
       WHEN OLD.status IN ('COMMITTED','VOID')
       BEGIN SELECT RAISE(ABORT,'casino terminal session is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_session_no_delete BEFORE DELETE ON CasinoSession
       BEGIN SELECT RAISE(ABORT,'casino session history cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_settlement_planned_immutable BEFORE UPDATE ON CasinoSettlement
       WHEN NEW.sessionId<>OLD.sessionId OR NEW.stakeEcy<>OLD.stakeEcy
         OR (NEW.grossPayoutEcy<>OLD.grossPayoutEcy AND NOT
             (OLD.status='PENDING' AND NEW.status='COMMITTED' AND NEW.receiptJson IS NOT NULL))
       BEGIN SELECT RAISE(ABORT,'casino settlement plan is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_settlement_receipt BEFORE UPDATE ON CasinoSettlement
       WHEN (OLD.receiptJson IS NOT NULL AND NEW.receiptJson IS NOT OLD.receiptJson)
         OR (OLD.receiptJson IS NULL AND NEW.receiptJson IS NOT NULL AND NEW.status<>'COMMITTED')
         OR (OLD.status IN ('COMMITTED','VOID'))
       BEGIN SELECT RAISE(ABORT,'casino settlement receipt is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_settlement_transition BEFORE UPDATE OF status ON CasinoSettlement
       WHEN NOT ((OLD.status='PENDING' AND NEW.status IN ('COMMITTED','VOID','REVIEW_REQUIRED'))
              OR (OLD.status='REVIEW_REQUIRED' AND NEW.status IN ('COMMITTED','VOID')) OR OLD.status=NEW.status)
       BEGIN SELECT RAISE(ABORT,'invalid casino settlement transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_reservation_transition BEFORE UPDATE OF status ON CasinoBankrollReservation
       WHEN NOT ((OLD.status='ACTIVE' AND NEW.status IN ('RELEASED','REVIEW_REQUIRED'))
              OR (OLD.status='REVIEW_REQUIRED' AND NEW.status='RELEASED') OR OLD.status=NEW.status)
       BEGIN SELECT RAISE(ABORT,'invalid casino reservation transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_reservation_immutable BEFORE UPDATE ON CasinoBankrollReservation
       WHEN NEW.sessionId<>OLD.sessionId OR NEW.guildId<>OLD.guildId OR NEW.liabilityEcy<>OLD.liabilityEcy
       BEGIN SELECT RAISE(ABORT,'casino reservation identity is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_reservation_terminal BEFORE UPDATE ON CasinoBankrollReservation
       WHEN OLD.status='RELEASED'
       BEGIN SELECT RAISE(ABORT,'casino released reservation is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_action_no_update BEFORE UPDATE ON CasinoSessionAction
       BEGIN SELECT RAISE(ABORT,'casino action is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_action_no_delete BEFORE DELETE ON CasinoSessionAction
       BEGIN SELECT RAISE(ABORT,'casino action is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_auth_audit_no_update BEFORE UPDATE ON CasinoAuthorizationAudit
       BEGIN SELECT RAISE(ABORT,'casino authorization audit is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_auth_audit_no_delete BEFORE DELETE ON CasinoAuthorizationAudit
       BEGIN SELECT RAISE(ABORT,'casino authorization audit is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_outbox_transition BEFORE UPDATE OF status ON CasinoNotificationOutbox
       WHEN NOT ((OLD.status IN ('PENDING','FAILED') AND NEW.status IN ('CLAIMED','REVIEW_REQUIRED'))
              OR (OLD.status='CLAIMED' AND NEW.status IN ('SENT','FAILED','REVIEW_REQUIRED'))
              OR OLD.status=NEW.status)
       BEGIN SELECT RAISE(ABORT,'invalid casino outbox transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_outbox_no_delete BEFORE DELETE ON CasinoNotificationOutbox
       BEGIN SELECT RAISE(ABORT,'casino outbox history cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_review_terminal BEFORE UPDATE ON CasinoRecoveryReview
       WHEN OLD.status='RESOLVED'
       BEGIN SELECT RAISE(ABORT,'casino resolved review is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_review_no_delete BEFORE DELETE ON CasinoRecoveryReview
       BEGIN SELECT RAISE(ABORT,'casino recovery review cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_financial_no_delete_settlement BEFORE DELETE ON CasinoSettlement
       BEGIN SELECT RAISE(ABORT,'casino financial history cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_financial_no_delete_reservation BEFORE DELETE ON CasinoBankrollReservation
       BEGIN SELECT RAISE(ABORT,'casino financial history cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_financial_no_delete_distribution BEFORE DELETE ON CasinoBankrollDistribution
       BEGIN SELECT RAISE(ABORT,'casino financial history cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_distribution_no_update BEFORE UPDATE ON CasinoBankrollDistribution
       BEGIN SELECT RAISE(ABORT,'casino distribution history is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_legacy_no_update BEFORE UPDATE ON CasinoLegacyStatistic
       BEGIN SELECT RAISE(ABORT,'casino legacy snapshot is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_casino_legacy_no_delete BEFORE DELETE ON CasinoLegacyStatistic
       BEGIN SELECT RAISE(ABORT,'casino legacy snapshot cannot be deleted'); END""",
)


def _canonical_sql(value):
    return " ".join(str(value).split())


PHASE5_SCHEMA_CHECKSUM = hashlib.sha256(
    (PHASE5_MIGRATION_NAME + "\n" + _canonical_sql(PHASE5_TABLE_SQL) + "\n" +
     "\n".join(_canonical_sql(v) for v in PHASE5_INDEX_SQL + PHASE5_TRIGGER_SQL)).encode("utf-8")
).hexdigest()

REQUIRED_PHASE5_TABLES = {
    "CasinoSession", "CasinoSessionAction", "CasinoSettlement", "CasinoBankrollReservation",
    "CasinoBankrollDistribution", "CasinoNotificationOutbox", "CasinoRecoveryReview",
    "CasinoLegacyStatistic", "CasinoAuthorization", "CasinoAuthorizationAudit",
}
REQUIRED_PHASE5_INDEXES = {re.search(r"INDEX IF NOT EXISTS (\w+)", sql).group(1) for sql in PHASE5_INDEX_SQL}
REQUIRED_PHASE5_TRIGGERS = {re.search(r"TRIGGER IF NOT EXISTS (\w+)", sql).group(1) for sql in PHASE5_TRIGGER_SQL}
REQUIRED_PHASE5_COLUMNS = {
    "CasinoSession": {"sessionId", "requestId", "guildId", "userId", "gameType", "stakeEcy",
                       "maximumGrossLiabilityEcy", "outcomeJson", "stateJson", "status", "reservationKey",
                       "version", "retryCount", "lastErrorCode", "lastAttemptedAt", "reviewMetadataJson",
                       "createdAt", "expiresAt", "settledAt"},
    "CasinoSessionAction": {"actionId", "sessionId", "requestId", "sequence", "actorId", "actionType",
                            "actionJson", "resultJson", "transactionId", "createdAt"},
    "CasinoSettlement": {"settlementId", "sessionId", "transactionId", "stakeEcy", "grossPayoutEcy",
                          "status", "receiptJson", "voidReasonCode", "createdAt", "settledAt"},
    "CasinoBankrollReservation": {"reservationId", "sessionId", "guildId", "liabilityEcy", "status",
                                   "createdAt", "releasedAt"},
    "CasinoBankrollDistribution": {"distributionId", "guildId", "transactionId", "operationType",
                                    "amountEcy", "generalEcy", "reserveEcy", "burnEcy", "actorId",
                                    "reasonCode", "receiptJson", "createdAt"},
    "CasinoNotificationOutbox": {"eventId", "eventKey", "guildId", "userId", "sessionId", "payloadJson",
                                  "status", "leaseOwner", "leaseExpiresAt", "attemptCount", "messageId",
                                  "lastErrorCode", "createdAt", "sentAt"},
    "CasinoRecoveryReview": {"reviewId", "guildId", "entityType", "entityId", "errorCode", "status",
                              "retryCount", "sanitizedMetadataJson", "firstDetectedAt", "lastAttemptedAt",
                              "resolvedAt"},
    "CasinoLegacyStatistic": {"snapshotId", "guildId", "userId", "sourceKey", "sourceHash",
                               "sanitizedSnapshotJson", "migrationStatus", "createdAt"},
    "CasinoAuthorization": {"guildId", "userId", "permissionClass", "enabled", "grantedById",
                             "reasonCode", "createdAt", "updatedAt"},
    "CasinoAuthorizationAudit": {"auditId", "guildId", "userId", "permissionClass", "oldEnabled",
                                  "newEnabled", "actionType", "actorId", "reasonCode", "createdAt"},
}


def phase5_capability_sync(connection):
    marker = connection.execute(
        "SELECT checksum FROM EconomySchemaMigration WHERE version=$1 AND status='COMPLETED'",
        (ECONOMY_PHASE5_MIGRATION_VERSION,),
    ).fetchone()
    if not marker or marker[0] != PHASE5_SCHEMA_CHECKSUM:
        return False
    objects = {row[0]: row[1] for row in connection.execute(
        "SELECT name,type FROM sqlite_master WHERE type IN ('table','index','trigger')"
    )}
    if not (all(objects.get(name) == "table" for name in REQUIRED_PHASE5_TABLES)
            and all(objects.get(name) == "index" for name in REQUIRED_PHASE5_INDEXES)
            and all(objects.get(name) == "trigger" for name in REQUIRED_PHASE5_TRIGGERS)):
        return False
    for table, required in REQUIRED_PHASE5_COLUMNS.items():
        actual = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
        if actual != required:
            return False
    return True


async def phase5_capability(db):
    try:
        marker = await db.fetchrow(
            "SELECT checksum FROM EconomySchemaMigration WHERE version=$1 AND status='COMPLETED'",
            (ECONOMY_PHASE5_MIGRATION_VERSION,),
        )
        if not marker or marker[0] != PHASE5_SCHEMA_CHECKSUM:
            return False
        async with db.execute(
            "SELECT name,type FROM sqlite_master WHERE type IN ('table','index','trigger')"
        ) as cursor:
            objects = {row[0]: row[1] for row in await cursor.fetchall()}
        if not (all(objects.get(name) == "table" for name in REQUIRED_PHASE5_TABLES)
                and all(objects.get(name) == "index" for name in REQUIRED_PHASE5_INDEXES)
                and all(objects.get(name) == "trigger" for name in REQUIRED_PHASE5_TRIGGERS)):
            return False
        for table, required in REQUIRED_PHASE5_COLUMNS.items():
            async with db.execute(f'PRAGMA table_info("{table}")') as cursor:
                actual = {row[1] for row in await cursor.fetchall()}
            if actual != required:
                return False
        return True
    except aiosqlite.Error:
        return False
