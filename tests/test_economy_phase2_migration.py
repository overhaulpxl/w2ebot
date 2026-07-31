import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from economy.migrations import apply_phase2_staging_migration, build_phase2_dry_run


def create_phase2_legacy_database(path):
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE DiscordStat (id TEXT PRIMARY KEY, displayName TEXT, coins INTEGER, "
        "xp INTEGER, level INTEGER, lastDaily TEXT, updatedAt TEXT)"
    )
    connection.execute("CREATE TABLE json_store (filename TEXT PRIMARY KEY, content TEXT)")
    connection.executemany(
        "INSERT INTO DiscordStat VALUES (?,?,?,?,?,?,?)",
        (
            ("10", "A", 5, 75, 12, "2025-01-01T12:00:00", "x"),
            ("20", "B", 0, -3, 101, "not-a-time", "x"),
        ),
    )
    users = {
        "10": {
            "lastWork": "2025-01-02T08:30:00+07:00",
            "energy": 75,
            "energyUpdatedAt": "2025-01-02T01:00:00+00:00",
        },
        "20": {"critBps": 6000, "workDailyCount": 3},
    }
    weekly = {"10": "2025-01-03", "20": "invalid"}
    connection.execute("INSERT INTO json_store VALUES ('users.json',?)", (json.dumps(users),))
    connection.execute("INSERT INTO json_store VALUES ('weekly.json',?)", (json.dumps(weekly),))
    connection.commit()
    connection.close()


class Phase2MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.production = root / "production.db"
        self.staging = root / "staging.db"
        self.backups = root / "backups"
        self.reports = root / "reports"
        create_phase2_legacy_database(self.production)

    def tearDown(self):
        self.temp.cleanup()

    def test_dry_run_mapping_and_no_source_write(self):
        before = self.production.read_bytes()
        report, _ = build_phase2_dry_run(
            self.production, guild_id="1", backup_dir=self.backups, report_dir=self.reports,
        )
        self.assertEqual(before, self.production.read_bytes())
        items = {item["user_id"]: item for item in report["profile_projection"]["items"]}
        self.assertEqual((items["10"]["level"], items["10"]["xp"]), (12, 75))
        self.assertEqual(items["10"]["energy"], 75)
        self.assertEqual((items["20"]["level"], items["20"]["xp"]), (100, 0))
        self.assertEqual(items["20"]["crit_bps"], 5000)
        codes = {code for row in report["issues"]["review_required"] for code in row["codes"]}
        self.assertIn("LEVEL_ABOVE_MAX", codes)
        self.assertIn("INVALID_XP", codes)
        self.assertIn("CRIT_BPS_ABOVE_MAX", codes)
        self.assertIn("UNKNOWN_WORK_COUNT_STATE", codes)

    def test_apply_second_run_and_legacy_source_unchanged(self):
        report, manifest = build_phase2_dry_run(
            self.production, guild_id="1", backup_dir=self.backups, report_dir=self.reports,
        )
        shutil.copy2(report["source"]["backup_path"], self.staging)
        first, first_replayed = apply_phase2_staging_migration(
            self.staging, manifest, production_path=self.production, allow_staging_apply=True,
        )
        second, second_replayed = apply_phase2_staging_migration(
            self.staging, manifest, production_path=self.production, allow_staging_apply=True,
        )
        self.assertFalse(first_replayed)
        self.assertTrue(second_replayed)
        self.assertEqual(first, second)
        connection = sqlite3.connect(self.staging)
        profile = connection.execute(
            "SELECT level,xp,currentHp,maxHp,critBps,energy FROM RpgProfile WHERE userId='10'"
        ).fetchone()
        daily = connection.execute(
            "SELECT lastClaimAt,nextEligibleAt,lastTransactionId FROM EconomyClaimState "
            "WHERE userId='10' AND claimType='DAILY'"
        ).fetchone()
        work = connection.execute(
            "SELECT successCount,lastSuccessAt,pendingRollId FROM EconomyWorkState WHERE userId='10'"
        ).fetchone()
        legacy = connection.execute("SELECT level,xp,lastDaily FROM DiscordStat WHERE id='20'").fetchone()
        activity_count = connection.execute("SELECT COUNT(*) FROM EconomyActivityEvent").fetchone()[0]
        connection.close()
        self.assertEqual(profile, (12, 75, 1000, 1000, 500, 75))
        self.assertIsNotNone(daily[0])
        self.assertIsNotNone(daily[1])
        self.assertIsNone(daily[2])
        self.assertEqual(work[0], 0)
        self.assertIsNotNone(work[1])
        self.assertIsNone(work[2])
        self.assertEqual(legacy, (101, -3, "not-a-time"))
        self.assertEqual(activity_count, 0)

    def test_production_apply_is_refused(self):
        _, manifest = build_phase2_dry_run(
            self.production, guild_id="1", backup_dir=self.backups, report_dir=self.reports,
        )
        with self.assertRaisesRegex(RuntimeError, "production"):
            apply_phase2_staging_migration(
                self.production, manifest, production_path=self.production,
                allow_staging_apply=True,
            )


if __name__ == "__main__":
    unittest.main()
