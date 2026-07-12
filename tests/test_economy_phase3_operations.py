import asyncio
import os
import tempfile
import unittest

import aiosqlite

from economy.database import initialize_database
from economy.equipment import initialize_phase3_profile
from economy.inventory import adjust_stack
from economy.open_items import reserve_open_item, settle_open_item
from economy.operations import reserve_operation
from economy.phase3_schema import migrate_phase3_schema
from economy.time_policy import utc_iso


class Phase3OperationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = handle.name
        handle.close()
        await initialize_database(self.db_path)
        await migrate_phase3_schema(self.db_path)
        await initialize_phase3_profile(self.db_path, "1", "2")

    async def asyncTearDown(self):
        os.unlink(self.db_path)

    async def test_different_invocations_reuse_one_reservation(self):
        async def reserve(number):
            return await reserve_operation(
                self.db_path, guild_id="1", user_id="2", operation_type="HUNT",
                reservation_key="hunt:1:2", source_resource_id="green_forest",
                outcome={"roll": number},
            )
        first, second = await asyncio.gather(reserve(1), reserve(2))
        self.assertEqual(first[0], second[0])
        async with aiosqlite.connect(self.db_path) as db:
            count = (await (await db.execute(
                "SELECT COUNT(*) FROM RpgOperation WHERE reservationKey='hunt:1:2'"
            )).fetchone())[0]
        self.assertEqual(count, 1)

    async def test_epic_chest_retry_does_not_reroll_or_duplicate(self):
        async with aiosqlite.connect(self.db_path) as db:
            await adjust_stack(db, "1", "2", "item_epic_chest", 1, utc_iso())
            await db.commit()
        operation_id, outcome, _ = await reserve_open_item(
            self.db_path, guild_id="1", user_id="2", item_id="item_epic_chest",
        )
        replay_id, replay_outcome, replayed = await reserve_open_item(
            self.db_path, guild_id="1", user_id="2", item_id="item_epic_chest",
        )
        self.assertTrue(replayed)
        self.assertEqual((operation_id, outcome), (replay_id, replay_outcome))
        result, was_replayed = await settle_open_item(
            self.db_path, guild_id="1", user_id="2", operation_id=operation_id,
        )
        second, was_replayed_again = await settle_open_item(
            self.db_path, guild_id="1", user_id="2", operation_id=operation_id,
        )
        self.assertFalse(was_replayed)
        self.assertTrue(was_replayed_again)
        self.assertEqual(result, second)
        async with aiosqlite.connect(self.db_path) as db:
            count = (await (await db.execute(
                "SELECT COUNT(*) FROM RpgEquipmentInstance WHERE acquiredSource='EPIC_CHEST'"
            )).fetchone())[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
