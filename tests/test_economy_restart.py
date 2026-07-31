import sqlite3
import unittest

from economy.database import initialize_database
from economy.recovery import inspect_recovery_state
from economy.treasury import system_seed
from tests.economy_test_utils import TempEconomyDatabase


class EconomyRestartTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = TempEconomyDatabase()
        await initialize_database(self.db.path)

    async def asyncTearDown(self):
        self.db.close()

    async def test_running_migration_blocks_enablement(self):
        connection = sqlite3.connect(self.db.path)
        connection.execute(
            "INSERT INTO EconomyMigrationRun "
            "(runId,migrationVersion,mode,status,guildId,sourceDbSha256,startedAt) "
            "VALUES ('run',100,'RECOVERY','RUNNING','1','hash','now')"
        )
        connection.commit()
        connection.close()
        state = await inspect_recovery_state(self.db.path)
        self.assertFalse(state["safe_to_enable"])
        self.assertEqual(state["unfinished"][0]["run_id"], "run")

    async def test_completed_seed_replays_after_restart(self):
        first = await system_seed(
            self.db.path, guild_id="1", account_code="ETM_GENERAL", amount=100,
            seed_key="restart-seed", reason="temporary restart test", idempotency_key="restart-seed-key",
        )
        await initialize_database(self.db.path)
        second = await system_seed(
            self.db.path, guild_id="1", account_code="ETM_GENERAL", amount=100,
            seed_key="restart-seed", reason="temporary restart test", idempotency_key="new-key",
        )
        self.assertTrue(first.ok)
        self.assertTrue(second.ok and second.replayed)
        connection = sqlite3.connect(self.db.path)
        balance = connection.execute(
            "SELECT balance FROM EconomySystemAccount WHERE accountCode='ETM_GENERAL'"
        ).fetchone()[0]
        connection.close()
        self.assertEqual(balance, 100)


if __name__ == "__main__":
    unittest.main()
