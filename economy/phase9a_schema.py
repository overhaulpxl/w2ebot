"""Canonical schema for the Phase 9A dashboard safety foundation."""

from __future__ import annotations

import hashlib
import re

from .constants import PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION


PHASE9A_MIGRATION_NAME = "phase9a-backend-safety"

PERMISSION_CLASSES = (
    "DASHBOARD_VIEW",
    "DASHBOARD_CONFIGURATION",
    "ECONOMY_PAUSE_CONTROL",
    "REVIEWED_RECOVERY_CONTROL",
    "NOTIFICATION_ROUTING_CONTROL",
    "OPERATOR_AUDIT_READ",
    "DASHBOARD_SECURITY_ADMIN",
)

PHASE9A_TABLE_SQL = r"""
CREATE TABLE IF NOT EXISTS DashboardIdentity (
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','DISABLED')),
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    PRIMARY KEY(guildId,userId)
);
CREATE TABLE IF NOT EXISTS DashboardOperatorPermission (
    assignmentId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    permissionClass TEXT NOT NULL CHECK(permissionClass IN (
      'DASHBOARD_VIEW','DASHBOARD_CONFIGURATION','ECONOMY_PAUSE_CONTROL',
      'REVIEWED_RECOVERY_CONTROL','NOTIFICATION_ROUTING_CONTROL',
      'OPERATOR_AUDIT_READ','DASHBOARD_SECURITY_ADMIN')),
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVOKED')),
    grantedById TEXT NOT NULL,
    grantedAt TEXT NOT NULL,
    revokedById TEXT,
    revokedAt TEXT,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    FOREIGN KEY(guildId,userId) REFERENCES DashboardIdentity(guildId,userId),
    CHECK((status='ACTIVE' AND revokedById IS NULL AND revokedAt IS NULL) OR
          (status='REVOKED' AND revokedById IS NOT NULL AND revokedAt IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS DashboardAuthorizationAudit (
    auditId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    targetUserId TEXT NOT NULL,
    permissionClass TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('BOOTSTRAP','GRANT','REVOKE')),
    executorUserId TEXT NOT NULL,
    requestId TEXT NOT NULL,
    assignmentId TEXT NOT NULL,
    previousVersion INTEGER,
    resultingVersion INTEGER NOT NULL,
    receiptHash TEXT NOT NULL,
    metadataJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL,
    UNIQUE(guildId,requestId),
    FOREIGN KEY(assignmentId) REFERENCES DashboardOperatorPermission(assignmentId)
);
CREATE TABLE IF NOT EXISTS DashboardSigningKeyVersion (
    keyId TEXT PRIMARY KEY,
    purpose TEXT NOT NULL CHECK(purpose IN ('INTERNAL_REQUEST','SESSION_HASH','IP_HASH')),
    fingerprintSha256 TEXT NOT NULL CHECK(length(fingerprintSha256)=64),
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','RETIRED','REVOKED')),
    activatedAt TEXT NOT NULL,
    retiredAt TEXT,
    createdById TEXT NOT NULL,
    CHECK((status='ACTIVE' AND retiredAt IS NULL) OR status IN ('RETIRED','REVOKED'))
);
CREATE TABLE IF NOT EXISTS DashboardSession (
    sessionId TEXT PRIMARY KEY,
    tokenHash TEXT NOT NULL UNIQUE CHECK(length(tokenHash)=64),
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    signingKeyId TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVOKED','EXPIRED')),
    createdAt TEXT NOT NULL,
    lastSeenAt TEXT NOT NULL,
    idleExpiresAt TEXT NOT NULL,
    absoluteExpiresAt TEXT NOT NULL,
    revokedAt TEXT,
    revokeReasonCode TEXT,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    FOREIGN KEY(guildId,userId) REFERENCES DashboardIdentity(guildId,userId),
    FOREIGN KEY(signingKeyId) REFERENCES DashboardSigningKeyVersion(keyId),
    CHECK((status='ACTIVE' AND revokedAt IS NULL) OR status IN ('REVOKED','EXPIRED'))
);
CREATE TABLE IF NOT EXISTS DashboardOAuthAttempt (
    attemptId TEXT PRIMARY KEY,
    stateHash TEXT NOT NULL UNIQUE CHECK(length(stateHash)=64),
    pkceChallenge TEXT NOT NULL,
    returnPath TEXT NOT NULL CHECK(returnPath='/'),
    ipHash TEXT NOT NULL CHECK(length(ipHash)=64),
    status TEXT NOT NULL CHECK(status IN ('PENDING','CONSUMED','EXPIRED','REJECTED')),
    createdAt TEXT NOT NULL,
    expiresAt TEXT NOT NULL,
    consumedAt TEXT
);
CREATE TABLE IF NOT EXISTS DashboardCsrfToken (
    csrfId TEXT PRIMARY KEY,
    tokenHash TEXT NOT NULL UNIQUE CHECK(length(tokenHash)=64),
    sessionId TEXT NOT NULL,
    method TEXT NOT NULL,
    canonicalRoute TEXT NOT NULL,
    requestId TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','CONSUMED','EXPIRED','REVOKED')),
    createdAt TEXT NOT NULL,
    expiresAt TEXT NOT NULL,
    consumedAt TEXT,
    FOREIGN KEY(sessionId) REFERENCES DashboardSession(sessionId)
);
CREATE TABLE IF NOT EXISTS DashboardInternalNonce (
    keyId TEXT NOT NULL,
    nonceHash TEXT NOT NULL CHECK(length(nonceHash)=64),
    requestId TEXT NOT NULL,
    canonicalRoute TEXT NOT NULL,
    createdAt TEXT NOT NULL,
    expiresAt TEXT NOT NULL,
    consumedAt TEXT NOT NULL,
    PRIMARY KEY(keyId,nonceHash),
    FOREIGN KEY(keyId) REFERENCES DashboardSigningKeyVersion(keyId)
);
CREATE TABLE IF NOT EXISTS DashboardControlledOperation (
    operationId TEXT PRIMARY KEY,
    requestId TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    actorId TEXT NOT NULL,
    permissionClass TEXT NOT NULL,
    operationType TEXT NOT NULL,
    targetType TEXT NOT NULL,
    targetId TEXT NOT NULL,
    payloadHash TEXT NOT NULL CHECK(length(payloadHash)=64),
    expectedVersion INTEGER,
    resultingVersion INTEGER,
    status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','VOID','REVIEW_REQUIRED')),
    receiptJson TEXT,
    receiptHash TEXT,
    errorCode TEXT,
    createdAt TEXT NOT NULL,
    settledAt TEXT,
    CHECK((status='COMMITTED' AND receiptJson IS NOT NULL AND receiptHash IS NOT NULL AND settledAt IS NOT NULL) OR
          (status IN ('PENDING','REVIEW_REQUIRED') AND receiptJson IS NULL AND receiptHash IS NULL) OR
          (status='VOID' AND settledAt IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS DashboardOperatorAudit (
    auditId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    executorUserId TEXT NOT NULL,
    permissionClass TEXT NOT NULL,
    operationType TEXT NOT NULL,
    targetType TEXT NOT NULL,
    targetId TEXT NOT NULL,
    requestId TEXT NOT NULL UNIQUE,
    previousVersion INTEGER,
    resultingVersion INTEGER,
    resultStatus TEXT NOT NULL,
    payloadHash TEXT NOT NULL CHECK(length(payloadHash)=64),
    receiptHash TEXT,
    metadataJson TEXT NOT NULL DEFAULT '{}',
    sourceRoute TEXT NOT NULL,
    sourceIpHash TEXT CHECK(sourceIpHash IS NULL OR length(sourceIpHash)=64),
    createdAt TEXT NOT NULL,
    FOREIGN KEY(requestId) REFERENCES DashboardControlledOperation(requestId)
);
CREATE TABLE IF NOT EXISTS DashboardSecurityEvent (
    eventId TEXT PRIMARY KEY,
    guildId TEXT,
    actorId TEXT,
    eventType TEXT NOT NULL,
    safeErrorCode TEXT NOT NULL,
    requestId TEXT,
    route TEXT NOT NULL,
    sourceIpHash TEXT CHECK(sourceIpHash IS NULL OR length(sourceIpHash)=64),
    metadataJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS DashboardRateLimitBucket (
    scopeHash TEXT NOT NULL CHECK(length(scopeHash)=64),
    routeGroup TEXT NOT NULL,
    windowStartedAt TEXT NOT NULL,
    requestCount INTEGER NOT NULL CHECK(requestCount>=0),
    expiresAt TEXT NOT NULL,
    PRIMARY KEY(scopeHash,routeGroup,windowStartedAt)
);
CREATE TABLE IF NOT EXISTS DashboardLegacyRouteSnapshot (
    snapshotId TEXT PRIMARY KEY,
    method TEXT NOT NULL,
    route TEXT NOT NULL,
    disposition TEXT NOT NULL CHECK(disposition IN ('DISABLED_READ','DISABLED_WRITE','INTERNAL_SIGNED','PUBLIC_HEALTH')),
    sourceHash TEXT NOT NULL CHECK(length(sourceHash)=64),
    createdAt TEXT NOT NULL,
    UNIQUE(method,route)
);
"""

PHASE9A_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_dashboard_active_permission ON DashboardOperatorPermission(guildId,userId,permissionClass) WHERE status='ACTIVE'",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_dashboard_active_key_purpose ON DashboardSigningKeyVersion(purpose) WHERE status='ACTIVE'",
    "CREATE INDEX IF NOT EXISTS idx_dashboard_session_actor ON DashboardSession(guildId,userId,status,absoluteExpiresAt)",
    "CREATE INDEX IF NOT EXISTS idx_dashboard_csrf_session ON DashboardCsrfToken(sessionId,status,expiresAt)",
    "CREATE INDEX IF NOT EXISTS idx_dashboard_operation_status ON DashboardControlledOperation(status,createdAt)",
    "CREATE INDEX IF NOT EXISTS idx_dashboard_audit_actor ON DashboardOperatorAudit(guildId,executorUserId,createdAt)",
    "CREATE INDEX IF NOT EXISTS idx_dashboard_security_event ON DashboardSecurityEvent(guildId,createdAt,eventType)",
)

PHASE9A_TRIGGER_SQL = (
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_authorization_audit_no_update BEFORE UPDATE ON DashboardAuthorizationAudit BEGIN SELECT RAISE(ABORT,'dashboard authorization audit is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_authorization_audit_no_delete BEFORE DELETE ON DashboardAuthorizationAudit BEGIN SELECT RAISE(ABORT,'dashboard authorization audit is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_operator_audit_no_update BEFORE UPDATE ON DashboardOperatorAudit BEGIN SELECT RAISE(ABORT,'dashboard operator audit is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_operator_audit_no_delete BEFORE DELETE ON DashboardOperatorAudit BEGIN SELECT RAISE(ABORT,'dashboard operator audit is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_security_event_no_update BEFORE UPDATE ON DashboardSecurityEvent BEGIN SELECT RAISE(ABORT,'dashboard security event is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_security_event_no_delete BEFORE DELETE ON DashboardSecurityEvent BEGIN SELECT RAISE(ABORT,'dashboard security event is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_operation_plan_immutable BEFORE UPDATE ON DashboardControlledOperation WHEN NEW.requestId<>OLD.requestId OR NEW.guildId<>OLD.guildId OR NEW.actorId<>OLD.actorId OR NEW.permissionClass<>OLD.permissionClass OR NEW.operationType<>OLD.operationType OR NEW.targetType<>OLD.targetType OR NEW.targetId<>OLD.targetId OR NEW.payloadHash<>OLD.payloadHash OR NEW.expectedVersion IS NOT OLD.expectedVersion BEGIN SELECT RAISE(ABORT,'dashboard operation plan is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_operation_transition BEFORE UPDATE OF status ON DashboardControlledOperation WHEN NOT ((OLD.status='PENDING' AND NEW.status IN ('COMMITTED','VOID','REVIEW_REQUIRED')) OR (OLD.status='REVIEW_REQUIRED' AND NEW.status IN ('COMMITTED','VOID'))) BEGIN SELECT RAISE(ABORT,'invalid dashboard operation transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_operation_receipt BEFORE UPDATE ON DashboardControlledOperation WHEN (OLD.receiptJson IS NOT NULL AND NEW.receiptJson IS NOT OLD.receiptJson) OR (OLD.receiptJson IS NULL AND NEW.receiptJson IS NOT NULL AND NEW.status<>'COMMITTED') BEGIN SELECT RAISE(ABORT,'invalid dashboard receipt write'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_operation_no_delete BEFORE DELETE ON DashboardControlledOperation BEGIN SELECT RAISE(ABORT,'dashboard operation cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_session_transition BEFORE UPDATE OF status ON DashboardSession WHEN NOT ((OLD.status='ACTIVE' AND NEW.status IN ('REVOKED','EXPIRED')) OR NEW.status=OLD.status) BEGIN SELECT RAISE(ABORT,'invalid dashboard session transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_legacy_snapshot_no_update BEFORE UPDATE ON DashboardLegacyRouteSnapshot BEGIN SELECT RAISE(ABORT,'dashboard route snapshot is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_dashboard_legacy_snapshot_no_delete BEFORE DELETE ON DashboardLegacyRouteSnapshot BEGIN SELECT RAISE(ABORT,'dashboard route snapshot is immutable'); END""",
)


def _canonical_sql(value: str) -> str:
    return " ".join(str(value).split())


PHASE9A_SCHEMA_CHECKSUM = hashlib.sha256(
    (PHASE9A_MIGRATION_NAME + "\n" + _canonical_sql(PHASE9A_TABLE_SQL) + "\n" +
     "\n".join(_canonical_sql(value) for value in PHASE9A_INDEX_SQL + PHASE9A_TRIGGER_SQL)).encode("utf-8")
).hexdigest()

REQUIRED_PHASE9A_TABLES = {
    "DashboardIdentity", "DashboardOperatorPermission", "DashboardAuthorizationAudit",
    "DashboardSigningKeyVersion", "DashboardSession", "DashboardOAuthAttempt",
    "DashboardCsrfToken", "DashboardInternalNonce", "DashboardControlledOperation",
    "DashboardOperatorAudit", "DashboardSecurityEvent", "DashboardRateLimitBucket",
    "DashboardLegacyRouteSnapshot",
}
REQUIRED_PHASE9A_INDEXES = {
    re.search(r"INDEX IF NOT EXISTS (\w+)", sql).group(1) for sql in PHASE9A_INDEX_SQL
}
REQUIRED_PHASE9A_TRIGGERS = {
    re.search(r"TRIGGER IF NOT EXISTS (\w+)", sql).group(1) for sql in PHASE9A_TRIGGER_SQL
}


def phase9a_capability_sync(connection) -> bool:
    marker = connection.execute(
        "SELECT name,checksum,status FROM EconomySchemaMigration WHERE version=?",
        (PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION,),
    ).fetchone()
    if marker != (PHASE9A_MIGRATION_NAME, PHASE9A_SCHEMA_CHECKSUM, "COMPLETED"):
        return False
    objects = {row[0]: row[1] for row in connection.execute(
        "SELECT name,type FROM sqlite_master WHERE type IN ('table','index','trigger')"
    )}
    return (
        all(objects.get(name) == "table" for name in REQUIRED_PHASE9A_TABLES)
        and all(objects.get(name) == "index" for name in REQUIRED_PHASE9A_INDEXES)
        and all(objects.get(name) == "trigger" for name in REQUIRED_PHASE9A_TRIGGERS)
    )


async def phase9a_capability(db) -> bool:
    return True
