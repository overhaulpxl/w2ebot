import sqlite3
import unittest

from economy.mining import purchase_rig
from economy.phase7_recovery import recover_phase7
from tests.mining_test_utils import TempMiningDatabase


class MiningRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = await TempMiningDatabase().initialize()
        await self.database.fund_user()

    async def asyncTearDown(self):
        self.database.close()

    async def test_review_operation_reuses_original_plan(self):
        failed = await purchase_rig(
            self.database.path, guild_id="1", user_id="2", request_id="recover-me",
            rig_definition_id="rig_basic", _failure_stage="before_receipt",
        )
        self.assertFalse(failed.ok)
        connection = sqlite3.connect(self.database.path)
        before = connection.execute(
            "SELECT operationId,outcomeJson,status FROM MiningOperation WHERE requestId='recover-me'"
        ).fetchone()
        connection.close()
        report = await recover_phase7(self.database.path)
        connection = sqlite3.connect(self.database.path)
        after = connection.execute(
            "SELECT operationId,outcomeJson,status FROM MiningOperation WHERE requestId='recover-me'"
        ).fetchone()
        connection.close()
        self.assertEqual(before[:2], after[:2])
        self.assertEqual(after[2], "COMMITTED")
        self.assertEqual(report["committed"], 1)

    async def test_expired_outbox_lease_is_reclaimed(self):
        result = await purchase_rig(
            self.database.path, guild_id="1", user_id="2", request_id="outbox",
            rig_definition_id="rig_basic",
        )
        self.assertTrue(result.ok)
        connection = sqlite3.connect(self.database.path)
        connection.execute(
            "UPDATE MiningNotificationOutbox SET status='CLAIMED',leaseOwner='dead',leaseExpiresAt='2000-01-01T00:00:00+00:00'"
        )
        connection.commit()
        connection.close()
        report = await recover_phase7(self.database.path)
        self.assertEqual(report["outboxLeasesReclaimed"], 1)
