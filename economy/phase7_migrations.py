"""Migrasi Mining Phase 7 yang eksplisit, staging-only, dan idempoten."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from .constants import CRYPTO_ASSETS, ECONOMY_PHASE7_MIGRATION_VERSION, MINING_RIG_CATALOG
from .phase7_schema import (
    PHASE7_CATALOG_VERSION, PHASE7_INDEX_SQL, PHASE7_MIGRATION_NAME,
    PHASE7_SCHEMA_CHECKSUM, PHASE7_TABLE_SQL, PHASE7_TRIGGER_SQL,
    REQUIRED_PHASE7_TABLES, phase3_profile_capability_sync, phase7_capability_sync,
)
from .phase6_schema import phase6_capability_sync
from .staging import create_logical_sqlite_backup, logical_sqlite_manifest, restore_logical_sqlite_backup


def _resolved(path):
    return Path(path).expanduser().resolve()


def assert_not_production(target_db, production_db):
    if _resolved(target_db) == _resolved(production_db):
        raise ValueError("Migrasi Phase 7 menolak database production.")


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
            statement, pending = pending.strip(), ""
            if statement:
                yield statement
    if pending.strip():
        raise ValueError("Schema Mining mengandung SQL tidak lengkap.")


def _phase1_target_guild(connection, explicit_guild_id=None):
    rows = connection.execute(
        "SELECT DISTINCT guildId FROM EconomyMigrationRun WHERE migrationVersion=100 AND status='COMPLETED'"
    ).fetchall()
    guilds = sorted({str(row[0]) for row in rows if row[0] is not None})
    explicit = str(explicit_guild_id) if explicit_guild_id is not None else None
    if explicit and guilds and guilds != [explicit]:
        raise ValueError("Guild target Mining berbeda dari resolusi migration Phase 1.")
    return (explicit if explicit and not guilds else (guilds[0] if len(guilds) == 1 else None)), guilds


def _legacy_users_raw(connection, users_json_path):
    if users_json_path:
        path = Path(users_json_path)
        return (path.read_bytes(), str(path)) if path.exists() else (None, str(path))
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='json_store'"
    ).fetchone()
    if not exists:
        return None, None
    row = connection.execute("SELECT content FROM json_store WHERE filename='users.json'").fetchone()
    return (row[0].encode("utf-8"), "json_store:users.json") if row else (None, None)


def _legacy_entries(parsed):
    for user_id, payload in sorted(parsed.items(), key=lambda item: str(item[0])):
        if isinstance(payload, dict):
            for key, value in sorted(payload.items(), key=lambda item: str(item[0])):
                lowered = str(key).lower()
                if "pending" in lowered and ("min" in lowered or "rig" in lowered):
                    yield str(user_id), "LEGACY", str(key), 1, value, "unknown_pending_field"
        rigs = payload.get("rigs") if isinstance(payload, dict) else None
        if not isinstance(rigs, dict):
            continue
        if all(str(key).isdigit() for key in rigs):
            rigs = {"ETHR": rigs}
        for raw_symbol, tiers in sorted(rigs.items(), key=lambda item: str(item[0])):
            symbol = str(raw_symbol).upper()
            if not isinstance(tiers, dict):
                yield str(user_id), symbol, "invalid", 1, tiers, "malformed_rig_group"
                continue
            for raw_tier, raw_count in sorted(tiers.items(), key=lambda item: str(item[0])):
                tier_text = str(raw_tier)
                if (isinstance(raw_count, bool) or not isinstance(raw_count, int) or
                        raw_count <= 0 or raw_count > 1_000):
                    yield str(user_id), symbol, tier_text, 1, raw_count, "invalid_count"
                    continue
                for ordinal in range(1, raw_count + 1):
                    yield str(user_id), symbol, tier_text, ordinal, raw_count, None


def _record_legacy(connection, *, user_id, symbol, tier_text, ordinal, raw_value,
                   source_hash, guild_id, rig_id, status, error_code, now):
    existing = connection.execute(
        "SELECT sourceHash FROM MiningLegacyRigMigration WHERE sourceUserId=$1 AND sourceSymbol=$2 AND sourceTierText=$3 AND sourceOrdinal=$4",
        (user_id, symbol, tier_text, ordinal),
    ).fetchone()
    if existing:
        if existing[0] != source_hash:
            connection.execute(
                "INSERT OR IGNORE INTO MiningRecoveryReview "
                "(reviewId,guildId,entityType,entityId,errorCode,status,sanitizedMetadataJson,firstDetectedAt,lastAttemptedAt) "
                "VALUES ($1,$2,$3,$4,$5,'OPEN','{}',$6,$7)",
                (str(uuid.uuid4()), guild_id, "LEGACY_RIG", f"{user_id}:{symbol}:{tier_text}:{ordinal}",
                 "changed_source_hash", now, now),
            )
            return "changed"
        return "replayed"
    raw_json = json.dumps(raw_value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    connection.execute(
        "INSERT INTO MiningLegacyRigMigration "
        "(sourceUserId,sourceSymbol,sourceTierText,sourceOrdinal,sourceHash,targetGuildId,rigInstanceId,status,errorCode,rawSourceJson,sanitizedMetadataJson,migratedAt) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
        (user_id, symbol, tier_text, ordinal, source_hash, guild_id, rig_id, status,
         error_code, raw_json, json.dumps({"ordinal": ordinal}, separators=(",", ":")), now),
    )
    return "inserted"


def _slot_limit(level):
    return 4 if level >= 70 else 3 if level >= 45 else 2 if level >= 25 else 1 if level >= 10 else 0


def _migrate_legacy_rigs(connection, *, guild_id, users_json_path, now):
    raw, source = _legacy_users_raw(connection, users_json_path)
    totals = {"source": source, "sourceSha256": None, "migrated": 0, "reviewRequired": 0,
              "unsupportedTiers": 0, "replayed": 0, "changedHashes": 0}
    if raw is None:
        return totals
    totals["sourceSha256"] = hashlib.sha256(raw).hexdigest()
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        totals["reviewRequired"] += 1
        return totals
    if not isinstance(parsed, dict):
        totals["reviewRequired"] += 1
        return totals
    created_by_user = {}
    tier_map = {"1": "rig_basic", "2": "rig_advanced", "3": "rig_elite"}
    for user_id, symbol, tier_text, ordinal, raw_value, pre_error in _legacy_entries(parsed):
        identity = f"{user_id}\n{symbol}\n{tier_text}\n{ordinal}\n{json.dumps(raw_value, sort_keys=True)}"
        source_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        definition = tier_map.get(tier_text)
        error = pre_error
        if not error and guild_id is None:
            error = "ambiguous_target_guild"
        elif not error and symbol not in CRYPTO_ASSETS:
            error = "unknown_symbol"
        elif not error and definition is None:
            error = "unsupported_legacy_tier"
            totals["unsupportedTiers"] += 1
        profile = None if guild_id is None else connection.execute(
            "SELECT level FROM RpgProfile WHERE guildId=$1 AND userId=$2", (guild_id, user_id)
        ).fetchone()
        if not error and (not profile or not 1 <= int(profile[0]) <= 100):
            error = "missing_or_invalid_profile"
        count = created_by_user.get(user_id, 0)
        if not error and count >= _slot_limit(int(profile[0])):
            error = "slot_limit_exceeded"
        rig_id = None
        if not error:
            rig_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:mining:{guild_id}:{user_id}:{symbol}:{tier_text}:{ordinal}"))
        outcome = _record_legacy(
            connection, user_id=user_id, symbol=symbol, tier_text=tier_text, ordinal=ordinal,
            raw_value=raw_value, source_hash=source_hash, guild_id=guild_id, rig_id=rig_id,
            status="REVIEW_REQUIRED" if error else "MIGRATED", error_code=error, now=now,
        )
        if outcome == "replayed":
            totals["replayed"] += 1
            continue
        if outcome == "changed":
            totals["changedHashes"] += 1
            continue
        if error:
            totals["reviewRequired"] += 1
            continue
        connection.execute(
            "INSERT INTO MiningRigInstance "
            "(rigInstanceId,guildId,userId,rigDefinitionId,catalogVersion,targetSymbol,status,durabilityBps,paidThrough,accruedThrough,migrationSourceHash,version,createdAt,updatedAt) "
            "VALUES ($1,$2,$3,$4,$5,$6,'MAINTENANCE_DUE',10000,NULL,$7,$8,0,$9,$10)",
            (rig_id, guild_id, user_id, definition, PHASE7_CATALOG_VERSION, symbol, now, source_hash, now, now),
        )
        created_by_user[user_id] = count + 1
        totals["migrated"] += 1
    return totals


def verify_phase7_staging(db_path):
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        marker = connection.execute(
            "SELECT name,checksum,status FROM EconomySchemaMigration WHERE version=$1",
            (ECONOMY_PHASE7_MIGRATION_VERSION,),
        ).fetchone()
        counts = {}
        for table in sorted(REQUIRED_PHASE7_TABLES):
            try:
                counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            except sqlite3.OperationalError:
                counts[table] = None
        return {
            "migrationVersion": ECONOMY_PHASE7_MIGRATION_VERSION,
            "migrationName": PHASE7_MIGRATION_NAME,
            "checksum": PHASE7_SCHEMA_CHECKSUM,
            "marker": list(marker) if marker else None,
            "schemaCapable": phase7_capability_sync(connection),
            "integrityCheck": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreignKeyErrors": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
            "rowTotals": counts,
            "databaseSize": Path(db_path).stat().st_size,
            "databaseSha256": file_sha256(db_path),
        }
    finally:
        connection.close()


def phase7_dry_run(db_path):
    connection = sqlite3.connect(db_path)
    try:
        prereqs = phase3_profile_capability_sync(connection) and phase6_capability_sync(connection)
        marker = connection.execute(
            "SELECT checksum,status FROM EconomySchemaMigration WHERE version=$1",
            (ECONOMY_PHASE7_MIGRATION_VERSION,),
        ).fetchone()
        already_applied = bool(marker and phase7_capability_sync(connection))
    finally:
        connection.close()
    manifest = logical_sqlite_manifest(db_path)
    mismatch = bool(marker and marker[0] != PHASE7_SCHEMA_CHECKSUM)
    marker_conflict = bool(marker and not already_applied)
    return {"mode": "DRY_RUN", "alreadyApplied": already_applied,
            "checksumMismatch": mismatch, "prerequisitesReady": prereqs,
            "markerConflict": marker_conflict,
            "canApply": prereqs and not mismatch and not marker_conflict and manifest["integrity_check"] == "ok" and not manifest["foreign_key_errors"],
            "manifest": manifest}


def apply_phase7_staging(target_db, *, production_db, guild_id=None, users_json_path=None,
                         backup_path=None, failure_stage=None):
    assert_not_production(target_db, production_db)
    dry = phase7_dry_run(target_db)
    if not dry["canApply"]:
        raise ValueError("Dry-run Phase 7 menolak apply.")
    if dry["alreadyApplied"]:
        return {"applied": False, "replayed": True, "verification": verify_phase7_staging(target_db)}
    backup = create_logical_sqlite_backup(target_db, backup_path) if backup_path else None
    connection = sqlite3.connect(target_db)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("BEGIN IMMEDIATE")
        now = datetime.now(timezone.utc).isoformat()
        resolved_guild, observed_guilds = _phase1_target_guild(connection, guild_id)
        connection.execute(
            "INSERT INTO EconomySchemaMigration (version,name,checksum,status,startedAt,detailsJson) VALUES ($1,$2,$3,'RUNNING',$4,'{}')",
            (ECONOMY_PHASE7_MIGRATION_VERSION, PHASE7_MIGRATION_NAME, PHASE7_SCHEMA_CHECKSUM, now),
        )
        if failure_stage == "after_marker":
            raise RuntimeError("Injected Phase 7 migration failure")
        for statement in _statements(PHASE7_TABLE_SQL):
            connection.execute(statement)
        if failure_stage == "after_tables":
            raise RuntimeError("Injected Phase 7 migration failure")
        for statement in PHASE7_INDEX_SQL:
            connection.execute(statement)
        for statement in PHASE7_TRIGGER_SQL:
            connection.execute(statement)
        if failure_stage == "after_triggers":
            raise RuntimeError("Injected Phase 7 migration failure")
        for rig_id, (name, price, gross, maintenance) in MINING_RIG_CATALOG.items():
            connection.execute(
                "INSERT INTO MiningRigCatalog (rigDefinitionId,name,purchasePriceEcy,grossEquivalentPerDay,maintenancePriceEcy,catalogVersion,createdAt) VALUES ($1,$2,$3,$4,$5,$6,$7)",
                (rig_id, name, price, gross, maintenance, PHASE7_CATALOG_VERSION, now),
            )
        legacy = _migrate_legacy_rigs(
            connection, guild_id=resolved_guild, users_json_path=users_json_path, now=now,
        )
        details = {"legacy": legacy, "phase1TargetGuilds": observed_guilds,
                   "resolvedTargetGuild": resolved_guild, "financialSeedApplied": False}
        connection.execute(
            "UPDATE EconomySchemaMigration SET status='COMPLETED',completedAt=$1,detailsJson=$2 WHERE version=$3",
            (now, json.dumps(details, sort_keys=True, separators=(",", ":")), ECONOMY_PHASE7_MIGRATION_VERSION),
        )
        if not phase7_capability_sync(connection):
            raise RuntimeError("Capability Mining gagal sebelum commit.")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Foreign key Mining tidak valid.")
        if failure_stage == "before_commit":
            raise RuntimeError("Injected Phase 7 migration failure")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    verification = verify_phase7_staging(target_db)
    if not verification["schemaCapable"] or verification["integrityCheck"] != "ok" or verification["foreignKeyErrors"]:
        raise RuntimeError("Verifikasi akhir migration Phase 7 gagal.")
    return {"applied": True, "replayed": False, "backup": backup, "verification": verification}


def reconcile_phase7_staging(db_path):
    connection = sqlite3.connect(db_path)
    try:
        checks = {
            "claimWithCurrencyTransaction": connection.execute(
                "SELECT COUNT(*) FROM MiningOperation WHERE operationType='CLAIM' AND transactionId IS NOT NULL"
            ).fetchone()[0],
            "unbalancedAssetClaims": connection.execute(
                "SELECT COUNT(*) FROM (SELECT claimId,symbol,SUM(unitsDelta) total FROM MiningAssetLedger GROUP BY claimId,symbol HAVING total<>0)"
            ).fetchone()[0],
            "negativePending": connection.execute(
                "SELECT COUNT(*) FROM MiningPendingAsset WHERE pendingUnits<0 OR fractionalBillionths<0 OR fractionalBillionths>=1000000000"
            ).fetchone()[0],
            "unsupportedTierMigrated": connection.execute(
                "SELECT COUNT(*) FROM MiningLegacyRigMigration WHERE sourceTierText NOT IN ('1','2','3') AND status='MIGRATED'"
            ).fetchone()[0],
            "financialWithoutTransaction": connection.execute(
                "SELECT COUNT(*) FROM MiningOperation WHERE operationType IN ('PURCHASE','MAINTENANCE') AND status='COMMITTED' AND transactionId IS NULL"
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


def restore_phase7_staging(target_db, *, backup_path, production_db, confirm=False):
    if not confirm:
        raise ValueError("Restore Phase 7 memerlukan konfirmasi eksplisit.")
    assert_not_production(target_db, production_db)
    assert_not_production(backup_path, production_db)
    manifest = logical_sqlite_manifest(backup_path)
    if manifest["integrity_check"] != "ok" or manifest["foreign_key_errors"]:
        raise ValueError("Backup Phase 7 tidak valid.")
    restore_logical_sqlite_backup(backup_path, target_db)
    return {"restored": True, "manifest": logical_sqlite_manifest(target_db)}
