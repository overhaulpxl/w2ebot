import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from economy.phase7_migrations import (
    apply_phase7_staging, assert_not_production, phase7_dry_run,
    reconcile_phase7_staging, restore_phase7_staging, verify_phase7_staging,
)
from economy.phase7_schema import PHASE7_MIGRATION_NAME, PHASE7_SCHEMA_CHECKSUM
from tests.mining_test_utils import TempMiningDatabase


class MiningMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_apply_replay_marker_integrity_and_foreign_keys(self):
        database = await TempMiningDatabase().initialize()
        try:
            replay = apply_phase7_staging(database.path, production_db=database.production, guild_id="1")
            self.assertTrue(replay["replayed"])
            verification = verify_phase7_staging(database.path)
            self.assertEqual(verification["marker"], [PHASE7_MIGRATION_NAME, PHASE7_SCHEMA_CHECKSUM, "COMPLETED"])
            self.assertEqual(verification["integrityCheck"], "ok")
            self.assertEqual(verification["foreignKeyErrors"], 0)
            self.assertTrue(reconcile_phase7_staging(database.path)["reconciled"])
        finally:
            database.close()

    async def test_legacy_tier_four_and_unknown_tier_enter_review(self):
        database = TempMiningDatabase()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "users.json"
            raw = json.dumps({"2": {"rigs": {"ETHR": {"1": 1, "4": 1, "9": 1}}}}, separators=(",", ":")).encode()
            source.write_bytes(raw)
            try:
                await database.initialize(migrate_phase7=False)
                apply_phase7_staging(
                    database.path, production_db=database.production, guild_id="1", users_json_path=source,
                )
                self.assertEqual(source.read_bytes(), raw)
                connection = sqlite3.connect(database.path)
                migrated = connection.execute("SELECT COUNT(*) FROM MiningRigInstance").fetchone()[0]
                reviews = connection.execute(
                    "SELECT sourceTierText,errorCode,rawSourceJson FROM MiningLegacyRigMigration WHERE status='REVIEW_REQUIRED' ORDER BY sourceTierText"
                ).fetchall()
                connection.close()
                self.assertEqual(migrated, 1)
                self.assertEqual([row[:2] for row in reviews], [("4", "unsupported_legacy_tier"), ("9", "unsupported_legacy_tier")])
                self.assertTrue(all(row[2] == "1" for row in reviews))
            finally:
                database.close()

    async def test_failure_injection_rolls_back_and_production_is_refused(self):
        for stage in ("after_marker", "after_tables", "after_triggers", "before_commit"):
            database = await TempMiningDatabase().initialize(migrate_phase7=False)
            try:
                with self.assertRaises(RuntimeError):
                    apply_phase7_staging(
                        database.path, production_db=database.production, guild_id="1", failure_stage=stage,
                    )
                connection = sqlite3.connect(database.path)
                marker = connection.execute("SELECT 1 FROM EconomySchemaMigration WHERE version=700").fetchone()
                connection.close()
                self.assertIsNone(marker)
            finally:
                database.close()
        with self.assertRaises(ValueError):
            assert_not_production("same.db", "same.db")

    async def test_backup_restore_and_dry_run(self):
        database = await TempMiningDatabase().initialize(migrate_phase7=False)
        backup = str(Path(database.temp.name) / "phase7-backup.db")
        try:
            dry = phase7_dry_run(database.path)
            self.assertTrue(dry["canApply"])
            result = apply_phase7_staging(
                database.path, production_db=database.production, guild_id="1", backup_path=backup,
            )
            self.assertTrue(result["applied"])
            restored = restore_phase7_staging(
                database.path, backup_path=backup, production_db=database.production, confirm=True,
            )
            self.assertTrue(restored["restored"])
            connection = sqlite3.connect(database.path)
            marker = connection.execute("SELECT 1 FROM EconomySchemaMigration WHERE version=700").fetchone()
            connection.close()
            self.assertIsNone(marker)
        finally:
            database.close()

    async def test_direct_sql_rejects_outcome_and_asset_ledger_mutation(self):
        database = await TempMiningDatabase().initialize()
        try:
            connection = sqlite3.connect(database.path)
            connection.execute(
                "INSERT INTO MiningOperation (operationId,requestId,guildId,userId,operationType,reservationKey,outcomeJson,status,createdAt) "
                "VALUES ('op','req','1','2','PURCHASE','key','{}','RESERVED','2026')"
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE MiningOperation SET outcomeJson='{\"changed\":true}' WHERE operationId='op'")
            connection.rollback()
            connection.close()
        finally:
            database.close()
