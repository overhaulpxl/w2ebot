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


class Phase9CRestartRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        connection = sqlite3.connect(self.path)
        connection.executescript(SCHEMA_SQL)
        connection.commit()
        connection.close()
        apply_phase9a_staging(self.path, production_db=self.path + ".production")
        apply_phase9b_staging(self.path, production_db=self.path + ".production")
        self.db = await aiosqlite.connect(self.path)
        await configure_connection(self.db)
        await update_notification_route(
            self.db, guild_id="1", actor_id="9", category="MARKET_CRYPTO", enabled=True,
            channel_id="12345678901234567", role_mention_id=None,
            event_types=["CRYPTO_MARKET_ALERT"], expected_version=0,
        )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        if os.path.exists(self.path):
            os.remove(self.path)

    async def test_restart_adopts_same_delivery_and_never_duplicates(self):
        first = await reserve_delivery(
            self.db, guild_id="1", delivery_kind="EVENT", source_type="CRYPTO_NEWS",
            source_key="tick:1", category="MARKET_CRYPTO", event_type="CRYPTO_MARKET_ALERT",
            payload={"marker": "stable"},
        )
        replay = await reserve_delivery(
            self.db, guild_id="1", delivery_kind="EVENT", source_type="CRYPTO_NEWS",
            source_key="tick:1", category="MARKET_CRYPTO", event_type="CRYPTO_MARKET_ALERT",
            payload={"marker": "stable"},
        )
        self.assertEqual(first["deliveryId"], replay["deliveryId"])
        claimed = await claim_deliveries(self.db, lease_owner="before-restart")
        self.assertEqual([row["deliveryId"] for row in claimed], [first["deliveryId"]])
        await finalize_delivery(
            self.db, delivery_id=first["deliveryId"], lease_owner="before-restart",
            outcome="FAILED", failure_code="conclusive_rejection", marker_inspected=True,
        )
        claimed_after = await claim_deliveries(self.db, lease_owner="after-restart")
        self.assertEqual([row["deliveryId"] for row in claimed_after], [first["deliveryId"]])
        await finalize_delivery(
            self.db, delivery_id=first["deliveryId"], lease_owner="after-restart",
            outcome="SENT", message_id="123", marker_inspected=True,
        )
        self.assertEqual(await claim_deliveries(self.db, lease_owner="duplicate-worker"), [])
        count = await (await self.db.execute("SELECT COUNT(*) FROM DashboardNotificationDelivery")).fetchone()
        self.assertEqual(count[0], 1)

    async def test_uncertain_send_is_review_held(self):
        delivery = await reserve_delivery(
            self.db, guild_id="1", delivery_kind="EVENT", source_type="LEGACY_BOSS",
            source_key="raid:1", category="MARKET_CRYPTO", event_type="CRYPTO_MARKET_ALERT", payload={},
        )
        await claim_deliveries(self.db, lease_owner="worker")
        await finalize_delivery(
            self.db, delivery_id=delivery["deliveryId"], lease_owner="worker",
            outcome="REVIEW_REQUIRED", failure_code="response_loss",
        )
        self.assertEqual(await claim_deliveries(self.db, lease_owner="restart"), [])


if __name__ == "__main__":
    unittest.main()
