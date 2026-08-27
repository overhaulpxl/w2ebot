"""Migrasi staging eksplisit Phase 8 Giveaway dan Eternal Options."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from .constants import ECONOMY_PHASE8_MIGRATION_VERSION
from .phase5_schema import phase5_capability_sync
from .phase6_schema import phase6_capability_sync
from .phase8_schema import (
    PHASE8_INDEX_SQL, PHASE8_MIGRATION_NAME, PHASE8_SCHEMA_CHECKSUM,
    PHASE8_TABLE_SQL, PHASE8_TRIGGER_SQL, phase8_capability_sync,
    phase2_activity_capability_sync,
)
from .staging import create_logical_sqlite_backup, logical_sqlite_manifest, restore_logical_sqlite_backup


def _resolved(path):
    return Path(path).expanduser().resolve()


def assert_not_production(target_db, production_db):
    if _resolved(target_db) == _resolved(production_db):
        raise ValueError("Migrasi Phase 8 menolak database production.")


def _statements(script):
    pending = ""
    for line in script.splitlines():
        pending += line + "\n"
        if sqlite3.complete_statement(pending):
            statement, pending = pending.strip(), ""
            if statement:
                yield statement
    if pending.strip():
        raise ValueError("Schema Phase 8 tidak lengkap.")


def _snapshot_legacy(connection, now):
    counts = {"giveaways": 0, "binomo": 0, "review": 0}
    has_giveaway = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Giveaway'"
    ).fetchone()
    if has_giveaway:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(Giveaway)")}
        names = [name for name in ("id", "channel_id", "message_id", "prize", "host_id", "end_at", "ended") if name in columns]
        if names:
            for row in connection.execute(f"SELECT {','.join(names)} FROM Giveaway"):
                payload = dict(zip(names, row))
                raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                source_id = str(payload.get("id", hashlib.sha256(raw.encode()).hexdigest()))
                status = "REVIEW_REQUIRED" if not int(payload.get("ended") or 0) else "READ_ONLY"
                connection.execute(
                    "INSERT OR IGNORE INTO GiveawayLegacySnapshot "
                    "(snapshotId,sourceType,sourceIdentity,sourceHash,rawSourceJson,status,createdAt) VALUES (?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), "GIVEAWAY", source_id, hashlib.sha256(raw.encode()).hexdigest(), raw, status, now),
                )
                counts["giveaways"] += 1
                counts["review"] += status == "REVIEW_REQUIRED"
    has_store = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='json_store'"
    ).fetchone()
    if has_store:
        row = connection.execute("SELECT content FROM json_store WHERE filename='binomo.json'").fetchone()
        if row:
            raw = row[0]
            try:
                parsed = json.loads(raw)
                unresolved = bool(parsed)
            except (TypeError, ValueError):
                unresolved = True
            connection.execute(
                "INSERT OR IGNORE INTO GiveawayLegacySnapshot "
                "(snapshotId,sourceType,sourceIdentity,sourceHash,rawSourceJson,status,createdAt) VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), "BINOMO", "binomo.json", hashlib.sha256(raw.encode()).hexdigest(), raw,
                 "REVIEW_REQUIRED" if unresolved else "READ_ONLY", now),
            )
            counts["binomo"] = 1
            counts["review"] += unresolved
    return counts


def phase8_dry_run(db_path):
    connection = sqlite3.connect(db_path)
    try:
        marker = connection.execute(
            "SELECT name,checksum,status FROM EconomySchemaMigration WHERE version=?",
            (ECONOMY_PHASE8_MIGRATION_VERSION,),
        ).fetchone()
        return {
            "migrationVersion": ECONOMY_PHASE8_MIGRATION_VERSION,
            "migrationName": PHASE8_MIGRATION_NAME,
            "checksum": PHASE8_SCHEMA_CHECKSUM,
            "existingMarker": marker,
            "phase5Capable": phase5_capability_sync(connection),
            "phase6Capable": phase6_capability_sync(connection),
            "wouldApply": marker is None,
        }
    finally:
        connection.close()


def verify_phase8_staging(db_path):
    connection = sqlite3.connect(db_path)
    try:
        return {
            "schemaCapable": phase8_capability_sync(connection),
            "migrationVersion": ECONOMY_PHASE8_MIGRATION_VERSION,
            "migrationName": PHASE8_MIGRATION_NAME,
            "migrationChecksum": PHASE8_SCHEMA_CHECKSUM,
            "integrityCheck": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreignKeyErrors": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
        }
    finally:
        connection.close()


def apply_phase8_staging(target_db, *, production_db, backup_path=None, failure_stage=None):
    assert_not_production(target_db, production_db)
    backup = create_logical_sqlite_backup(target_db, backup_path) if backup_path else None
    connection = sqlite3.connect(target_db, isolation_level=None)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        if (not phase2_activity_capability_sync(connection) or not phase5_capability_sync(connection)
                or not phase6_capability_sync(connection)):
            raise RuntimeError("Migration Phase 8 memerlukan Activity Phase 2 serta capability Phase 5 dan Phase 6.")
        marker = connection.execute(
            "SELECT name,checksum,status FROM EconomySchemaMigration WHERE version=?",
            (ECONOMY_PHASE8_MIGRATION_VERSION,),
        ).fetchone()
        if marker:
            if marker != (PHASE8_MIGRATION_NAME, PHASE8_SCHEMA_CHECKSUM, "COMPLETED"):
                raise RuntimeError("Marker migration Phase 8 tidak cocok; proses dihentikan.")
            if not phase8_capability_sync(connection):
                raise RuntimeError("Marker Phase 8 ada tetapi schema tidak lengkap.")
            connection.rollback()
            return {"applied": False, "replayed": True, "backup": backup,
                    "verification": verify_phase8_staging(target_db)}
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO EconomySchemaMigration (version,name,checksum,status,startedAt,detailsJson) "
            "VALUES (?,?,?,'RUNNING',?,'{}')",
            (ECONOMY_PHASE8_MIGRATION_VERSION, PHASE8_MIGRATION_NAME, PHASE8_SCHEMA_CHECKSUM, now),
        )
        if failure_stage == "after_marker":
            raise RuntimeError("Injected Phase 8 migration failure")
        for statement in _statements(PHASE8_TABLE_SQL):
            connection.execute(statement)
        if failure_stage == "after_tables":
            raise RuntimeError("Injected Phase 8 migration failure")
        for statement in PHASE8_INDEX_SQL:
            connection.execute(statement)
        for statement in PHASE8_TRIGGER_SQL:
            connection.execute(statement)
        if failure_stage == "after_triggers":
            raise RuntimeError("Injected Phase 8 migration failure")
        legacy = _snapshot_legacy(connection, now)
        connection.execute(
            "UPDATE EconomySchemaMigration SET status='COMPLETED',completedAt=?,detailsJson=? WHERE version=?",
            (now, json.dumps({"legacySnapshots": legacy, "financialSeedApplied": False},
                             sort_keys=True, separators=(",", ":")), ECONOMY_PHASE8_MIGRATION_VERSION),
        )
        if not phase8_capability_sync(connection):
            raise RuntimeError("Capability Phase 8 gagal sebelum commit.")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Foreign key Phase 8 tidak valid.")
        if failure_stage == "before_commit":
            raise RuntimeError("Injected Phase 8 migration failure")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    verification = verify_phase8_staging(target_db)
    if not verification["schemaCapable"] or verification["integrityCheck"] != "ok" or verification["foreignKeyErrors"]:
        raise RuntimeError("Verifikasi migration Phase 8 gagal.")
    return {"applied": True, "replayed": False, "backup": backup, "verification": verification}


def reconcile_phase8_staging(db_path):
    connection = sqlite3.connect(db_path)
    try:
        checks = {
            "unbalancedGiveawayEscrow": connection.execute(
                "SELECT COUNT(*) FROM GiveawayEscrow WHERE amountEcy<>paidTickets*10000"
            ).fetchone()[0],
            "optionWithoutReservation": connection.execute(
                "SELECT COUNT(*) FROM EternalOptionPosition p LEFT JOIN EternalOptionReservation r "
                "ON r.positionId=p.positionId WHERE p.status IN ('ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED') AND r.positionId IS NULL"
            ).fetchone()[0],
            "releasedUnresolvedOption": connection.execute(
                "SELECT COUNT(*) FROM EternalOptionPosition p JOIN EternalOptionReservation r ON r.positionId=p.positionId "
                "WHERE p.status IN ('ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED') AND r.status='RELEASED'"
            ).fetchone()[0],
            "duplicateVoiceEvents": connection.execute(
                "SELECT COUNT(*) FROM (SELECT activityEventId,COUNT(*) n FROM GiveawayVoiceBlock GROUP BY activityEventId HAVING n>1)"
            ).fetchone()[0],
        }
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        blocking = sum(int(value) for value in checks.values())
        return {"checks": checks, "blocking": blocking, "integrityCheck": integrity,
                "foreignKeyErrors": foreign_keys,
                "reconciled": blocking == 0 and integrity == "ok" and not foreign_keys}
    finally:
        connection.close()


def restore_phase8_staging(target_db, *, backup_path, production_db, confirm=False):
    if not confirm:
        raise ValueError("Restore Phase 8 memerlukan konfirmasi eksplisit.")
    assert_not_production(target_db, production_db)
    manifest = logical_sqlite_manifest(backup_path)
    if manifest["integrity_check"] != "ok" or manifest["foreign_key_errors"]:
        raise ValueError("Backup Phase 8 tidak valid.")
    restore_logical_sqlite_backup(backup_path, target_db)
    return {"restored": True, "manifest": logical_sqlite_manifest(target_db)}
