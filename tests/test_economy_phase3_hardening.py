import json
import os
import tempfile
import unittest
import asyncio
from unittest.mock import AsyncMock, patch

import aiosqlite

from economy.database import configure_connection, ensure_system_accounts, initialize_database
from economy.catalog import (
    CatalogValidationError, EQUIPMENT, HUNT_DROPS, roll_drops, validate_catalog,
)
from economy.equipment import initialize_phase3_profile
from economy.bosses import reserve_boss_attack, settle_boss, start_boss
from economy.equipment import EffectiveStats
from economy.operations import record_operation_retry, reserve_operation
from economy.phase3_migrations import quarantine_legacy_assets
from economy.phase3_schema import migrate_phase3_schema


class Phase3HardeningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = handle.name
        handle.close()
        await initialize_database(self.db_path)
        await migrate_phase3_schema(self.db_path)

    async def asyncTearDown(self):
        os.unlink(self.db_path)

    async def test_outcome_result_and_transition_triggers(self):
        operation_id, _, _, _ = await reserve_operation(
            self.db_path, guild_id="1", user_id="2", operation_type="HUNT",
            reservation_key="hunt:1:2", source_resource_id="green_forest",
            outcome={"roll": 7, "reward": 10},
        )
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            with self.assertRaises(aiosqlite.IntegrityError):
                await db.execute(
                    "UPDATE RpgOperation SET outcomeJson='{}' WHERE operationId=?", (operation_id,),
                )
            await db.rollback()
        self.assertTrue(await record_operation_retry(self.db_path, operation_id, error_code="retry"))
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                "UPDATE RpgOperation SET status='AWAITING_FUNDS',updatedAt=updatedAt "
                "WHERE operationId=?", (operation_id,),
            )
            row = await (await db.execute(
                "SELECT reservationKey,resultJson,retryCount FROM RpgOperation WHERE operationId=?",
                (operation_id,),
            )).fetchone()
            self.assertEqual(row[0], "hunt:1:2")
            self.assertIsNone(row[1])
            self.assertEqual(row[2], 1)
            await db.execute(
                "UPDATE RpgOperation SET status='COMMITTED',reservationKey=NULL,resultJson=? "
                "WHERE operationId=?", (json.dumps({"ok": True}), operation_id),
            )
            await db.commit()
            with self.assertRaises(aiosqlite.IntegrityError):
                await db.execute(
                    "UPDATE RpgOperation SET resultJson=? WHERE operationId=?",
                    (json.dumps({"ok": False}), operation_id),
                )

    async def test_operation_specific_outcome_update_and_delete_are_rejected(self):
        operation_id, _, _, _ = await reserve_operation(
            self.db_path, guild_id="1", user_id="2", operation_type="HUNT",
            reservation_key="hunt:1:2", source_resource_id="green_forest",
            outcome={"xp": 20, "pet_instance_id": None},
        )
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            await db.execute(
                "INSERT INTO RpgHuntRun(operationId,areaId,playerXp,activePetInstanceId) "
                "VALUES (?,'green_forest',20,NULL)", (operation_id,),
            )
            await db.commit()
            with self.assertRaises(aiosqlite.IntegrityError):
                await db.execute(
                    "UPDATE RpgHuntRun SET playerXp=21 WHERE operationId=?", (operation_id,),
                )
            await db.rollback()
            with self.assertRaises(aiosqlite.IntegrityError):
                await db.execute("DELETE FROM RpgHuntRun WHERE operationId=?", (operation_id,))

    async def test_starter_marker_survives_cleared_slots(self):
        self.assertTrue(await initialize_phase3_profile(self.db_path, "1", "2"))
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE RpgProfile SET activeWeaponInstanceId=NULL,activePetInstanceId=NULL "
                "WHERE guildId='1' AND userId='2'"
            )
            await db.commit()
            before = (await (await db.execute(
                "SELECT COUNT(*) FROM RpgEquipmentInstance WHERE guildId='1' AND ownerId='2'"
            )).fetchone())[0]
        self.assertFalse(await initialize_phase3_profile(self.db_path, "1", "2"))
        async with aiosqlite.connect(self.db_path) as db:
            after = (await (await db.execute(
                "SELECT COUNT(*) FROM RpgEquipmentInstance WHERE guildId='1' AND ownerId='2'"
            )).fetchone())[0]
        self.assertEqual(before, after)

    async def test_starter_concurrency_creates_one_package(self):
        results = await asyncio.gather(*(
            initialize_phase3_profile(self.db_path, "5", "6") for _ in range(4)
        ))
        self.assertEqual(results.count(True), 1)
        async with aiosqlite.connect(self.db_path) as db:
            equipment = (await (await db.execute(
                "SELECT COUNT(*) FROM RpgEquipmentInstance WHERE guildId='5' AND ownerId='6'"
            )).fetchone())[0]
            pets = (await (await db.execute(
                "SELECT COUNT(*) FROM RpgPetInstance WHERE guildId='5' AND ownerId='6'"
            )).fetchone())[0]
            grants = (await (await db.execute(
                "SELECT COUNT(*) FROM RpgStarterGrant WHERE guildId='5' AND userId='6'"
            )).fetchone())[0]
        self.assertEqual((equipment, pets, grants), (3, 1, 1))

    async def test_completed_migration_checksum_mismatch_fails_closed(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE EconomySchemaMigration SET checksum='mismatch' WHERE version=301"
            )
            await db.commit()
        with self.assertRaises(ValueError):
            await migrate_phase3_schema(self.db_path)

    async def test_legacy_quarantine_is_replay_safe_and_source_unchanged(self):
        source = {"9": {"items": {"legacy_sword": 2}, "pet": "slime"}}
        source_text = json.dumps(source, separators=(",", ":"))
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("CREATE TABLE json_store(filename TEXT PRIMARY KEY,content TEXT)")
            await db.execute("INSERT INTO json_store VALUES ('users.json',?)", (source_text,))
            await db.commit()
        first = await quarantine_legacy_assets(self.db_path, guild_id="1")
        second = await quarantine_legacy_assets(self.db_path, guild_id="1")
        self.assertEqual(first["quarantined_items"], 1)
        self.assertEqual(first["quarantined_pets"], 1)
        self.assertEqual(second["replayed_records"], 2)
        async with aiosqlite.connect(self.db_path) as db:
            stored = (await (await db.execute(
                "SELECT content FROM json_store WHERE filename='users.json'"
            )).fetchone())[0]
            rows = await (await db.execute(
                "SELECT bindingStatus FROM RpgLegacyAsset ORDER BY sourceType"
            )).fetchall()
        self.assertEqual(stored, source_text)
        self.assertEqual([row[0] for row in rows], ["LEGACY_BOUND", "LEGACY_BOUND"])

    async def test_profile_rebuild_rolls_back_at_each_checkpoint(self):
        for stage in ("after_create", "after_copy", "after_validate", "after_drop", "after_rename"):
            handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            path = handle.name
            handle.close()
            try:
                await initialize_database(path)
                async with aiosqlite.connect(path) as db:
                    await db.execute(
                        "INSERT INTO RpgProfile "
                        "(guildId,userId,level,xp,maxHp,currentHp,attack,defense,critBps,energy,"
                        "energyUpdatedAt,version,createdAt,updatedAt) "
                        "VALUES ('1','2',10,5,1000,1000,50,25,500,100,'x',0,'x','x')"
                    )
                    await db.commit()
                with self.assertRaises(RuntimeError):
                    await migrate_phase3_schema(path, _failure_stage=stage)
                async with aiosqlite.connect(path) as db:
                    row = await (await db.execute(
                        "SELECT level,xp,currentHp FROM RpgProfile WHERE guildId='1' AND userId='2'"
                    )).fetchone()
                    leaked = await (await db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='RpgProfile_new'"
                    )).fetchone()
                self.assertEqual(row, (10, 5, 1000))
                self.assertIsNone(leaked)
            finally:
                os.unlink(path)

    async def test_additive_migration_extends_partial_canonical_tables(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        path = handle.name
        handle.close()
        try:
            await initialize_database(path)
            async with aiosqlite.connect(path) as db:
                await db.execute("CREATE TABLE RpgStarterGrant(guildId TEXT,userId TEXT)")
                await db.execute("INSERT INTO RpgStarterGrant VALUES ('1','2')")
                await db.execute(
                    "CREATE TABLE RpgLegacyAsset(guildId TEXT,userId TEXT,sourceType TEXT,sourceKey TEXT)"
                )
                await db.commit()
            await migrate_phase3_schema(path)
            async with aiosqlite.connect(path) as db:
                starter_columns = {row[1] for row in await (await db.execute(
                    "PRAGMA table_info(RpgStarterGrant)"
                )).fetchall()}
                legacy_columns = {row[1] for row in await (await db.execute(
                    "PRAGMA table_info(RpgLegacyAsset)"
                )).fetchall()}
                preserved = await (await db.execute(
                    "SELECT guildId,userId FROM RpgStarterGrant"
                )).fetchone()
            self.assertIn("recoveryReviewJson", starter_columns)
            self.assertIn("sourceHash", legacy_columns)
            self.assertEqual(preserved, ("1", "2"))
        finally:
            os.unlink(path)

    def test_catalog_validation_raises_explicit_exception(self):
        original = EQUIPMENT["eq_wanderer_blade"]["slot"]
        try:
            EQUIPMENT["eq_wanderer_blade"]["slot"] = "INVALID"
            with self.assertRaises(CatalogValidationError):
                validate_catalog()
        finally:
            EQUIPMENT["eq_wanderer_blade"]["slot"] = original

    def test_hunt_drop_rng_is_injectable_and_highest_rarity_first(self):
        dropped = roll_drops(HUNT_DROPS["eternal_ruins"], randbelow=lambda _: 0)
        self.assertEqual(EQUIPMENT[dropped["equipment"]]["rarity"], "EPIC")
        self.assertIn("egg_pet_rare", dropped["stacks"])
        empty = roll_drops(HUNT_DROPS["eternal_ruins"], randbelow=lambda _: 9_999)
        self.assertEqual(empty, {"stacks": [], "equipment": None})

    async def test_boss_damage_uses_current_player_level(self):
        await initialize_phase3_profile(self.db_path, "1", "2")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE RpgProfile SET level=37 WHERE guildId='1' AND userId='2'")
            await db.commit()
        await start_boss(
            self.db_path, guild_id="1", tier="normal", start_key="test", authorized=True,
        )
        captured = {}

        def damage(**kwargs):
            captured.update(kwargs)
            return 123

        stats = EffectiveStats(1198, 71, 35, 600, 634, 0, 0, 0)
        with patch("economy.bosses.get_effective_stats", new=AsyncMock(return_value=stats)), \
                patch("economy.bosses.final_damage", side_effect=damage), \
                patch("economy.bosses.secrets.randbelow", return_value=0):
            await reserve_boss_attack(self.db_path, guild_id="1", user_id="2")
        self.assertEqual(captured["attacker_level"], 37)

    async def test_boss_awaiting_funds_reuses_immutable_plan(self):
        raid = await start_boss(
            self.db_path, guild_id="1", tier="normal", start_key="fund", authorized=True,
        )
        plan = {"tier": "NORMAL", "minimum_damage": 100, "no_valid_participants": False,
                "participants": [{"user_id": "2", "damage": 100, "rank": 1,
                                  "etm": 100, "drop": {"stacks": [], "equipment": None},
                                  "equipment_instance_id": None, "pet_instance_id": None,
                                  "pet_xp": 100}]}
        raw_plan = json.dumps(plan, sort_keys=True)
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            await db.execute(
                "UPDATE RpgBossRaid SET currentHp=0,status='DEFEATED',rewardPlanJson=? WHERE raidId=?",
                (raw_plan, raid["raid_id"]),
            )
            await db.commit()
        blocked = await settle_boss(
            self.db_path, guild_id="1", raid_id=raid["raid_id"], authorized=True,
        )
        self.assertEqual(blocked.code, "awaiting_funds")
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            await ensure_system_accounts(db, "1", "2026-01-01T00:00:00+00:00")
            await db.execute(
                "UPDATE EconomySystemAccount SET balance=100 WHERE guildId='1' "
                "AND accountCode='ETM_BOSS_DUNGEON'"
            )
            await db.commit()
        settled = await settle_boss(
            self.db_path, guild_id="1", raid_id=raid["raid_id"], authorized=True,
        )
        replayed = await settle_boss(
            self.db_path, guild_id="1", raid_id=raid["raid_id"], authorized=True,
        )
        self.assertTrue(settled.ok)
        self.assertTrue(replayed.ok)
        self.assertTrue(replayed.replayed)
        async with aiosqlite.connect(self.db_path) as db:
            persisted = (await (await db.execute(
                "SELECT rewardPlanJson,status FROM RpgBossRaid WHERE raidId=?", (raid["raid_id"],)
            )).fetchone())
        self.assertEqual(persisted, (raw_plan, "SETTLED"))


if __name__ == "__main__":
    unittest.main()
