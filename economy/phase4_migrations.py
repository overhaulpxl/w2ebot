"""Facade migrasi, verifikasi, dan rekonsiliasi Phase 4 staging-only."""

import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
from datetime import datetime, timezone


from .catalog import catalog_hash
from .database import configure_connection
from .phase4_schema import (
    ECONOMY_PHASE4_MIGRATION_VERSION,
    PHASE4_MIGRATION_CHECKSUM,
    migrate_phase4_schema,
    phase4_schema_capability,
)
from .staging import (
    create_logical_sqlite_backup, logical_sqlite_manifest, restore_logical_sqlite_backup,
)


def _resolved(path):
    return Path(path).expanduser().resolve()


def assert_not_production(target_db, production_db):
    if _resolved(target_db) == _resolved(production_db):
        raise ValueError("Migrasi Phase 4 menolak database production.")


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stack_summary(connection):
    columns = [row[1] for row in connection.execute("PRAGMA table_info(RpgInventoryStack)")]
    phase4 = {"catalogVersion", "bindingStatus", "status"}.issubset(columns)
    if phase4:
        rows = connection.execute(
            "SELECT guildId,userId,itemId,catalogVersion,bindingStatus,status,quantity "
            "FROM RpgInventoryStack ORDER BY guildId,userId,itemId,catalogVersion,bindingStatus"
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT guildId,userId,itemId,quantity FROM RpgInventoryStack ORDER BY guildId,userId,itemId"
        ).fetchall()
    checksum = hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()
    return {
        "schema": "PHASE4" if phase4 else "PHASE3", "owner_column": "userId",
        "rows": len(rows), "quantity": sum(int(row[-1]) for row in rows), "checksum": checksum,
    }


async def verify_phase4_staging(db_path):
    manifest = logical_sqlite_manifest(db_path)
    async with _pool.acquire() as db:
        
        capable = await phase4_schema_capability(db)
        marker = await db.fetchrow(
            "SELECT checksum,status FROM EconomySchemaMigration WHERE version=$1",
            (ECONOMY_PHASE4_MIGRATION_VERSION,),
        )
        catalog = await db.fetchrow("SELECT catalogHash FROM RpgCatalogManifest ORDER BY catalogVersion DESC LIMIT 1")
    connection = sqlite3.connect(db_path)
    try:
        stack = _stack_summary(connection)
    finally:
        connection.close()
    return {
        "mode": "VERIFY", "migration_version": ECONOMY_PHASE4_MIGRATION_VERSION,
        "checksum": PHASE4_MIGRATION_CHECKSUM, "marker": tuple(marker) if marker else None,
        "schema_capable": capable, "catalog_checksum": catalog[0] if catalog else None,
        "catalog_checksum_valid": bool(catalog and catalog[0] == catalog_hash()),
        "stack": stack, "database_size": Path(db_path).stat().st_size,
        "database_sha256": file_sha256(db_path), "manifest": manifest,
    }


async def phase4_dry_run(db_path):
    verification = await verify_phase4_staging(db_path)
    return {
        "mode": "DRY_RUN", "migration_version": ECONOMY_PHASE4_MIGRATION_VERSION,
        "checksum": PHASE4_MIGRATION_CHECKSUM, "stack": verification["stack"],
        "catalog_checksum_valid": verification["catalog_checksum_valid"],
        "integrity_check": verification["manifest"]["integrity_check"],
        "foreign_key_errors": verification["manifest"]["foreign_key_errors"],
        "already_applied": verification["schema_capable"],
        "can_apply": verification["catalog_checksum_valid"]
                     and verification["manifest"]["integrity_check"] == "ok"
                     and verification["manifest"]["foreign_key_errors"] == 0,
    }


async def reconcile_phase4_staging(db_path):
    async with _pool.acquire() as db:
        
        if not await phase4_schema_capability(db):
            raise ValueError("Schema Phase 4 belum siap untuk rekonsiliasi.")
        checks = {}
        queries = {
            "listing_escrow_mismatch": "SELECT COUNT(*) FROM MarketplaceListing l LEFT JOIN MarketplaceEscrow e ON e.escrowId=l.escrowId WHERE e.escrowId IS NULL OR e.listingId!=l.listingId OR e.remainingQuantity!=l.remainingQuantity",
            "sale_transaction_mismatch": "SELECT COUNT(*) FROM MarketplaceSale s LEFT JOIN EconomyTransaction t ON t.transactionId=s.transactionId WHERE t.transactionId IS NULL OR t.guildId!=s.guildId",
            "equipment_escrow_mismatch": "SELECT COUNT(*) FROM MarketplaceEscrow e LEFT JOIN RpgEquipmentInstance i ON i.equipmentInstanceId=e.equipmentInstanceId WHERE e.assetType='EQUIPMENT' AND e.status IN ('HELD','PARTIAL','REVIEW_REQUIRED') AND (i.equipmentInstanceId IS NULL OR i.status!='ESCROWED')",
            "negative_stack_rows": "SELECT COUNT(*) FROM RpgInventoryStack WHERE quantity<0",
            "unbalanced_committed_sales": "SELECT COUNT(*) FROM MarketplaceSale s WHERE s.status='COMMITTED' AND EXISTS (SELECT 1 FROM EconomyLedger l WHERE l.transactionId=s.transactionId GROUP BY l.currency HAVING SUM(l.amount)!=0)",
            "pending_pairs": "SELECT COUNT(*) FROM MarketplaceSale s JOIN EconomyTransaction t ON t.transactionId=s.transactionId WHERE s.status='PENDING' AND t.status='PENDING'",
            "review_required": "SELECT (SELECT COUNT(*) FROM MarketplaceSale WHERE status='REVIEW_REQUIRED')+(SELECT COUNT(*) FROM MarketplaceListing WHERE status='REVIEW_REQUIRED')+(SELECT COUNT(*) FROM MarketplaceReturn WHERE status='REVIEW_REQUIRED')",
        }
        for key, query in queries.items():
            async with db.execute(query) as cursor:
                checks[key] = int((await cursor.fetchone())[0])
        async with db.execute("PRAGMA integrity_check") as cursor:
            integrity = (await cursor.fetchone())[0]
        async with db.execute("PRAGMA foreign_key_check") as cursor:
            foreign_keys = len(await cursor.fetchall())
    blocking = sum(checks[key] for key in (
        "listing_escrow_mismatch", "sale_transaction_mismatch", "equipment_escrow_mismatch",
        "negative_stack_rows", "unbalanced_committed_sales",
    ))
    return {"mode": "RECONCILE", "checks": checks, "blocking": blocking,
            "integrity_check": integrity, "foreign_key_errors": foreign_keys,
            "reconciled": blocking == 0 and integrity == "ok" and foreign_keys == 0}


async def apply_phase4_staging(target_db, *, production_db, backup_path=None, failure_stage=None):
    assert_not_production(target_db, production_db)
    if backup_path is not None:
        assert_not_production(backup_path, production_db)
        if _resolved(backup_path) == _resolved(target_db):
            raise ValueError("Backup Phase 4 harus berbeda dari database target.")
    dry_run = await phase4_dry_run(target_db)
    if not dry_run["can_apply"]:
        raise ValueError("Dry-run Phase 4 tidak mengizinkan apply.")
    backup = create_logical_sqlite_backup(target_db, backup_path) if backup_path else None
    result = await migrate_phase4_schema(target_db, failure_stage=failure_stage)
    verification = await verify_phase4_staging(target_db)
    reconciliation = await reconcile_phase4_staging(target_db)
    if not verification["schema_capable"] or not reconciliation["reconciled"]:
        raise ValueError("Verifikasi migration Phase 4 gagal.")
    return {
        "migration_version": ECONOMY_PHASE4_MIGRATION_VERSION,
        "checksum": PHASE4_MIGRATION_CHECKSUM, "target": str(_resolved(target_db)),
        "production_cutover": False, "migration": result, "backup": backup,
        "verification": verification, "reconciliation": reconciliation,
    }


async def restore_phase4_staging(target_db, *, backup_path, production_db,
                                 confirm_restore_staging=False, safety_backup_path=None,
                                 failure_stage=None):
    if not confirm_restore_staging:
        raise ValueError("Restore staging memerlukan konfirmasi eksplisit.")
    target = _resolved(target_db)
    backup = _resolved(backup_path)
    production = _resolved(production_db)
    assert_not_production(target, production)
    assert_not_production(backup, production)
    if target == backup:
        raise ValueError("Backup restore harus berbeda dari target staging.")
    if not target.exists() or not backup.exists():
        raise ValueError("Target staging atau backup restore tidak ditemukan.")

    backup_manifest = logical_sqlite_manifest(backup)
    backup_verification = await verify_phase4_staging(backup)
    if (
        backup_manifest["integrity_check"] != "ok"
        or backup_manifest["foreign_key_errors"]
        or not backup_verification["schema_capable"]
        or not backup_verification["catalog_checksum_valid"]
        or backup_verification["marker"] != (PHASE4_MIGRATION_CHECKSUM, "COMPLETED")
    ):
        raise ValueError("Backup Phase 4 tidak lolos validasi restore.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safety = _resolved(safety_backup_path) if safety_backup_path else target.with_name(
        f"{target.stem}.pre-restore-{timestamp}{target.suffix}"
    )
    assert_not_production(safety, production)
    if safety in (target, backup):
        raise ValueError("Path safety backup restore tidak valid.")
    safety_result = create_logical_sqlite_backup(target, safety)
    if failure_stage == "after_safety_backup":
        raise RuntimeError("Injected Phase 4 restore failure")

    handle = tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}.restore-", suffix=target.suffix, dir=target.parent, delete=False,
    )
    temporary = Path(handle.name)
    handle.close()
    replaced = False
    try:
        restore_logical_sqlite_backup(backup, temporary)
        restored_verification = await verify_phase4_staging(temporary)
        restored_manifest = logical_sqlite_manifest(temporary)
        comparable = ("object_count", "object_checksum", "row_counts", "table_checksums")
        if any(restored_manifest[key] != backup_manifest[key] for key in comparable):
            raise ValueError("Manifest hasil restore berbeda dari backup.")
        if not restored_verification["schema_capable"] or not restored_verification["catalog_checksum_valid"]:
            raise ValueError("Database sementara hasil restore tidak siap Phase 4.")
        if failure_stage == "before_replace":
            raise RuntimeError("Injected Phase 4 restore failure")
        os.replace(temporary, target)
        replaced = True
        if failure_stage == "after_replace":
            raise RuntimeError("Injected Phase 4 restore failure")
        final_verification = await verify_phase4_staging(target)
        final_manifest = logical_sqlite_manifest(target)
        if any(final_manifest[key] != backup_manifest[key] for key in comparable):
            raise ValueError("Validasi final restore Phase 4 gagal.")
        return {
            "mode": "RESTORE", "target": str(target), "backup": str(backup),
            "target_sha256": file_sha256(target), "backup_sha256": file_sha256(backup),
            "safety_backup": safety_result, "verification": final_verification,
            "production_cutover": False,
        }
    except Exception:
        if replaced:
            rollback_handle = tempfile.NamedTemporaryFile(
                prefix=f".{target.stem}.rollback-", suffix=target.suffix,
                dir=target.parent, delete=False,
            )
            rollback = Path(rollback_handle.name)
            rollback_handle.close()
            try:
                restore_logical_sqlite_backup(safety, rollback)
                rollback_manifest = logical_sqlite_manifest(rollback)
                if rollback_manifest["integrity_check"] != "ok" or rollback_manifest["foreign_key_errors"]:
                    raise RuntimeError("Safety backup Phase 4 gagal diverifikasi saat rollback.")
                os.replace(rollback, target)
            finally:
                if rollback.exists():
                    rollback.unlink()
        raise
    finally:
        if temporary.exists():
            temporary.unlink()
