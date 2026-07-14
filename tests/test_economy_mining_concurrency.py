import asyncio
from datetime import datetime, timezone
import sqlite3
import unittest

from economy.mining import purchase_rig
from tests.mining_test_utils import TempMiningDatabase


class MiningConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = await TempMiningDatabase().initialize(level=10)
        await self.database.fund_user(5_000_000)

    async def asyncTearDown(self):
        self.database.close()

    async def test_different_requests_cannot_bypass_single_slot(self):
        now = datetime.now(timezone.utc).isoformat()
        results = await asyncio.gather(*(
            purchase_rig(
                self.database.path, guild_id="1", user_id="2", request_id=f"race-{index}",
                rig_definition_id="rig_basic", observed_at=now,
            ) for index in range(2)
        ))
        self.assertEqual(sum(result.ok for result in results), 1)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM MiningRigInstance").fetchone()[0], 1)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM MiningPurchase").fetchone()[0], 1)
        self.assertEqual(connection.execute(
            "SELECT COUNT(*) FROM EconomyLedger WHERE transactionType='MINING_PURCHASE'"
        ).fetchone()[0], 4)
        connection.close()

    async def test_same_request_replays_without_duplicate_debit(self):
        now = datetime.now(timezone.utc).isoformat()
        first, second = await asyncio.gather(*(
            purchase_rig(
                self.database.path, guild_id="1", user_id="2", request_id="duplicate",
                rig_definition_id="rig_basic", observed_at=now,
            ) for _ in range(2)
        ))
        self.assertEqual(sum(result.ok for result in (first, second)), 2)
        self.assertTrue(first.replayed or second.replayed)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM MiningPurchase").fetchone()[0], 1)
        connection.close()
