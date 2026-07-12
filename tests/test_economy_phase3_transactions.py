import asyncio
import json
import os
import tempfile
import unittest

import aiosqlite

from economy.adventures import reserve_hunt, settle_hunt
from economy.bosses import boss_status, settle_boss, start_boss
from economy.database import configure_connection, ensure_system_accounts, initialize_database
from economy.enhancement import reserve_enhancement, settle_enhancement
from economy.equipment import initialize_phase3_profile
from economy.phase3_schema import migrate_phase3_schema
from economy.time_policy import utc_iso
from economy.rewards import reserve_work_roll, settle_work_roll


class Phase3TransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = handle.name
        handle.close()
        await initialize_database(self.db_path)
        await migrate_phase3_schema(self.db_path)
        await initialize_phase3_profile(self.db_path, "1", "2")
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            await ensure_system_accounts(db, "1", utc_iso())
            await db.execute(
                "INSERT INTO EconomyWallet (guildId,userId,etmBalance,ecyBalance,version,createdAt,updatedAt) "
                "VALUES ('1','2',1000000,0,0,?,?)",
                (utc_iso(), utc_iso()),
            )
            await db.commit()

    async def asyncTearDown(self):
        os.unlink(self.db_path)

    async def test_enhancement_duplicate_settlement_is_one_transaction(self):
        async with aiosqlite.connect(self.db_path) as db:
            instance_id = (await (await db.execute(
                "SELECT activeWeaponInstanceId FROM RpgProfile WHERE guildId='1' AND userId='2'"
            )).fetchone())[0]
        reserved = await reserve_enhancement(
            self.db_path, guild_id="1", user_id="2", equipment_instance_id=instance_id,
        )
        results = await asyncio.gather(*(
            settle_enhancement(self.db_path, guild_id="1", user_id="2", operation_id=reserved[0])
            for _ in range(2)
        ))
        self.assertTrue(all(result.ok for result in results))
        async with aiosqlite.connect(self.db_path) as db:
            transactions = (await (await db.execute(
                "SELECT COUNT(*) FROM EconomyTransaction WHERE operation='RPG_ENHANCEMENT' AND status='COMMITTED'"
            )).fetchone())[0]
            level = (await (await db.execute(
                "SELECT enhancementLevel FROM RpgEquipmentInstance WHERE equipmentInstanceId=?", (instance_id,)
            )).fetchone())[0]
        self.assertEqual(transactions, 1)
        self.assertEqual(level, 1)

    async def test_hunt_reward_and_event_commit_once(self):
        operation_id, outcome, _ = await reserve_hunt(
            self.db_path, guild_id="1", user_id="2", area_id="green_forest",
        )
        first = await settle_hunt(self.db_path, guild_id="1", user_id="2", operation_id=operation_id)
        second = await settle_hunt(self.db_path, guild_id="1", user_id="2", operation_id=operation_id)
        self.assertTrue(first.ok and second.ok)
        async with aiosqlite.connect(self.db_path) as db:
            events = (await (await db.execute(
                "SELECT COUNT(*) FROM EconomyActivityEvent WHERE eventType='HUNT_COMPLETED'"
            )).fetchone())[0]
        self.assertEqual(events, 1)

    async def test_boss_awaiting_funds_reuses_reward_plan(self):
        raid = await start_boss(self.db_path, guild_id="1", tier="normal", start_key="one", authorized=True)
        async with aiosqlite.connect(self.db_path) as db:
            pet_id = (await (await db.execute(
                "SELECT activePetInstanceId FROM RpgProfile WHERE guildId='1' AND userId='2'"
            )).fetchone())[0]
            plan = {"tier": "NORMAL", "minimum_damage": 100, "no_valid_participants": False,
                    "participants": [{"user_id": "2", "damage": 1000, "rank": 1,
                                      "etm": 2_000_000, "drop": {},
                                      "pet_instance_id": pet_id, "pet_xp": 100}]}
            await db.execute(
                "UPDATE RpgBossRaid SET status='DEFEATED',currentHp=0,rewardPlanJson=?,updatedAt=? WHERE raidId=?",
                (json.dumps(plan, sort_keys=True), utc_iso(), raid["raid_id"]),
            )
            await db.commit()
        waiting = await settle_boss(
            self.db_path, guild_id="1", raid_id=raid["raid_id"], authorized=True,
        )
        self.assertEqual(waiting.code, "awaiting_funds")
        before = await boss_status(self.db_path, "1")
        self.assertTrue(before["manual_settlement_required"])
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE EconomySystemAccount SET balance=2000000 WHERE guildId='1' AND accountCode='ETM_BOSS_DUNGEON'"
            )
            await db.commit()
        settled = await settle_boss(
            self.db_path, guild_id="1", raid_id=raid["raid_id"], authorized=True,
        )
        replay = await settle_boss(
            self.db_path, guild_id="1", raid_id=raid["raid_id"], authorized=True,
        )
        self.assertTrue(settled.ok and replay.ok)
        async with aiosqlite.connect(self.db_path) as db:
            events = (await (await db.execute(
                "SELECT COUNT(*) FROM EconomyActivityEvent WHERE eventType='BOSS_PARTICIPATION'"
            )).fetchone())[0]
        self.assertEqual(events, 1)

    async def test_phase2_work_event_metric_is_one(self):
        reserved = await reserve_work_roll(self.db_path, guild_id="1", user_id="2")
        result = await settle_work_roll(
            self.db_path, guild_id="1", user_id="2", roll_id=reserved.roll_id,
        )
        self.assertTrue(result.ok)
        async with aiosqlite.connect(self.db_path) as db:
            metric = (await (await db.execute(
                "SELECT metricValue FROM EconomyActivityEvent WHERE eventType='WORK_SUCCESS'"
            )).fetchone())[0]
        self.assertEqual(metric, 1)


if __name__ == "__main__":
    unittest.main()
