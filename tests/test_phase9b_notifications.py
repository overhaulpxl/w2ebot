import json
import os
import sqlite3
import tempfile
import unittest

import aiosqlite

from economy.database import SCHEMA_SQL, configure_connection
from economy.notification_delivery import claim_deliveries, finalize_delivery, reserve_delivery
from economy.notification_routing import update_notification_route
from economy.phase9a_migrations import apply_phase9a_staging
from economy.phase9b_migrations import apply_phase9b_staging


class Phase9BNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db"); os.close(handle)
        connection = sqlite3.connect(self.path); connection.executescript(SCHEMA_SQL); connection.commit(); connection.close()
        apply_phase9a_staging(self.path, production_db=self.path + ".prod")
        apply_phase9b_staging(self.path, production_db=self.path + ".prod")
        self.db = await aiosqlite.connect(self.path); await configure_connection(self.db)
        await update_notification_route(self.db, guild_id="1", actor_id="9", category="MARKET_CRYPTO",
                                        enabled=True, channel_id="12345678901234567", role_mention_id=None,
                                        event_types=["CRYPTO_MARKET_ALERT"], expected_version=0)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close(); os.remove(self.path)

    async def test_one_identity_and_immutable_route_snapshot(self):
        first = await reserve_delivery(self.db, guild_id="1", delivery_kind="EVENT", source_type="SOURCE",
                                       source_key="one", category="MARKET_CRYPTO", event_type="CRYPTO_MARKET_ALERT",
                                       payload={"value": "1"})
        replay = await reserve_delivery(self.db, guild_id="1", delivery_kind="EVENT", source_type="SOURCE",
                                        source_key="one", category="MARKET_CRYPTO", event_type="CRYPTO_MARKET_ALERT",
                                        payload={"value": "1"})
        await update_notification_route(self.db, guild_id="1", actor_id="9", category="MARKET_CRYPTO",
                                        enabled=True, channel_id="12345678901234568", role_mention_id=None,
                                        event_types=["CRYPTO_MARKET_ALERT"], expected_version=0)
        self.assertEqual(first["deliveryId"], replay["deliveryId"])
        row = await (await self.db.execute("SELECT channelId,routeVersion FROM DashboardNotificationDelivery")).fetchone()
        self.assertEqual(row, ("12345678901234567", 0))

    async def test_lease_finalize_and_uncertain_review(self):
        delivery = await reserve_delivery(self.db, guild_id="1", delivery_kind="EVENT", source_type="SOURCE",
                                          source_key="two", category="MARKET_CRYPTO", event_type="CRYPTO_MARKET_ALERT",
                                          payload={"value": "2"})
        rows = await claim_deliveries(self.db, lease_owner="worker", limit=5)
        self.assertEqual(rows[0]["deliveryId"], delivery["deliveryId"])
        receipt = await finalize_delivery(self.db, delivery_id=delivery["deliveryId"], lease_owner="worker",
                                          outcome="REVIEW_REQUIRED", failure_code="response_loss")
        self.assertEqual(receipt["status"], "REVIEW_REQUIRED")
        self.assertEqual(await claim_deliveries(self.db, lease_owner="again"), [])
        with self.assertRaises(Exception):
            await self.db.execute(
                "UPDATE DashboardNotificationDelivery SET messageId='changed' WHERE deliveryId=?",
                (delivery["deliveryId"],),
            )

    async def test_test_delivery_is_separate(self):
        event = await reserve_delivery(self.db, guild_id="1", delivery_kind="EVENT", source_type="SOURCE",
                                       source_key="same", category="MARKET_CRYPTO", event_type="CRYPTO_MARKET_ALERT", payload={})
        test = await reserve_delivery(self.db, guild_id="1", delivery_kind="TEST", source_type="SOURCE",
                                      source_key="same", category="MARKET_CRYPTO", event_type="CRYPTO_MARKET_ALERT", payload={})
        self.assertNotEqual(event["deliveryId"], test["deliveryId"])

    async def test_conclusive_failure_can_retry_same_identity(self):
        delivery = await reserve_delivery(self.db, guild_id="1", delivery_kind="EVENT", source_type="SOURCE",
                                          source_key="retry", category="MARKET_CRYPTO", event_type="CRYPTO_MARKET_ALERT",
                                          payload={"value": "3"})
        await claim_deliveries(self.db, lease_owner="first")
        await finalize_delivery(self.db, delivery_id=delivery["deliveryId"], lease_owner="first",
                                outcome="FAILED", failure_code="discord_forbidden", marker_inspected=True)
        rows = await claim_deliveries(self.db, lease_owner="second")
        self.assertEqual([row["deliveryId"] for row in rows], [delivery["deliveryId"]])
        await finalize_delivery(self.db, delivery_id=delivery["deliveryId"], lease_owner="second",
                                outcome="SENT", message_id="123", marker_inspected=True)
