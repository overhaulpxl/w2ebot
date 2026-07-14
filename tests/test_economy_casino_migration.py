import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from economy.database import ensure_phase1_schema
from economy.phase5_migrations import (
    apply_phase5_staging, assert_not_production, phase5_dry_run,
    reconcile_phase5_staging, verify_phase5_staging,
)
from economy.phase5_schema import PHASE5_SCHEMA_CHECKSUM


def new_database(directory):
    path = Path(directory) / "staging.db"
    connection = sqlite3.connect(path)
    ensure_phase1_schema(connection)
    connection.commit()
    connection.close()
    return path


class CasinoMigrationTests(unittest.TestCase):
    def test_disabled_phase1_startup_does_not_create_phase5(self):
        with tempfile.TemporaryDirectory() as directory:
            path = new_database(directory)
            connection = sqlite3.connect(path)
            count = connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'Casino%'").fetchone()[0]
            marker = connection.execute("SELECT COUNT(*) FROM EconomySchemaMigration WHERE version=500").fetchone()[0]
            connection.close()
            self.assertEqual((count, marker), (0, 0))

    def test_apply_verify_reconcile_and_second_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = new_database(directory)
            first = apply_phase5_staging(path, production_db=Path(directory) / "prod.db")
            second = apply_phase5_staging(path, production_db=Path(directory) / "prod.db")
            self.assertTrue(first["applied"])
            self.assertTrue(second["replayed"])
            verify = verify_phase5_staging(path)
            self.assertTrue(verify["schemaCapable"])
            self.assertEqual(verify["marker"][1], PHASE5_SCHEMA_CHECKSUM)
            self.assertEqual(verify["integrityCheck"], "ok")
            self.assertEqual(verify["foreignKeyErrors"], 0)
            self.assertTrue(reconcile_phase5_staging(path)["reconciled"])

    def test_every_failure_stage_rolls_back(self):
        for stage in ("after_marker", "after_tables", "after_triggers", "before_commit"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                path = new_database(directory)
                with self.assertRaises(RuntimeError):
                    apply_phase5_staging(path, production_db=Path(directory) / "prod.db", failure_stage=stage)
                connection = sqlite3.connect(path)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM EconomySchemaMigration WHERE version=500").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'Casino%'").fetchone()[0], 0)
                connection.close()

    def test_production_refusal_and_checksum_mismatch(self):
        with self.assertRaises(ValueError):
            assert_not_production("w2ebot.db", "./w2ebot.db")
        with tempfile.TemporaryDirectory() as directory:
            path = new_database(directory)
            apply_phase5_staging(path, production_db=Path(directory) / "prod.db")
            connection = sqlite3.connect(path)
            connection.execute("UPDATE EconomySchemaMigration SET checksum='wrong' WHERE version=500")
            connection.commit()
            connection.close()
            self.assertFalse(verify_phase5_staging(path)["schemaCapable"])
            self.assertFalse(phase5_dry_run(path)["canApply"])

    def test_capability_rejects_partial_canonical_table(self):
        with tempfile.TemporaryDirectory() as directory:
            path = new_database(directory)
            apply_phase5_staging(path, production_db=Path(directory) / "prod.db")
            connection = sqlite3.connect(path)
            connection.execute("ALTER TABLE CasinoAuthorization RENAME TO CasinoAuthorizationComplete")
            connection.execute("CREATE TABLE CasinoAuthorization (guildId TEXT, userId TEXT)")
            connection.commit()
            connection.close()
            self.assertFalse(verify_phase5_staging(path)["schemaCapable"])

    def test_legacy_snapshot_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = new_database(directory)
            source = Path(directory) / "users.json"
            source.write_bytes(b'{"2":{"games":{"slot":{"plays":3},"hunt":{"plays":9}}}}')
            before = source.read_bytes()
            apply_phase5_staging(path, production_db=Path(directory) / "prod.db", guild_id="1", users_json_path=source)
            self.assertEqual(source.read_bytes(), before)
            connection = sqlite3.connect(path)
            snapshot = connection.execute("SELECT sanitizedSnapshotJson FROM CasinoLegacyStatistic").fetchone()[0]
            connection.close()
            self.assertEqual(json.loads(snapshot), {"slot": {"plays": 3}})

    def test_direct_sql_guards_outcome_receipt_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = new_database(directory)
            apply_phase5_staging(path, production_db=Path(directory) / "prod.db")
            connection = sqlite3.connect(path)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                "INSERT INTO CasinoSession (sessionId,requestId,guildId,userId,gameType,stakeEcy,maximumGrossLiabilityEcy,outcomeJson,stateJson,status,reservationKey,createdAt) "
                "VALUES ('s','r','1','2','SLOT',1000,8000,'{}','{}','RESERVED','key','now')"
            )
            connection.execute(
                "INSERT INTO CasinoSettlement (settlementId,sessionId,stakeEcy,grossPayoutEcy,status,createdAt) VALUES ('x','s',1000,0,'PENDING','now')"
            )
            connection.execute(
                "INSERT INTO CasinoBankrollReservation (reservationId,sessionId,guildId,liabilityEcy,status,createdAt) VALUES ('b','s','1',8000,'ACTIVE','now')"
            )
            connection.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE CasinoSession SET outcomeJson='{\"x\":1}' WHERE sessionId='s'")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE CasinoSettlement SET receiptJson='{}' WHERE settlementId='x'")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM CasinoSettlement WHERE settlementId='x'")
            connection.execute(
                "UPDATE CasinoBankrollReservation SET status='RELEASED',releasedAt='done' WHERE reservationId='b'"
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE CasinoBankrollReservation SET releasedAt='changed' WHERE reservationId='b'")
            connection.close()


if __name__ == "__main__":
    unittest.main()
