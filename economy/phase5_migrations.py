"""Migrasi eksplisit Casino Phase 5 untuk database staging."""

import hashlib
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
import uuid

from .constants import ECONOMY_PHASE5_MIGRATION_VERSION
from .phase5_schema import (
    PHASE5_INDEX_SQL,
    PHASE5_MIGRATION_NAME,
    PHASE5_SCHEMA_CHECKSUM,
    PHASE5_TABLE_SQL,
    PHASE5_TRIGGER_SQL,
    phase5_capability_sync,
)
from .staging import create_logical_sqlite_backup, logical_sqlite_manifest, restore_logical_sqlite_backup


def _resolved(path):
    return Path(path).expanduser().resolve()


def assert_not_production(target_db, production_db):
    if _resolved(target_db) == _resolved(production_db):
        raise ValueError("Migrasi Phase 5 menolak database production.")


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _statements(script):
    pending = ""
    for line in script.splitlines():
        pending += line + "\n"
        if sqlite3.complete_statement(pending):
            statement = pending.strip()
            pending = ""
            if statement:
                yield statement
    if pending.strip():
        raise ValueError("Schema Casino mengandung SQL yang tidak lengkap.")


def _legacy_snapshots(connection, guild_id, users_json_path, now):
    if not users_json_path:
        return {"source": None, "snapshots": 0, "reviews": 0}
    path = Path(users_json_path)
    if not path.exists():
        return {"source": str(path), "snapshots": 0, "reviews": 0}
    raw = path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        connection.execute(
            "INSERT OR IGNORE INTO CasinoLegacyStatistic "
            "(snapshotId,guildId,userId,sourceKey,sourceHash,sanitizedSnapshotJson,migrationStatus,createdAt) "
            "VALUES ($1,$2,$3,$4,$5,$6,'REVIEW_REQUIRED',$7)",
            (str(uuid.uuid4()), str(guild_id), "0", "users.json:malformed", source_hash, "{}", now),
        )
        return {"source": str(path), "sourceSha256": source_hash, "snapshots": 0, "reviews": 1}
    snapshots = reviews = 0
    for user_id, payload in sorted(parsed.items(), key=lambda item: str(item[0])):
        games = payload.get("games") if isinstance(payload, dict) else None
        if not isinstance(games, dict):
            continue
        casino_games = {key: value for key, value in sorted(games.items())
                        if key in {"blackjack", "slot", "cf", "rps", "tebak", "gacha", "box"}}
        if not casino_games:
            continue
        sanitized = json.dumps(casino_games, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        row_hash = hashlib.sha256(sanitized.encode("utf-8")).hexdigest()
        source_key = "users.json:games"
        existing = connection.execute(
            "SELECT sourceHash FROM CasinoLegacyStatistic WHERE guildId=$1 AND userId=$2 AND sourceKey=$3",
            (str(guild_id), str(user_id), source_key),
        ).fetchone()
        if existing and existing[0] != row_hash:
            reviews += 1
            continue
        connection.execute(
            "INSERT OR IGNORE INTO CasinoLegacyStatistic "
            "(snapshotId,guildId,userId,sourceKey,sourceHash,sanitizedSnapshotJson,migrationStatus,createdAt) "
            "VALUES ($1,$2,$3,$4,$5,$6,'SNAPSHOT',$7)",
            (str(uuid.uuid4()), str(guild_id), str(user_id), source_key, row_hash, sanitized, now),
        )
        snapshots += int(existing is None)
    return {"source": str(path), "sourceSha256": source_hash, "snapshots": snapshots, "reviews": reviews}


def verify_phase5_staging(db_path):
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        marker = connection.execute(
            "SELECT name,checksum,status FROM EconomySchemaMigration WHERE version=$1",
            (ECONOMY_PHASE5_MIGRATION_VERSION,),
        ).fetchone()
        capable = phase5_capability_sync(connection)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        counts = {}
        for table in (
            "CasinoSession", "CasinoSessionAction", "CasinoSettlement", "CasinoBankrollReservation",
            "CasinoBankrollDistribution", "CasinoNotificationOutbox", "CasinoRecoveryReview",
            "CasinoLegacyStatistic", "CasinoAuthorization", "CasinoAuthorizationAudit",
        ):
            try:
                counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            except sqlite3.OperationalError:
                counts[table] = None
        return {
            "migrationVersion": ECONOMY_PHASE5_MIGRATION_VERSION,
            "migrationName": PHASE5_MIGRATION_NAME,
            "checksum": PHASE5_SCHEMA_CHECKSUM,
            "marker": list(marker) if marker else None,
            "schemaCapable": capable,
            "integrityCheck": integrity,
            "foreignKeyErrors": len(foreign_keys),
            "rowTotals": counts,
            "databaseSize": Path(db_path).stat().st_size,
            "databaseSha256": file_sha256(db_path),
        }
    finally:
        connection.close()


def phase5_dry_run(db_path):
    verification = verify_phase5_staging(db_path)
    manifest = logical_sqlite_manifest(db_path)
    marker = verification["marker"]
    mismatch = bool(marker and marker[1] != PHASE5_SCHEMA_CHECKSUM)
    return {
        "mode": "DRY_RUN",
        "alreadyApplied": verification["schemaCapable"],
        "checksumMismatch": mismatch,
        "canApply": not mismatch and manifest["integrity_check"] == "ok" and manifest["foreign_key_errors"] == 0,
        "verification": verification,
        "manifest": manifest,
    }


def apply_phase5_staging(target_db, *, production_db, guild_id="0", users_json_path=None,
                         backup_path=None, failure_stage=None):
    assert_not_production(target_db, production_db)
    dry_run = phase5_dry_run(target_db)
    if not dry_run["canApply"]:
        raise ValueError("Dry-run Phase 5 menolak apply.")
    if dry_run["alreadyApplied"]:
        return {"applied": False, "replayed": True, "verification": verify_phase5_staging(target_db)}
    backup = None
    if backup_path:
        assert_not_production(backup_path, production_db)
        if _resolved(backup_path) == _resolved(target_db):
            raise ValueError("Backup harus berbeda dari database target.")
        backup = create_logical_sqlite_backup(target_db, backup_path)

    connection = sqlite3.connect(target_db)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT checksum,status FROM EconomySchemaMigration WHERE version=$1",
            (ECONOMY_PHASE5_MIGRATION_VERSION,),
        ).fetchone()
        if existing and existing[0] != PHASE5_SCHEMA_CHECKSUM:
            raise ValueError("Checksum migration 500 yang sudah tercatat berbeda.")
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO EconomySchemaMigration "
            "(version,name,checksum,status,startedAt,detailsJson) VALUES ($1,$2,$3,'RUNNING',$4,'{}') "
            "ON CONFLICT(version) DO UPDATE SET status='RUNNING',startedAt=excluded.startedAt",
            (ECONOMY_PHASE5_MIGRATION_VERSION, PHASE5_MIGRATION_NAME, PHASE5_SCHEMA_CHECKSUM, now),
        )
        if failure_stage == "after_marker":
            raise RuntimeError("Injected Phase 5 migration failure")
        for statement in _statements(PHASE5_TABLE_SQL):
            connection.execute(statement)
        if failure_stage == "after_tables":
            raise RuntimeError("Injected Phase 5 migration failure")
        for statement in PHASE5_INDEX_SQL:
            connection.execute(statement)
        for statement in PHASE5_TRIGGER_SQL:
            connection.execute(statement)
        if failure_stage == "after_triggers":
            raise RuntimeError("Injected Phase 5 migration failure")
        legacy = _legacy_snapshots(connection, guild_id, users_json_path, now)
        connection.execute(
            "UPDATE EconomySchemaMigration SET status='COMPLETED',completedAt=$1,detailsJson=$2 WHERE version=$3",
            (now, json.dumps({"legacy": legacy}, sort_keys=True, separators=(",", ":")),
             ECONOMY_PHASE5_MIGRATION_VERSION),
        )
        if not phase5_capability_sync(connection):
            raise RuntimeError("Capability schema Casino gagal sebelum commit.")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Foreign key schema Casino tidak valid.")
        if failure_stage == "before_commit":
            raise RuntimeError("Injected Phase 5 migration failure")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    verification = verify_phase5_staging(target_db)
    if not verification["schemaCapable"] or verification["integrityCheck"] != "ok" or verification["foreignKeyErrors"]:
        raise RuntimeError("Verifikasi akhir migration Phase 5 gagal.")
    return {"applied": True, "replayed": False, "backup": backup, "verification": verification}


def reconcile_phase5_staging(db_path):
    connection = sqlite3.connect(db_path)
    try:
        checks = {
            "settlementWithoutSession": connection.execute(
                "SELECT COUNT(*) FROM CasinoSettlement x LEFT JOIN CasinoSession s ON s.sessionId=x.sessionId WHERE s.sessionId IS NULL"
            ).fetchone()[0],
            "reservationWithoutSession": connection.execute(
                "SELECT COUNT(*) FROM CasinoBankrollReservation r LEFT JOIN CasinoSession s ON s.sessionId=r.sessionId WHERE s.sessionId IS NULL"
            ).fetchone()[0],
            "terminalActiveReservation": connection.execute(
                "SELECT COUNT(*) FROM CasinoSession s JOIN CasinoBankrollReservation r ON r.sessionId=s.sessionId "
                "WHERE s.status IN ('COMMITTED','VOID') AND r.status!='RELEASED'"
            ).fetchone()[0],
            "unbalancedTransactions": connection.execute(
                "SELECT COUNT(*) FROM (SELECT l.transactionId,SUM(l.amount) total FROM EconomyLedger l "
                "JOIN CasinoSettlement s ON s.transactionId=l.transactionId GROUP BY l.transactionId HAVING total<>0)"
            ).fetchone()[0],
        }
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        blocking = sum(int(value) for value in checks.values())
        return {"checks": checks, "blocking": blocking, "integrityCheck": integrity,
                "foreignKeyErrors": foreign_keys, "reconciled": blocking == 0 and integrity == "ok" and not foreign_keys}
    finally:
        connection.close()


def restore_phase5_staging(target_db, *, backup_path, production_db, confirm=False):
    if not confirm:
        raise ValueError("Restore Phase 5 memerlukan konfirmasi eksplisit.")
    assert_not_production(target_db, production_db)
    assert_not_production(backup_path, production_db)
    backup_manifest = logical_sqlite_manifest(backup_path)
    if backup_manifest["integrity_check"] != "ok" or backup_manifest["foreign_key_errors"]:
        raise ValueError("Backup Phase 5 tidak valid.")
    safety = str(_resolved(target_db).with_suffix(".pre-phase5-restore.db"))
    create_logical_sqlite_backup(target_db, safety)
    try:
        restore_logical_sqlite_backup(backup_path, target_db)
        manifest = logical_sqlite_manifest(target_db)
        if manifest["integrity_check"] != "ok" or manifest["foreign_key_errors"]:
            raise RuntimeError("Hasil restore Phase 5 tidak valid.")
    except Exception:
        restore_logical_sqlite_backup(safety, target_db)
        raise
    return {"restored": True, "safetyBackup": safety, "verification": verify_phase5_staging(target_db)}
