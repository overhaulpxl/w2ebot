import os
import tempfile
import unittest

import aiosqlite

from economy.catalog import catalog_hash, seed_catalog, validate_catalog
from economy.database import initialize_database
from economy.equipment import (
    calculate_effective_stats, get_effective_stats, initialize_phase3_profile,
    starter_effective_stats,
)
from economy.phase3_schema import migrate_phase3_schema
from economy.combat import final_damage
from economy.xp import apply_player_xp


class Phase3ProfileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = handle.name
        handle.close()
        await initialize_database(self.db_path)
        await migrate_phase3_schema(self.db_path)
        async with aiosqlite.connect(self.db_path) as db:
            await seed_catalog(db)
            await db.commit()

    async def asyncTearDown(self):
        os.unlink(self.db_path)

    def test_starter_effective_stat_regression(self):
        stats = starter_effective_stats()
        self.assertEqual((stats.max_hp, stats.attack, stats.defense, stats.crit_bps, stats.power_score),
                         (1198, 71, 35, 600, 634))

    async def test_starter_granted_once_and_current_hp_is_effective(self):
        self.assertTrue(await initialize_phase3_profile(self.db_path, "1", "2"))
        self.assertFalse(await initialize_phase3_profile(self.db_path, "1", "2"))
        stats = await get_effective_stats(self.db_path, "1", "2")
        async with aiosqlite.connect(self.db_path) as db:
            current_hp = (await (await db.execute(
                "SELECT currentHp FROM RpgProfile WHERE guildId='1' AND userId='2'"
            )).fetchone())[0]
            equipment_count = (await (await db.execute(
                "SELECT COUNT(*) FROM RpgEquipmentInstance WHERE guildId='1' AND ownerId='2'"
            )).fetchone())[0]
        self.assertEqual(current_hp, 1198)
        self.assertEqual(stats.max_hp, 1198)
        self.assertEqual(equipment_count, 3)

    def test_additive_percentage_and_critical_cap(self):
        stats = calculate_effective_stats(
            base_hp=1000, base_attack=50, base_defense=25, base_crit_bps=4900,
            equipped=(), active_pet_id="pet_gale_fox",
        )
        self.assertEqual(stats.crit_bps, 5000)

    def test_pet_passive_scales_to_120_percent_at_level_50(self):
        level_one = calculate_effective_stats(
            base_hp=1000, base_attack=50, base_defense=25, base_crit_bps=500,
            active_pet_id="pet_moss_slime", active_pet_level=1,
        )
        level_fifty = calculate_effective_stats(
            base_hp=1000, base_attack=50, base_defense=25, base_crit_bps=500,
            active_pet_id="pet_moss_slime", active_pet_level=50,
        )
        self.assertEqual(level_one.max_hp, 1040)
        self.assertEqual(level_fifty.max_hp, 1048)

    def test_level_100_discards_xp(self):
        self.assertEqual(apply_player_xp(100, 25, 100), (100, 0, 125))

    def test_catalog_hash_is_stable(self):
        self.assertEqual(validate_catalog(), catalog_hash())

    def test_context_multiplier_applies_once_after_reduction_and_crit(self):
        normal = final_damage(
            attack=100, attacker_level=20, defender_defense=100,
            variance_bps=10_000, critical=True, context_damage_bps=0,
        )
        boosted = final_damage(
            attack=100, attacker_level=20, defender_defense=100,
            variance_bps=10_000, critical=True, context_damage_bps=1_000,
        )
        self.assertEqual(boosted, normal * 11_000 // 10_000)


if __name__ == "__main__":
    unittest.main()
