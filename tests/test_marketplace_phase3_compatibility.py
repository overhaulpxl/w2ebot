import json
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

import aiosqlite

from economy.activity import append_activity_event
from economy.adventures import reserve_dungeon, reserve_hunt, settle_dungeon, settle_hunt
from economy.bosses import settle_boss, start_boss
from economy.catalog import RPG_PHASE3_CATALOG_VERSION
from economy.crafting import reserve_craft, settle_craft
from economy.database import configure_connection, ensure_system_accounts, initialize_database
from economy.enhancement import reserve_enhancement, settle_enhancement
from economy.equipment import initialize_phase3_profile
from economy.inventory import adjust_stack, inventory_quantity
from economy.open_items import reserve_open_item, settle_open_item
from economy.operations import reserve_operation
from economy.phase3_migrations import apply_phase3_staging
from economy.phase3_recovery import recover_phase3_operations
from economy.phase4_migrations import apply_phase4_staging
from economy.quests import claim_quest, ensure_quest_assignments, quest_period
from economy.time_policy import utc_iso


class Phase3AfterMarketplaceMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = handle.name
        handle.close()
        self.production_path = self.db_path + ".production"
        await initialize_database(self.db_path)
        await apply_phase3_staging(self.db_path, production_db=self.production_path)
        await initialize_phase3_profile(self.db_path, "1", "2")
        await apply_phase4_staging(self.db_path, production_db=self.production_path)
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            await ensure_system_accounts(db, "1", utc_iso())
            await db.execute(
                "INSERT INTO EconomyWallet "
                "(guildId,userId,etmBalance,ecyBalance,version,createdAt,updatedAt) "
                "VALUES ('1','2',1000000000,0,0,?,?)",
                (utc_iso(), utc_iso()),
            )
            await db.execute(
                "UPDATE EconomySystemAccount SET balance=10000000 "
                "WHERE guildId='1' AND accountCode='ETM_BOSS_DUNGEON'"
            )
            await db.execute(
                "UPDATE RpgProfile SET level=50,energy=100 WHERE guildId='1' AND userId='2'"
            )
            await db.commit()

    async def asyncTearDown(self):
        async with aiosqlite.connect(self.db_path) as db:
            self.assertEqual((await (await db.execute("PRAGMA integrity_check")).fetchone())[0], "ok")
            self.assertEqual(await (await db.execute("PRAGMA foreign_key_check")).fetchall(), [])
        os.unlink(self.db_path)

    async def _active_weapon(self):
        async with aiosqlite.connect(self.db_path) as db:
            return (await (await db.execute(
                "SELECT activeWeaponInstanceId FROM RpgProfile WHERE guildId='1' AND userId='2'"
            )).fetchone())[0]

    async def test_grant_debit_enhancement_and_crafting_use_migrated_identity(self):
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            await adjust_stack(
                db, "1", "2", "mat_iron_shard", 25, utc_iso(),
                catalog_version=RPG_PHASE3_CATALOG_VERSION,
            )
            await adjust_stack(
                db, "1", "2", "mat_iron_shard", -5, utc_iso(),
                catalog_version=RPG_PHASE3_CATALOG_VERSION,
            )
            await db.commit()
            self.assertEqual(await inventory_quantity(
                db, "1", "2", "mat_iron_shard",
                catalog_version=RPG_PHASE3_CATALOG_VERSION,
            ), 20)

        weapon_id = await self._active_weapon()
        enhancement = await reserve_enhancement(
            self.db_path, guild_id="1", user_id="2", equipment_instance_id=weapon_id,
        )
        enhanced = await settle_enhancement(
            self.db_path, guild_id="1", user_id="2", operation_id=enhancement[0],
        )
        self.assertTrue(enhanced.ok)

        craft = await reserve_craft(
            self.db_path, guild_id="1", user_id="2", base_equipment_instance_id=weapon_id,
        )
        crafted = await settle_craft(
            self.db_path, guild_id="1", user_id="2", operation_id=craft[0],
        )
        self.assertTrue(crafted.ok)
        async with aiosqlite.connect(self.db_path) as db:
            row = await (await db.execute(
                "SELECT catalogVersion,status FROM RpgInventoryStack "
                "WHERE guildId='1' AND userId='2' AND itemId='mat_iron_shard'"
            )).fetchone()
        self.assertEqual(row, (RPG_PHASE3_CATALOG_VERSION, "ACTIVE"))

    async def test_open_hunt_dungeon_boss_quest_and_recovery_after_migration(self):
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            await adjust_stack(
                db, "1", "2", "item_epic_chest", 1, utc_iso(),
                catalog_version=RPG_PHASE3_CATALOG_VERSION,
            )
            await db.commit()
        open_operation, _outcome, _replayed = await reserve_open_item(
            self.db_path, guild_id="1", user_id="2", item_id="item_epic_chest",
        )
        recovered = await recover_phase3_operations(self.db_path)
        self.assertGreaterEqual(recovered["committed"], 1)
        async with aiosqlite.connect(self.db_path) as db:
            self.assertEqual((await (await db.execute(
                "SELECT status FROM RpgOperation WHERE operationId=?", (open_operation,)
            )).fetchone())[0], "COMMITTED")

        hunt = await reserve_hunt(
            self.db_path, guild_id="1", user_id="2", area_id="green_forest",
        )
        self.assertTrue((await settle_hunt(
            self.db_path, guild_id="1", user_id="2", operation_id=hunt[0],
        )).ok)

        dungeon = await reserve_dungeon(
            self.db_path, guild_id="1", user_id="2", dungeon_id="forgotten_crypt",
        )
        self.assertTrue((await settle_dungeon(
            self.db_path, guild_id="1", user_id="2", operation_id=dungeon[0],
        )).ok)

        raid = await start_boss(
            self.db_path, guild_id="1", tier="normal", start_key="compat-boss", authorized=True,
        )
        plan = {
            "tier": "NORMAL", "minimum_damage": 100, "participants": [],
            "no_valid_participants": True, "catalog_version": RPG_PHASE3_CATALOG_VERSION,
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE RpgBossRaid SET status='DEFEATED',currentHp=0,rewardPlanJson=?,updatedAt=? "
                "WHERE raidId=?",
                (json.dumps(plan, sort_keys=True), utc_iso(), raid["raid_id"]),
            )
            await db.commit()
        self.assertTrue((await settle_boss(
            self.db_path, guild_id="1", raid_id=raid["raid_id"], authorized=True,
        )).ok)

        await ensure_quest_assignments(self.db_path, "1", "2")
        _, period_start, _ = quest_period("DAILY")
        occurred = period_start.replace(microsecond=0)
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            for event_type, count in (("HUNT_COMPLETED", 3), ("WORK_SUCCESS", 2), ("BOSS_ATTACK", 3)):
                for index in range(count):
                    await append_activity_event(
                        db, guild_id="1", user_id="2", event_type=event_type,
                        event_key=f"compat:{event_type}:{index}", points=0,
                        metric_value=100 if event_type == "BOSS_ATTACK" else 1,
                        occurred_at=occurred,
                    )
            await db.commit()
        claim = await claim_quest(
            self.db_path, guild_id="1", user_id="2", quest_type="DAILY",
        )
        self.assertTrue(claim.ok)
        async with aiosqlite.connect(self.db_path) as db:
            ticket = await inventory_quantity(
                db, "1", "2", "item_dungeon_ticket",
                catalog_version=RPG_PHASE3_CATALOG_VERSION,
            )
        self.assertEqual(ticket, 1)

    async def test_all_openables_and_material_enhancement_keep_exact_migrated_identity(self):
        openables = (
            "egg_pet_common", "egg_pet_uncommon", "egg_pet_rare", "egg_pet_epic",
            "egg_pet_legendary", "egg_pet_eternal", "item_epic_chest",
        )
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            for item_id in openables:
                await adjust_stack(
                    db, "1", "2", item_id, 1, utc_iso(),
                    catalog_version=RPG_PHASE3_CATALOG_VERSION,
                )
            await db.commit()
        for item_id in openables:
            operation_id, _outcome, _ = await reserve_open_item(
                self.db_path, guild_id="1", user_id="2", item_id=item_id,
            )
            _result, replayed = await settle_open_item(
                self.db_path, guild_id="1", user_id="2", operation_id=operation_id,
            )
            self.assertFalse(replayed)
            async with aiosqlite.connect(self.db_path) as db:
                self.assertEqual(await inventory_quantity(
                    db, "1", "2", item_id, catalog_version=RPG_PHASE3_CATALOG_VERSION,
                ), 0)

        weapon_id = await self._active_weapon()
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            await db.execute(
                "UPDATE RpgEquipmentInstance SET enhancementLevel=5 WHERE equipmentInstanceId=?",
                (weapon_id,),
            )
            await adjust_stack(
                db, "1", "2", "mat_iron_shard", 10, utc_iso(),
                catalog_version=RPG_PHASE3_CATALOG_VERSION,
            )
            await db.commit()
        operation = await reserve_enhancement(
            self.db_path, guild_id="1", user_id="2", equipment_instance_id=weapon_id,
        )
        self.assertTrue((await settle_enhancement(
            self.db_path, guild_id="1", user_id="2", operation_id=operation[0],
        )).ok)
        async with aiosqlite.connect(self.db_path) as db:
            remaining = await inventory_quantity(
                db, "1", "2", "mat_iron_shard", catalog_version=RPG_PHASE3_CATALOG_VERSION,
            )
        self.assertLess(remaining, 10)

    async def test_deterministic_hunt_and_dungeon_drops_do_not_merge_binding_or_version(self):
        with patch("economy.catalog.secrets.randbelow", return_value=0):
            hunt = await reserve_hunt(
                self.db_path, guild_id="1", user_id="2", area_id="green_forest",
            )
            self.assertTrue((await settle_hunt(
                self.db_path, guild_id="1", user_id="2", operation_id=hunt[0],
            )).ok)
            dungeon = await reserve_dungeon(
                self.db_path, guild_id="1", user_id="2", dungeon_id="forgotten_crypt",
            )
            self.assertTrue((await settle_dungeon(
                self.db_path, guild_id="1", user_id="2", operation_id=dungeon[0],
            )).ok)
        async with aiosqlite.connect(self.db_path) as db:
            rows = await (await db.execute(
                "SELECT DISTINCT catalogVersion,bindingStatus,status FROM RpgInventoryStack "
                "WHERE guildId='1' AND userId='2'"
            )).fetchall()
        self.assertTrue(rows)
        self.assertTrue(all(row[0] == RPG_PHASE3_CATALOG_VERSION for row in rows))
        self.assertTrue(all(row[1] == "UNBOUND" and row[2] == "ACTIVE" for row in rows))

    async def test_valid_boss_weekly_reward_and_eternal_craft_use_migrated_stacks(self):
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            pet_id = (await (await db.execute(
                "SELECT activePetInstanceId FROM RpgProfile WHERE guildId='1' AND userId='2'"
            )).fetchone())[0]
        raid = await start_boss(
            self.db_path, guild_id="1", tier="normal", start_key="compat-valid-boss",
            authorized=True,
        )
        plan = {
            "tier": "NORMAL", "minimum_damage": 100, "no_valid_participants": False,
            "catalog_version": RPG_PHASE3_CATALOG_VERSION,
            "participants": [{
                "user_id": "2", "damage": 1_000, "rank": 1, "etm": 100,
                "drop": {"stacks": ["mat_iron_shard"], "equipment": None},
                "equipment_instance_id": None, "pet_instance_id": pet_id, "pet_xp": 100,
            }],
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE RpgBossRaid SET status='DEFEATED',currentHp=0,rewardPlanJson=?,updatedAt=? "
                "WHERE raidId=?",
                (json.dumps(plan, sort_keys=True), utc_iso(), raid["raid_id"]),
            )
            await db.commit()
        self.assertTrue((await settle_boss(
            self.db_path, guild_id="1", raid_id=raid["raid_id"], authorized=True,
        )).ok)
        async with aiosqlite.connect(self.db_path) as db:
            self.assertEqual(await inventory_quantity(
                db, "1", "2", "mat_iron_shard", catalog_version=RPG_PHASE3_CATALOG_VERSION,
            ), 1)

        await ensure_quest_assignments(self.db_path, "1", "2")
        _, weekly_start, _ = quest_period("WEEKLY")
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            for index in range(25):
                await append_activity_event(
                    db, guild_id="1", user_id="2", event_type="HUNT_COMPLETED",
                    event_key=f"compat-weekly-hunt:{index}", points=0, metric_value=1,
                    occurred_at=weekly_start,
                )
            for index in range(5):
                await append_activity_event(
                    db, guild_id="1", user_id="2", event_type="DUNGEON_COMPLETED",
                    event_key=f"compat-weekly-dungeon:{index}", points=3, metric_value=1,
                    occurred_at=weekly_start,
                )
            await append_activity_event(
                db, guild_id="1", user_id="2", event_type="BOSS_ATTACK",
                event_key="compat-weekly-boss", points=0, metric_value=30_000,
                occurred_at=weekly_start,
            )
            await db.commit()
        self.assertTrue((await claim_quest(
            self.db_path, guild_id="1", user_id="2", quest_type="WEEKLY",
        )).ok)
        async with aiosqlite.connect(self.db_path) as db:
            self.assertEqual(await inventory_quantity(
                db, "1", "2", "item_epic_chest", catalog_version=RPG_PHASE3_CATALOG_VERSION,
            ), 1)

        legendary_id = str(uuid.uuid4())
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            timestamp = utc_iso()
            await db.execute(
                "INSERT INTO RpgEquipmentInstance "
                "(equipmentInstanceId,guildId,ownerId,itemId,catalogVersion,slot,enhancementLevel,pityBps,"
                "bindingStatus,status,acquiredSource,createdAt,updatedAt) "
                "VALUES (?,'1','2','eq_void_reaver',?,'WEAPON',0,0,'BOUND_ON_EQUIP','OWNED','TEST',?,?)",
                (legendary_id, RPG_PHASE3_CATALOG_VERSION, timestamp, timestamp),
            )
            for item_id, quantity in (
                ("mat_eternal_fragment", 50), ("mat_dragon_core", 20),
                ("bp_eternal_weapon", 1),
            ):
                await adjust_stack(
                    db, "1", "2", item_id, quantity, timestamp,
                    catalog_version=RPG_PHASE3_CATALOG_VERSION,
                )
            await db.commit()
        craft = await reserve_craft(
            self.db_path, guild_id="1", user_id="2",
            base_equipment_instance_id=legendary_id,
        )
        self.assertTrue((await settle_craft(
            self.db_path, guild_id="1", user_id="2", operation_id=craft[0],
        )).ok)
        async with aiosqlite.connect(self.db_path) as db:
            for item_id in ("mat_eternal_fragment", "mat_dragon_core", "bp_eternal_weapon"):
                self.assertEqual(await inventory_quantity(
                    db, "1", "2", item_id, catalog_version=RPG_PHASE3_CATALOG_VERSION,
                ), 0)

    async def test_restart_recovery_reuses_phase4_stack_identity_for_all_supported_operations(self):
        timestamp = utc_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            await adjust_stack(
                db, "1", "2", "mat_iron_shard", 20, timestamp,
                catalog_version=RPG_PHASE3_CATALOG_VERSION,
            )
            await adjust_stack(
                db, "1", "2", "item_epic_chest", 1, timestamp,
                catalog_version=RPG_PHASE3_CATALOG_VERSION,
            )
            await db.commit()
        weapon_id = await self._active_weapon()
        craft = await reserve_craft(
            self.db_path, guild_id="1", user_id="2", base_equipment_instance_id=weapon_id,
        )
        opened = await reserve_open_item(
            self.db_path, guild_id="1", user_id="2", item_id="item_epic_chest",
        )
        hunt = await reserve_hunt(
            self.db_path, guild_id="1", user_id="2", area_id="green_forest",
        )
        dungeon = await reserve_dungeon(
            self.db_path, guild_id="1", user_id="2", dungeon_id="forgotten_crypt",
        )

        await ensure_quest_assignments(self.db_path, "1", "2")
        period_key, period_start, _ = quest_period("DAILY")
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            for event_type, count in (("HUNT_COMPLETED", 3), ("WORK_SUCCESS", 2), ("BOSS_ATTACK", 3)):
                for index in range(count):
                    await append_activity_event(
                        db, guild_id="1", user_id="2", event_type=event_type,
                        event_key=f"restart:{event_type}:{index}", points=0,
                        metric_value=100 if event_type == "BOSS_ATTACK" else 1,
                        occurred_at=period_start,
                    )
            await db.commit()
        quest_operation = await reserve_operation(
            self.db_path, guild_id="1", user_id="2", operation_type="QUEST_CLAIM",
            reservation_key=f"quest-claim:1:2:DAILY:{period_key}",
            source_resource_id=f"DAILY:{period_key}",
            outcome={
                "quest_type": "DAILY", "period_key": period_key, "etm": 80_000,
                "xp": 150, "item_id": "item_dungeon_ticket",
                "catalog_version": RPG_PHASE3_CATALOG_VERSION,
            },
        )

        raid = await start_boss(
            self.db_path, guild_id="1", tier="normal", start_key="compat-recovery-boss",
            authorized=True,
        )
        plan = {
            "tier": "NORMAL", "minimum_damage": 100, "no_valid_participants": False,
            "catalog_version": RPG_PHASE3_CATALOG_VERSION,
            "participants": [{
                "user_id": "2", "damage": 1_000, "rank": 1, "etm": 100,
                "drop": {"stacks": ["mat_shadow_crystal"], "equipment": None},
                "equipment_instance_id": None, "pet_instance_id": None, "pet_xp": 100,
            }],
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE RpgBossRaid SET status='AWAITING_FUNDS',currentHp=0,rewardPlanJson=?,updatedAt=? "
                "WHERE raidId=?",
                (json.dumps(plan, sort_keys=True), timestamp, raid["raid_id"]),
            )
            await db.commit()

        recovered = await recover_phase3_operations(self.db_path)
        self.assertGreaterEqual(recovered["committed"], 5)
        self.assertEqual(recovered["boss_settled"], 1)
        operation_ids = (craft[0], opened[0], hunt[0], dungeon[0], quest_operation[0])
        async with aiosqlite.connect(self.db_path) as db:
            placeholders = ",".join("?" for _ in operation_ids)
            statuses = await (await db.execute(
                f"SELECT operationId,status FROM RpgOperation WHERE operationId IN ({placeholders})",
                operation_ids,
            )).fetchall()
            boss_status_row = await (await db.execute(
                "SELECT status FROM RpgBossRaid WHERE raidId=?", (raid["raid_id"],)
            )).fetchone()
        self.assertEqual({row[1] for row in statuses}, {"COMMITTED"})
        self.assertEqual(boss_status_row[0], "SETTLED")


if __name__ == "__main__":
    unittest.main()
