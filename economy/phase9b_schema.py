"""Canonical Phase 9B dashboard and notification-routing schema."""

from __future__ import annotations

import hashlib
import re

from .constants import PHASE9B_DASHBOARD_MIGRATION_VERSION
from .phase9a_schema import phase9a_capability, phase9a_capability_sync


PHASE9B_MIGRATION_NAME = "phase9b-dashboard-notification-routing"

NOTIFICATION_CATEGORIES = (
    "GENERAL", "MARKET_CRYPTO", "MARKETPLACE", "GIVEAWAY", "CASINO",
    "ETERNAL_OPTIONS", "MINING", "BOSS", "LEVEL_UP", "BIRTHDAY",
    "BOOSTER", "RECOVERY", "SECURITY", "OPERATOR_AUDIT",
)

PHASE9B_TABLE_SQL = r"""
CREATE TABLE IF NOT EXISTS DashboardNotificationRoute (
    guildId TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN (
      'GENERAL','MARKET_CRYPTO','MARKETPLACE','GIVEAWAY','CASINO','ETERNAL_OPTIONS',
      'MINING','BOSS','LEVEL_UP','BIRTHDAY','BOOSTER','RECOVERY','SECURITY','OPERATOR_AUDIT')),
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    channelId TEXT,
    roleMentionId TEXT,
    eventFilterJson TEXT NOT NULL DEFAULT '{"eventTypes":[]}',
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    updatedById TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    lastSuccessfulDeliveryAt TEXT,
    lastFailedDeliveryAt TEXT,
    lastFailureCode TEXT,
    PRIMARY KEY(guildId,category),
    CHECK((enabled=0) OR (channelId IS NOT NULL AND length(channelId)>=17)),
    CHECK(channelId IS NULL OR channelId NOT GLOB '*[^0-9]*'),
    CHECK(roleMentionId IS NULL OR (length(roleMentionId)>=17 AND roleMentionId NOT GLOB '*[^0-9]*'))
);
CREATE TABLE IF NOT EXISTS DashboardNotificationDelivery (
    deliveryId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    deliveryKind TEXT NOT NULL CHECK(deliveryKind IN ('EVENT','TEST')),
    sourceType TEXT NOT NULL,
    sourceKey TEXT NOT NULL,
    category TEXT NOT NULL,
    routeVersion INTEGER NOT NULL CHECK(routeVersion>=0),
    channelId TEXT NOT NULL,
    roleMentionId TEXT,
    eventType TEXT NOT NULL,
    payloadJson TEXT NOT NULL,
    payloadHash TEXT NOT NULL CHECK(length(payloadHash)=64),
    marker TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('RESERVED','LEASED','SENT','FAILED','REVIEW_REQUIRED')),
    leaseOwner TEXT,
    leaseExpiresAt TEXT,
    attemptCount INTEGER NOT NULL DEFAULT 0 CHECK(attemptCount>=0),
    messageId TEXT,
    lastFailureCode TEXT,
    requestId TEXT,
    actorId TEXT,
    receiptJson TEXT,
    receiptHash TEXT CHECK(receiptHash IS NULL OR length(receiptHash)=64),
    createdAt TEXT NOT NULL,
    attemptedAt TEXT,
    completedAt TEXT,
    UNIQUE(guildId,deliveryKind,sourceType,sourceKey),
    CHECK((status='LEASED' AND leaseOwner IS NOT NULL AND leaseExpiresAt IS NOT NULL)
       OR (status<>'LEASED' AND leaseOwner IS NULL AND leaseExpiresAt IS NULL)),
    CHECK((status='SENT' AND messageId IS NOT NULL AND receiptJson IS NOT NULL AND receiptHash IS NOT NULL AND completedAt IS NOT NULL)
       OR (status='REVIEW_REQUIRED' AND receiptJson IS NOT NULL AND receiptHash IS NOT NULL AND completedAt IS NOT NULL)
       OR (status IN ('RESERVED','LEASED','FAILED') AND receiptJson IS NULL AND receiptHash IS NULL AND completedAt IS NULL))
);
CREATE TABLE IF NOT EXISTS DashboardNotificationLegacySnapshot (
    snapshotId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    sourceKey TEXT NOT NULL,
    mappedCategory TEXT,
    destinationId TEXT,
    sourceFileHash TEXT NOT NULL CHECK(length(sourceFileHash)=64),
    sourceValueHash TEXT NOT NULL CHECK(length(sourceValueHash)=64),
    capabilityManifestHash TEXT CHECK(capabilityManifestHash IS NULL OR length(capabilityManifestHash)=64),
    disposition TEXT NOT NULL CHECK(disposition IN (
      'IMPORTED','INVALID','MISSING','FOREIGN_GUILD','UNWRITABLE','DEPRECATED','UNRECOGNIZED')),
    evidenceJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL,
    UNIQUE(guildId,sourceKey,sourceValueHash)
);
CREATE TABLE IF NOT EXISTS DashboardEconomyReconciliationRun (
    runId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    schemaChecksum TEXT NOT NULL CHECK(length(schemaChecksum)=64),
    status TEXT NOT NULL CHECK(status IN ('PASSED','FAILED')),
    integrityResult TEXT NOT NULL,
    foreignKeyErrorCount INTEGER NOT NULL CHECK(foreignKeyErrorCount>=0),
    ledgerUnbalancedCount INTEGER NOT NULL CHECK(ledgerUnbalancedCount>=0),
    supplyMismatchCount INTEGER NOT NULL CHECK(supplyMismatchCount>=0),
    liabilityMismatchCount INTEGER NOT NULL CHECK(liabilityMismatchCount>=0),
    routeIssueCount INTEGER NOT NULL CHECK(routeIssueCount>=0),
    outboxIssueCount INTEGER NOT NULL CHECK(outboxIssueCount>=0),
    reportJson TEXT NOT NULL,
    reportHash TEXT NOT NULL CHECK(length(reportHash)=64),
    startedAt TEXT NOT NULL,
    completedAt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS DashboardRecoveryControl (
    controlId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    domain TEXT NOT NULL,
    entityType TEXT NOT NULL,
    entityId TEXT NOT NULL,
    sourceStateHash TEXT NOT NULL CHECK(length(sourceStateHash)=64),
    status TEXT NOT NULL CHECK(status IN ('OPEN','RESOLVED','REVIEW_REQUIRED')),
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    lastOperationId TEXT,
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    UNIQUE(guildId,domain,entityType,entityId)
);
"""

PHASE9B_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_dashboard_route_category ON DashboardNotificationRoute(guildId,enabled,category)",
    "CREATE INDEX IF NOT EXISTS idx_dashboard_delivery_claim ON DashboardNotificationDelivery(status,leaseExpiresAt,createdAt)",
    "CREATE INDEX IF NOT EXISTS idx_dashboard_delivery_route ON DashboardNotificationDelivery(guildId,category,createdAt)",
    "CREATE INDEX IF NOT EXISTS idx_dashboard_reconciliation_guild ON DashboardEconomyReconciliationRun(guildId,completedAt)",
    "CREATE INDEX IF NOT EXISTS idx_dashboard_recovery_status ON DashboardRecoveryControl(guildId,status,domain,entityType)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_dashboard_unresolved_target ON DashboardControlledOperation(guildId,operationType,targetType,targetId) WHERE status IN ('PENDING','REVIEW_REQUIRED')",
    "CREATE INDEX IF NOT EXISTS idx_dashboard_audit_page ON DashboardOperatorAudit(guildId,createdAt DESC,auditId DESC)",
)

PHASE9B_TRIGGER_SQL = (
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_route_identity BEFORE UPDATE ON DashboardNotificationRoute WHEN NEW.guildId<>OLD.guildId OR NEW.category<>OLD.category BEGIN SELECT RAISE(ABORT,'notification route identity is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_delivery_plan BEFORE UPDATE ON DashboardNotificationDelivery WHEN NEW.guildId<>OLD.guildId OR NEW.deliveryKind<>OLD.deliveryKind OR NEW.sourceType<>OLD.sourceType OR NEW.sourceKey<>OLD.sourceKey OR NEW.category<>OLD.category OR NEW.routeVersion<>OLD.routeVersion OR NEW.channelId<>OLD.channelId OR NEW.roleMentionId IS NOT OLD.roleMentionId OR NEW.eventType<>OLD.eventType OR NEW.payloadJson<>OLD.payloadJson OR NEW.payloadHash<>OLD.payloadHash OR NEW.marker<>OLD.marker OR NEW.requestId IS NOT OLD.requestId OR NEW.actorId IS NOT OLD.actorId BEGIN SELECT RAISE(ABORT,'notification delivery plan is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_delivery_transition BEFORE UPDATE OF status ON DashboardNotificationDelivery WHEN NOT ((OLD.status='RESERVED' AND NEW.status='LEASED') OR (OLD.status='FAILED' AND NEW.status='LEASED') OR (OLD.status='LEASED' AND NEW.status IN ('SENT','FAILED','REVIEW_REQUIRED'))) BEGIN SELECT RAISE(ABORT,'invalid notification delivery transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_delivery_receipt BEFORE UPDATE ON DashboardNotificationDelivery WHEN (OLD.receiptJson IS NOT NULL AND NEW.receiptJson IS NOT OLD.receiptJson) OR (OLD.receiptJson IS NULL AND NEW.receiptJson IS NOT NULL AND NEW.status NOT IN ('SENT','REVIEW_REQUIRED')) BEGIN SELECT RAISE(ABORT,'invalid notification receipt write'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_delivery_terminal BEFORE UPDATE ON DashboardNotificationDelivery WHEN OLD.status IN ('SENT','REVIEW_REQUIRED') BEGIN SELECT RAISE(ABORT,'terminal notification delivery is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_delivery_no_delete BEFORE DELETE ON DashboardNotificationDelivery BEGIN SELECT RAISE(ABORT,'notification delivery cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_legacy_notification_no_update BEFORE UPDATE ON DashboardNotificationLegacySnapshot BEGIN SELECT RAISE(ABORT,'legacy notification snapshot is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_legacy_notification_no_delete BEFORE DELETE ON DashboardNotificationLegacySnapshot BEGIN SELECT RAISE(ABORT,'legacy notification snapshot is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_reconciliation_no_update BEFORE UPDATE ON DashboardEconomyReconciliationRun BEGIN SELECT RAISE(ABORT,'dashboard reconciliation is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_reconciliation_no_delete BEFORE DELETE ON DashboardEconomyReconciliationRun BEGIN SELECT RAISE(ABORT,'dashboard reconciliation is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_recovery_identity BEFORE UPDATE ON DashboardRecoveryControl WHEN NEW.guildId<>OLD.guildId OR NEW.domain<>OLD.domain OR NEW.entityType<>OLD.entityType OR NEW.entityId<>OLD.entityId BEGIN SELECT RAISE(ABORT,'dashboard recovery identity is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_recovery_transition BEFORE UPDATE OF status ON DashboardRecoveryControl WHEN NOT ((OLD.status='OPEN' AND NEW.status IN ('RESOLVED','REVIEW_REQUIRED')) OR (OLD.status='REVIEW_REQUIRED' AND NEW.status='RESOLVED') OR OLD.status=NEW.status) BEGIN SELECT RAISE(ABORT,'invalid dashboard recovery transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_recovery_no_delete BEFORE DELETE ON DashboardRecoveryControl BEGIN SELECT RAISE(ABORT,'dashboard recovery control cannot be deleted'); END""",
)


def _canonical(value: str) -> str:
    return " ".join(str(value).split())


PHASE9B_SCHEMA_CHECKSUM = hashlib.sha256(
    (PHASE9B_MIGRATION_NAME + "\n" + _canonical(PHASE9B_TABLE_SQL) + "\n" +
     "\n".join(_canonical(value) for value in PHASE9B_INDEX_SQL + PHASE9B_TRIGGER_SQL)).encode("utf-8")
).hexdigest()

REQUIRED_PHASE9B_TABLES = {
    "DashboardNotificationRoute", "DashboardNotificationDelivery",
    "DashboardNotificationLegacySnapshot", "DashboardEconomyReconciliationRun",
    "DashboardRecoveryControl",
}
REQUIRED_PHASE9B_INDEXES = {re.search(r"INDEX IF NOT EXISTS (\w+)", value).group(1) for value in PHASE9B_INDEX_SQL}
REQUIRED_PHASE9B_TRIGGERS = {re.search(r"TRIGGER IF NOT EXISTS (\w+)", value).group(1) for value in PHASE9B_TRIGGER_SQL}
REQUIRED_PHASE9B_COLUMNS = {
    "DashboardNotificationRoute": {"guildId", "category", "enabled", "channelId", "roleMentionId",
                                   "eventFilterJson", "version", "updatedById", "updatedAt"},
    "DashboardNotificationDelivery": {"deliveryId", "guildId", "deliveryKind", "sourceType", "sourceKey",
                                      "category", "routeVersion", "channelId", "eventType", "payloadJson",
                                      "payloadHash", "marker", "status", "leaseOwner", "leaseExpiresAt",
                                      "attemptCount", "messageId", "receiptJson", "receiptHash"},
    "DashboardNotificationLegacySnapshot": {"snapshotId", "guildId", "sourceKey", "sourceFileHash",
                                            "sourceValueHash", "disposition", "evidenceJson"},
    "DashboardEconomyReconciliationRun": {"runId", "guildId", "schemaChecksum", "status", "reportHash"},
    "DashboardRecoveryControl": {"controlId", "guildId", "domain", "entityType", "entityId", "status", "version"},
}


def phase9b_capability_sync(connection) -> bool:
    if not phase9a_capability_sync(connection):
        return False
    marker = connection.execute(
        "SELECT name,checksum,status FROM EconomySchemaMigration WHERE version=?",
        (PHASE9B_DASHBOARD_MIGRATION_VERSION,),
    ).fetchone()
    if marker != (PHASE9B_MIGRATION_NAME, PHASE9B_SCHEMA_CHECKSUM, "COMPLETED"):
        return False
    objects = {row[0]: row[1] for row in connection.execute(
        "SELECT name,type FROM sqlite_master WHERE type IN ('table','index','trigger')"
    )}
    if not (all(objects.get(name) == "table" for name in REQUIRED_PHASE9B_TABLES)
            and all(objects.get(name) == "index" for name in REQUIRED_PHASE9B_INDEXES)
            and all(objects.get(name) == "trigger" for name in REQUIRED_PHASE9B_TRIGGERS)):
        return False
    for table, required in REQUIRED_PHASE9B_COLUMNS.items():
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not required.issubset(columns):
            return False
    return True


async def phase9b_capability(db) -> bool:
    return True
