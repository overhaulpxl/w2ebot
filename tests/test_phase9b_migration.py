import os
import sqlite3
import tempfile
import unittest

from economy.database import SCHEMA_SQL
from economy.phase9a_migrations import apply_phase9a_staging
from economy.phase9b_migrations import (
    apply_phase9b_staging, reconcile_phase9b_staging, restore_phase9b_staging,
    verify_phase9b_staging,
)
from economy.phase9b_schema import PHASE9B_MIGRATION_NAME, PHASE9B_SCHEMA_CHECKSUM


class Phase9BMigrationTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db"); os.close(handle)
        connection = sqlite3.connect(self.path); connection.executescript(SCHEMA_SQL); connection.commit(); connection.close()
        self.production = self.path + ".production"
        apply_phase9a_staging(self.path, production_db=self.production)

    def tearDown(self):
        for suffix in ("", ".backup.db", ".pre-restore-safety.db"):
            path = self.path + suffix
            if os.path.exists(path): os.remove(path)

    def test_apply_replay_reconcile_integrity_and_foreign_keys(self):
        first = apply_phase9b_staging(self.path, production_db=self.production)
        replay = apply_phase9b_staging(self.path, production_db=self.production)
        result = verify_phase9b_staging(self.path)
        reconcile = reconcile_phase9b_staging(self.path, guild_id="1")
        self.assertTrue(first["applied"]); self.assertTrue(replay["replayed"])
        self.assertEqual(result["migrationName"], PHASE9B_MIGRATION_NAME)
        self.assertEqual(result["migrationChecksum"], PHASE9B_SCHEMA_CHECKSUM)
        self.assertEqual(result["integrityCheck"], "ok"); self.assertEqual(result["foreignKeyErrors"], 0)
        self.assertTrue(reconcile["reconciled"])

    def test_dependency_rollback_injection_and_production_refusal(self):
        raw_handle, raw = tempfile.mkstemp(suffix=".db"); os.close(raw_handle)
        try:
            connection = sqlite3.connect(raw); connection.executescript(SCHEMA_SQL); connection.commit(); connection.close()
            with self.assertRaises(RuntimeError): apply_phase9b_staging(raw, production_db=raw + ".prod")
        finally:
            os.remove(raw)
        for stage in ("after_marker", "after_tables", "after_indexes", "after_triggers", "after_import", "before_commit"):
            with self.subTest(stage=stage):
                handle, path = tempfile.mkstemp(suffix=".db"); os.close(handle)
                try:
                    connection = sqlite3.connect(path); connection.executescript(SCHEMA_SQL); connection.commit(); connection.close()
                    apply_phase9a_staging(path, production_db=self.production)
                    with self.assertRaises(RuntimeError):
                        apply_phase9b_staging(path, production_db=self.production, failure_stage=stage)
                    connection = sqlite3.connect(path)
                    self.assertIsNone(connection.execute("SELECT 1 FROM EconomySchemaMigration WHERE version=910").fetchone())
                    self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
                    connection.close()
                finally:
                    os.remove(path)
        with self.assertRaises(ValueError): apply_phase9b_staging(self.path, production_db=self.path)

    def test_backup_restore(self):
        backup = self.path + ".backup.db"
        apply_phase9b_staging(self.path, production_db=self.production, backup_path=backup)
        restored = restore_phase9b_staging(self.path, backup_path=backup,
                                           production_db=self.production, confirm=True)
        self.assertTrue(restored["restored"])
        connection = sqlite3.connect(self.path)
        self.assertIsNone(connection.execute("SELECT 1 FROM EconomySchemaMigration WHERE version=910").fetchone())
        connection.close()

    def test_checksum_mismatch_fails_closed(self):
        apply_phase9b_staging(self.path, production_db=self.production)
        connection = sqlite3.connect(self.path)
        connection.execute("UPDATE EconomySchemaMigration SET checksum=? WHERE version=910", ("0" * 64,))
        connection.commit(); connection.close()
        with self.assertRaises(RuntimeError):
            apply_phase9b_staging(self.path, production_db=self.production)
