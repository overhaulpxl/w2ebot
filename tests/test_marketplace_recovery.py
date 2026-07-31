import json
import sqlite3
import unittest

import aiosqlite

from economy.marketplace import (
    claim_notification_events, create_listing, finalize_notification_event,
    pending_watch_notifications, reserve_purchase, set_watch,
    settle_pending_return, settle_purchase, void_purchase,
)
from economy.constants import RPG_PHASE3_CATALOG_VERSION
from economy.phase4_recovery import recover_phase4_runtime
from economy.phase4_schema import PHASE4_TRIGGER_SQL
from tests.marketplace_test_utils import MarketplaceDatabaseMixin, NOW


class MarketplaceRecoveryTests(MarketplaceDatabaseMixin, unittest.IsolatedAsyncioTestCase):
    def _trigger_sql(self, name):
        return next(trigger for trigger in PHASE4_TRIGGER_SQL if name in trigger)

    def _make_sale_pending_after_commit(self, sale_id):
        connection = sqlite3.connect(self.db_path)
        connection.execute("DROP TRIGGER trg_market_sale_transition")
        connection.execute(
            "UPDATE MarketplaceSale SET status='PENDING',buyerReceiptJson=NULL,sellerReceiptJson=NULL,completedAt=NULL "
            "WHERE saleId=?", (sale_id,),
        )
        connection.execute(self._trigger_sql("trg_market_sale_transition"))
        connection.commit()
        connection.close()

    async def _reserved_equipment_sale(self, suffix="one"):
        await self.add_equipment(f"eq-{suffix}", "10")
        await self.fund_user("20")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT", asset_id=f"eq-{suffix}",
            quantity=1, unit_price_etm=100_000, idempotency_key=f"listing-{suffix}", authorization=self.member_auth("10"),
        )
        sale = await reserve_purchase(
            self.db_path, guild_id="1", buyer_id="20", listing_id=listing.listing_id,
            quantity=1, idempotency_key=f"sale-{suffix}", authorization=self.member_auth("20"),
        )
        return listing, sale

    async def test_pending_pair_restart_settles_once(self):
        _listing, sale = await self._reserved_equipment_sale("restart")
        report = await recover_phase4_runtime(self.db_path)
        self.assertEqual(report["settled"], 1)
        replay = await settle_purchase(self.db_path, guild_id="1", sale_id=sale.sale_id)
        self.assertTrue(replay.ok and replay.replayed)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM EconomyLedger WHERE transactionId=?", (sale.transaction_id,)), 5)
        connection = sqlite3.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE MarketplaceSale SET buyerReceiptJson='{}' WHERE saleId=?",
                    (sale.sale_id,),
                )
        finally:
            connection.rollback()
            connection.close()

    async def test_pending_pair_with_ledger_enters_review(self):
        listing, sale = await self._reserved_equipment_sale("partial")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO EconomyLedger (transactionId,sequence,guildId,accountKind,accountId,userId,currency,"
                "transactionType,amount,balanceBefore,balanceAfter,referenceId,source,createdAt) "
                "VALUES (?,1,'1','USER','20','20','ETM','MARKETPLACE_PURCHASE',-1,10,9,?,'marketplace',?)",
                (sale.transaction_id, listing.listing_id, NOW),
            )
            await db.commit()
        report = await recover_phase4_runtime(self.db_path)
        self.assertEqual(report["review_required"], 1)
        self.assertEqual(await self.scalar("SELECT status FROM MarketplaceSale WHERE saleId=?", (sale.sale_id,)), "REVIEW_REQUIRED")
        self.assertEqual(await self.scalar("SELECT status FROM MarketplaceListing WHERE listingId=?", (listing.listing_id,)), "REVIEW_REQUIRED")

    async def test_mutation_free_pair_can_void_only_once(self):
        _listing, sale = await self._reserved_equipment_sale("void")
        result = await void_purchase(self.db_path, guild_id="1", sale_id=sale.sale_id, reason_code="buyer_cancelled")
        self.assertTrue(result.ok)
        self.assertEqual(await self.scalar("SELECT status FROM MarketplaceSale WHERE saleId=?", (sale.sale_id,)), "VOID")
        self.assertEqual(await self.scalar("SELECT status FROM EconomyTransaction WHERE transactionId=?", (sale.transaction_id,)), "REVERSED")
        with self.assertRaises(ValueError):
            await void_purchase(self.db_path, guild_id="1", sale_id=sale.sale_id)

    async def test_committed_header_incomplete_receipt_is_reconstructed(self):
        listing, sale = await self._reserved_equipment_sale("receipt")
        self.assertTrue((await settle_purchase(
            self.db_path, guild_id="1", sale_id=sale.sale_id,
        )).ok)
        self._make_sale_pending_after_commit(sale.sale_id)
        report = await recover_phase4_runtime(self.db_path)
        self.assertEqual(report["replayed"], 1)
        receipt = await self.scalar("SELECT buyerReceiptJson FROM MarketplaceSale WHERE saleId=?", (sale.sale_id,))
        self.assertEqual(json.loads(receipt)["asset_id"], "eq-receipt")

    async def test_committed_ledger_with_wrong_equipment_owner_enters_review(self):
        listing, sale = await self._reserved_equipment_sale("wrong-owner")
        self.assertTrue((await settle_purchase(self.db_path, guild_id="1", sale_id=sale.sale_id)).ok)
        self._make_sale_pending_after_commit(sale.sale_id)
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "UPDATE RpgEquipmentInstance SET ownerId='30' WHERE equipmentInstanceId='eq-wrong-owner'"
        )
        connection.commit()
        connection.close()
        report = await recover_phase4_runtime(self.db_path)
        self.assertEqual(report["review_required"], 1)
        second = await recover_phase4_runtime(self.db_path)
        self.assertGreaterEqual(second["review_required"], 1)
        self.assertEqual(await self.scalar(
            "SELECT COUNT(*) FROM MarketplaceRecoveryReview WHERE entityType='SALE' AND entityId=?",
            (sale.sale_id,),
        ), 1)
        self.assertGreaterEqual(await self.scalar(
            "SELECT retryCount FROM MarketplaceRecoveryReview WHERE entityType='SALE' AND entityId=?",
            (sale.sale_id,),
        ), 2)
        self.assertEqual(await self.scalar(
            "SELECT buyerReceiptJson FROM MarketplaceSale WHERE saleId=?", (sale.sale_id,)
        ), None)

    async def test_committed_ledger_with_equipment_still_escrowed_enters_review(self):
        _listing, sale = await self._reserved_equipment_sale("still-escrowed")
        self.assertTrue((await settle_purchase(self.db_path, guild_id="1", sale_id=sale.sale_id)).ok)
        self._make_sale_pending_after_commit(sale.sale_id)
        connection = sqlite3.connect(self.db_path)
        connection.execute("DROP TRIGGER trg_market_equipment_enter_escrow")
        connection.execute(
            "UPDATE RpgEquipmentInstance SET status='ESCROWED' WHERE equipmentInstanceId='eq-still-escrowed'"
        )
        connection.execute(self._trigger_sql("trg_market_equipment_enter_escrow"))
        connection.commit()
        connection.close()
        report = await recover_phase4_runtime(self.db_path)
        self.assertEqual(report["review_required"], 1)
        self.assertEqual(await self.scalar(
            "SELECT status FROM MarketplaceSale WHERE saleId=?", (sale.sale_id,)
        ), "REVIEW_REQUIRED")

    async def test_wrong_ledger_allocation_never_reconstructs_receipt(self):
        _listing, sale = await self._reserved_equipment_sale("wrong-ledger")
        self.assertTrue((await settle_purchase(self.db_path, guild_id="1", sale_id=sale.sale_id)).ok)
        self._make_sale_pending_after_commit(sale.sale_id)
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "UPDATE EconomyLedger SET amount=amount+1 WHERE transactionId=? AND sequence=3",
            (sale.transaction_id,),
        )
        connection.commit()
        connection.close()
        report = await recover_phase4_runtime(self.db_path)
        self.assertEqual(report["review_required"], 1)
        self.assertEqual(await self.scalar(
            "SELECT status FROM MarketplaceSale WHERE saleId=?", (sale.sale_id,)
        ), "REVIEW_REQUIRED")

    async def test_committed_transaction_identity_mismatch_never_reconstructs_receipt(self):
        _listing, sale = await self._reserved_equipment_sale("wrong-transaction")
        self.assertTrue((await settle_purchase(
            self.db_path, guild_id="1", sale_id=sale.sale_id,
        )).ok)
        self._make_sale_pending_after_commit(sale.sale_id)
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "UPDATE EconomyTransaction SET metadataJson='{}' WHERE transactionId=?",
            (sale.transaction_id,),
        )
        connection.commit()
        connection.close()
        report = await recover_phase4_runtime(self.db_path)
        self.assertEqual(report["review_required"], 1)
        self.assertEqual(await self.scalar(
            "SELECT status FROM MarketplaceSale WHERE saleId=?", (sale.sale_id,)
        ), "REVIEW_REQUIRED")
        self.assertIsNone(await self.scalar(
            "SELECT buyerReceiptJson FROM MarketplaceSale WHERE saleId=?", (sale.sale_id,)
        ))

    async def test_missing_or_wrong_binding_stack_credit_enters_review(self):
        await self.add_stack("10", quantity=4)
        await self.fund_user("20")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="STACK",
            asset_id="mat_iron_shard", catalog_version=RPG_PHASE3_CATALOG_VERSION,
            quantity=4, unit_price_etm=10_000, idempotency_key="stack-proof-listing",
            authorization=self.member_auth("10"),
        )
        sale = await reserve_purchase(
            self.db_path, guild_id="1", buyer_id="20", listing_id=listing.listing_id,
            quantity=2, idempotency_key="stack-proof-sale", authorization=self.member_auth("20"),
        )
        self.assertTrue((await settle_purchase(self.db_path, guild_id="1", sale_id=sale.sale_id)).ok)
        self._make_sale_pending_after_commit(sale.sale_id)
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "DELETE FROM RpgInventoryStack WHERE guildId='1' AND userId='20' "
            "AND itemId='mat_iron_shard' AND catalogVersion=? AND bindingStatus='UNBOUND'",
            (RPG_PHASE3_CATALOG_VERSION,),
        )
        connection.execute(
            "INSERT INTO RpgInventoryStack "
            "(guildId,userId,itemId,catalogVersion,bindingStatus,status,quantity,version,createdAt,updatedAt) "
            "VALUES ('1','20','mat_iron_shard',?,'ACCOUNT_BOUND','ACTIVE',2,0,?,?)",
            (RPG_PHASE3_CATALOG_VERSION, NOW, NOW),
        )
        connection.commit()
        connection.close()
        report = await recover_phase4_runtime(self.db_path)
        self.assertEqual(report["review_required"], 1)
        self.assertEqual(await self.scalar(
            "SELECT buyerReceiptJson FROM MarketplaceSale WHERE saleId=?", (sale.sale_id,)
        ), None)

    async def test_listing_escrow_quantity_mismatch_never_reconstructs_receipt(self):
        await self.add_stack("10", quantity=4)
        await self.fund_user("20")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="STACK",
            asset_id="mat_iron_shard", catalog_version=RPG_PHASE3_CATALOG_VERSION,
            quantity=4, unit_price_etm=10_000, idempotency_key="mismatch-listing",
            authorization=self.member_auth("10"),
        )
        sale = await reserve_purchase(
            self.db_path, guild_id="1", buyer_id="20", listing_id=listing.listing_id,
            quantity=1, idempotency_key="mismatch-sale", authorization=self.member_auth("20"),
        )
        self.assertTrue((await settle_purchase(self.db_path, guild_id="1", sale_id=sale.sale_id)).ok)
        self._make_sale_pending_after_commit(sale.sale_id)
        connection = sqlite3.connect(self.db_path)
        connection.execute("DROP TRIGGER trg_market_escrow_quantity_authoritative")
        connection.execute(
            "UPDATE MarketplaceEscrow SET remainingQuantity=2 WHERE listingId=?",
            (listing.listing_id,),
        )
        connection.execute(self._trigger_sql("trg_market_escrow_quantity_authoritative"))
        connection.commit()
        connection.close()
        report = await recover_phase4_runtime(self.db_path)
        self.assertGreaterEqual(report["review_required"], 1)
        self.assertEqual(await self.scalar(
            "SELECT buyerReceiptJson FROM MarketplaceSale WHERE saleId=?", (sale.sale_id,)
        ), None)
    async def test_pending_return_and_watch_notification_recovery(self):
        await self.add_equipment("eq-return", "10")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="EQUIPMENT", asset_id="eq-return",
            quantity=1, unit_price_etm=100_000, idempotency_key="return-listing", authorization=self.member_auth("10"),
        )
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute(
                "SELECT l.listingId,e.escrowId,l.assetType,l.equipmentInstanceId,l.stackItemId,"
                "l.catalogVersion,l.stackBindingStatus FROM MarketplaceListing l "
                "JOIN MarketplaceEscrow e ON e.listingId=l.listingId WHERE l.listingId=?",
                (listing.listing_id,),
            )).fetchone()
            await db.execute(
                "INSERT INTO MarketplaceReturn (returnId,listingId,escrowId,guildId,recipientId,assetType,equipmentInstanceId,stackItemId,catalogVersion,stackBindingStatus,quantity,reasonCode,initiatedById,authorizationSource,status,idempotencyKey,createdAt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ('return-pending', row['listingId'], row['escrowId'], '1', '10', row['assetType'],
                 row['equipmentInstanceId'], row['stackItemId'], row['catalogVersion'],
                 row['stackBindingStatus'], 1, 'recovery', '99', 'recovery', 'PENDING',
                 'return-pending', NOW),
            )
            await db.commit()
        result = await settle_pending_return(self.db_path, guild_id="1", recipient_id="10", return_id="return-pending")
        self.assertTrue(result.ok)
        self.assertEqual(await self.scalar("SELECT status FROM MarketplaceReturn WHERE returnId='return-pending'"), "COMMITTED")
        self.assertEqual(await pending_watch_notifications(self.db_path), [])

    async def test_missing_transaction_pair_is_not_replaced(self):
        listing, sale = await self._reserved_equipment_sale("missing")
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("DELETE FROM EconomyTransaction WHERE transactionId=?", (sale.transaction_id,))
        connection.commit()
        connection.close()
        report = await recover_phase4_runtime(self.db_path)
        self.assertEqual(report["review_required"], 1)
        self.assertEqual(await self.scalar("SELECT transactionId FROM MarketplaceSale WHERE saleId=?", (sale.sale_id,)), sale.transaction_id)
        self.assertEqual(await self.scalar("SELECT COUNT(*) FROM MarketplaceSale"), 1)
        # Pulihkan fixture korup untuk memastikan database test tetap lolos FK check.
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "INSERT INTO EconomyTransaction (transactionId,guildId,idempotencyKey,operation,source,referenceId,"
            "actorId,reasonCode,reasonText,metadataJson,status,createdAt) "
            "VALUES (?, '1','fixture-restored','MARKETPLACE_PURCHASE','test',?,'20','test','test','{}','PENDING',?)",
            (sale.transaction_id, listing.listing_id, NOW),
        )
        connection.commit()
        connection.close()

    async def test_notification_outbox_preserves_multiple_events_and_retries(self):
        await self.add_stack("10", quantity=4)
        await self.fund_user("20")
        await self.fund_user("30")
        listing = await create_listing(
            self.db_path, guild_id="1", seller_id="10", asset_type="STACK",
            asset_id="mat_iron_shard", catalog_version=RPG_PHASE3_CATALOG_VERSION,
            quantity=4, unit_price_etm=10_000, idempotency_key="outbox-listing",
            authorization=self.member_auth("10"),
        )
        await set_watch(
            self.db_path, guild_id="1", user_id="40", listing_id=listing.listing_id,
            authorization=self.member_auth("40"),
        )
        for buyer in ("20", "30"):
            sale = await reserve_purchase(
                self.db_path, guild_id="1", buyer_id=buyer, listing_id=listing.listing_id,
                quantity=1, idempotency_key=f"outbox-{buyer}", authorization=self.member_auth(buyer),
            )
            self.assertTrue((await settle_purchase(
                self.db_path, guild_id="1", sale_id=sale.sale_id,
            )).ok)
        self.assertEqual(await self.scalar(
            "SELECT COUNT(*) FROM MarketplaceNotificationOutbox WHERE listingId=?",
            (listing.listing_id,),
        ), 2)
        claimed = await claim_notification_events(
            self.db_path, lease_owner="worker-a", limit=10,
        )
        self.assertEqual(len(claimed), 2)
        self.assertTrue(await finalize_notification_event(
            self.db_path, event_id=claimed[0]["eventId"], lease_owner="worker-a",
            sent=True, message_id="message-1",
        ))
        self.assertTrue(await finalize_notification_event(
            self.db_path, event_id=claimed[1]["eventId"], lease_owner="worker-a",
            sent=False, error_code="network",
        ))
        retried = await claim_notification_events(
            self.db_path, lease_owner="worker-b", limit=10,
        )
        self.assertEqual([row["eventId"] for row in retried], [claimed[1]["eventId"]])
        self.assertEqual(await self.scalar(
            "SELECT COUNT(*) FROM EconomyLedger WHERE transactionType='MARKETPLACE_PURCHASE'"
        ), 10)


if __name__ == "__main__":
    unittest.main()
