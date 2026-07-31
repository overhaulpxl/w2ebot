import asyncio
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

from scripts.run_phase3_staging import _read_staging_env
from scripts.setup_phase3_staging import prepare_staging


class LocalPhase3StagingTests(unittest.TestCase):
    def test_placeholder_token_and_guild_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.staging"
            path.write_text(
                "STAGING_MODE=true\nSTAGING_GUILD_ID=REPLACE_WITH_DEDICATED_STAGING_GUILD_ID\n"
                "DATABASE_PATH=C:/staging.db\nECONOMY_V1_ENABLED=true\n"
                "ECONOMY_PHASE2_ENABLED=true\nECONOMY_PHASE3_ENABLED=true\n"
                "DISCORD_TOKEN=REPLACE_WITH_DEDICATED_STAGING_BOT_TOKEN\n",
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                _read_staging_env(path)

    def test_launcher_parser_accepts_valid_guild_without_logging_token(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.staging"
            path.write_text(
                "STAGING_MODE=true\nSTAGING_GUILD_ID=123456789012345678\n"
                "DATABASE_PATH=C:/staging.db\nECONOMY_V1_ENABLED=true\n"
                "ECONOMY_PHASE2_ENABLED=true\nECONOMY_PHASE3_ENABLED=true\n"
                "DISCORD_TOKEN=staging-secret-sentinel\n",
                encoding="utf-8",
            )
            values = _read_staging_env(path)
            self.assertEqual(values["STAGING_GUILD_ID"], "123456789012345678")
            self.assertNotIn(values["DISCORD_TOKEN"], repr(values.keys()))

    def test_clean_setup_creates_database_migrates_twice_and_env(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = asyncio.run(prepare_staging(root))
            database = Path(result["database_path"])
            env_path = Path(result["env_staging_path"])
            self.assertTrue(database.exists())
            self.assertTrue(env_path.exists())
            self.assertTrue(result["second_migration_idempotent"])
            self.assertEqual(result["checks"]["integrity_check"], "ok")
            self.assertEqual(result["checks"]["foreign_key_errors"], 0)
            self.assertEqual(result["checks"]["blocking_review_rows"], 0)
            connection = sqlite3.connect(database)
            try:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM RpgCatalogItem"
                ).fetchone()[0], 49)
            finally:
                connection.close()

    def test_existing_env_is_preserved_and_reset_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asyncio.run(prepare_staging(root))
            env_path = root / ".env.staging"
            original = env_path.read_text(encoding="utf-8")
            env_path.write_text(original.replace(
                "REPLACE_WITH_DEDICATED_STAGING_GUILD_ID", "123456789012345678",
            ).replace(
                "REPLACE_WITH_DEDICATED_STAGING_BOT_TOKEN", "staging-secret-sentinel",
            ), encoding="utf-8")
            database = root / "staging" / "w2ebot-staging.db"
            with self.assertRaises(RuntimeError):
                asyncio.run(prepare_staging(root, reset=True, confirm_reset=False))
            self.assertTrue(database.exists())
            self.assertIn("staging-secret-sentinel", env_path.read_text(encoding="utf-8"))
            asyncio.run(prepare_staging(root, reset=True, confirm_reset=True))
            self.assertTrue(database.exists())
            self.assertIn("staging-secret-sentinel", env_path.read_text(encoding="utf-8"))

    def test_git_ignores_local_staging_env(self):
        completed = subprocess.run(
            ["git", "check-ignore", "-q", ".env.staging"],
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(completed.returncode, 0)


if __name__ == "__main__":
    unittest.main()
