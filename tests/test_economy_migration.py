import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from economy.migrations import (
    apply_staging_migration,
    build_dry_run,
    restore_staging_backup,
    verify_staging_migration,
)


def create_legacy_database(path):
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE DiscordStat (id TEXT PRIMARY KEY, displayName TEXT, coins INTEGER, xp INTEGER, level INTEGER, lastDaily TEXT, updatedAt TEXT)"
    )
    connection.execute("CREATE TABLE json_store (filename TEXT PRIMARY KEY, content TEXT)")
    connection.execute(
        "CREATE TABLE Giveaway (id INTEGER PRIMARY KEY, channel_id TEXT, message_id TEXT, prize TEXT, host_id TEXT, end_at TEXT, ended INTEGER DEFAULT 0)"
    )
    connection.executemany(
        "INSERT INTO DiscordStat (id,displayName,coins,xp,level) VALUES (?,?,?,?,?)",
        (("10", "A", 5, 0, 1), ("20", "B", 0, 100, 2)),
    )
    users = {
        "10": {"items": {"shield": 1}, "pet": "slime", "crypto": {"ETHR": 1}, "rigs": {"1": 1}, "games": {"slot": {"plays": 1}}}
    }
    connection.execute("INSERT INTO json_store VALUES ('users.json',?)", (json.dumps(users),))
    connection.execute("INSERT INTO json_store VALUES ('market.json',?)", (json.dumps({"coins": {"ETHR": {"price": 10}}}),))
    connection.execute("INSERT INTO json_store VALUES ('binomo.json',?)", (json.dumps({"10": {"bet": 2, "symbol": "ETHR"}}),))
    connection.execute("INSERT INTO Giveaway VALUES (1,'1','2','legacy','3','later',0)")
    connection.commit()
    connection.close()


class EconomyMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.production = root / "production.db"
        self.staging = root / "staging.db"
        self.backups = root / "backups"
        self.reports = root / "reports"
        create_legacy_database(self.production)

    def tearDown(self):
        self.temp.cleanup()

    def test_dry_run_does_not_write_source(self):
        before = self.production.read_bytes()
        report, manifest = build_dry_run(
            self.production, guild_id="1", backup_dir=self.backups, report_dir=self.reports,
        )
        self.assertEqual(before, self.production.read_bytes())
        self.assertTrue(Path(manifest).exists())
        self.assertTrue(Path(report["source"]["backup_path"]).exists())
        self.assertEqual(report["wallet_projection"]["projected_etm_total"], 5000)
        self.assertEqual(report["wallet_projection"]["projected_ecy_total"], 0)
        self.assertEqual(report["binomo_refunds"]["projected_etm_total"], 2000)
        self.assertEqual(report["deferred_entities"]["legacy_giveaways"], 1)

    def test_apply_and_second_run_are_idempotent(self):
        report, manifest = build_dry_run(
            self.production, guild_id="1", backup_dir=self.backups, report_dir=self.reports,
        )
        shutil.copy2(report["source"]["backup_path"], self.staging)
        first, replayed_first = apply_staging_migration(
            self.staging, manifest, production_path=self.production, allow_staging_apply=True,
        )
        second, replayed_second = apply_staging_migration(
            self.staging, manifest, production_path=self.production, allow_staging_apply=True,
        )
        self.assertFalse(replayed_first)
        self.assertTrue(replayed_second)
        self.assertEqual(first, second)
        connection = sqlite3.connect(self.staging)
        wallet = connection.execute(
            "SELECT etmBalance,ecyBalance FROM EconomyWallet WHERE guildId='1' AND userId='10'"
        ).fetchone()
        legacy = connection.execute("SELECT coins FROM DiscordStat WHERE id='10'").fetchone()[0]
        binomo = connection.execute("SELECT content FROM json_store WHERE filename='binomo.json'").fetchone()[0]
        refunds = connection.execute(
            "SELECT COUNT(*) FROM EconomyTransaction WHERE operation='LEGACY_REFUND' AND status='COMMITTED'"
        ).fetchone()[0]
        ledger_sum = connection.execute("SELECT COALESCE(SUM(amount),0) FROM EconomyLedger").fetchone()[0]
        connection.close()
        self.assertEqual(wallet, (7000, 0))
        self.assertEqual(legacy, 5)
        self.assertIn('"bet": 2', binomo)
        self.assertEqual(refunds, 1)
        self.assertEqual(ledger_sum, 0)
        verification = verify_staging_migration(self.staging, guild_id="1")
        self.assertTrue(verification["valid"])

    def test_production_apply_is_refused(self):
        _, manifest = build_dry_run(
            self.production, guild_id="1", backup_dir=self.backups, report_dir=self.reports,
        )
        with self.assertRaisesRegex(RuntimeError, "production"):
            apply_staging_migration(
                self.production, manifest, production_path=self.production, allow_staging_apply=True,
            )

    def test_manifest_checksum_mismatch_is_refused(self):
        _, manifest = build_dry_run(
            self.production, guild_id="1", backup_dir=self.backups, report_dir=self.reports,
        )
        report = json.loads(Path(manifest).read_text(encoding="utf-8"))
        shutil.copy2(report["source"]["backup_path"], self.staging)
        with open(self.staging, "ab") as handle:
            handle.write(b"changed")
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            apply_staging_migration(
                self.staging, manifest, production_path=self.production, allow_staging_apply=True,
            )

    def test_staging_rollback_restores_backup_and_refuses_production(self):
        report, _ = build_dry_run(
            self.production, guild_id="1", backup_dir=self.backups, report_dir=self.reports,
        )
        self.staging.write_bytes(b"not a database")
        result = restore_staging_backup(
            report["source"]["backup_path"], self.staging,
            production_path=self.production, allow_staging_restore=True,
        )
        self.assertTrue(result["restored"])
        connection = sqlite3.connect(self.staging)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM DiscordStat").fetchone()[0], 2)
        connection.close()
        with self.assertRaisesRegex(RuntimeError, "production"):
            restore_staging_backup(
                report["source"]["backup_path"], self.production,
                production_path=self.production, allow_staging_restore=True,
            )


if __name__ == "__main__":
    unittest.main()
