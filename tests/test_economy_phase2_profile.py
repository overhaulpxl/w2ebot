import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

import aiosqlite

from economy.activity import append_activity_event, rolling_activity_score
from economy.database import configure_connection
from economy.profile import (
    calculate_power_score,
    ensure_profile,
    get_profile_snapshot,
    materialize_energy,
    validate_profile_stats,
)
from tests.economy_test_utils import TempEconomyDatabase


class Phase2ProfileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = TempEconomyDatabase()

    async def asyncTearDown(self):
        self.database.close()

    async def test_default_power_score_is_480(self):
        self.assertEqual(
            calculate_power_score(attack=50, defense=25, max_hp=1000, crit_bps=500),
            480,
        )
        await ensure_profile(self.database.path, "1", "10")
        profile = await get_profile_snapshot(self.database.path, "1", "10")
        self.assertEqual(profile.power_score, 480)
        self.assertEqual((profile.current_hp, profile.max_hp, profile.energy), (1000, 1000, 100))

    async def test_critical_chance_cap_and_instance_placeholders(self):
        validate_profile_stats(
            level=1, xp=0, max_hp=1000, current_hp=1000,
            attack=50, defense=25, crit_bps=5000, energy=100,
        )
        with self.assertRaises(ValueError):
            validate_profile_stats(
                level=1, xp=0, max_hp=1000, current_hp=1000,
                attack=50, defense=25, crit_bps=5001, energy=100,
            )
        await ensure_profile(self.database.path, "1", "10")
        profile = await get_profile_snapshot(self.database.path, "1", "10")
        self.assertIsNone(profile.active_weapon_instance_id)
        self.assertIsNone(profile.active_pet_instance_id)
        connection = sqlite3.connect(self.database.path)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE RpgProfile SET critBps=5001 WHERE guildId='1' AND userId='10'"
            )
        connection.close()

    async def test_energy_regeneration_is_integer_atomic_and_capped(self):
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        await ensure_profile(self.database.path, "1", "10", now=now)
        old = now - timedelta(minutes=25)
        async with aiosqlite.connect(self.database.path) as db:
            await db.execute(
                "UPDATE RpgProfile SET energy=90,energyUpdatedAt=? WHERE guildId='1' AND userId='10'",
                (old.isoformat(),),
            )
            await db.commit()
        energy = await materialize_energy(self.database.path, "1", "10", now=now)
        self.assertEqual(energy, 92)
        async with aiosqlite.connect(self.database.path) as db:
            async with db.execute(
                "SELECT energyUpdatedAt FROM RpgProfile WHERE guildId='1' AND userId='10'"
            ) as cursor:
                updated = (await cursor.fetchone())[0]
        self.assertEqual(datetime.fromisoformat(updated), old + timedelta(minutes=20))

    async def test_activity_score_is_rolling_30_days_and_events_are_append_only(self):
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        async with aiosqlite.connect(self.database.path) as db:
            await configure_connection(db)
            await append_activity_event(
                db, guild_id="1", user_id="10", event_type="VOICE",
                event_key="voice:recent", points=7, occurred_at=now - timedelta(days=29),
            )
            await append_activity_event(
                db, guild_id="1", user_id="10", event_type="VOICE",
                event_key="voice:boundary", points=3, occurred_at=now - timedelta(days=30),
            )
            await append_activity_event(
                db, guild_id="1", user_id="10", event_type="VOICE",
                event_key="voice:old", points=99, occurred_at=now - timedelta(days=31),
            )
            await db.commit()
        self.assertEqual(await rolling_activity_score(self.database.path, "1", "10", now=now), 10)
        async with aiosqlite.connect(self.database.path) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                await db.execute("UPDATE EconomyActivityEvent SET points=8 WHERE eventKey='voice:recent'")

    async def test_activity_score_is_not_a_profile_column(self):
        connection = sqlite3.connect(self.database.path)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(RpgProfile)")}
        connection.close()
        self.assertNotIn("activityPoints", columns)


if __name__ == "__main__":
    unittest.main()
