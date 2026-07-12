import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import aiosqlite

from economy.activity import append_activity_event
from economy.database import initialize_database
from economy.equipment import initialize_phase3_profile
from economy.phase3_schema import migrate_phase3_schema
from economy.quests import ensure_quest_assignments, quest_period, quest_progress, weekly_boss_target


class Phase3QuestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = handle.name
        handle.close()
        await initialize_database(self.db_path)
        await migrate_phase3_schema(self.db_path)
        await initialize_phase3_profile(self.db_path, "1", "2")
        self.now = datetime(2026, 7, 12, 4, 0, tzinfo=timezone.utc)

    async def asyncTearDown(self):
        os.unlink(self.db_path)

    def test_weekly_target_bands(self):
        self.assertEqual([weekly_boss_target(level) for level in (1, 25, 45, 70, 90)],
                         [3000, 10000, 30000, 75000, 150000])

    def test_jakarta_periods(self):
        daily = quest_period("DAILY", now=self.now)
        weekly = quest_period("WEEKLY", now=self.now)
        self.assertEqual(daily[1].hour, 17)
        self.assertEqual(weekly[1].weekday(), 6)  # UTC Sunday 17:00 = Jakarta Monday 00:00

    async def test_daily_counts_attacks_weekly_sums_damage(self):
        await ensure_quest_assignments(self.db_path, "1", "2", now=self.now)
        async with aiosqlite.connect(self.db_path) as db:
            for index, damage in enumerate((100, 250, 400), 1):
                await append_activity_event(
                    db, guild_id="1", user_id="2", event_type="BOSS_ATTACK",
                    event_key=f"attack:{index}", points=0, metric_value=damage,
                    occurred_at=self.now,
                )
            await db.commit()
        progress = await quest_progress(self.db_path, "1", "2", now=self.now)
        self.assertEqual(progress["DAILY"]["progress"]["boss_attacks"], 3)
        self.assertEqual(progress["WEEKLY"]["progress"]["boss_damage"], 750)


if __name__ == "__main__":
    unittest.main()
