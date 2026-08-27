"""Explicit, production-refusing migration for Phase 9A backend safety."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from .constants import PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION
from .phase9a_schema import (
    PHASE9A_INDEX_SQL,
    PHASE9A_MIGRATION_NAME,
    PHASE9A_SCHEMA_CHECKSUM,
    PHASE9A_TABLE_SQL,
    PHASE9A_TRIGGER_SQL,
    phase9a_capability_sync,
)
from .staging import create_logical_sqlite_backup, logical_sqlite_manifest, restore_logical_sqlite_backup


LEGACY_READ_ROUTES = (
    "/api/config", "/api/server", "/api/radar", "/api/channels", "/api/announce-config",
    "/api/leaderboard", "/api/user/{id}", "/api/market", "/api/treasury", "/api/boss",
    "/api/economy/stats", "/api/economy/v1-supply", "/api/economy/v1-profile/{id}",
    "/api/economy/v1-marketplace", "/api/economy/v1-casino", "/api/economy/v1-crypto",
    "/api/economy/v1-mining", "/api/economy/v1-phase8", "/api/marriages",
    "/api/stats/summary", "/api/bot/stats", "/api/economy/level-distribution", "/api/audit",
)
LEGACY_WRITE_ROUTES = (
    "/api/config", "/api/announce-config", "/api/broadcast", "/api/announce",
    "/api/user/{id}/coins", "/api/user/{id}/xp", "/api/user/{id}/give-item",
    "/api/user/{id}/reset-cooldown", "/api/user/{id}/persona", "/api/user/{id}/birthday",
    "/api/user/{id}/bg", "/api/user/{id}/divorce", "/api/user/{id}/bounty",
    "/api/user/{id}/reset-weekly", "/api/user/{id}/reset-quest", "/api/user/{id}/reset",
    "/api/reset-all-players", "/api/boss/spawn", "/api/boss/settle",
    "/api/economy/v1-marketplace/action",
)


def _resolved(path):
    return Path(path).expanduser().resolve()


def assert_not_production(target_db, production_db):
    if _resolved(target_db) == _resolved(production_db):
        raise ValueError("Migrasi Phase 9A menolak database production.")


def _statements(script):
    pending = ""
    for line in script.splitlines():
        pending += line + "\n"
        if sqlite3.complete_statement(pending):
            statement, pending = pending.strip(), ""
            if statement:
                yield statement
    if pending.strip():
        raise ValueError("Schema Phase 9A tidak lengkap.")


def _route_source_hash(method, route, disposition):
    return hashlib.sha256(f"{method}\n{route}\n{disposition}".encode("utf-8")).hexdigest()


def _insert_route_snapshots(connection, now):
    rows = [("GET", "/healthz", "PUBLIC_HEALTH")]
    rows.extend(("GET", route, "DISABLED_READ") for route in LEGACY_READ_ROUTES)
    rows.extend(("POST", route, "DISABLED_WRITE") for route in LEGACY_WRITE_ROUTES)
    for method, route, disposition in rows:
        connection.execute(
            "INSERT INTO DashboardLegacyRouteSnapshot "
            "(snapshotId,method,route,disposition,sourceHash,createdAt) VALUES ($1,$2,$3,$4,$5,$6)",
            (str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:phase9a-route:{method}:{route}")), method, route,
             disposition, _route_source_hash(method, route, disposition), now),
        )


def phase9a_dry_run(db_path):
    connection = sqlite3.connect(db_path)
    try:
        marker = connection.execute(
            "SELECT name,checksum,status FROM EconomySchemaMigration WHERE version=$1",
            (PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION,),
        ).fetchone()
        return {
            "migrationVersion": PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION,
            "migrationName": PHASE9A_MIGRATION_NAME,
            "checksum": PHASE9A_SCHEMA_CHECKSUM,
            "existingMarker": marker,
            "wouldApply": marker is None,
        }
    finally:
        connection.close()


def verify_phase9a_staging(db_path):
    connection = sqlite3.connect(db_path)
    try:
        return {
            "schemaCapable": phase9a_capability_sync(connection),
            "migrationVersion": PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION,
            "migrationName": PHASE9A_MIGRATION_NAME,
            "migrationChecksum": PHASE9A_SCHEMA_CHECKSUM,
            "integrityCheck": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreignKeyErrors": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
            "routeSnapshots": connection.execute(
                "SELECT COUNT(*) FROM DashboardLegacyRouteSnapshot"
            ).fetchone()[0] if phase9a_capability_sync(connection) else 0,
        }
    finally:
        connection.close()


def apply_phase9a_staging(target_db, *, production_db, backup_path=None, failure_stage=None):
    assert_not_production(target_db, production_db)
    backup = create_logical_sqlite_backup(target_db, backup_path) if backup_path else None
    connection = sqlite3.connect(target_db, isolation_level=None)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        marker = connection.execute(
            "SELECT name,checksum,status FROM EconomySchemaMigration WHERE version=$1",
            (PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION,),
        ).fetchone()
        if marker:
            if marker != (PHASE9A_MIGRATION_NAME, PHASE9A_SCHEMA_CHECKSUM, "COMPLETED"):
                raise RuntimeError("Marker migration Phase 9A tidak cocok; proses dihentikan.")
            if not phase9a_capability_sync(connection):
                raise RuntimeError("Marker Phase 9A ada tetapi schema tidak lengkap.")
            connection.rollback()
            return {"applied": False, "replayed": True, "backup": backup,
                    "verification": verify_phase9a_staging(target_db)}
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO EconomySchemaMigration (version,name,checksum,status,startedAt,detailsJson) "
            "VALUES ($1,$2,$3,'RUNNING',$4,'{}')",
            (PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION, PHASE9A_MIGRATION_NAME,
             PHASE9A_SCHEMA_CHECKSUM, now),
        )
        if failure_stage == "after_marker":
            raise RuntimeError("Injected Phase 9A migration failure")
        for statement in _statements(PHASE9A_TABLE_SQL):
            connection.execute(statement)
        if failure_stage == "after_tables":
            raise RuntimeError("Injected Phase 9A migration failure")
        for statement in PHASE9A_INDEX_SQL:
            connection.execute(statement)
        if failure_stage == "after_indexes":
            raise RuntimeError("Injected Phase 9A migration failure")
        for statement in PHASE9A_TRIGGER_SQL:
            connection.execute(statement)
        if failure_stage == "after_triggers":
            raise RuntimeError("Injected Phase 9A migration failure")
        _insert_route_snapshots(connection, now)
        if failure_stage == "after_snapshots":
            raise RuntimeError("Injected Phase 9A migration failure")
        details = json.dumps({"rawSecretsStored": False, "phase1To8DataChanged": False},
                            sort_keys=True, separators=(",", ":"))
        connection.execute(
            "UPDATE EconomySchemaMigration SET status='COMPLETED',completedAt=$1,detailsJson=$2 WHERE version=$3",
            (now, details, PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION),
        )
        if not phase9a_capability_sync(connection):
            raise RuntimeError("Capability Phase 9A gagal sebelum commit.")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Foreign key Phase 9A tidak valid.")
        if failure_stage == "before_commit":
            raise RuntimeError("Injected Phase 9A migration failure")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    verification = verify_phase9a_staging(target_db)
    if not verification["schemaCapable"] or verification["integrityCheck"] != "ok" or verification["foreignKeyErrors"]:
        raise RuntimeError("Verifikasi migration Phase 9A gagal.")
    return {"applied": True, "replayed": False, "backup": backup, "verification": verification}


def reconcile_phase9a_staging(db_path):
    connection = sqlite3.connect(db_path)
    try:
        checks = {
            "activeSessionWithoutIdentity": connection.execute(
                "SELECT COUNT(*) FROM DashboardSession s LEFT JOIN DashboardIdentity i "
                "ON i.guildId=s.guildId AND i.userId=s.userId WHERE s.status='ACTIVE' AND i.userId IS NULL"
            ).fetchone()[0],
            "committedOperationWithoutAudit": connection.execute(
                "SELECT COUNT(*) FROM DashboardControlledOperation o LEFT JOIN DashboardOperatorAudit a "
                "ON a.requestId=o.requestId WHERE o.status='COMMITTED' AND a.auditId IS NULL"
            ).fetchone()[0],
            "committedOperationWithoutReceipt": connection.execute(
                "SELECT COUNT(*) FROM DashboardControlledOperation WHERE status='COMMITTED' "
                "AND (receiptJson IS NULL OR receiptHash IS NULL)"
            ).fetchone()[0],
            "multipleActiveKeys": connection.execute(
                "SELECT COUNT(*) FROM (SELECT purpose,COUNT(*) n FROM DashboardSigningKeyVersion "
                "WHERE status='ACTIVE' GROUP BY purpose HAVING n>1)"
            ).fetchone()[0],
        }
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        blocking = sum(checks.values())
        return {"checks": checks, "blocking": blocking, "integrityCheck": integrity,
                "foreignKeyErrors": foreign_keys,
                "reconciled": blocking == 0 and integrity == "ok" and foreign_keys == 0}
    finally:
        connection.close()


def restore_phase9a_staging(target_db, *, backup_path, production_db, confirm=False):
    if not confirm:
        raise ValueError("Restore Phase 9A memerlukan konfirmasi eksplisit.")
    assert_not_production(target_db, production_db)
    manifest = logical_sqlite_manifest(backup_path)
    if manifest["integrity_check"] != "ok" or manifest["foreign_key_errors"]:
        raise ValueError("Backup Phase 9A tidak valid.")
    restore_logical_sqlite_backup(backup_path, target_db)
    return {"restored": True, "manifest": logical_sqlite_manifest(target_db)}


def register_signing_key(db_path, *, key_id, purpose, fingerprint_sha256, actor_id):
    if len(fingerprint_sha256) != 64:
        raise ValueError("Fingerprint signing key tidak valid.")
    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(db_path, isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        if not phase9a_capability_sync(connection):
            raise RuntimeError("Capability Phase 9A belum tersedia.")
        connection.execute(
            "UPDATE DashboardSigningKeyVersion SET status='RETIRED',retiredAt=$1 "
            "WHERE purpose=$1 AND status='ACTIVE'", (now, purpose),
        )
        connection.execute(
            "INSERT INTO DashboardSigningKeyVersion "
            "(keyId,purpose,fingerprintSha256,status,activatedAt,createdById) VALUES ($1,$2,$3,'ACTIVE',$4,$5)",
            (key_id, purpose, fingerprint_sha256.lower(), now, str(actor_id)),
        )
        connection.execute(
            "UPDATE DashboardSession SET status='REVOKED',revokedAt=$1,revokeReasonCode='SIGNING_KEY_ROTATED',version=version+1 "
            "WHERE status='ACTIVE'", (now,),
        )
        connection.execute(
            "UPDATE DashboardCsrfToken SET status='REVOKED' WHERE status='ACTIVE'"
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def bootstrap_admin(db_path, *, guild_id, user_id, actor_id="STAGING_BOOTSTRAP"):
    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(db_path, isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        if not phase9a_capability_sync(connection):
            raise RuntimeError("Capability Phase 9A belum tersedia.")
        connection.execute(
            "INSERT OR IGNORE INTO DashboardIdentity (guildId,userId,status,createdAt,updatedAt) "
            "VALUES ($1,$2,'ACTIVE',$3,$4)", (str(guild_id), str(user_id), now, now),
        )
        created = []
        for permission in ("DASHBOARD_VIEW", "OPERATOR_AUDIT_READ", "DASHBOARD_SECURITY_ADMIN"):
            existing = connection.execute(
                "SELECT assignmentId FROM DashboardOperatorPermission WHERE guildId=$1 AND userId=$2 "
                "AND permissionClass=$1 AND status='ACTIVE'",
                (str(guild_id), str(user_id), permission),
            ).fetchone()
            if existing:
                continue
            assignment_id = str(uuid.uuid4())
            request_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO DashboardOperatorPermission "
                "(assignmentId,guildId,userId,permissionClass,status,grantedById,grantedAt) "
                "VALUES ($1,$2,$3,$4,'ACTIVE',$5,$6)",
                (assignment_id, str(guild_id), str(user_id), permission, str(actor_id), now),
            )
            receipt_hash = hashlib.sha256(f"{assignment_id}:{permission}:BOOTSTRAP".encode()).hexdigest()
            connection.execute(
                "INSERT INTO DashboardAuthorizationAudit "
                "(auditId,guildId,targetUserId,permissionClass,action,executorUserId,requestId,assignmentId,"
                "resultingVersion,receiptHash,createdAt) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,0,$9,$10)",
                (str(uuid.uuid4()), str(guild_id), str(user_id), permission, "BOOTSTRAP",
                 str(actor_id), request_id, assignment_id, receipt_hash, now),
            )
            created.append(permission)
        connection.commit()
        return {"createdPermissions": created, "userId": str(user_id), "guildId": str(guild_id)}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
