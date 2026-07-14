import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from economy.constants import ASSET_UNIT_SCALE
from economy.phase6_migrations import (
    apply_phase6_staging, assert_not_production, reconcile_phase6_staging,
    verify_phase6_staging,
)
from economy.phase6_schema import PHASE6_MIGRATION_NAME, PHASE6_SCHEMA_CHECKSUM
from economy.phase6_schema import phase6_capability_sync
from tests.crypto_test_utils import TempCryptoDatabase


class CryptoMigrationTests(unittest.TestCase):
    def test_apply_replay_integrity_and_marker(self):
        database = TempCryptoDatabase()
        try:
            replay = apply_phase6_staging(
                database.path, production_db=str(Path(database.path).with_name("prod.db")), guild_id="1",
            )
            self.assertTrue(replay["replayed"])
            verification = verify_phase6_staging(database.path)
            self.assertEqual(verification["marker"], [PHASE6_MIGRATION_NAME, PHASE6_SCHEMA_CHECKSUM, "COMPLETED"])
            self.assertEqual(verification["integrityCheck"], "ok")
            self.assertEqual(verification["foreignKeyErrors"], 0)
            self.assertTrue(reconcile_phase6_staging(database.path)["reconciled"])
        finally:
            database.close()

    def test_capability_fails_closed_for_incomplete_global_market(self):
        database = TempCryptoDatabase()
        try:
            connection = sqlite3.connect(database.path)
            connection.execute("DELETE FROM CryptoMarketState WHERE symbol='ETHR'")
            connection.commit()
            self.assertFalse(phase6_capability_sync(connection))
            connection.close()
        finally:
            database.close()

    def test_legacy_guild_mapping_and_source_preservation(self):
        database = TempCryptoDatabase(migrate=False)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "users.json"
            raw = b'{"9":{"crypto":{"ETHR":1.25,"ORCL":0.000000001}}}'
            source.write_bytes(raw)
            try:
                apply_phase6_staging(
                    database.path, production_db=str(Path(database.path).with_name("prod.db")),
                    guild_id="1", users_json_path=source,
                )
                self.assertEqual(source.read_bytes(), raw)
                connection = sqlite3.connect(database.path)
                holding = connection.execute(
                    "SELECT guildId,units,totalCostBasisEcy FROM CryptoHolding WHERE userId='9' AND symbol='ETHR'"
                ).fetchone()
                review = connection.execute(
                    "SELECT status,errorCode FROM CryptoLegacyHoldingMigration WHERE sourceSymbol='ORCL'"
                ).fetchone()
                connection.close()
                self.assertEqual(holding, ("1", ASSET_UNIT_SCALE + ASSET_UNIT_SCALE // 4, 12_500))
                self.assertEqual(review, ("REVIEW_REQUIRED", "over_precision"))
            finally:
                database.close()

    def test_ambiguous_guild_is_review_only(self):
        database = TempCryptoDatabase(migrate=False)
        connection = sqlite3.connect(database.path)
        connection.execute(
            "INSERT INTO EconomyMigrationRun (runId,migrationVersion,mode,status,guildId,sourceDbSha256,startedAt,completedAt) "
            "VALUES ('other',100,'APPLY','COMPLETED','2','x','2026','2026')"
        )
        connection.commit()
        connection.close()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "users.json"
            source.write_text(json.dumps({"9": {"crypto": {"ETHR": 1}}}), encoding="utf-8")
            try:
                apply_phase6_staging(
                    database.path, production_db=str(Path(database.path).with_name("prod.db")),
                    users_json_path=source,
                )
                connection = sqlite3.connect(database.path)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM CryptoHolding").fetchone()[0], 0)
                self.assertEqual(connection.execute(
                    "SELECT errorCode FROM CryptoLegacyHoldingMigration"
                ).fetchone()[0], "ambiguous_target_guild")
                connection.close()
            finally:
                database.close()

    def test_rollback_injection_and_production_refusal(self):
        for stage in ("after_marker", "after_tables", "after_triggers", "before_commit"):
            with self.subTest(stage=stage):
                database = TempCryptoDatabase(migrate=False)
                try:
                    with self.assertRaises(RuntimeError):
                        apply_phase6_staging(
                            database.path, production_db=str(Path(database.path).with_name("prod.db")),
                            guild_id="1", failure_stage=stage,
                        )
                    connection = sqlite3.connect(database.path)
                    self.assertIsNone(connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='CryptoTrade'"
                    ).fetchone())
                    self.assertIsNone(connection.execute(
                        "SELECT 1 FROM EconomySchemaMigration WHERE version=600"
                    ).fetchone())
                    connection.close()
                finally:
                    database.close()
        database = TempCryptoDatabase(migrate=False)
        try:
            with self.assertRaises(ValueError):
                assert_not_production(database.path, database.path)
        finally:
            database.close()
