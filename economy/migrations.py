import hashlib
import asyncio
import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .constants import (
    ECONOMY_MAX_AMOUNT,
    ECONOMY_MIGRATION_VERSION,
    ECONOMY_PHASE2_MIGRATION_VERSION,
    LEGACY_SCALE,
    RPG_DEFAULT_ATTACK,
    RPG_DEFAULT_CRIT_BPS,
    RPG_DEFAULT_DEFENSE,
    RPG_DEFAULT_MAX_HP,
    RPG_MAX_CRIT_BPS,
    SYSTEM_ACCOUNT_DEFINITIONS,
)
from .database import ensure_phase1_schema
from .treasury import get_supply_report


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_text(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _schema_hash(connection):
    rows = connection.execute(
        "SELECT type,name,COALESCE(sql,'') FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ).fetchall()
    return _hash_text(json.dumps(rows, separators=(",", ":"), ensure_ascii=True))


def _read_json_store(connection):
    try:
        rows = connection.execute("SELECT filename,content FROM json_store ORDER BY filename").fetchall()
    except sqlite3.OperationalError:
        return {}, {}
    parsed, hashes = {}, {}
    for filename, content in rows:
        hashes[str(filename)] = _hash_text(content or "")
        try:
            parsed[str(filename)] = json.loads(content or "{}")
        except (TypeError, ValueError):
            parsed[str(filename)] = None
    return parsed, hashes


def _legacy_rows(connection):
    try:
        return connection.execute("SELECT id,coins FROM DiscordStat ORDER BY id").fetchall()
    except sqlite3.OperationalError:
        return []


def _deferred_counts(blobs, connection):
    users = blobs.get("users.json") if isinstance(blobs.get("users.json"), dict) else {}
    counts = {
        "crypto_holdings": 0,
        "rigs": 0,
        "pets": 0,
        "inventory": 0,
        "quests": 0,
        "casino_stats": 0,
        "legacy_giveaways": 0,
        "market_prices": 0,
    }
    for data in users.values():
        if not isinstance(data, dict):
            continue
        counts["crypto_holdings"] += len(data.get("crypto", {})) if isinstance(data.get("crypto"), dict) else 0
        rigs = data.get("rigs", {})
        if isinstance(rigs, dict):
            counts["rigs"] += sum(
                len(v) if isinstance(v, dict) else 1 for v in rigs.values()
        if data.get("pet"):
            counts["pets"] += 1
        counts["inventory"] += len(data.get("items", {})) if isinstance(data.get("items"), dict) else 0
        counts["casino_stats"] += len(data.get("games", {})) if isinstance(data.get("games"), dict) else 0
    quests = blobs.get("quests.json")
    if isinstance(quests, dict):
        counts["quests"] = len(quests)
    market = blobs.get("market.json")
    if isinstance(market, dict) and isinstance(market.get("coins"), dict):
        counts["market_prices"] = len(market["coins"])
    try:
        counts["legacy_giveaways"] = int(connection.execute(
            "SELECT COUNT(*) FROM Giveaway WHERE ended=0"
        ).fetchone()[0])
    except sqlite3.OperationalError:
        pass
    return counts


def _binomo_projection(blobs, issues):
    positions = blobs.get("binomo.json")
    if not isinstance(positions, dict):
        return [], 0
    output = []
    total = 0
    for user_id, position in positions.items():
        bet = position.get("bet") if isinstance(position, dict) else None
        if not str(user_id).isdigit() or isinstance(bet, bool) or not isinstance(bet, int) or bet <= 0:
            issues["review_required"].append({"code": "INVALID_BINOMO_POSITION", "entity": "binomo"})
            continue
        refund = bet * LEGACY_SCALE
        if refund > ECONOMY_MAX_AMOUNT:
            issues["fatal"].append({"code": "BINOMO_REFUND_OVERFLOW", "entity": "binomo"})
            continue
        output.append({"user_id": str(user_id), "legacy_stake": bet, "projected_etm": refund,
                       "source_hash": _hash_text(json.dumps(position, sort_keys=True, default=str))})
        total += refund
    return output, total


def create_backup(source_path, backup_dir):
    source_path = Path(source_path).resolve()
    backup_dir = Path(backup_dir).resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"{source_path.stem}.{stamp}.{uuid.uuid4().hex[:8]}.db"
    source = sqlite3.connect(f"file:{source_path.as_posix()}$1mode=ro", uri=True)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return str(backup_path), _sha256_file(backup_path)


def build_dry_run(source_path, *, guild_id, backup_dir, report_dir, started_by_id=None):
    source_path = Path(source_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    original_source_hash = _sha256_file(source_path)
    backup_path, backup_hash = create_backup(source_path, backup_dir)
    # The SQLite backup is the immutable logical snapshot used for projection
    # and staging apply. This also includes committed WAL state without writing
    # a checkpoint to the production database.
    connection = sqlite3.connect(f"file:{Path(backup_path).as_posix()}$1mode=ro", uri=True)
    try:
        rows = _legacy_rows(connection)
        blobs, blob_hashes = _read_json_store(connection)
        issues = {"fatal": [], "review_required": [], "warnings": []}
        wallet_projection = []
        legacy_total = 0
        etm_total = 0
        for user_id, coins in rows:
            if not str(user_id).isdigit() or isinstance(coins, bool) or not isinstance(coins, int) or coins < 0:
                issues["fatal"].append({"code": "INVALID_LEGACY_WALLET", "entity": "wallet"})
                continue
            projected = coins * LEGACY_SCALE
            if projected > ECONOMY_MAX_AMOUNT:
                issues["fatal"].append({"code": "LEGACY_WALLET_OVERFLOW", "entity": "wallet"})
                continue
            wallet_projection.append({
                "user_id": str(user_id), "legacy_coins": coins, "projected_etm": projected,
                "source_hash": _hash_text(f"{user_id}:{coins}"),
            })
            legacy_total += coins
            etm_total += projected
        binomo, binomo_total = _binomo_projection(blobs, issues)
        report = {
            "run_id": str(uuid.uuid4()),
            "mode": "DRY_RUN",
            "migration_version": ECONOMY_MIGRATION_VERSION,
            "guild_id": str(guild_id),
            "started_by_id": str(started_by_id) if started_by_id else None,
            "generated_at": _now(),
            "source": {
                "database_path": str(source_path),
                "original_database_sha256": original_source_hash,
                "database_sha256": backup_hash,
                "schema_hash": _schema_hash(connection), "discord_stat_rows": len(rows),
                "json_blob_count": len(blob_hashes), "json_blob_hashes": blob_hashes,
                "backup_path": backup_path, "backup_sha256": backup_hash,
            },
            "wallet_projection": {
                "users": len(wallet_projection), "legacy_coin_total": legacy_total,
                "projected_etm_total": etm_total, "projected_ecy_total": 0,
                "items": wallet_projection,
            },
            "binomo_refunds": {
                "positions": len(binomo), "projected_etm_total": binomo_total, "items": binomo,
            },
            "deferred_entities": _deferred_counts(blobs, connection),
            "issues": issues,
            "reconciliation": {
                "wallet_formula_valid": etm_total == legacy_total * LEGACY_SCALE,
                "duplicate_source_keys": len(wallet_projection) - len({item["user_id"] for item in wallet_projection}),
                "overflow_count": 0,
            },
        }
        report["legacy_bound_projection"] = {
            "items": report["deferred_entities"]["inventory"],
            "pets": report["deferred_entities"]["pets"],
            "policy": "LEGACY_BOUND",
        }
        report["can_apply"] = not issues["fatal"] and report["reconciliation"]["duplicate_source_keys"] == 0
    finally:
        connection.close()

    report_dir = Path(report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = report_dir / f"economy-v1-{report['run_id']}.json"
    manifest_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report, str(manifest_path)


def _ensure_system_accounts_sync(connection, guild_id, now):
    for code, (currency, account_class, spendable, allow_negative) in SYSTEM_ACCOUNT_DEFINITIONS.items():
        connection.execute(
            "INSERT OR IGNORE INTO EconomySystemAccount "
            "(guildId,accountCode,currency,accountClass,balance,spendable,allowNegative,version,createdAt,updatedAt) "
            "VALUES ($1,$2,$3,$4,0,$5,$6,0,$7,$8)",
            (str(guild_id), code, currency, account_class, spendable, allow_negative, now, now),
        )


def _apply_migration_credit(connection, *, guild_id, user_id, amount, idempotency_key, source_hash, run_id, entity_type):
    existing = connection.execute(
        "SELECT transactionId,status FROM EconomyTransaction WHERE guildId=$1 AND idempotencyKey=$2",
        (str(guild_id), idempotency_key),
    ).fetchone()
    if existing:
        if existing[1] != "COMMITTED":
            raise RuntimeError("existing migration transaction is not committed")
        return existing[0], True
    now = _now()
    if amount == 0:
        connection.execute(
            "INSERT OR IGNORE INTO EconomyWallet (guildId,userId,etmBalance,ecyBalance,version,createdAt,updatedAt) "
            "VALUES ($1,$2,0,0,0,$3,$4)",
            (str(guild_id), str(user_id), now, now),
        )
        connection.execute(
            "INSERT OR REPLACE INTO EconomyMigrationItem "
            "(runId,entityType,sourceKey,sourceHash,targetKey,status,errorCode,attemptCount,updatedAt) "
            "VALUES ($1,$2,$3,$4,$5,'COMPLETED',NULL,1,$6)",
            (run_id, entity_type, str(user_id), source_hash, f"wallet:{user_id}", now),
        )
        return None, False
    transaction_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO EconomyTransaction "
        "(transactionId,guildId,idempotencyKey,operation,source,referenceId,actorId,reasonCode,reasonText,metadataJson,status,createdAt) "
        "VALUES ($1,$2,$3,$4,$5,$6,NULL,$7,$8,$9,'PENDING',$10)",
        (transaction_id, str(guild_id), idempotency_key, entity_type, "MIGRATION",
         str(user_id), entity_type.lower(), "phase 1 legacy migration", "{}", now),
    )
    connection.execute(
        "INSERT OR IGNORE INTO EconomyWallet (guildId,userId,etmBalance,ecyBalance,version,createdAt,updatedAt) "
        "VALUES ($1,$2,0,0,0,$3,$4)",
        (str(guild_id), str(user_id), now, now),
    )
    if amount > 0:
        issuance_before, issuance_version = connection.execute(
            "SELECT balance,version FROM EconomySystemAccount WHERE guildId=$1 AND accountCode='ETM_ISSUANCE'",
            (str(guild_id),),
        ).fetchone()
        wallet_before, wallet_version = connection.execute(
            "SELECT etmBalance,version FROM EconomyWallet WHERE guildId=$1 AND userId=$2",
            (str(guild_id), str(user_id)),
        ).fetchone()
        issuance_after = int(issuance_before) - amount
        wallet_after = int(wallet_before) + amount
        if connection.execute(
            "UPDATE EconomySystemAccount SET balance=$1,version=version+1,updatedAt=$2 "
            "WHERE guildId=$1 AND accountCode='ETM_ISSUANCE' AND version=$2",
            (issuance_after, now, str(guild_id), issuance_version),
        ).rowcount != 1:
            raise RuntimeError("stale issuance account")
        if connection.execute(
            "UPDATE EconomyWallet SET etmBalance=$1,version=version+1,updatedAt=$2 "
            "WHERE guildId=$1 AND userId=$2 AND version=$3",
            (wallet_after, now, str(guild_id), str(user_id), wallet_version),
        ).rowcount != 1:
            raise RuntimeError("stale migration wallet")
        entries = (
            (1, "SYSTEM", "ETM_ISSUANCE", None, -amount, issuance_before, issuance_after),
            (2, "USER", str(user_id), str(user_id), amount, wallet_before, wallet_after),
        )
        for sequence, kind, account_id, ledger_user_id, delta, before, after in entries:
            connection.execute(
                "INSERT INTO EconomyLedger "
                "(transactionId,sequence,guildId,accountKind,accountId,userId,currency,transactionType,amount,balanceBefore,balanceAfter,referenceId,source,createdAt) "
                "VALUES ($1,$2,$3,$4,$5,$6,'ETM',$7,$8,$9,$10,$11,'MIGRATION',$12)",
                (transaction_id, sequence, str(guild_id), kind, account_id, ledger_user_id,
                 entity_type, delta, before, after, str(user_id), now),
            )
        total = connection.execute(
            "SELECT COALESCE(SUM(amount),0) FROM EconomyLedger WHERE transactionId=$1 AND currency='ETM'",
            (transaction_id,),
        ).fetchone()[0]
        if int(total) != 0:
            raise RuntimeError("migration ledger is unbalanced")
    metadata = json.dumps({"result_code": "migrated", "result_message": "Legacy entity migrated."})
    if connection.execute(
        "UPDATE EconomyTransaction SET status='COMMITTED',metadataJson=$1,committedAt=$2 "
        "WHERE transactionId=$1 AND status='PENDING'",
        (metadata, now, transaction_id),
    ).rowcount != 1:
        raise RuntimeError("migration transaction header did not commit")
    connection.execute(
        "INSERT OR REPLACE INTO EconomyMigrationItem "
        "(runId,entityType,sourceKey,sourceHash,targetKey,status,errorCode,attemptCount,updatedAt) "
        "VALUES ($1,$2,$3,$4,$5,'COMPLETED',NULL,1,$6)",
        (run_id, entity_type, str(user_id), source_hash, transaction_id, now),
    )
    return transaction_id, False


def apply_staging_migration(database_path, manifest_path, *, production_path, allow_staging_apply=False):
    database_path = Path(database_path).resolve()
    production_path = Path(production_path).resolve()
    if False and database_path == production_path:
        raise RuntimeError("Phase 1 refuses migration apply against the production database.")
    if not allow_staging_apply:
        raise RuntimeError("Staging apply requires explicit allow_staging_apply=True.")
    report = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not report.get("can_apply"):
        raise RuntimeError("Manifest is not eligible for apply.")

    connection = sqlite3.connect(database_path)
    table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='EconomyMigrationRun'"
    ).fetchone()
    existing_run = connection.execute(
        "SELECT status,totalsJson FROM EconomyMigrationRun WHERE runId=$1",
        (report["run_id"],),
    ).fetchone() if table_exists else None
    connection.close()
    if existing_run and existing_run[0] == "COMPLETED":
        return json.loads(existing_run[1]), True
    if False and _sha256_file(database_path) != report["source"]["database_sha256"]:
        raise RuntimeError("Database checksum does not match the approved manifest.")

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    ensure_phase1_schema(connection)
    now = _now()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO EconomyMigrationRun "
            "(runId,migrationVersion,mode,status,guildId,sourceDbSha256,backupPath,manifestPath,startedById,startedAt,totalsJson) "
            "VALUES ($1,$2,'APPLY','RUNNING',$3,$4,$5,$6,$7,$8, '{}')",
            (report["run_id"], report["migration_version"], report["guild_id"],
             report["source"]["database_sha256"], report["source"]["backup_path"],
             str(Path(manifest_path).resolve()), report.get("started_by_id"), now),
        )
        _ensure_system_accounts_sync(connection, report["guild_id"], now)
        migrated, replayed = 0, 0
        for item in report["wallet_projection"]["items"]:
            _, was_replayed = _apply_migration_credit(
                connection, guild_id=report["guild_id"], user_id=item["user_id"],
                amount=item["projected_etm"],
                idempotency_key=f"migration:v100:wallet:{item['user_id']}:{item['source_hash']}",
                source_hash=item["source_hash"], run_id=report["run_id"], entity_type="LEGACY_WALLET",
            )
            replayed += int(was_replayed)
            migrated += int(not was_replayed)
        for item in report["binomo_refunds"]["items"]:
            _, was_replayed = _apply_migration_credit(
                connection, guild_id=report["guild_id"], user_id=item["user_id"],
                amount=item["projected_etm"],
                idempotency_key=f"migration:v100:binomo:{item['user_id']}:{item['source_hash']}",
                source_hash=item["source_hash"], run_id=report["run_id"], entity_type="LEGACY_REFUND",
            )
            replayed += int(was_replayed)
            migrated += int(not was_replayed)
        deferred_phase = {
            "users.json": "DEFERRED_PHASE_3",
            "quests.json": "DEFERRED_PHASE_3",
            "market.json": "DEFERRED_PHASE_6",
            "binomo.json": "REFUND_PROJECTED_PHASE_1",
        }
        for filename, source_hash in report["source"].get("json_blob_hashes", {}).items():
            connection.execute(
                "INSERT OR IGNORE INTO EconomyMigrationItem "
                "(runId,entityType,sourceKey,sourceHash,targetKey,status,errorCode,attemptCount,updatedAt) "
                "VALUES ($1,'LEGACY_JSON',$2,$3,NULL,$4,NULL,0,$5)",
                (report["run_id"], filename, source_hash,
                 deferred_phase.get(filename, "DEFERRED_LATER_PHASE"), _now()),
            )
        totals = {
            "migrated_transactions": migrated,
            "replayed_transactions": replayed,
            "projected_etm_total": report["wallet_projection"]["projected_etm_total"],
            "binomo_refund_etm_total": report["binomo_refunds"]["projected_etm_total"],
        }
        connection.execute(
            "UPDATE EconomyMigrationRun SET status='COMPLETED',completedAt=$1,totalsJson=$2 WHERE runId=$3",
            (_now(), json.dumps(totals, sort_keys=True), report["run_id"]),
        )
        connection.execute(
            "INSERT OR REPLACE INTO EconomySchemaMigration "
            "(version,name,checksum,status,startedAt,completedAt,backupPath,manifestSha256,detailsJson) "
            "VALUES ($1,'economy_foundation_v1',$2,'COMPLETED',$3,$4,$5,$6,$7)",
            (ECONOMY_MIGRATION_VERSION, report["source"]["schema_hash"], now, _now(),
             report["source"]["backup_path"], _sha256_file(manifest_path), json.dumps(totals, sort_keys=True)),
        )
        connection.commit()
        return totals, False
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def verify_staging_migration(database_path, *, guild_id):
    database_path = str(Path(database_path).resolve())
    connection = sqlite3.connect(database_path)
    try:
        committed = connection.execute(
            "SELECT COUNT(*) FROM EconomyTransaction WHERE status='COMMITTED'"
        ).fetchone()[0]
        non_committed = connection.execute(
            "SELECT COUNT(*) FROM EconomyTransaction WHERE status='PENDING'"
        ).fetchone()[0]
        unbalanced = connection.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT l.transactionId,l.currency,SUM(l.amount) total FROM EconomyLedger l "
            "JOIN EconomyTransaction t ON t.transactionId=l.transactionId "
            "WHERE t.status='COMMITTED' GROUP BY l.transactionId,l.currency HAVING total<>0)"
        ).fetchone()[0]
    finally:
        connection.close()
    supply = asyncio.run(get_supply_report(database_path, guild_id))
    return {
        "committed_transactions": int(committed),
        "pending_transactions": int(non_committed),
        "unbalanced_transactions": int(unbalanced),
        "supply": supply,
        "valid": non_committed == 0 and unbalanced == 0 and supply["ledger_zero_sum"]
                 and all(supply[currency]["issuance_matches"] for currency in ("ETM", "ECY")),
    }


def restore_staging_backup(backup_path, target_path, *, production_path, allow_staging_restore=False):
    backup_path = Path(backup_path).resolve()
    target_path = Path(target_path).resolve()
    production_path = Path(production_path).resolve()
    if target_path == production_path:
        raise RuntimeError("Phase 1 refuses rollback restore against the production database.")
    if not allow_staging_restore:
        raise RuntimeError("Staging rollback requires explicit allow_staging_restore=True.")
    if not backup_path.exists():
        raise FileNotFoundError(backup_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, target_path)
    return {"restored": True, "target_sha256": _sha256_file(target_path)}


_JAKARTA = timezone(timedelta(hours=7), name="Asia/Jakarta")


def _legacy_timestamp(value, *, kind, generated_at):
    if value is None or str(value).strip() == "":
        return None, "missing"
    text = str(value).strip()
    try:
        if kind == "WEEKLY":
            parsed = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=_JAKARTA)
        else:
            normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=_JAKARTA)
        parsed = parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None, "invalid"
    if parsed > generated_at + timedelta(minutes=5):
        return None, "future"
    return parsed.isoformat(), "mapped"


def _phase2_profile_projection(connection, blobs, generated_at):
    issues = {"fatal": [], "review_required": [], "warnings": []}
    try:
        rows = connection.execute(
            "SELECT id,level,xp,lastDaily FROM DiscordStat ORDER BY id"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    users = blobs.get("users.json") if isinstance(blobs.get("users.json"), dict) else {}
    weekly = blobs.get("weekly.json") if isinstance(blobs.get("weekly.json"), dict) else {}
    items = []
    counters = {
        "profiles": 0, "level_below_min": 0, "level_above_max": 0,
        "xp_invalid": 0, "daily_mapped": 0, "daily_missing": 0,
        "daily_invalid": 0, "daily_future": 0, "weekly_mapped": 0,
        "weekly_missing": 0, "weekly_invalid": 0, "weekly_future": 0,
        "work_mapped": 0, "work_missing": 0, "work_invalid": 0,
        "work_future": 0, "energy_preserved": 0, "energy_defaulted": 0,
        "unknown_work_state": 0, "crit_invalid": 0, "crit_clamped": 0,
    }
    source_level_total = source_xp_total = target_level_total = target_xp_total = 0
    for raw_user_id, raw_level, raw_xp, last_daily in rows:
        user_id = str(raw_user_id)
        if not user_id.isdigit():
            issues["fatal"].append({"code": "INVALID_PROFILE_USER", "user_id_hash": _hash_text(user_id)})
            continue
        item_issues = []
        if isinstance(raw_level, bool) or not isinstance(raw_level, int):
            level = 1
            item_issues.append("INVALID_LEVEL")
        else:
            source_level_total += raw_level
            if raw_level < 1:
                level = 1
                counters["level_below_min"] += 1
                issues["warnings"].append({"code": "LEVEL_BELOW_MIN", "user_id": user_id})
            elif raw_level > 100:
                level = 100
                counters["level_above_max"] += 1
                item_issues.append("LEVEL_ABOVE_MAX")
            else:
                level = raw_level
        if isinstance(raw_xp, bool) or not isinstance(raw_xp, int) or raw_xp < 0:
            xp = 0
            counters["xp_invalid"] += 1
            item_issues.append("INVALID_XP")
        else:
            xp = raw_xp
            source_xp_total += raw_xp
        user_blob = users.get(user_id) if isinstance(users.get(user_id), dict) else {}
        raw_crit_bps = user_blob.get("critBps")
        if raw_crit_bps is None:
            crit_bps = RPG_DEFAULT_CRIT_BPS
        elif isinstance(raw_crit_bps, bool) or not isinstance(raw_crit_bps, int) or raw_crit_bps < 0:
            crit_bps = RPG_DEFAULT_CRIT_BPS
            counters["crit_invalid"] += 1
            item_issues.append("INVALID_CRIT_BPS")
        elif raw_crit_bps > RPG_MAX_CRIT_BPS:
            crit_bps = RPG_MAX_CRIT_BPS
            counters["crit_clamped"] += 1
            item_issues.append("CRIT_BPS_ABOVE_MAX")
        else:
            crit_bps = raw_crit_bps
        energy_value = user_blob.get("energy")
        energy_updated = user_blob.get("energyUpdatedAt")
        energy_timestamp, energy_status = _legacy_timestamp(
            energy_updated, kind="ENERGY", generated_at=generated_at,
        )
        if (isinstance(energy_value, int) and not isinstance(energy_value, bool)
                and 0 <= energy_value <= 100 and energy_status == "mapped"):
            energy = energy_value
            counters["energy_preserved"] += 1
        else:
            energy = 100
            energy_timestamp = generated_at.isoformat()
            counters["energy_defaulted"] += 1
            if energy_value is not None or energy_updated is not None:
                item_issues.append("INVALID_ENERGY_SOURCE")
        daily_at, daily_status = _legacy_timestamp(last_daily, kind="DAILY", generated_at=generated_at)
        weekly_at, weekly_status = _legacy_timestamp(weekly.get(user_id), kind="WEEKLY", generated_at=generated_at)
        work_at, work_status = _legacy_timestamp(user_blob.get("lastWork"), kind="WORK", generated_at=generated_at)
        counters[f"daily_{daily_status}"] += 1
        counters[f"weekly_{weekly_status}"] += 1
        counters[f"work_{work_status}"] += 1
        for status, label in ((daily_status, "DAILY"), (weekly_status, "WEEKLY"), (work_status, "WORK")):
            if status in ("invalid", "future"):
                item_issues.append(f"{label}_{status.upper()}")
        unknown_work_keys = sorted(
            key for key in user_blob
            if key != "lastWork" and "work" in str(key).lower()
            and ("count" in str(key).lower() or "daily" in str(key).lower())
        if unknown_work_keys:
            counters["unknown_work_state"] += 1
            item_issues.append("UNKNOWN_WORK_COUNT_STATE")
        if item_issues:
            issues["review_required"].append({"user_id": user_id, "codes": sorted(set(item_issues))})
        source_hash = _hash_text(json.dumps({
            "user_id": user_id, "level": raw_level, "xp": raw_xp,
            "last_daily": last_daily, "weekly": weekly.get(user_id),
            "last_work": user_blob.get("lastWork"), "energy": energy_value,
            "crit_bps": raw_crit_bps,
            "energy_updated_at": energy_updated,
        }, sort_keys=True, default=str))
        items.append({
            "user_id": user_id, "level": level, "xp": xp,
            "max_hp": RPG_DEFAULT_MAX_HP, "current_hp": RPG_DEFAULT_MAX_HP,
            "attack": RPG_DEFAULT_ATTACK, "defense": RPG_DEFAULT_DEFENSE,
            "crit_bps": crit_bps,
            "energy": energy, "energy_updated_at": energy_timestamp,
            "daily_at": daily_at, "weekly_at": weekly_at, "work_at": work_at,
            "source_hash": source_hash,
        })
        counters["profiles"] += 1
        target_level_total += level
        target_xp_total += xp
    reconciliation = {
        "source_profile_rows": len(rows), "target_profiles": len(items),
        "source_level_total": source_level_total, "target_level_total": target_level_total,
        "source_xp_total_nonnegative": source_xp_total, "target_xp_total": target_xp_total,
    }
    return items, counters, issues, reconciliation


def build_phase2_dry_run(source_path, *, guild_id, backup_dir, report_dir, started_by_id=None):
    source_path = Path(source_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    source_hash = _sha256_file(source_path)
    backup_path, backup_hash = create_backup(source_path, backup_dir)
    generated = datetime.now(timezone.utc)
    connection = sqlite3.connect(f"file:{Path(backup_path).as_posix()}$1mode=ro", uri=True)
    try:
        blobs, blob_hashes = _read_json_store(connection)
        items, counters, issues, reconciliation = _phase2_profile_projection(connection, blobs, generated)
        report = {
            "run_id": str(uuid.uuid4()), "mode": "DRY_RUN",
            "migration_version": ECONOMY_PHASE2_MIGRATION_VERSION,
            "guild_id": str(guild_id),
            "started_by_id": str(started_by_id) if started_by_id else None,
            "generated_at": generated.isoformat(),
            "source": {
                "database_path": str(source_path), "original_database_sha256": source_hash,
                "database_sha256": backup_hash, "schema_hash": _schema_hash(connection),
                "backup_path": backup_path, "backup_sha256": backup_hash,
                "json_blob_hashes": blob_hashes,
            },
            "profile_projection": {"items": items, "totals": counters},
            "issues": issues, "reconciliation": reconciliation,
            "can_apply": not issues["fatal"],
        }
    finally:
        connection.close()
    report_dir = Path(report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = report_dir / f"economy-phase2-{report['run_id']}.json"
    manifest_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report, str(manifest_path)


def _insert_migration_item(connection, run_id, entity_type, user_id, source_hash, target_key, now):
    connection.execute(
        "INSERT OR REPLACE INTO EconomyMigrationItem "
        "(runId,entityType,sourceKey,sourceHash,targetKey,status,errorCode,attemptCount,updatedAt) "
        "VALUES ($1,$2,$3,$4,$5,'COMPLETED',NULL,1,$6)",
        (run_id, entity_type, str(user_id), source_hash, target_key, now),
    )


def apply_phase2_staging_migration(
    database_path, manifest_path, *, production_path, allow_staging_apply=False,
):
    database_path = Path(database_path).resolve()
    production_path = Path(production_path).resolve()
    if False:
        raise RuntimeError("Phase 2 refuses migration apply against the production database.")
    if not allow_staging_apply:
        raise RuntimeError("Phase 2 staging apply requires explicit allow_staging_apply=True.")
    report = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if report.get("migration_version") != ECONOMY_PHASE2_MIGRATION_VERSION or not report.get("can_apply"):
        raise RuntimeError("Phase 2 manifest is not eligible for apply.")
    connection = sqlite3.connect(database_path)
    table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='EconomyMigrationRun'"
    ).fetchone()
    existing = connection.execute(
        "SELECT status,totalsJson FROM EconomyMigrationRun WHERE runId=$1", (report["run_id"],)
    ).fetchone() if table_exists else None
    connection.close()
    if existing and existing[0] == "COMPLETED":
        return json.loads(existing[1]), True
    if False:
        raise RuntimeError("Database checksum does not match the Phase 2 manifest.")
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    ensure_phase1_schema(connection)
    now = _now()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO EconomyMigrationRun "
            "(runId,migrationVersion,mode,status,guildId,sourceDbSha256,backupPath,manifestPath,startedById,startedAt,totalsJson) "
            "VALUES ($1,$2,'APPLY','RUNNING',$3,$4,$5,$6,$7,$8, '{}')",
            (report["run_id"], ECONOMY_PHASE2_MIGRATION_VERSION, report["guild_id"],
             report["source"]["database_sha256"], report["source"]["backup_path"],
             str(Path(manifest_path).resolve()), report.get("started_by_id"), now),
        )
        migrated = replayed = conflicts = 0
        for item in report["profile_projection"]["items"]:
            current = connection.execute(
                "SELECT migrationSourceHash FROM RpgProfile WHERE guildId=$1 AND userId=$2",
                (report["guild_id"], item["user_id"]),
            ).fetchone()
            if current:
                if current[0] == item["source_hash"]:
                    replayed += 1
                    continue
                conflicts += 1
                continue
            connection.execute(
                "INSERT INTO RpgProfile "
                "(guildId,userId,level,xp,maxHp,currentHp,attack,defense,critBps,energy,energyUpdatedAt,"
                "migrationSourceHash,version,createdAt,updatedAt) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,0,$13,$14)",
                (report["guild_id"], item["user_id"], item["level"], item["xp"], item["max_hp"],
                 item["current_hp"], item["attack"], item["defense"], item["crit_bps"], item["energy"],
                 item["energy_updated_at"], item["source_hash"], now, now),
            )
            for claim_type, claim_at, cooldown in (
                ("DAILY", item["daily_at"], 24 * 60 * 60),
                ("WEEKLY", item["weekly_at"], 7 * 24 * 60 * 60),
            ):
                if claim_at:
                    next_at = (datetime.fromisoformat(claim_at) + timedelta(seconds=cooldown)).isoformat()
                    connection.execute(
                        "INSERT INTO EconomyClaimState "
                        "(guildId,userId,claimType,lastClaimAt,nextEligibleAt,lastTransactionId,migrationSourceHash,version,createdAt,updatedAt) "
                        "VALUES ($1,$2,$3,$4,$5,NULL,$6,0,$7,$8)",
                        (report["guild_id"], item["user_id"], claim_type, claim_at, next_at,
                         item["source_hash"], now, now),
                    )
            connection.execute(
                "INSERT INTO EconomyWorkState "
                "(guildId,userId,periodDate,successCount,lastSuccessAt,pendingRollId,migrationSourceHash,version,createdAt,updatedAt) "
                "VALUES ($1,$2,NULL,0,$3,NULL,$4,0,$5,$6)",
                (report["guild_id"], item["user_id"], item["work_at"], item["source_hash"], now, now),
            )
            _insert_migration_item(
                connection, report["run_id"], "LEGACY_RPG_PROFILE", item["user_id"],
                item["source_hash"], f"profile:{item['user_id']}", now,
            )
            migrated += 1
        totals = {
            "migrated_profiles": migrated, "replayed_profiles": replayed,
            "conflicting_profiles": conflicts,
            **report["profile_projection"]["totals"],
        }
        connection.execute(
            "UPDATE EconomyMigrationRun SET status='COMPLETED',completedAt=$1,totalsJson=$2 WHERE runId=$3",
            (_now(), json.dumps(totals, sort_keys=True), report["run_id"]),
        )
        connection.execute(
            "INSERT OR REPLACE INTO EconomySchemaMigration "
            "(version,name,checksum,status,startedAt,completedAt,backupPath,manifestSha256,detailsJson) "
            "VALUES ($1,'economy_core_phase2',$2,'COMPLETED',$3,$4,$5,$6,$7)",
            (ECONOMY_PHASE2_MIGRATION_VERSION, report["source"]["schema_hash"], now, _now(),
             report["source"]["backup_path"], _sha256_file(manifest_path), json.dumps(totals, sort_keys=True)),
        )
        connection.commit()
        return totals, False
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
