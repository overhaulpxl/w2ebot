"""Manual, production-refusing migration 910 for Phase 9B."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from .constants import PHASE9B_DASHBOARD_MIGRATION_VERSION
from .phase9a_schema import phase9a_capability_sync
from .phase9b_schema import (
    PHASE9B_INDEX_SQL, PHASE9B_MIGRATION_NAME, PHASE9B_SCHEMA_CHECKSUM,
    PHASE9B_TABLE_SQL, PHASE9B_TRIGGER_SQL, phase9b_capability_sync,
)
from .staging import create_logical_sqlite_backup, logical_sqlite_manifest, restore_logical_sqlite_backup


LEGACY_ROUTE_MAP = {
    "default": "GENERAL", "market": "MARKET_CRYPTO", "levelup": "LEVEL_UP",
    "birthday": "BIRTHDAY", "boss": "BOSS", "booster": "BOOSTER",
    "booster_channel_id": "BOOSTER", "binomo": None,
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _resolved(path):
    return Path(path).expanduser().resolve()


def assert_not_production(target_db, production_db):
    if _resolved(target_db) == _resolved(production_db):
        raise ValueError("Migrasi Phase 9B menolak database production.")


def _statements(script):
    pending = ""
    for line in script.splitlines():
        pending += line + "\n"
        if sqlite3.complete_statement(pending):
            value, pending = pending.strip(), ""
            if value:
                yield value
    if pending.strip():
        raise ValueError("Schema Phase 9B tidak lengkap.")


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha(value):
    raw = value if isinstance(value, bytes) else str(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_json_file(path):
    if not path:
        return None, None
    raw = Path(path).read_bytes()
    return json.loads(raw.decode("utf-8")), _sha(raw)


def _manifest_index(manifest, allowed_guild_id):
    if not isinstance(manifest, dict) or str(manifest.get("guildId", "")) != str(allowed_guild_id):
        return {}, {}, None
    channels = {}
    for item in manifest.get("channels", []):
        if not isinstance(item, dict) or not str(item.get("id", "")).isdigit():
            continue
        channels[str(item["id"])] = item
    roles = {}
    for item in manifest.get("roles", []):
        if isinstance(item, dict) and str(item.get("id", "")).isdigit():
            roles[str(item["id"])] = item
    return channels, roles, _sha(_canonical_json(manifest))


def _legacy_values(config):
    if not isinstance(config, dict):
        return {}
    result = {}
    announce = config.get("announce_channels")
    if isinstance(announce, dict):
        result.update({str(key): value for key, value in announce.items()})
    if "booster_channel_id" in config and "booster" not in result:
        result["booster_channel_id"] = config.get("booster_channel_id")
    return result


def _import_legacy_routes(connection, *, config, config_hash, manifest, guild_id, now):
    values = _legacy_values(config)
    channels, _, manifest_hash = _manifest_index(manifest, guild_id)
    imported = issues = 0
    for key, raw_value in sorted(values.items()):
        mapped = LEGACY_ROUTE_MAP.get(key)
        destination = str(raw_value).strip() if raw_value is not None else ""
        if key not in LEGACY_ROUTE_MAP:
            disposition = "UNRECOGNIZED"
        elif key == "binomo":
            disposition = "DEPRECATED"
        elif not destination.isdigit():
            disposition = "INVALID"
        else:
            capability = channels.get(destination)
            if capability is None:
                disposition = "MISSING"
            elif str(capability.get("guildId", guild_id)) != str(guild_id):
                disposition = "FOREIGN_GUILD"
            elif capability.get("type") not in ("text", "news") or not capability.get("botCanView") or not capability.get("botCanSend"):
                disposition = "UNWRITABLE"
            else:
                disposition = "IMPORTED"
        value_hash = _sha(_canonical_json({"key": key, "value": destination}))
        snapshot_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:p9b:{guild_id}:{key}:{value_hash}"))
        connection.execute(
            "INSERT OR IGNORE INTO DashboardNotificationLegacySnapshot "
            "(snapshotId,guildId,sourceKey,mappedCategory,destinationId,sourceFileHash,sourceValueHash,"
            "capabilityManifestHash,disposition,evidenceJson,createdAt) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (snapshot_id, str(guild_id), key, mapped, destination or None, config_hash or _sha(b""),
             value_hash, manifest_hash, disposition,
             _canonical_json({"sourceKey": key, "validatedByManifest": bool(manifest_hash)}), now),
        )
        if disposition == "IMPORTED":
            connection.execute(
                "INSERT INTO DashboardNotificationRoute "
                "(guildId,category,enabled,channelId,eventFilterJson,version,updatedById,updatedAt) "
                "VALUES (?,?,1,?,'{\"eventTypes\":[]}',0,'MIGRATION_910',?) "
                "ON CONFLICT(guildId,category) DO NOTHING",
                (str(guild_id), mapped, destination, now),
            )
            imported += 1
        else:
            issues += 1
    return {"imported": imported, "issues": issues, "sourceRows": len(values)}


def phase9b_dry_run(db_path, *, legacy_config_path=None, channel_manifest_path=None, guild_id=None):
    connection = sqlite3.connect(db_path)
    try:
        marker = connection.execute(
            "SELECT name,checksum,status FROM EconomySchemaMigration WHERE version=?",
            (PHASE9B_DASHBOARD_MIGRATION_VERSION,),
        ).fetchone()
        config, _ = _load_json_file(legacy_config_path)
        manifest, _ = _load_json_file(channel_manifest_path)
        channels, _, manifest_hash = _manifest_index(manifest, guild_id) if guild_id else ({}, {}, None)
        return {
            "migrationVersion": PHASE9B_DASHBOARD_MIGRATION_VERSION,
            "migrationName": PHASE9B_MIGRATION_NAME,
            "checksum": PHASE9B_SCHEMA_CHECKSUM,
            "existingMarker": marker,
            "wouldApply": marker is None,
            "legacyKeys": sorted(_legacy_values(config)),
            "manifestChannelCount": len(channels),
            "manifestHash": manifest_hash,
        }
    finally:
        connection.close()


def apply_phase9b_staging(target_db, *, production_db, backup_path=None, legacy_config_path=None,
                          channel_manifest_path=None, guild_id=None, failure_stage=None):
    assert_not_production(target_db, production_db)
    backup = create_logical_sqlite_backup(target_db, backup_path) if backup_path else None
    config, config_hash = _load_json_file(legacy_config_path)
    manifest, _ = _load_json_file(channel_manifest_path)
    connection = sqlite3.connect(target_db, isolation_level=None)
    connection.execute("PRAGMA foreign_keys=ON")
    now = _now()
    try:
        connection.execute("BEGIN IMMEDIATE")
        if not phase9a_capability_sync(connection):
            raise RuntimeError("Capability Phase 9A wajib sebelum migrasi Phase 9B.")
        marker = connection.execute(
            "SELECT name,checksum,status FROM EconomySchemaMigration WHERE version=?",
            (PHASE9B_DASHBOARD_MIGRATION_VERSION,),
        ).fetchone()
        if marker:
            if marker == (PHASE9B_MIGRATION_NAME, PHASE9B_SCHEMA_CHECKSUM, "COMPLETED") and phase9b_capability_sync(connection):
                connection.rollback()
                return {"applied": False, "replayed": True, "checksum": PHASE9B_SCHEMA_CHECKSUM,
                        "backup": backup}
            raise RuntimeError("Marker migrasi Phase 9B tidak cocok atau schema tidak lengkap.")
        connection.execute(
            "INSERT INTO EconomySchemaMigration (version,name,checksum,status,startedAt,backupPath) "
            "VALUES (?,?,?,'RUNNING',?,?)",
            (PHASE9B_DASHBOARD_MIGRATION_VERSION, PHASE9B_MIGRATION_NAME,
             PHASE9B_SCHEMA_CHECKSUM, now, str(backup) if backup else None),
        )
        if failure_stage == "after_marker":
            raise RuntimeError("injected failure after_marker")
        for statement in _statements(PHASE9B_TABLE_SQL):
            connection.execute(statement)
        if failure_stage == "after_tables":
            raise RuntimeError("injected failure after_tables")
        for statement in PHASE9B_INDEX_SQL:
            connection.execute(statement)
        if failure_stage == "after_indexes":
            raise RuntimeError("injected failure after_indexes")
        for statement in PHASE9B_TRIGGER_SQL:
            connection.execute(statement)
        if failure_stage == "after_triggers":
            raise RuntimeError("injected failure after_triggers")
        imported = {"imported": 0, "issues": 0, "sourceRows": 0}
        if config is not None:
            if not guild_id:
                raise ValueError("guild_id wajib saat mengimpor konfigurasi legacy.")
            imported = _import_legacy_routes(
                connection, config=config, config_hash=config_hash, manifest=manifest,
                guild_id=guild_id, now=now,
            )
        if failure_stage == "after_import":
            raise RuntimeError("injected failure after_import")
        connection.execute(
            "UPDATE EconomySchemaMigration SET status='COMPLETED',completedAt=? WHERE version=? AND status='RUNNING'",
            (now, PHASE9B_DASHBOARD_MIGRATION_VERSION),
        )
        if failure_stage == "before_commit":
            raise RuntimeError("injected failure before_commit")
        connection.commit()
        return {"applied": True, "replayed": False, "checksum": PHASE9B_SCHEMA_CHECKSUM,
                "backup": backup, "legacyImport": imported}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _reconciliation_values(connection, guild_id):
    guild = str(guild_id)
    ledger_totals = {}
    for transaction_id, currency, amount in connection.execute(
        "SELECT l.transactionId,l.currency,l.amount FROM EconomyLedger l JOIN EconomyTransaction t "
        "ON t.transactionId=l.transactionId WHERE t.guildId=? AND t.status='COMMITTED'", (guild,),
    ):
        key = (transaction_id, currency)
        ledger_totals[key] = ledger_totals.get(key, 0) + int(amount)
    unbalanced = sum(1 for value in ledger_totals.values() if value)
    supply_totals = {"ETM": 0, "ECY": 0}
    for etm, ecy in connection.execute("SELECT etmBalance,ecyBalance FROM EconomyWallet WHERE guildId=?", (guild,)):
        supply_totals["ETM"] += int(etm)
        supply_totals["ECY"] += int(ecy)
    for currency, balance in connection.execute(
        "SELECT currency,balance FROM EconomySystemAccount WHERE guildId=?", (guild,),
    ):
        supply_totals[str(currency)] += int(balance)
    supply_mismatches = sum(1 for value in supply_totals.values() if value)
    liability_mismatches = 0
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if {"CasinoBankrollReservation", "CasinoSession"}.issubset(tables):
        liability_mismatches += connection.execute(
            "SELECT COUNT(*) FROM CasinoBankrollReservation r JOIN CasinoSession s ON s.sessionId=r.sessionId "
            "WHERE r.guildId=? AND r.liabilityEcy<>s.maximumGrossLiabilityEcy", (guild,),
        ).fetchone()[0]
    if {"EternalOptionReservation", "EternalOptionPosition"}.issubset(tables):
        liability_mismatches += connection.execute(
            "SELECT COUNT(*) FROM EternalOptionReservation r JOIN EternalOptionPosition p ON p.positionId=r.positionId "
            "WHERE r.guildId=? AND r.liabilityEcy<>p.liabilityEcy", (guild,),
        ).fetchone()[0]
    route_issues = connection.execute(
        "SELECT (SELECT COUNT(*) FROM DashboardNotificationLegacySnapshot WHERE guildId=? AND disposition<>'IMPORTED') "
        "+ (SELECT COUNT(*) FROM DashboardNotificationRoute WHERE guildId=? AND enabled=1 AND channelId IS NULL)",
        (guild, guild),
    ).fetchone()[0]
    outbox_issues = connection.execute(
        "SELECT COUNT(*) FROM DashboardNotificationDelivery WHERE guildId=? AND status IN ('FAILED','REVIEW_REQUIRED')",
        (guild,),
    ).fetchone()[0]
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    foreign = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    return {"integrityResult": integrity, "foreignKeyErrors": foreign,
            "ledgerUnbalanced": int(unbalanced), "routeIssues": int(route_issues),
            "outboxIssues": int(outbox_issues), "supplyMismatches": int(supply_mismatches),
            "liabilityMismatches": int(liability_mismatches)}


def reconcile_phase9b_staging(db_path, *, guild_id):
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        if not phase9b_capability_sync(connection):
            return {"reconciled": False, "code": "capability_unavailable"}
        started = _now()
        report = _reconciliation_values(connection, guild_id)
        status = "PASSED" if (report["integrityResult"] == "ok" and not report["foreignKeyErrors"]
                              and not report["ledgerUnbalanced"] and not report["supplyMismatches"]
                              and not report["liabilityMismatches"]) else "FAILED"
        completed = _now()
        report_json = _canonical_json(report)
        connection.execute(
            "INSERT INTO DashboardEconomyReconciliationRun "
            "(runId,guildId,schemaChecksum,status,integrityResult,foreignKeyErrorCount,ledgerUnbalancedCount,"
            "supplyMismatchCount,liabilityMismatchCount,routeIssueCount,outboxIssueCount,reportJson,reportHash,startedAt,completedAt) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), str(guild_id), PHASE9B_SCHEMA_CHECKSUM, status,
             report["integrityResult"], report["foreignKeyErrors"], report["ledgerUnbalanced"],
             report["supplyMismatches"], report["liabilityMismatches"], report["routeIssues"],
             report["outboxIssues"], report_json, _sha(report_json), started, completed),
        )
        connection.commit()
        return {"reconciled": status == "PASSED", **report}
    finally:
        connection.close()


def verify_phase9b_staging(db_path):
    connection = sqlite3.connect(db_path)
    try:
        capable = phase9b_capability_sync(connection)
        return {
            "schemaCapable": capable,
            "migrationVersion": PHASE9B_DASHBOARD_MIGRATION_VERSION,
            "migrationName": PHASE9B_MIGRATION_NAME,
            "migrationChecksum": PHASE9B_SCHEMA_CHECKSUM,
            "integrityCheck": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreignKeyErrors": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
            "routeCount": connection.execute("SELECT COUNT(*) FROM DashboardNotificationRoute").fetchone()[0] if capable else 0,
        }
    finally:
        connection.close()


def restore_phase9b_staging(target_db, *, backup_path, production_db, confirm=False):
    assert_not_production(target_db, production_db)
    if not confirm:
        raise ValueError("Restore Phase 9B memerlukan confirm=True.")
    safety = create_logical_sqlite_backup(target_db, str(target_db) + ".pre-restore-safety.db")
    restored = restore_logical_sqlite_backup(backup_path, target_db)
    return {"restored": True, "target": str(restored), "safetyBackup": str(safety),
            "manifest": logical_sqlite_manifest(target_db)}
