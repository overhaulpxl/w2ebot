import os
import sqlite3
import tempfile
import unittest

from economy.database import SCHEMA_SQL
from economy.phase9a_migrations import (
    apply_phase9a_staging, reconcile_phase9a_staging, restore_phase9a_staging,
    verify_phase9a_staging,
)
from economy.phase9a_schema import PHASE9A_MIGRATION_NAME, PHASE9A_SCHEMA_CHECKSUM


class Phase9AMigrationTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db"); os.close(handle)
        connection = sqlite3.connect(self.path); connection.executescript(SCHEMA_SQL); connection.commit(); connection.close()
        self.production = self.path + ".production"

    def tearDown(self):
        if os.path.exists(self.path): os.remove(self.path)

    def test_apply_replay_reconcile_and_integrity(self):
        first = apply_phase9a_staging(self.path, production_db=self.production)
        replay = apply_phase9a_staging(self.path, production_db=self.production)
        verified = verify_phase9a_staging(self.path)
        self.assertTrue(first["applied"]); self.assertTrue(replay["replayed"])
        self.assertEqual(verified["migrationName"], PHASE9A_MIGRATION_NAME)
        self.assertEqual(verified["migrationChecksum"], PHASE9A_SCHEMA_CHECKSUM)
        self.assertEqual(verified["integrityCheck"], "ok"); self.assertEqual(verified["foreignKeyErrors"], 0)
        self.assertTrue(reconcile_phase9a_staging(self.path)["reconciled"])

    def test_failure_rolls_back_and_production_refused(self):
        for stage in ("after_marker", "after_tables", "after_indexes", "after_triggers",
                      "after_snapshots", "before_commit"):
            with self.subTest(stage=stage):
                handle, path = tempfile.mkstemp(suffix=".db"); os.close(handle)
                try:
                    connection = sqlite3.connect(path)
                    connection.executescript(SCHEMA_SQL); connection.commit(); connection.close()
                    with self.assertRaises(RuntimeError):
                        apply_phase9a_staging(path, production_db=self.production, failure_stage=stage)
                    connection = sqlite3.connect(path)
                    self.assertIsNone(connection.execute(
                        "SELECT 1 FROM EconomySchemaMigration WHERE version=900"
                    ).fetchone())
                    self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
                    connection.close()
                finally:
                    if os.path.exists(path): os.remove(path)
        with self.assertRaises(ValueError):
            apply_phase9a_staging(self.path, production_db=self.path)

    def test_backup_and_restore(self):
        backup = self.path + ".backup.db"
        try:
            applied = apply_phase9a_staging(
                self.path, production_db=self.production, backup_path=backup,
            )
            self.assertTrue(applied["applied"])
            restored = restore_phase9a_staging(
                self.path, backup_path=backup, production_db=self.production, confirm=True,
            )
            self.assertTrue(restored["restored"])
            connection = sqlite3.connect(self.path)
            self.assertIsNone(connection.execute(
                "SELECT 1 FROM EconomySchemaMigration WHERE version=900"
            ).fetchone())
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            connection.close()
        finally:
            if os.path.exists(backup): os.remove(backup)
