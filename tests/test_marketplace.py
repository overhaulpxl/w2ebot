import sqlite3
import unittest
from unittest.mock import patch

import aiosqlite

from economy.constants import ECONOMY_MAX_AMOUNT, MARKETPLACE_MAX_PRICE_ETM
from economy.constants import RPG_PHASE3_CATALOG_VERSION
from economy.marketplace import (
    calculate_marketplace_amounts, cancel_listing, create_listing, create_report,
    get_listing_details, issue_internal_api_authorization, list_watchlist,
    MarketplaceAuthorizationContext, moderate_listing, set_marketplace_user_state, set_watch,
)
from economy.controls import set_feature_paused
from economy.phase4_schema import REQUIRED_INDEXES, REQUIRED_TABLES, REQUIRED_TRIGGERS, phase4_schema_capability
from tests.marketplace_test_utils import MarketplaceDatabaseMixin, NOW


class MarketplaceServiceTests(MarketplaceDatabaseMixin, unittest.IsolatedAsyncioTestCase):
    async def test_schema_objects_and_capability(self):
        async with aiosqlite.connect(self.db_path) as db:
            self.assertTrue(await phase4_schema_capability(db))
            objects = {}
            for kind in ("table", "index", "trigger"):
                rows = await (await db.execute("SELECT name FROM sqlite_master WHERE type=?", (kind,))).fetchall()
                objects[kind] = {row[0] for row in rows}
        self.assertTrue(REQUIRED_TABLES <= objects["table"])
        self.assertTrue(REQUIRED_INDEXES <= objects["index"])
        self.assertTrue(REQUIRED_TRIGGERS <= objects["trigger"])

    async def test_deferred_listing_escrow_references_reject_single_side_commit(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO MarketplaceListing "
                "(listingId,guildId,sellerId,assetType,equipmentInstanceId,stackItemId,"
                "catalogVersion,stackBindingStatus,originalQuantity,remainingQuantity,unitPriceEtm,"
                "totalListingValue,assetSnapshotJson,status,escrowId,idempotencyKey,createdAt) "
                "VALUES ('single-listing','1','10','EQUIPMENT','eq-missing',NULL,?,NULL,1,1,"
                "10000,10000,'{}','ACTIVE','missing-escrow','single-listing',?)",
                (RPG_PHASE3_CATALOG_VERSION, NOW),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.commit()
            connection.rollback()
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO MarketplaceEscrow "
                "(escrowId,listingId,guildId,authoritativeOwnerId,assetType,equipmentInstanceId,"
                "stackItemId,catalogVersion,stackBindingStatus,originalQuantity,remainingQuantity,"
                "assetSnapshotJson,status,createdAt,updatedAt) "
                "VALUES ('single-escrow','missing-listing','1','10','EQUIPMENT','eq-missing',NULL,"
                "?,NULL,1,1,'{}','HELD',?,?)",
                (RPG_PHASE3_CATALOG_VERSION, NOW, NOW),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.commit()
        finally:
            connection.rollback()
            connection.close()

    def test_checked_arithmetic_boundaries_and_bool_rejection(self):
        minimum = calculate_marketplace_amounts(10_000, 1)
        self.assertEqual(minimum["fee"], 500)
        self.assertEqual(minimum["proceeds"] + minimum["treasury"] + minimum["reserve"] + minimum["burn"], 10_000)
        maximum_quantity = ECONOMY_MAX_AMOUNT // MARKETPLACE_MAX_PRICE_ETM
        self.assertLessEqual(calculate_marketplace_amounts(MARKETPLACE_MAX_PRICE_ETM, maximum_quantity)["gross"], ECONOMY_MAX_AMOUNT)
        for price, quantity in ((True, 1), (10_000, True), (MARKETPLACE_MAX_PRICE_ETM, maximum_quantity + 1)):
            with self.assertRaises(ValueError):
                calculate_marketplace_amounts(price, quantity)

    async def test_sparse_user_state_listing_and_atomic_cancel(self):
        await self.add_equipment("eq-1", "10")
        created = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT", asset_id="eq-1",
            quantity=1, unit_price_etm=100_000, idempotency_key="listing-1", authorization=self.member_auth("10"),
        )
        self.assertTrue(created.ok)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM MarketplaceUserState"), 0)
        self.assertEqual(await self.scalar("SELECT status FROM RpgEquipmentInstance WHERE equipmentInstanceId='eq-1'"), "ESCROWED")
        returned = await cancel_listing(self.db_path, guild_id="1", listing_id=created.listing_id, authorization=self.member_auth("10"))
        self.assertTrue(returned.ok)
        self.assertEqual(await self.scalar("SELECT status FROM MarketplaceListing WHERE listingId=?", (created.listing_id,)), "RETURNED")
        self.assertEqual(await self.scalar("SELECT status FROM RpgEquipmentInstance WHERE equipmentInstanceId='eq-1'"), "OWNED")
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM MarketplaceReturn WHERE listingId=?", (created.listing_id,)), 1)

    async def test_mixed_stack_bindings_never_merge(self):
        await self.add_stack("10", quantity=5, binding="UNBOUND")
        await self.add_stack("10", quantity=7, binding="ACCOUNT_BOUND")
        valid = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="STACK", asset_id="mat_iron_shard",
            catalog_version=RPG_PHASE3_CATALOG_VERSION, binding_status="UNBOUND", quantity=3,
            unit_price_etm=10_000, idempotency_key="stack-valid", authorization=self.member_auth("10"),
        )
        self.assertTrue(valid.ok)
        invalid = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="STACK", asset_id="mat_iron_shard",
            catalog_version=RPG_PHASE3_CATALOG_VERSION, binding_status="ACCOUNT_BOUND", quantity=1,
            unit_price_etm=10_000, idempotency_key="stack-bound", authorization=self.member_auth("10"),
        )
        self.assertFalse(invalid.ok)
        self.assertEqual(await self.scalar(
            "SELECT quantity FROM RpgInventoryStack WHERE userId='10' AND itemId='mat_iron_shard' AND bindingStatus='ACCOUNT_BOUND'"
        ), 7)

    async def test_historical_catalog_version_is_preserved(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO RpgCatalogManifest VALUES ('historical-v1','hash-old',?, '{}')", (NOW,))
            await db.execute(
                "INSERT INTO RpgCatalogItem VALUES ('historical-v1','old_material','MATERIAL','Old Material','RARE',NULL,1,1,?)",
                ('{"item_id":"old_material","tradeable":true}',),
            )
            await db.commit()
        await self.add_stack("10", item_id="old_material", quantity=2, catalog_version="historical-v1")
        result = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="STACK", asset_id="old_material",
            catalog_version="historical-v1", quantity=2, unit_price_etm=25_000,
            idempotency_key="old-version", authorization=self.member_auth("10"),
        )
        self.assertTrue(result.ok)
        details = await get_listing_details(self.db_path, "1", result.listing_id)
        self.assertEqual(details["catalogVersion"], "historical-v1")

    async def test_escrowed_equipment_direct_mutation_is_rejected(self):
        await self.add_equipment("eq-lock", "10")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT", asset_id="eq-lock",
            quantity=1, unit_price_etm=100_000, idempotency_key="lock", authorization=self.member_auth("10"),
        )
        self.assertTrue(listing.ok)
        connection = sqlite3.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE RpgEquipmentInstance SET enhancementLevel=1 WHERE equipmentInstanceId='eq-lock'")
        finally:
            connection.rollback()
            connection.close()

    async def test_listing_identity_and_no_delete_triggers(self):
        await self.add_equipment("eq-trigger", "10")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT",
            asset_id="eq-trigger", quantity=1, unit_price_etm=100_000,
            idempotency_key="trigger-listing", authorization=self.member_auth("10"),
        )
        connection = sqlite3.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE MarketplaceListing SET unitPriceEtm=200000 WHERE listingId=?",
                    (listing.listing_id,),
                )
            connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM MarketplaceListing WHERE listingId=?", (listing.listing_id,)
                )
        finally:
            connection.rollback()
            connection.close()

    async def test_listing_quantity_cannot_diverge_from_escrow(self):
        await self.add_stack("10", quantity=3)
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="STACK",
            asset_id="mat_iron_shard", catalog_version=RPG_PHASE3_CATALOG_VERSION,
            quantity=3, unit_price_etm=10_000, idempotency_key="quantity-trigger", authorization=self.member_auth("10"),
        )
        connection = sqlite3.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE MarketplaceListing SET remainingQuantity=2,status='PARTIALLY_FILLED' "
                    "WHERE listingId=?", (listing.listing_id,),
                )
            connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE MarketplaceEscrow SET remainingQuantity=2,status='PARTIAL' "
                    "WHERE listingId=?", (listing.listing_id,),
                )
            connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE MarketplaceListing SET status='PAUSED',version=version+1 "
                    "WHERE listingId=?", (listing.listing_id,),
                )
        finally:
            connection.rollback()
            connection.close()

    async def test_listing_and_escrow_insertion_failures_roll_back_together(self):
        stages = ("after_listing_insert", "after_escrow_insert", "before_listing_commit")
        for index, stage in enumerate(stages):
            instance_id = f"eq-listing-failure-{index}"
            await self.add_equipment(instance_id, "10")
            with self.subTest(stage=stage), self.assertRaises(RuntimeError):
                await create_listing(
                    self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT",
                    asset_id=instance_id, quantity=1, unit_price_etm=100_000,
                    idempotency_key=f"listing-failure-{index}", failure_stage=stage, authorization=self.member_auth("10"),
                )
            self.assertEqual(await self.scalar(
                "SELECT COUNT(*) FROM MarketplaceListing WHERE idempotencyKey=?",
                (f"listing-failure-{index}",),
            ), 0)
            self.assertEqual(await self.scalar(
                "SELECT COUNT(*) FROM MarketplaceEscrow WHERE equipmentInstanceId=?",
                (instance_id,),
            ), 0)
            self.assertEqual(await self.scalar(
                "SELECT status FROM RpgEquipmentInstance WHERE equipmentInstanceId=?",
                (instance_id,),
            ), "OWNED")

    async def test_watch_report_and_user_state_rules(self):
        await self.add_equipment("eq-watch", "10")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT", asset_id="eq-watch",
            quantity=1, unit_price_etm=100_000, idempotency_key="watch-listing", authorization=self.member_auth("10"),
        )
        self.assertTrue((await set_watch(self.db_path, guild_id="1", user_id="20", listing_id=listing.listing_id, authorization=self.member_auth("20"))).ok)
        watch_replay = await set_watch(
            self.db_path, guild_id="1", user_id="20", listing_id=listing.listing_id, authorization=self.member_auth("20"),
        )
        self.assertTrue(watch_replay.ok and watch_replay.replayed)
        self.assertEqual(len(await list_watchlist(self.db_path, "1", "20")), 1)
        first = await create_report(self.db_path, guild_id="1", reporter_id="20", listing_id=listing.listing_id, category="PRICE", authorization=self.member_auth("20"))
        second = await create_report(self.db_path, guild_id="1", reporter_id="20", listing_id=listing.listing_id, category="PRICE", authorization=self.member_auth("20"))
        self.assertTrue(first.ok)
        self.assertTrue(second.ok and second.replayed)
        connection = sqlite3.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO MarketplaceReport "
                    "(reportId,guildId,listingId,reporterId,reasonCategory,sanitizedDetails,status,createdAt) "
                    "VALUES ('duplicate-report','1',?,'20','PRICE','','OPEN',?)",
                    (listing.listing_id, NOW),
                )
        finally:
            connection.rollback()
            connection.close()
        await set_marketplace_user_state(self.db_path, guild_id="1", user_id="10", status="FROZEN", authorization=self.staff_auth(), reason_code="test")
        blocked = await cancel_listing(self.db_path, guild_id="1", listing_id=listing.listing_id, authorization=self.member_auth("10"))
        self.assertFalse(blocked.ok)

    async def test_watch_limit_is_enforced_without_extra_row(self):
        listing_ids = []
        for index in range(2):
            instance_id = f"eq-watch-limit-{index}"
            await self.add_equipment(instance_id, "10")
            result = await create_listing(
                self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT",
                asset_id=instance_id, quantity=1, unit_price_etm=100_000,
                idempotency_key=f"watch-limit-listing-{index}", authorization=self.member_auth("10"),
            )
            listing_ids.append(result.listing_id)
        with patch("economy.marketplace.MARKETPLACE_MAX_WATCHES", 1):
            first = await set_watch(
                self.db_path, guild_id="1", user_id="20", listing_id=listing_ids[0], authorization=self.member_auth("20"),
            )
            second = await set_watch(
                self.db_path, guild_id="1", user_id="20", listing_id=listing_ids[1], authorization=self.member_auth("20"),
            )
        self.assertTrue(first.ok)
        self.assertFalse(second.ok)
        self.assertEqual(second.code, "watch_limit")
        self.assertEqual(await self.scalar(
            "SELECT COUNT(*) FROM MarketplaceWatch WHERE guildId='1' AND userId='20' AND active=1"
        ), 1)

    async def test_staff_return_uses_authoritative_escrow_owner(self):
        await self.add_equipment("eq-staff-return", "10")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT",
            asset_id="eq-staff-return", quantity=1, unit_price_etm=100_000,
            idempotency_key="staff-return-listing", authorization=self.member_auth("10"),
        )
        returned = await cancel_listing(
            self.db_path, guild_id="1", listing_id=listing.listing_id,
            authorization=self.staff_auth(), reason_code="audited_return",
        )
        self.assertTrue(returned.ok)
        self.assertEqual(await self.scalar(
            "SELECT recipientId FROM MarketplaceReturn WHERE listingId=?", (listing.listing_id,)
        ), "10")
        self.assertEqual(await self.scalar(
            "SELECT ownerId FROM RpgEquipmentInstance WHERE equipmentInstanceId='eq-staff-return'"
        ), "10")

    async def test_global_pause_blocks_entry_but_allows_seller_exit(self):
        await self.add_equipment("eq-pause-active", "10")
        await self.add_equipment("eq-pause-blocked", "10")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT",
            asset_id="eq-pause-active", quantity=1, unit_price_etm=100_000,
            idempotency_key="pause-active", authorization=self.member_auth("10"),
        )
        await set_feature_paused(
            self.db_path, guild_id="1", feature="marketplace", paused=True,
            actor_id="99", reason="test pause",
        )
        blocked_listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT",
            asset_id="eq-pause-blocked", quantity=1, unit_price_etm=100_000,
            idempotency_key="pause-blocked", authorization=self.member_auth("10"),
        )
        blocked_watch = await set_watch(
            self.db_path, guild_id="1", user_id="20", listing_id=listing.listing_id, authorization=self.member_auth("20"),
        )
        blocked_report = await create_report(
            self.db_path, guild_id="1", reporter_id="20", listing_id=listing.listing_id,
            category="PRICE", authorization=self.member_auth("20"),
        )
        returned = await cancel_listing(
            self.db_path, guild_id="1", listing_id=listing.listing_id, authorization=self.member_auth("10"),
        )
        self.assertFalse(blocked_listing.ok)
        self.assertFalse(blocked_watch.ok)
        self.assertFalse(blocked_report.ok)
        self.assertTrue(returned.ok)

    async def test_reviewed_listing_can_be_resumed_with_escrow_in_sync(self):
        await self.add_equipment("eq-review-resume", "10")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT",
            asset_id="eq-review-resume", quantity=1, unit_price_etm=100_000,
            idempotency_key="review-resume", authorization=self.member_auth("10"),
        )
        reviewed = await moderate_listing(
            self.db_path, guild_id="1", listing_id=listing.listing_id, authorization=self.staff_auth(),
            action="REVIEW", reason_code="manual_review",
        )
        resumed = await moderate_listing(
            self.db_path, guild_id="1", listing_id=listing.listing_id, authorization=self.staff_auth(),
            action="RESUME", reason_code="review_complete",
        )
        self.assertTrue(reviewed.ok and resumed.ok)
        self.assertEqual(await self.scalar(
            "SELECT status FROM MarketplaceListing WHERE listingId=?", (listing.listing_id,)
        ), "ACTIVE")
        self.assertEqual(await self.scalar(
            "SELECT status FROM MarketplaceEscrow WHERE listingId=?", (listing.listing_id,)
        ), "HELD")
        self.assertEqual(await self.scalar(
            "SELECT COUNT(*) FROM MarketplaceQuantityMutation WHERE listingId=? AND applied=1",
            (listing.listing_id,),
        ), 2)

    async def test_forged_staff_context_is_rejected_and_verified_contexts_succeed(self):
        await self.add_equipment("eq-forged", "10")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT",
            asset_id="eq-forged", quantity=1, unit_price_etm=100_000,
            idempotency_key="forged-listing", authorization=self.member_auth("10"),
        )
        forged = MarketplaceAuthorizationContext(
            "20", "1", "INTERNAL_API", True, True, True, NOW, "forged",
        )
        denied = await cancel_listing(
            self.db_path, guild_id="1", listing_id=listing.listing_id,
            authorization=forged, reason_code="forged",
        )
        self.assertFalse(denied.ok)
        self.assertEqual(denied.code, "unauthorized")
        returned = await cancel_listing(
            self.db_path, guild_id="1", listing_id=listing.listing_id,
            authorization=self.api_auth(), reason_code="audited_return",
        )
        self.assertTrue(returned.ok)
        self.assertEqual(await self.scalar(
            "SELECT authorizationSource FROM MarketplaceReturn WHERE listingId=?",
            (listing.listing_id,),
        ), "INTERNAL_API")
        self.assertEqual(await self.scalar(
            "SELECT recipientId FROM MarketplaceReturn WHERE listingId=?", (listing.listing_id,),
        ), "10")
        self.assertTrue((await set_marketplace_user_state(
            self.db_path, guild_id="1", user_id="30", status="RESTRICTED",
            authorization=self.staff_auth("98", owner=True), reason_code="owner_review",
        )).ok)
        self.assertTrue((await set_marketplace_user_state(
            self.db_path, guild_id="1", user_id="31", status="FROZEN",
            authorization=self.api_auth("api-state"), reason_code="api_review",
        )).ok)
        with self.assertRaises(PermissionError):
            issue_internal_api_authorization(
                actor_id="api", guild_id="1", request_id="invalid", verified_api_principal=False,
            )

    async def test_user_state_is_sparse_audited_versioned_and_not_deletable(self):
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM MarketplaceUserState"), 0)
        admin = self.staff_auth()
        await set_marketplace_user_state(
            self.db_path, guild_id="1", user_id="10", status="RESTRICTED",
            authorization=admin, reason_code="risk",
        )
        await set_marketplace_user_state(
            self.db_path, guild_id="1", user_id="10", status="FROZEN",
            authorization=admin, reason_code="risk", expected_version=0,
        )
        await set_marketplace_user_state(
            self.db_path, guild_id="1", user_id="10", status="ACTIVE",
            authorization=admin, reason_code="cleared", expected_version=1,
        )
        self.assertEqual(await self.scalar(
            "SELECT status FROM MarketplaceUserState WHERE guildId='1' AND userId='10'"
        ), "ACTIVE")
        self.assertEqual(await self.scalar(
            "SELECT COUNT(*) FROM MarketplaceUserStateAudit WHERE guildId='1' AND userId='10'"
        ), 3)
        with self.assertRaises(ValueError):
            await set_marketplace_user_state(
                self.db_path, guild_id="1", user_id="10", status="FROZEN",
                authorization=admin, reason_code="stale", expected_version=0,
            )
        connection = sqlite3.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM MarketplaceUserState WHERE guildId='1' AND userId='10'")
        finally:
            connection.rollback()
            connection.close()


if __name__ == "__main__":
    unittest.main()
