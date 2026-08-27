"""Migration Crypto Phase 6 yang eksplisit dan staging-only."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from .constants import ASSET_UNIT_SCALE, CRYPTO_ASSETS, ECONOMY_PHASE6_MIGRATION_VERSION
from .phase6_schema import (
    PHASE6_INDEX_SQL, PHASE6_MIGRATION_NAME, PHASE6_SCHEMA_CHECKSUM,
    PHASE6_TABLE_SQL, PHASE6_TRIGGER_SQL, phase6_capability_sync,
)
from .staging import create_logical_sqlite_backup, logical_sqlite_manifest, restore_logical_sqlite_backup


def _resolved(path):
    return Path(path).expanduser().resolve()


def assert_not_production(target_db, production_db):
    if _resolved(target_db) == _resolved(production_db):
        raise ValueError("Migrasi Phase 6 menolak database production.")


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
        raise ValueError("Schema Crypto mengandung SQL tidak lengkap.")


def _phase1_target_guild(connection, explicit_guild_id=None):
    rows = connection.execute(
        "SELECT DISTINCT guildId FROM EconomyMigrationRun WHERE migrationVersion=100 AND status='COMPLETED'"
    ).fetchall()
    guilds = sorted({str(row[0]) for row in rows if row[0] is not None})
    explicit = str(explicit_guild_id) if explicit_guild_id is not None else None
    if explicit and guilds and guilds != [explicit]:
        raise ValueError("Guild target Phase 6 berbeda dari resolusi migration Phase 1.")
    return guilds[0] if len(guilds) == 1 else None, guilds


def _legacy_users_raw(connection, users_json_path):
    if users_json_path:
        path = Path(users_json_path)
        return path.read_bytes() if path.exists() else None, str(path)
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='json_store'"
    ).fetchone()
    if not table:
        return None, None
    row = connection.execute("SELECT content FROM json_store WHERE filename='users.json'").fetchone()
    return (row[0].encode("utf-8"), "json_store:users.json") if row else (None, None)


def _source_hash(user_id, symbol, raw_value):
    value = f"{user_id}\n{symbol}\n{raw_value}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _record_legacy(connection, *, user_id, symbol, source_hash, guild_id, units,
                   status, error_code, metadata, now):
    existing = connection.execute(
        "SELECT sourceHash FROM CryptoLegacyHoldingMigration WHERE sourceUserId=? AND sourceSymbol=?",
        (str(user_id), str(symbol)),
    ).fetchone()
    if existing:
        if existing[0] != source_hash:
            connection.execute(
                "INSERT OR IGNORE INTO CryptoRecoveryReview "
                "(reviewId,guildId,entityType,entityId,errorCode,status,sanitizedMetadataJson,firstDetectedAt,lastAttemptedAt) "
                "VALUES (?,?,?,?,?,'OPEN',?,?,?)",
                (str(uuid.uuid4()), guild_id, "LEGACY_HOLDING", f"{user_id}:{symbol}",
                 "changed_source_hash", "{}", now, now),
            )
            return "changed"
        return "replayed"
    connection.execute(
        "INSERT INTO CryptoLegacyHoldingMigration "
        "(sourceUserId,sourceSymbol,sourceHash,targetGuildId,targetUnits,status,errorCode,sanitizedMetadataJson,migratedAt) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (str(user_id), str(symbol), source_hash, guild_id, units, status, error_code,
         json.dumps(metadata, sort_keys=True, separators=(",", ":")), now),
    )
    return "inserted"


def _migrate_legacy_holdings(connection, *, guild_id, users_json_path, now):
    raw, source = _legacy_users_raw(connection, users_json_path)
    totals = {"source": source, "sourceSha256": None, "migrated": 0, "reviewRequired": 0,
              "replayed": 0, "changedHashes": 0}
    if raw is None:
        return totals
    totals["sourceSha256"] = hashlib.sha256(raw).hexdigest()
    try:
        parsed = json.loads(raw.decode("utf-8"), parse_float=Decimal, parse_int=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError):
        totals["reviewRequired"] = 1
        return totals
    if not isinstance(parsed, dict):
        totals["reviewRequired"] = 1
        return totals
    for user_id, payload in sorted(parsed.items(), key=lambda item: str(item[0])):
        holdings = payload.get("crypto") if isinstance(payload, dict) else None
        if not isinstance(holdings, dict):
            continue
        for raw_symbol, raw_value in sorted(holdings.items(), key=lambda item: str(item[0])):
            symbol = str(raw_symbol).upper()
            raw_text = str(raw_value)
            row_hash = _source_hash(user_id, symbol, raw_text)
            status, error, units = "MIGRATED", None, None
            try:
                value = raw_value if isinstance(raw_value, Decimal) else Decimal(raw_text)
                if not value.is_finite() or value < 0:
                    raise InvalidOperation
                exponent = -value.as_tuple().exponent
                if exponent > 8:
                    status, error = "REVIEW_REQUIRED", "over_precision"
                else:
                    units = int(value * ASSET_UNIT_SCALE)
            except (InvalidOperation, ValueError, TypeError):
                status, error = "REVIEW_REQUIRED", "invalid_quantity"
            if symbol not in CRYPTO_ASSETS:
                status, error, units = "REVIEW_REQUIRED", "unknown_symbol", None
            if guild_id is None:
                status, error = "REVIEW_REQUIRED", "ambiguous_target_guild"
            outcome = _record_legacy(
                connection, user_id=user_id, symbol=symbol, source_hash=row_hash,
                guild_id=guild_id, units=units, status=status, error_code=error,
                metadata={"quantity": raw_text}, now=now,
            )
            if outcome == "replayed":
                totals["replayed"] += 1
                continue
            if outcome == "changed":
                totals["changedHashes"] += 1
                continue
            if status == "MIGRATED" and units and units > 0:
                price = CRYPTO_ASSETS[symbol][1]
                cost_basis = units * price // ASSET_UNIT_SCALE
                connection.execute(
                    "INSERT INTO CryptoHolding "
                    "(guildId,userId,symbol,units,totalCostBasisEcy,realizedProfitEcy,status,migrationSourceHash,version,createdAt,updatedAt) "
                    "VALUES (?,?,?,?,?,0,'ACTIVE',?,0,?,?)",
                    (guild_id, str(user_id), symbol, units, cost_basis, row_hash, now, now),
                )
                totals["migrated"] += 1
            elif status == "REVIEW_REQUIRED":
                totals["reviewRequired"] += 1
    return totals


def verify_phase6_staging(db_path):
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        marker = connection.execute(
            "SELECT name,checksum,status FROM EconomySchemaMigration WHERE version=?",
            (ECONOMY_PHASE6_MIGRATION_VERSION,),
        ).fetchone()
        counts = {}
        for table in sorted(__import__("economy.phase6_schema", fromlist=["REQUIRED_PHASE6_TABLES"]).REQUIRED_PHASE6_TABLES):
            try:
                counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            except sqlite3.OperationalError:
                counts[table] = None
        return {
            "migrationVersion": ECONOMY_PHASE6_MIGRATION_VERSION,
            "migrationName": PHASE6_MIGRATION_NAME,
            "checksum": PHASE6_SCHEMA_CHECKSUM,
            "marker": list(marker) if marker else None,
            "schemaCapable": phase6_capability_sync(connection),
            "integrityCheck": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreignKeyErrors": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
            "rowTotals": counts,
            "databaseSize": Path(db_path).stat().st_size,
            "databaseSha256": file_sha256(db_path),
        }
    finally:
        connection.close()


def phase6_dry_run(db_path):
    verification = verify_phase6_staging(db_path)
    manifest = logical_sqlite_manifest(db_path)
    marker = verification["marker"]
    mismatch = bool(marker and marker[1] != PHASE6_SCHEMA_CHECKSUM)
    return {"mode": "DRY_RUN", "alreadyApplied": verification["schemaCapable"],
            "checksumMismatch": mismatch,
            "canApply": not mismatch and manifest["integrity_check"] == "ok" and not manifest["foreign_key_errors"],
            "verification": verification, "manifest": manifest}


def apply_phase6_staging(target_db, *, production_db, guild_id=None, users_json_path=None,
                         backup_path=None, failure_stage=None):
    assert_not_production(target_db, production_db)
    dry = phase6_dry_run(target_db)
    if not dry["canApply"]:
        raise ValueError("Dry-run Phase 6 menolak apply.")
    if dry["alreadyApplied"]:
        return {"applied": False, "replayed": True, "verification": verify_phase6_staging(target_db)}
    backup = None
    if backup_path:
        assert_not_production(backup_path, production_db)
        backup = create_logical_sqlite_backup(target_db, backup_path)
    connection = sqlite3.connect(target_db)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("BEGIN IMMEDIATE")
        now = datetime.now(timezone.utc).isoformat()
        resolved_guild, observed_guilds = _phase1_target_guild(connection, guild_id)
        connection.execute(
            "INSERT INTO EconomySchemaMigration (version,name,checksum,status,startedAt,detailsJson) "
            "VALUES (?,?,?,'RUNNING',?,'{}')",
            (ECONOMY_PHASE6_MIGRATION_VERSION, PHASE6_MIGRATION_NAME, PHASE6_SCHEMA_CHECKSUM, now),
        )
        if failure_stage == "after_marker":
            raise RuntimeError("Injected Phase 6 migration failure")
        for statement in _statements(PHASE6_TABLE_SQL):
            connection.execute(statement)
        if failure_stage == "after_tables":
            raise RuntimeError("Injected Phase 6 migration failure")
        for statement in PHASE6_INDEX_SQL:
            connection.execute(statement)
        for statement in PHASE6_TRIGGER_SQL:
            connection.execute(statement)
        if failure_stage == "after_triggers":
            raise RuntimeError("Injected Phase 6 migration failure")
        initial_tick = "phase6-initial"
        connection.execute(
            "INSERT INTO CryptoMarketTick (tickId,scheduledAt,outcomeJson,status,resultJson,createdAt,committedAt) "
            "VALUES (?,?,?,'COMMITTED',?,?,?)",
            (initial_tick, now, '{"type":"INITIAL"}', '{"initialized":true}', now, now),
        )
        for symbol, (name, price, maximum_bps, level) in CRYPTO_ASSETS.items():
            connection.execute(
                "INSERT INTO CryptoAssetDefinition "
                "(symbol,name,basePriceEcy,minimumPriceEcy,maximumPriceEcy,maximumNormalChangeBps,volatilityLevel,catalogVersion,createdAt) "
                "VALUES (?,?,?,?,?,?,?,'crypto-v1.0.0',?)",
                (symbol, name, price, price * 20 // 100, price * 500 // 100, maximum_bps, level, now),
            )
            connection.execute(
                "INSERT INTO CryptoMarketState (symbol,currentPriceEcy,lastTickId,version,updatedAt) VALUES (?,?,?,0,?)",
                (symbol, price, initial_tick, now),
            )
            connection.execute(
                "INSERT INTO CryptoPriceHistory "
                "(historyId,tickId,symbol,previousPriceEcy,currentPriceEcy,movementBps,movementType,occurredAt) "
                "VALUES (?,?,?,?,?,0,'INITIAL',?)",
                (str(uuid.uuid4()), initial_tick, symbol, price, price, now),
            )
        legacy = _migrate_legacy_holdings(
            connection, guild_id=resolved_guild, users_json_path=users_json_path, now=now,
        )
        details = {"legacy": legacy, "phase1TargetGuilds": observed_guilds,
                   "resolvedTargetGuild": resolved_guild, "financialSeedApplied": False}
        connection.execute(
            "UPDATE EconomySchemaMigration SET status='COMPLETED',completedAt=?,detailsJson=? WHERE version=?",
            (now, json.dumps(details, sort_keys=True, separators=(",", ":")), ECONOMY_PHASE6_MIGRATION_VERSION),
        )
        if not phase6_capability_sync(connection):
            raise RuntimeError("Capability Crypto gagal sebelum commit.")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Foreign key Crypto tidak valid.")
        if failure_stage == "before_commit":
            raise RuntimeError("Injected Phase 6 migration failure")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    verification = verify_phase6_staging(target_db)
    if not verification["schemaCapable"] or verification["integrityCheck"] != "ok" or verification["foreignKeyErrors"]:
        raise RuntimeError("Verifikasi akhir migration Phase 6 gagal.")
    return {"applied": True, "replayed": False, "backup": backup, "verification": verification}


def reconcile_phase6_staging(db_path):
    connection = sqlite3.connect(db_path)
    try:
        checks = {
            "tradeWithoutTransaction": connection.execute(
                "SELECT COUNT(*) FROM CryptoTrade c LEFT JOIN EconomyTransaction t ON t.transactionId=c.transactionId WHERE t.transactionId IS NULL"
            ).fetchone()[0],
            "committedWithoutReceipt": connection.execute(
                "SELECT COUNT(*) FROM CryptoTrade WHERE status='COMMITTED' AND receiptJson IS NULL"
            ).fetchone()[0],
            "negativeHolding": connection.execute(
                "SELECT COUNT(*) FROM CryptoHolding WHERE units<0 OR totalCostBasisEcy<0"
            ).fetchone()[0],
            "unbalancedTransactions": connection.execute(
                "SELECT COUNT(*) FROM (SELECT l.transactionId,SUM(l.amount) total FROM EconomyLedger l "
                "JOIN CryptoTrade c ON c.transactionId=l.transactionId GROUP BY l.transactionId HAVING total<>0)"
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


def restore_phase6_staging(target_db, *, backup_path, production_db, confirm=False):
    if not confirm:
        raise ValueError("Restore Phase 6 memerlukan konfirmasi eksplisit.")
    assert_not_production(target_db, production_db)
    assert_not_production(backup_path, production_db)
    manifest = logical_sqlite_manifest(backup_path)
    if manifest["integrity_check"] != "ok" or manifest["foreign_key_errors"]:
        raise ValueError("Backup Phase 6 tidak valid.")
    restore_logical_sqlite_backup(backup_path, target_db)
    return {"restored": True, "manifest": logical_sqlite_manifest(target_db)}
