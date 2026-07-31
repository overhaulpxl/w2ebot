import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from economy.eternal_options import open_option, option_liability, settle_option
from tests.phase8_test_utils import TempPhase8Database


class Phase8OptionsTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_open_retry_and_loss_domain_receipt(self):
        accepted = self.market_time()
        result = await open_option(self.database.path, guild_id="1", user_id="10", request_id="open",
                                   symbol="ETHR", direction="UP", stake_ecy=1000,
                                   duration_minutes=5, accepted_at=accepted)
        replay = await open_option(self.database.path, guild_id="1", user_id="10", request_id="open",
                                   symbol="ETHR", direction="UP", stake_ecy=1000,
                                   duration_minutes=5, accepted_at=accepted)
        self.assertTrue(result.ok and replay.replayed)
        connection = sqlite3.connect(self.database.path)
        tick = "expiry"
        connection.execute("INSERT INTO CryptoMarketTick(tickId,scheduledAt,outcomeJson,status,resultJson,createdAt,committedAt) VALUES (?,?,?,'COMMITTED',?,?,?)",
                           (tick, (accepted+timedelta(minutes=5)).isoformat(), "{}", "{}", accepted.isoformat(), accepted.isoformat()))
        connection.execute("INSERT INTO CryptoPriceHistory(historyId,tickId,symbol,previousPriceEcy,currentPriceEcy,movementBps,movementType,occurredAt) VALUES ('expiry-h',?,'ETHR',10000,9000,-1000,'NORMAL',?)",
                           (tick, (accepted+timedelta(minutes=5)).isoformat()))
        connection.commit(); connection.close()
        settled = await settle_option(self.database.path, result.entity_id, now=accepted+timedelta(minutes=6))
        self.assertEqual(settled.receipt["resultCode"], "LOSS")
        self.assertIsNone(settled.receipt["settlementTransactionId"])
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM EconomyTransaction WHERE operation='OPTIONS_SETTLE'").fetchone()[0], 0)
        connection.close()

    async def test_shared_exposure_subtracts_casino_and_options_reservations(self):
        accepted = self.market_time()
        first = await open_option(self.database.path, guild_id="1", user_id="10", request_id="one",
                                  symbol="ETHR", direction="UP", stake_ecy=500000,
                                  duration_minutes=30, accepted_at=accepted)
        self.assertTrue(first.ok)
        connection = sqlite3.connect(self.database.path)
        connection.execute("INSERT INTO CasinoSession(sessionId,requestId,guildId,userId,gameType,stakeEcy,maximumGrossLiabilityEcy,outcomeJson,stateJson,status,reservationKey,createdAt,expiresAt) VALUES ('s','r','1','20','SLOT',1000,1000000,'{}','{}','RESERVED','casino:x','n','later')")
        connection.execute("INSERT INTO CasinoBankrollReservation(reservationId,sessionId,guildId,liabilityEcy,status,createdAt) VALUES ('cr','s','1',1000000,'ACTIVE','n')")
        connection.commit(); connection.close()
        from economy.eternal_options import options_status
        state = await options_status(self.database.path, "1")
        self.assertEqual(state["reservedLiabilityEcy"], 1_950_000)
        self.assertEqual(state["optionsReservedLiabilityEcy"], 950_000)

    def test_checked_stake_boundaries(self):
        self.assertEqual(option_liability(1000), 1900)
        self.assertEqual(option_liability(500000), 950000)
        with self.assertRaises(ValueError):
            option_liability(1500)
