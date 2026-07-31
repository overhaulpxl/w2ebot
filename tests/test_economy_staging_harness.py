import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from economy.database import initialize_database
from economy.phase3_migrations import apply_phase3_staging
from economy.staging import (
    create_logical_sqlite_backup, logical_sqlite_manifest, restore_logical_sqlite_backup,
)
from runtime_config import (
    PROJECT_ROOT, PRODUCTION_DATABASE_PATH, StartupConfiguration,
    command_sync_guild_id, resolve_database_path, validate_startup_configuration,
)


NOW = "2026-01-01T00:00:00+00:00"


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _create_realistic_phase2_fixture(path):
    await initialize_database(path)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE json_store(filename TEXT PRIMARY KEY,content TEXT)")
        connection.execute(
            "INSERT INTO EconomyWallet(guildId,userId,etmBalance,ecyBalance,version,createdAt,updatedAt) "
            "VALUES ('1','42',5000,25,0,?,?)", (NOW, NOW),
        )
        connection.execute(
            "INSERT INTO EconomyTransaction(transactionId,guildId,idempotencyKey,operation,source,"
            "referenceId,actorId,reasonCode,reasonText,metadataJson,status,createdAt,committedAt) "
            "VALUES ('tx-1','1','fixture-1','FIXTURE','TEST',NULL,'42','fixture','fixture','{}',"
            "'COMMITTED',?,?)", (NOW, NOW),
        )
        connection.executemany(
            "INSERT INTO EconomyLedger(transactionId,sequence,guildId,accountKind,accountId,userId,"
            "currency,transactionType,amount,balanceBefore,balanceAfter,referenceId,source,createdAt) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("tx-1", 1, "1", "SYSTEM", "ETM_ISSUANCE", None, "ETM", "FIXTURE", -5000,
                 -5000, -10000, None, "TEST", NOW),
                ("tx-1", 2, "1", "USER", "42", "42", "ETM", "FIXTURE", 5000,
                 0, 5000, None, "TEST", NOW),
            ],
        )
        profiles = [
            ("1", "42", 1, 0, 100),
            ("1", "43", 50, 250, 73),
            ("1", "44", 100, 999, 20),
        ]
        for guild_id, user_id, level, xp, energy in profiles:
            connection.execute(
                "INSERT INTO RpgProfile(guildId,userId,level,xp,maxHp,currentHp,attack,defense,critBps,"
                "energy,energyUpdatedAt,version,createdAt,updatedAt) "
                "VALUES (?,?,?,?,1000,1000,50,25,500,?,?,0,?,?)",
                (guild_id, user_id, level, xp, energy, NOW, NOW, NOW),
            )
        connection.execute(
            "INSERT INTO EconomyWorkState(guildId,userId,periodDate,successCount,lastSuccessAt,pendingRollId,"
            "version,createdAt,updatedAt) VALUES ('1','42','2026-01-01',2,?,NULL,0,?,?)",
            (NOW, NOW, NOW),
        )
        connection.execute(
            "INSERT INTO EconomyActivityEvent(eventId,guildId,userId,eventType,eventKey,points,transactionId,"
            "referenceId,occurredAt,createdAt,metricValue) "
            "VALUES ('event-1','1','42','WORK_SUCCESS','fixture-work',1,'tx-1','work',?,?,1)",
            (NOW, NOW),
        )
        users = {
            "42": {
                "items": {"legacy_sword": 2},
                "pet": "slime",
                "achievements": ["legacy_boss_winner"],
            }
        }
        connection.execute(
            "INSERT INTO json_store(filename,content) VALUES ('users.json',?)",
            (json.dumps(users, separators=(",", ":")),),
        )
        connection.execute("INSERT INTO json_store VALUES ('quests.json','{malformed')")
        connection.execute("INSERT INTO json_store VALUES ('boss.json','not-json')")
        connection.commit()
    finally:
        connection.close()


class StagingConfigurationTests(unittest.TestCase):
    def test_default_and_override_database_paths(self):
        self.assertEqual(resolve_database_path(None, project_root=PROJECT_ROOT), PRODUCTION_DATABASE_PATH)
        override = resolve_database_path("tests/tmp/staging.db", project_root=PROJECT_ROOT)
        self.assertEqual(override, (PROJECT_ROOT / "tests/tmp/staging.db").resolve())

    def test_fail_closed_startup_matrix(self):
        production_enabled = StartupConfiguration(
            PRODUCTION_DATABASE_PATH, PRODUCTION_DATABASE_PATH, False, None, True, True, True, True,
        )
        with self.assertRaises(RuntimeError):
            validate_startup_configuration(production_enabled, verify_database=False)
        staging_on_production = StartupConfiguration(
            PRODUCTION_DATABASE_PATH, PRODUCTION_DATABASE_PATH, True, 1, True, False, False, False,
        )
        with self.assertRaises(RuntimeError):
            validate_startup_configuration(staging_on_production, verify_database=False)
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        try:
            valid = StartupConfiguration(
                Path(handle.name).resolve(), PRODUCTION_DATABASE_PATH, True, 123, True, True, True, True,
            )
            self.assertEqual(validate_startup_configuration(valid).staging_guild_id, 123)
            for bad in (
                StartupConfiguration(valid.database_path, PRODUCTION_DATABASE_PATH, True, None, True, True, True, True),
                StartupConfiguration(valid.database_path, PRODUCTION_DATABASE_PATH, True, 123, False, True, True, True),
                StartupConfiguration(Path(handle.name + ".missing"), PRODUCTION_DATABASE_PATH,
                                     True, 123, True, True, True, True),
            ):
                with self.assertRaises(RuntimeError):
                    validate_startup_configuration(bad)
        finally:
            os.unlink(handle.name)

    def test_core_import_refuses_enabled_flags_without_staging_before_db_init(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "must-remain-empty.db"
            database.touch()
            environment = os.environ.copy()
            environment.update({
                "DATABASE_PATH": str(database), "STAGING_MODE": "false",
                "STAGING_GUILD_ID": "123", "DISCORD_TOKEN": "configured-not-logged",
                "ECONOMY_V1_ENABLED": "true", "ECONOMY_PHASE2_ENABLED": "true",
                "ECONOMY_PHASE3_ENABLED": "true",
            })
            completed = subprocess.run(
                [sys.executable, "-c", "import core"], cwd=PROJECT_ROOT, env=environment,
                text=True, capture_output=True, timeout=30,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(database.stat().st_size, 0)
            self.assertNotIn("configured-not-logged", completed.stdout + completed.stderr)

    def test_runtime_sources_have_no_literal_database_open(self):
        offenders = []
        for root in (PROJECT_ROOT, PROJECT_ROOT / "economy", PROJECT_ROOT / "cogs", PROJECT_ROOT / "scripts"):
            paths = [root] if root.is_file() else root.glob("*.py")
            for path in paths:
                if not path.is_file() or path.name.startswith("test_"):
                    continue
                text = path.read_text(encoding="utf-8")
                if "connect('w2ebot.db'" in text or 'connect("w2ebot.db"' in text:
                    offenders.append(str(path))
        self.assertEqual(offenders, [])

    def test_staging_command_sync_targets_only_dedicated_guild(self):
        staging = StartupConfiguration(
            Path("staging.db"), PRODUCTION_DATABASE_PATH, True, 999, True, True, True, True,
        )
        production = StartupConfiguration(
            PRODUCTION_DATABASE_PATH, PRODUCTION_DATABASE_PATH, False, None,
            True, False, False, False,
        )
        self.assertEqual(command_sync_guild_id(111, staging), 999)
        self.assertEqual(command_sync_guild_id(111, production), 111)

    def test_bot_runtime_and_migration_use_the_same_override(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "runtime-staging.db"
            database.touch()
            environment = os.environ.copy()
            environment.update({
                "DATABASE_PATH": str(database),
                "STAGING_MODE": "false",
                "ECONOMY_V1_ENABLED": "false",
                "ECONOMY_PHASE2_ENABLED": "false",
                "ECONOMY_PHASE3_ENABLED": "false",
            })
            completed = subprocess.run(
                [sys.executable, "-c",
                 "import main; print('RUNTIME_DB=' + main.DB_PATH); "
                 "print('COMMAND_COUNT=' + str(len(main.tree.get_commands())))"],
                cwd=PROJECT_ROOT, env=environment, text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn(f"RUNTIME_DB={database.resolve()}", completed.stdout)
            self.assertRegex(completed.stdout, r"COMMAND_COUNT=[1-9][0-9]*")
            asyncio.run(apply_phase3_staging(
                database, production_db=PRODUCTION_DATABASE_PATH, seed=False,
            ))
            connection = sqlite3.connect(database)
            try:
                self.assertIsNotNone(connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='RpgOperation'"
                ).fetchone())
                self.assertIsNotNone(connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='DiscordStat'"
                ).fetchone())
            finally:
                connection.close()


class StagingMigrationFixtureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.source = root / "phase2-source.db"
        self.target = root / "phase3-target.db"
        self.backup = root / "phase2-logical-backup.db"
        self.restored = root / "phase2-restored.db"
        await _create_realistic_phase2_fixture(self.source)

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_realistic_migration_twice_is_reconciled_and_idempotent(self):
        source_before = _sha256(self.source)
        source_manifest = logical_sqlite_manifest(self.source)
        self.assertNotIn("RpgOperation", source_manifest["row_counts"])
        shutil.copy2(self.source, self.target)
        production = Path(self.temp.name) / "production-never-open.db"
        first = await apply_phase3_staging(self.target, production_db=production, seed=True)
        after_first = logical_sqlite_manifest(self.target)
        second = await apply_phase3_staging(self.target, production_db=production, seed=True)
        after_second = logical_sqlite_manifest(self.target)

        self.assertEqual(_sha256(self.source), source_before)
        for table in ("EconomyWallet", "EconomyLedger", "EconomyWorkState", "EconomyActivityEvent"):
            self.assertEqual(after_first["row_counts"][table], source_manifest["row_counts"][table])
        connection = sqlite3.connect(self.target)
        try:
            level_cap = connection.execute(
                "SELECT xp,starterPackClaimed FROM RpgProfile WHERE guildId='1' AND userId='44'"
            ).fetchone()
            reviews = connection.execute(
                "SELECT COUNT(*) FROM RpgPhase3MigrationReview WHERE warningCode='LEVEL_100_XP_RESET'"
            ).fetchone()[0]
            legacy = connection.execute(
                "SELECT sourceType,bindingStatus FROM RpgLegacyAsset ORDER BY sourceType"
            ).fetchall()
            starter_grants = connection.execute("SELECT COUNT(*) FROM RpgStarterGrant").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(level_cap, (0, 0))
        self.assertEqual(reviews, 1)
        self.assertEqual(legacy, [("ITEM", "LEGACY_BOUND"), ("PET", "LEGACY_BOUND")])
        self.assertEqual(starter_grants, 0)
        self.assertEqual(first["legacy_quarantine"]["malformed_records"], 2)
        self.assertEqual(second["legacy_quarantine"]["replayed_records"], 2)
        self.assertEqual(after_first["row_counts"], after_second["row_counts"])
        self.assertEqual(after_first["table_checksums"], after_second["table_checksums"])
        self.assertEqual(after_second["integrity_check"], "ok")
        self.assertEqual(after_second["foreign_key_errors"], 0)

    async def test_sqlite_backup_api_and_restore_are_logically_identical(self):
        result = await asyncio.to_thread(
            create_logical_sqlite_backup, self.source, self.backup,
        )
        self.assertEqual(result["method"], "sqlite_backup_api")
        self.assertEqual(result["source"]["row_counts"], result["backup"]["row_counts"])
        restored = await asyncio.to_thread(
            restore_logical_sqlite_backup, self.backup, self.restored,
        )
        self.assertEqual(restored["integrity_check"], "ok")
        self.assertEqual(restored["foreign_key_errors"], 0)
        connection = sqlite3.connect(self.restored)
        try:
            self.assertEqual(connection.execute("SELECT etmBalance FROM EconomyWallet").fetchone()[0], 5000)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
