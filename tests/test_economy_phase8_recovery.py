import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from economy.eternal_options import open_option
from economy.phase8_recovery import claim_phase8_outbox, finalize_phase8_outbox, recover_phase8
from tests.phase8_test_utils import TempPhase8Database


class Phase8RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = TempPhase8Database()
        await self.database.fund_user("10")
        await self.database.seed_casino()

    async def asyncTearDown(self):
        self.database.close()

    def market_time(self):
        connection = sqlite3.connect(self.database.path)
        value = connection.execute("SELECT MAX(occurredAt) FROM CryptoPriceHistory").fetchone()[0]
        connection.close()
        return datetime.fromisoformat(value) + timedelta(seconds=1)

    async def test_restart_settles_using_first_expiry_history(self):
        start = self.market_time()
        position = await open_option(self.database.path, guild_id="1", user_id="10", request_id="r",
                                     symbol="ETHR", direction="UP", stake_ecy=1000,
                                     duration_minutes=5, accepted_at=start)
        connection = sqlite3.connect(self.database.path)
        for index, price in enumerate((11000, 12000), start=1):
            occurred = start + timedelta(minutes=4 + index)
            connection.execute("INSERT INTO CryptoMarketTick(tickId,scheduledAt,outcomeJson,status,resultJson,createdAt,committedAt) VALUES (?,?,?,'COMMITTED',?,?,?)",
                               (f"t{index}", occurred.isoformat(), "{}", "{}", occurred.isoformat(), occurred.isoformat()))
            connection.execute("INSERT INTO CryptoPriceHistory(historyId,tickId,symbol,previousPriceEcy,currentPriceEcy,movementBps,movementType,occurredAt) VALUES (?,?,?,?,?,?,?,?)",
                               (f"h{index}", f"t{index}", "ETHR", 10000, price, 1000, "NORMAL", occurred.isoformat()))
        connection.commit(); connection.close()
        report = await recover_phase8(self.database.path, limit=10, now=(start+timedelta(minutes=7)).isoformat())
        self.assertEqual(report["optionsSettled"], 1)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT expiryHistoryId FROM EternalOptionPosition WHERE positionId=?", (position.entity_id,)).fetchone()[0], "h1")
        connection.close()

    async def test_direct_sql_rejects_outcome_mutation_and_financial_delete(self):
        start = self.market_time()
        position = await open_option(self.database.path, guild_id="1", user_id="10", request_id="r2",
                                     symbol="ETHR", direction="UP", stake_ecy=1000,
                                     duration_minutes=5, accepted_at=start)
        connection = sqlite3.connect(self.database.path)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("UPDATE EternalOptionPosition SET stakeEcy=2000 WHERE positionId=?", (position.entity_id,))
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM EternalOptionPosition WHERE positionId=?", (position.entity_id,))
        connection.close()

    async def test_outbox_failure_replays_same_event_and_finalizes_once(self):
        connection = sqlite3.connect(self.database.path)
        connection.execute(
            "INSERT INTO Phase8NotificationOutbox "
            "(outboxId,eventKey,guildId,userId,entityType,entityId,payloadJson,status,createdAt) "
            "VALUES ('outbox','event','1','10','OPTIONS_SETTLEMENT','position','{}','PENDING',?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
        connection.commit()
        connection.close()

        first = await claim_phase8_outbox(self.database.path, lease_owner="worker-1")
        self.assertEqual([row["outboxId"] for row in first], ["outbox"])
        self.assertEqual(await claim_phase8_outbox(self.database.path, lease_owner="worker-2"), [])
        self.assertTrue(await finalize_phase8_outbox(
            self.database.path, outbox_id="outbox", lease_owner="worker-1",
            sent=False, error_code="delivery_failed",
        ))

        replay = await claim_phase8_outbox(self.database.path, lease_owner="worker-2")
        self.assertEqual([row["eventKey"] for row in replay], ["event"])
        self.assertTrue(await finalize_phase8_outbox(
            self.database.path, outbox_id="outbox", lease_owner="worker-2",
            sent=True, message_id="message",
        ))
        self.assertFalse(await finalize_phase8_outbox(
            self.database.path, outbox_id="outbox", lease_owner="worker-2", sent=True,
        ))

        connection = sqlite3.connect(self.database.path)
        row = connection.execute(
            "SELECT status,attemptCount,messageId,lastErrorCode FROM Phase8NotificationOutbox WHERE outboxId='outbox'"
        ).fetchone()
        connection.close()
        self.assertEqual(row, ("SENT", 2, "message", None))
