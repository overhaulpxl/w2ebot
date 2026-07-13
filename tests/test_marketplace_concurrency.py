import asyncio
import unittest

from economy.constants import RPG_PHASE3_CATALOG_VERSION
from economy.marketplace import (
    cancel_listing, create_listing, create_report, reserve_purchase, set_marketplace_user_state,
    settle_purchase,
)
from tests.marketplace_test_utils import MarketplaceDatabaseMixin


class MarketplaceConcurrencyTests(MarketplaceDatabaseMixin, unittest.IsolatedAsyncioTestCase):
    async def test_purchase_reservation_pair_rolls_back_at_every_crash_point(self):
        await self.add_equipment("eq-reservation-crash", "10")
        await self.fund_user("20")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT",
            asset_id="eq-reservation-crash", quantity=1, unit_price_etm=100_000,
            idempotency_key="reservation-crash-listing", authorization=self.member_auth("10"),
        )
        for index, stage in enumerate((
            "after_transaction_header", "after_sale_envelope", "before_reservation_commit",
        )):
            with self.subTest(stage=stage), self.assertRaises(RuntimeError):
                await reserve_purchase(
                    self.db_path, guild_id="1", buyer_id="20",
                    listing_id=listing.listing_id, quantity=1,
                    idempotency_key=f"reservation-crash-{index}", failure_stage=stage, authorization=self.member_auth("20"),
                )
            self.assertEqual(await self.scalar(
                "SELECT COUNT(*) FROM MarketplaceSale WHERE listingId=?", (listing.listing_id,)
            ), 0)
            self.assertEqual(await self.scalar(
                "SELECT COUNT(*) FROM EconomyTransaction "
                "WHERE operation='MARKETPLACE_PURCHASE' AND referenceId=?", (listing.listing_id,)
            ), 0)

    async def test_different_request_ids_reuse_one_buyer_reservation(self):
        await self.add_equipment("eq-reserve", "10")
        await self.fund_user("20")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT", asset_id="eq-reserve",
            quantity=1, unit_price_etm=100_000, idempotency_key="reserve-listing", authorization=self.member_auth("10"),
        )
        first, second = await asyncio.gather(
            reserve_purchase(self.db_path, guild_id="1", buyer_id="20", listing_id=listing.listing_id, quantity=1, idempotency_key="request-a", authorization=self.member_auth("20", "request-a")),
            reserve_purchase(self.db_path, guild_id="1", buyer_id="20", listing_id=listing.listing_id, quantity=1, idempotency_key="request-b", authorization=self.member_auth("20", "request-b")),
        )
        self.assertEqual(first.sale_id, second.sale_id)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM MarketplaceSale"), 1)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM EconomyTransaction WHERE operation='MARKETPLACE_PURCHASE'"), 1)

    async def test_two_buyers_have_one_equipment_winner(self):
        await self.add_equipment("eq-race", "10")
        await self.fund_user("20")
        await self.fund_user("30")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT", asset_id="eq-race",
            quantity=1, unit_price_etm=100_000, idempotency_key="race-listing", authorization=self.member_auth("10"),
        )
        reservations = await asyncio.gather(*(
            reserve_purchase(self.db_path, guild_id="1", buyer_id=user, listing_id=listing.listing_id,
                             quantity=1, idempotency_key=f"race-{user}", authorization=self.member_auth(user)) for user in ("20", "30")
        ))
        results = await asyncio.gather(*(
            settle_purchase(self.db_path, guild_id="1", sale_id=row.sale_id) for row in reservations
        ))
        self.assertEqual(sum(result.ok for result in results), 1)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM MarketplaceSale WHERE status='COMMITTED'"), 1)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM EconomyLedger"), 5)
        self.assertIn(await self.scalar("SELECT ownerId FROM RpgEquipmentInstance WHERE equipmentInstanceId='eq-race'"), ("20", "30"))

    async def test_partial_stack_race_cannot_oversell(self):
        await self.add_stack("10", quantity=10)
        await self.fund_user("20")
        await self.fund_user("30")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="STACK", asset_id="mat_iron_shard",
            catalog_version=RPG_PHASE3_CATALOG_VERSION, quantity=10, unit_price_etm=10_000, idempotency_key="stack-race", authorization=self.member_auth("10"),
        )
        reservations = await asyncio.gather(*(
            reserve_purchase(self.db_path, guild_id="1", buyer_id=user, listing_id=listing.listing_id,
                             quantity=7, idempotency_key=f"stack-{user}", authorization=self.member_auth(user)) for user in ("20", "30")
        ))
        results = await asyncio.gather(*(
            settle_purchase(self.db_path, guild_id="1", sale_id=row.sale_id) for row in reservations
        ))
        self.assertEqual(sum(result.ok for result in results), 1)
        self.assertEqual(await self.scalar("SELECT remainingQuantity FROM MarketplaceEscrow WHERE listingId=?", (listing.listing_id,)), 3)
        credited = await self.scalar("SELECT COALESCE(SUM(quantity),0) FROM RpgInventoryStack WHERE userId IN ('20','30') AND itemId='mat_iron_shard'")
        self.assertEqual(credited, 7)

    async def test_purchase_cancel_race_has_single_asset_exit(self):
        await self.add_equipment("eq-cancel-race", "10")
        await self.fund_user("20")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT", asset_id="eq-cancel-race",
            quantity=1, unit_price_etm=100_000, idempotency_key="cancel-race", authorization=self.member_auth("10"),
        )
        reservation = await reserve_purchase(
            self.db_path, guild_id="1", buyer_id="20", listing_id=listing.listing_id,
            quantity=1, idempotency_key="cancel-buy", authorization=self.member_auth("20"),
        )
        purchase, returned = await asyncio.gather(
            settle_purchase(self.db_path, guild_id="1", sale_id=reservation.sale_id),
            cancel_listing(self.db_path, guild_id="1", listing_id=listing.listing_id, authorization=self.member_auth("10")),
        )
        self.assertEqual(int(purchase.ok) + int(returned.ok), 1)
        self.assertIn(await self.scalar("SELECT status FROM MarketplaceListing WHERE listingId=?", (listing.listing_id,)), ("SOLD", "RETURNED"))

    async def test_committed_replay_does_not_duplicate_ledger(self):
        await self.add_equipment("eq-replay", "10")
        await self.fund_user("20")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT", asset_id="eq-replay",
            quantity=1, unit_price_etm=100_000, idempotency_key="replay-listing", authorization=self.member_auth("10"),
        )
        reserved = await reserve_purchase(self.db_path, guild_id="1", buyer_id="20", listing_id=listing.listing_id, quantity=1, idempotency_key="replay-buy", authorization=self.member_auth("20"))
        first = await settle_purchase(self.db_path, guild_id="1", sale_id=reserved.sale_id)
        second = await settle_purchase(self.db_path, guild_id="1", sale_id=reserved.sale_id)
        self.assertTrue(first.ok and second.ok and second.replayed)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM EconomyLedger WHERE transactionId=?", (reserved.transaction_id,)), 5)
        self.assertEqual(await self.scalar("SELECT SUM(amount) FROM EconomyLedger WHERE transactionId=?", (reserved.transaction_id,)), 0)

    async def test_seller_freeze_after_reservation_blocks_settlement(self):
        await self.add_equipment("eq-freeze-race", "10")
        await self.fund_user("20")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT",
            asset_id="eq-freeze-race", quantity=1, unit_price_etm=100_000,
            idempotency_key="freeze-listing", authorization=self.member_auth("10"),
        )
        reserved = await reserve_purchase(
            self.db_path, guild_id="1", buyer_id="20", listing_id=listing.listing_id,
            quantity=1, idempotency_key="freeze-buy", authorization=self.member_auth("20"),
        )
        await set_marketplace_user_state(
            self.db_path, guild_id="1", user_id="10", status="FROZEN",
            authorization=self.staff_auth(), reason_code="moderation",
        )
        result = await settle_purchase(
            self.db_path, guild_id="1", sale_id=reserved.sale_id,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "seller_restricted")
        self.assertEqual(await self.scalar(
            "SELECT status FROM MarketplaceSale WHERE saleId=?", (reserved.sale_id,)
        ), "PENDING")
        self.assertEqual(await self.scalar(
            "SELECT COUNT(*) FROM EconomyLedger WHERE transactionId=?", (reserved.transaction_id,)
        ), 0)

    async def test_concurrent_duplicate_reports_reuse_one_unresolved_identity(self):
        await self.add_equipment("eq-report-race", "10")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT",
            asset_id="eq-report-race", quantity=1, unit_price_etm=100_000,
            idempotency_key="report-race-listing", authorization=self.member_auth("10"),
        )
        first, second = await asyncio.gather(
            create_report(
                self.db_path, guild_id="1", reporter_id="20", listing_id=listing.listing_id,
                category="PRICE", authorization=self.member_auth("20", "report-a"),
            ),
            create_report(
                self.db_path, guild_id="1", reporter_id="20", listing_id=listing.listing_id,
                category="PRICE", authorization=self.member_auth("20", "report-b"),
            ),
        )
        self.assertTrue(first.ok and second.ok)
        self.assertEqual(first.data["report_id"], second.data["report_id"])
        self.assertEqual(await self.scalar(
            "SELECT COUNT(*) FROM MarketplaceReport WHERE status IN ('OPEN','IN_REVIEW')"
        ), 1)

    async def test_quantity_mutation_failure_rolls_back_both_sides(self):
        await self.add_equipment("eq-quantity-rollback", "10")
        await self.fund_user("20")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT",
            asset_id="eq-quantity-rollback", quantity=1, unit_price_etm=100_000,
            idempotency_key="quantity-rollback-listing", authorization=self.member_auth("10"),
        )
        sale = await reserve_purchase(
            self.db_path, guild_id="1", buyer_id="20", listing_id=listing.listing_id,
            quantity=1, idempotency_key="quantity-rollback-sale", authorization=self.member_auth("20"),
        )
        result = await settle_purchase(
            self.db_path, guild_id="1", sale_id=sale.sale_id,
            failure_stage="after_quantity_mutation",
        )
        self.assertFalse(result.ok)
        self.assertEqual(await self.scalar(
            "SELECT remainingQuantity FROM MarketplaceListing WHERE listingId=?", (listing.listing_id,)
        ), 1)
        self.assertEqual(await self.scalar(
            "SELECT remainingQuantity FROM MarketplaceEscrow WHERE listingId=?", (listing.listing_id,)
        ), 1)
        self.assertEqual(await self.scalar(
            "SELECT COUNT(*) FROM MarketplaceQuantityMutation WHERE listingId=?", (listing.listing_id,)
        ), 0)


if __name__ == "__main__":
    unittest.main()
