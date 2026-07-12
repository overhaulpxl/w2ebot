import json
import os
import tempfile
import unittest

import aiosqlite

from economy.bosses import boss_status, settle_boss, start_boss
from economy.database import initialize_database
from economy.phase3_schema import migrate_phase3_schema
from economy.time_policy import utc_iso


class Phase3BossTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = handle.name
        handle.close()
        await initialize_database(self.db_path)
        await migrate_phase3_schema(self.db_path)

    async def asyncTearDown(self):
        os.unlink(self.db_path)

    async def test_only_one_unresolved_raid(self):
        first = await start_boss(self.db_path, guild_id="1", tier="normal", start_key="a", authorized=True)
        second = await start_boss(self.db_path, guild_id="1", tier="world", start_key="b", authorized=True)
        self.assertEqual(first["raid_id"], second["raid_id"])
        self.assertTrue(second["replayed"])

    async def test_no_valid_participant_settles_without_fund(self):
        raid = await start_boss(self.db_path, guild_id="1", tier="normal", start_key="a", authorized=True)
        plan = {"tier": "NORMAL", "minimum_damage": 100, "participants": [], "no_valid_participants": True}
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE RpgBossRaid SET status='DEFEATED',currentHp=0,rewardPlanJson=?,defeatedAt=?,updatedAt=? WHERE raidId=?",
                (json.dumps(plan, sort_keys=True), utc_iso(), utc_iso(), raid["raid_id"]),
            )
            await db.commit()
        result = await settle_boss(self.db_path, guild_id="1", raid_id=raid["raid_id"], authorized=True)
        replay = await settle_boss(self.db_path, guild_id="1", raid_id=raid["raid_id"], authorized=True)
        self.assertTrue(result.ok)
        self.assertTrue(replay.ok)
        status = await boss_status(self.db_path, "1")
        self.assertEqual(status["status"], "SETTLED")
        self.assertEqual(status["noValidParticipants"], 1)


if __name__ == "__main__":
    unittest.main()
