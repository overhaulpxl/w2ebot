import asyncio
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from economy.rewards import (
    claim_reward,
    recover_stale_work_rolls,
    reserve_work_roll,
    settle_work_roll,
)
from economy.recovery import recover_phase2_runtime
from tests.economy_test_utils import TempEconomyDatabase


class Phase2RewardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = TempEconomyDatabase()
        self.now = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

    async def asyncTearDown(self):
        self.database.close()

    async def test_daily_is_atomic_idempotent_and_records_activity(self):
        results = await asyncio.gather(
            claim_reward(
                self.database.path, guild_id="1", user_id="10", claim_type="DAILY",
                request_id="a", now=self.now,
            ),
            claim_reward(
                self.database.path, guild_id="1", user_id="10", claim_type="DAILY",
                request_id="b", now=self.now,
            ),
        )
        self.assertEqual(sum(result.ok for result in results), 1)
        connection = sqlite3.connect(self.database.path)
        wallet = connection.execute(
            "SELECT etmBalance,ecyBalance FROM EconomyWallet WHERE guildId='1' AND userId='10'"
        ).fetchone()
        events = connection.execute(
            "SELECT points,transactionId FROM EconomyActivityEvent WHERE eventType='DAILY_CLAIM'"
        ).fetchall()
        connection.close()
        self.assertEqual(wallet, (50_000, 5_000))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], 2)
        self.assertIsNotNone(events[0][1])

    async def test_weekly_replay_pays_once(self):
        first = await claim_reward(
            self.database.path, guild_id="1", user_id="10", claim_type="WEEKLY",
            request_id="same", now=self.now,
        )
        second = await claim_reward(
            self.database.path, guild_id="1", user_id="10", claim_type="WEEKLY",
            request_id="same", now=self.now,
        )
        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        self.assertTrue(second.replayed)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute(
            "SELECT COUNT(*) FROM EconomyActivityEvent WHERE eventType='WEEKLY_CLAIM'"
        ).fetchone()[0], 1)
        connection.close()

    async def test_work_reuses_roll_and_uses_only_work_state_counter(self):
        reserved = await reserve_work_roll(
            self.database.path, guild_id="1", user_id="10", now=self.now,
        )
        reused = await reserve_work_roll(
            self.database.path, guild_id="1", user_id="10", now=self.now + timedelta(minutes=1),
        )
        self.assertEqual(reserved.roll_id, reused.roll_id)
        self.assertEqual(reserved.amount, reused.amount)
        paid = await settle_work_roll(
            self.database.path, guild_id="1", user_id="10", roll_id=reserved.roll_id, now=self.now,
        )
        self.assertTrue(paid.ok)
        connection = sqlite3.connect(self.database.path)
        state = connection.execute(
            "SELECT successCount,pendingRollId FROM EconomyWorkState WHERE guildId='1' AND userId='10'"
        ).fetchone()
        work_usage = connection.execute(
            "SELECT COUNT(*) FROM EconomyDailyUsage WHERE usageType='WORK'"
        ).fetchone()[0]
        connection.close()
        self.assertEqual(state, (1, None))
        self.assertEqual(work_usage, 0)

    async def test_stale_roll_recovery_is_atomic_idempotent_and_void_cannot_pay(self):
        reserved = await reserve_work_roll(
            self.database.path, guild_id="1", user_id="10", now=self.now,
        )
        recovery_time = self.now + timedelta(hours=25)
        first = (await recover_phase2_runtime(self.database.path, now=recovery_time))["work_rolls"]
        second = await recover_stale_work_rolls(self.database.path, now=recovery_time)
        self.assertEqual(first["voided"], 1)
        self.assertEqual(second["voided"], 0)
        result = await settle_work_roll(
            self.database.path, guild_id="1", user_id="10", roll_id=reserved.roll_id,
            now=recovery_time,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "void_roll")
        connection = sqlite3.connect(self.database.path)
        roll = connection.execute(
            "SELECT status,transactionId FROM EconomyRewardRoll WHERE rollId=?", (reserved.roll_id,)
        ).fetchone()
        pending = connection.execute(
            "SELECT pendingRollId FROM EconomyWorkState WHERE guildId='1' AND userId='10'"
        ).fetchone()[0]
        wallet_count = connection.execute("SELECT COUNT(*) FROM EconomyWallet").fetchone()[0]
        connection.close()
        self.assertEqual(roll, ("VOID", None))
        self.assertIsNone(pending)
        self.assertEqual(wallet_count, 0)

    async def test_work_four_per_jakarta_day_limit(self):
        for index in range(4):
            current = self.now + timedelta(hours=index * 2)
            reserved = await reserve_work_roll(
                self.database.path, guild_id="1", user_id="10", now=current,
            )
            self.assertTrue(reserved.ok)
            paid = await settle_work_roll(
                self.database.path, guild_id="1", user_id="10",
                roll_id=reserved.roll_id, now=current,
            )
            self.assertTrue(paid.ok)
        blocked = await reserve_work_roll(
            self.database.path, guild_id="1", user_id="10", now=self.now + timedelta(hours=8),
        )
        self.assertFalse(blocked.ok)
        self.assertEqual(blocked.code, "daily_limit")
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute(
            "SELECT successCount FROM EconomyWorkState WHERE guildId='1' AND userId='10'"
        ).fetchone()[0], 4)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM EconomyDailyUsage").fetchone()[0], 0)
        connection.close()

    async def test_work_settlement_duplicate_and_recovery_race(self):
        reserved = await reserve_work_roll(
            self.database.path, guild_id="1", user_id="10", now=self.now,
        )
        duplicate = await asyncio.gather(
            settle_work_roll(
                self.database.path, guild_id="1", user_id="10",
                roll_id=reserved.roll_id, now=self.now,
            ),
            settle_work_roll(
                self.database.path, guild_id="1", user_id="10",
                roll_id=reserved.roll_id, now=self.now,
            ),
        )
        self.assertTrue(all(result.ok for result in duplicate))
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute(
            "SELECT COUNT(*) FROM EconomyTransaction WHERE operation='WORK_REWARD' AND status='COMMITTED'"
        ).fetchone()[0], 1)
        connection.close()

        stale_user = "20"
        stale = await reserve_work_roll(
            self.database.path, guild_id="1", user_id=stale_user, now=self.now,
        )
        race_time = self.now + timedelta(hours=25)
        settlement, recovery = await asyncio.gather(
            settle_work_roll(
                self.database.path, guild_id="1", user_id=stale_user,
                roll_id=stale.roll_id, now=race_time,
            ),
            recover_stale_work_rolls(self.database.path, now=race_time),
        )
        self.assertFalse(settlement.ok)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute(
            "SELECT status FROM EconomyRewardRoll WHERE rollId=?", (stale.roll_id,)
        ).fetchone()[0], "VOID")
        self.assertIsNone(connection.execute(
            "SELECT pendingRollId FROM EconomyWorkState WHERE userId=?", (stale_user,)
        ).fetchone()[0])
        connection.close()

    async def test_daily_usage_schema_rejects_work(self):
        connection = sqlite3.connect(self.database.path)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO EconomyDailyUsage VALUES ('1','10','2026-01-01','WORK',1,0,'x','x')"
            )
        connection.close()


if __name__ == "__main__":
    unittest.main()
