import os
import sqlite3
import tempfile
import unittest

import aiosqlite

from economy.database import initialize_database
from economy.constants import RPG_PHASE3_CATALOG_VERSION
from economy.inventory import adjust_stack, inventory_quantity, stack_schema_is_phase4
from economy.phase3_migrations import apply_phase3_staging
from economy.phase4_migrations import (
    apply_phase4_staging, assert_not_production, file_sha256,
    restore_phase4_staging, verify_phase4_staging,
)
from economy.phase4_schema import (
    PHASE4_MIGRATION_CHECKSUM, PHASE4_PRE_HARDENING_CHECKSUM,
    migrate_phase4_schema, phase4_schema_capability,
)
from economy.staging import create_logical_sqlite_backup, logical_sqlite_manifest


class MarketplaceMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def _new_phase3(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        path = handle.name
        handle.close()
        await initialize_database(path)
        await apply_phase3_staging(path, production_db=path + ".prod")
        return path

    async def test_phase3_stack_works_before_and_after_migration(self):
        path = await self._new_phase3()
        try:
            async with aiosqlite.connect(path) as db:
                await adjust_stack(db, "1", "2", "mat_iron_shard", 4, "2026-01-01T00:00:00+00:00")
                self.assertFalse(await stack_schema_is_phase4(db))
                self.assertEqual(await inventory_quantity(db, "1", "2", "mat_iron_shard"), 4)
                await db.commit()
            await apply_phase4_staging(path, production_db=path + ".prod")
            async with aiosqlite.connect(path) as db:
                self.assertTrue(await stack_schema_is_phase4(db))
                self.assertEqual(await inventory_quantity(
                    db, "1", "2", "mat_iron_shard", catalog_version=RPG_PHASE3_CATALOG_VERSION,
                ), 4)
                await adjust_stack(
                    db, "1", "2", "mat_iron_shard", 2, "2026-01-02T00:00:00+00:00",
                    catalog_version=RPG_PHASE3_CATALOG_VERSION,
                )
                await db.commit()
            connection = sqlite3.connect(path)
            info = connection.execute("PRAGMA table_info(RpgInventoryStack)").fetchall()
            self.assertIn("userId", [row[1] for row in info])
            self.assertNotIn("ownerId", [row[1] for row in info])
            self.assertEqual(connection.execute("SELECT SUM(quantity) FROM RpgInventoryStack").fetchone()[0], 6)
            connection.close()
        finally:
            os.unlink(path)

    async def test_disabled_startup_does_not_create_phase4_schema(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        path = handle.name
        handle.close()
        try:
            await initialize_database(path)
            connection = sqlite3.connect(path)
            try:
                tables = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Marketplace%'"
                    )
                }
                marker = connection.execute(
                    "SELECT COUNT(*) FROM EconomySchemaMigration WHERE version=400"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(tables, set())
            self.assertEqual(marker, 0)
        finally:
            os.unlink(path)

    async def test_second_apply_is_idempotent_and_checksum_guarded(self):
        path = await self._new_phase3()
        try:
            first = await apply_phase4_staging(path, production_db=path + ".prod")
            second = await apply_phase4_staging(path, production_db=path + ".prod")
            self.assertTrue(first["migration"]["applied"])
            self.assertTrue(second["migration"]["idempotent"])
            verification = await verify_phase4_staging(path)
            self.assertTrue(verification["schema_capable"])
            self.assertEqual(verification["marker"][0], PHASE4_MIGRATION_CHECKSUM)
            connection = sqlite3.connect(path)
            connection.execute("UPDATE EconomySchemaMigration SET checksum='mismatch' WHERE version=400")
            connection.commit()
            connection.close()
            with self.assertRaises(ValueError):
                await migrate_phase4_schema(path)
        finally:
            os.unlink(path)

    async def test_every_injected_stage_rolls_back(self):
        stages = (
            "after_marker", "after_stack_create", "after_stack_copy", "after_stack_swap",
            "after_listing", "after_escrow", "after_triggers", "after_marker_complete", "before_commit",
        )
        for stage in stages:
            with self.subTest(stage=stage):
                path = await self._new_phase3()
                try:
                    with self.assertRaises(RuntimeError):
                        await migrate_phase4_schema(path, failure_stage=stage)
                    connection = sqlite3.connect(path)
                    marker = connection.execute("SELECT COUNT(*) FROM EconomySchemaMigration WHERE version=400").fetchone()[0]
                    columns = [row[1] for row in connection.execute("PRAGMA table_info(RpgInventoryStack)")]
                    self.assertEqual(marker, 0)
                    self.assertNotIn("catalogVersion", columns)
                    self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
                    connection.close()
                finally:
                    os.unlink(path)

    async def test_marker_or_required_trigger_mismatch_fails_capability(self):
        path = await self._new_phase3()
        try:
            await apply_phase4_staging(path, production_db=path + ".prod")
            connection = sqlite3.connect(path)
            connection.execute("DROP TRIGGER trg_market_sale_no_delete")
            connection.commit()
            connection.close()
            async with aiosqlite.connect(path) as db:
                self.assertFalse(await phase4_schema_capability(db))
        finally:
            os.unlink(path)

    def test_production_path_refusal(self):
        with self.assertRaises(ValueError):
            assert_not_production("w2ebot.db", "./w2ebot.db")

    async def test_apply_refuses_production_or_target_backup_path(self):
        path = await self._new_phase3()
        try:
            with self.assertRaises(ValueError):
                await apply_phase4_staging(
                    path, production_db=path + ".prod", backup_path=path,
                )
            with self.assertRaises(ValueError):
                await apply_phase4_staging(
                    path, production_db=path + ".prod", backup_path=path + ".prod",
                )
        finally:
            os.unlink(path)

    async def test_verified_staging_restore_and_interrupted_restore_safety(self):
        path = await self._new_phase3()
        backup = path + ".restore-source"
        safety = path + ".safety"
        try:
            await apply_phase4_staging(path, production_db=path + ".prod")
            create_logical_sqlite_backup(path, backup)
            connection = sqlite3.connect(path)
            connection.execute(
                "INSERT INTO EconomyWallet (guildId,userId,etmBalance,ecyBalance,version,createdAt,updatedAt) "
                "VALUES ('1','999',1,0,0,'2026-01-01','2026-01-01')"
            )
            connection.commit()
            connection.close()
            changed_hash = file_sha256(path)
            changed_manifest = logical_sqlite_manifest(path)
            with self.assertRaises(RuntimeError):
                await restore_phase4_staging(
                    path, backup_path=backup, production_db=path + ".prod",
                    confirm_restore_staging=True, safety_backup_path=safety,
                    failure_stage="before_replace",
                )
            self.assertEqual(file_sha256(path), changed_hash)
            with self.assertRaises(RuntimeError):
                await restore_phase4_staging(
                    path, backup_path=backup, production_db=path + ".prod",
                    confirm_restore_staging=True, safety_backup_path=safety + ".after",
                    failure_stage="after_replace",
                )
            rolled_back = logical_sqlite_manifest(path)
            for key in ("object_count", "object_checksum", "row_counts", "table_checksums"):
                self.assertEqual(rolled_back[key], changed_manifest[key])
            self.assertEqual(rolled_back["integrity_check"], "ok")
            self.assertEqual(rolled_back["foreign_key_errors"], 0)
            result = await restore_phase4_staging(
                path, backup_path=backup, production_db=path + ".prod",
                confirm_restore_staging=True, safety_backup_path=safety + ".second",
            )
            self.assertEqual(result["mode"], "RESTORE")
            connection = sqlite3.connect(path)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM EconomyWallet WHERE userId='999'"
            ).fetchone()[0], 0)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            connection.close()
        finally:
            for candidate in (path, backup, safety, safety + ".after", safety + ".second"):
                if os.path.exists(candidate):
                    os.unlink(candidate)

    async def test_restore_rejects_corrupt_checksum_and_production_paths(self):
        path = await self._new_phase3()
        backup = path + ".backup"
        try:
            await apply_phase4_staging(path, production_db=path + ".prod")
            create_logical_sqlite_backup(path, backup)
            connection = sqlite3.connect(backup)
            connection.execute("UPDATE EconomySchemaMigration SET checksum='wrong' WHERE version=400")
            connection.commit()
            connection.close()
            with self.assertRaises(ValueError):
                await restore_phase4_staging(
                    path, backup_path=backup, production_db=path + ".prod",
                    confirm_restore_staging=True,
                )
            with self.assertRaises(ValueError):
                await restore_phase4_staging(
                    path, backup_path=backup, production_db=path,
                    confirm_restore_staging=True,
                )
            with open(backup, "wb") as handle:
                handle.write(b"not sqlite")
            with self.assertRaises((ValueError, sqlite3.DatabaseError)):
                await restore_phase4_staging(
                    path, backup_path=backup, production_db=path + ".prod",
                    confirm_restore_staging=True,
                )
        finally:
            for candidate in (path, backup):
                if os.path.exists(candidate):
                    os.unlink(candidate)

    async def test_hardening_migration_fails_closed_on_duplicate_unresolved_reports(self):
        path = await self._new_phase3()
        try:
            await apply_phase4_staging(path, production_db=path + ".prod")
            connection = sqlite3.connect(path)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("DROP INDEX idx_market_report_unresolved")
            # Buat pasangan listing/escrow minimal dalam satu transaksi deferred.
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO MarketplaceListing "
                "(listingId,guildId,sellerId,assetType,equipmentInstanceId,stackItemId,catalogVersion,"
                "stackBindingStatus,originalQuantity,remainingQuantity,unitPriceEtm,totalListingValue,"
                "assetSnapshotJson,status,escrowId,idempotencyKey,createdAt) "
                "VALUES ('dup-listing','1','10','STACK',NULL,'mat_iron_shard',?,'UNBOUND',1,1,10000,10000,'{}','ACTIVE','dup-escrow','dup-listing','2026-01-01')",
                (RPG_PHASE3_CATALOG_VERSION,),
            )
            connection.execute(
                "INSERT INTO MarketplaceEscrow "
                "(escrowId,listingId,guildId,authoritativeOwnerId,assetType,equipmentInstanceId,stackItemId,"
                "catalogVersion,stackBindingStatus,originalQuantity,remainingQuantity,assetSnapshotJson,status,createdAt,updatedAt) "
                "VALUES ('dup-escrow','dup-listing','1','10','STACK',NULL,'mat_iron_shard',?,'UNBOUND',1,1,'{}','HELD','2026-01-01','2026-01-01')",
                (RPG_PHASE3_CATALOG_VERSION,),
            )
            for report_id in ("dup-report-a", "dup-report-b"):
                connection.execute(
                    "INSERT INTO MarketplaceReport "
                    "(reportId,guildId,listingId,reporterId,reasonCategory,sanitizedDetails,status,createdAt) "
                    "VALUES (?,'1','dup-listing','20','PRICE','','OPEN','2026-01-01')",
                    (report_id,),
                )
            connection.execute(
                "UPDATE EconomySchemaMigration SET checksum=? WHERE version=400",
                (PHASE4_PRE_HARDENING_CHECKSUM,),
            )
            connection.commit()
            connection.close()
            with self.assertRaises(ValueError):
                await migrate_phase4_schema(path)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
