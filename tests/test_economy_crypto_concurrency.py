import asyncio
import sqlite3
import unittest

from economy.crypto import execute_trade
from economy.crypto_market import DeterministicRng, run_market_tick
from tests.crypto_test_utils import TempCryptoDatabase


class CryptoConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = TempCryptoDatabase()
        await self.database.seed(10_000_000)

    async def asyncTearDown(self):
        self.database.close()

    async def test_same_request_replays_and_different_requests_cannot_overdraw(self):
        await self.database.fund_user("2", 10_200)
        same = await asyncio.gather(*(
            execute_trade(self.database.path, guild_id="1", user_id="2", request_id="same",
                          side="BUY", symbol="ETHR", quantity="1") for _ in range(2)
        ))
        self.assertEqual(sum(result.ok for result in same), 2)
        self.assertEqual(sum(result.replayed for result in same), 1)
        await self.database.fund_user("3", 10_200)
        raced = await asyncio.gather(
            execute_trade(self.database.path, guild_id="1", user_id="3", request_id="a",
                          side="BUY", symbol="ETHR", quantity="1"),
            execute_trade(self.database.path, guild_id="1", user_id="3", request_id="b",
                          side="BUY", symbol="ETHR", quantity="1"),
        )
        self.assertEqual(sum(result.ok for result in raced), 1)

    async def test_concurrent_sell_cannot_oversell(self):
        await self.database.fund_user("4", 10_200)
        await execute_trade(self.database.path, guild_id="1", user_id="4", request_id="buy",
                            side="BUY", symbol="ETHR", quantity="1")
        results = await asyncio.gather(
            execute_trade(self.database.path, guild_id="1", user_id="4", request_id="s1",
                          side="SELL", symbol="ETHR", quantity="1"),
            execute_trade(self.database.path, guild_id="1", user_id="4", request_id="s2",
                          side="SELL", symbol="ETHR", quantity="1"),
        )
        self.assertEqual(sum(result.ok for result in results), 1)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute(
            "SELECT units FROM CryptoHolding WHERE guildId='1' AND userId='4' AND symbol='ETHR'"
        ).fetchone()[0], 0)
        self.assertEqual(connection.execute(
            "SELECT COUNT(*) FROM (SELECT transactionId FROM EconomyLedger GROUP BY transactionId HAVING SUM(amount)<>0)"
        ).fetchone()[0], 0)
        self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        connection.close()

    async def test_two_sellers_cannot_overdraw_market_reserve(self):
        for user_id in ("7", "8"):
            await self.database.fund_user(user_id, 10_200)
            result = await execute_trade(
                self.database.path, guild_id="1", user_id=user_id,
                request_id=f"buy:{user_id}", side="BUY", symbol="ETHR", quantity="1",
            )
            self.assertTrue(result.ok)
        connection = sqlite3.connect(self.database.path)
        connection.execute(
            "UPDATE EconomySystemAccount SET balance=10000 WHERE guildId='1' AND accountCode='ECY_MARKET'"
        )
        connection.commit()
        connection.close()
        results = await asyncio.gather(*(
            execute_trade(
                self.database.path, guild_id="1", user_id=user_id,
                request_id=f"sell:{user_id}", side="SELL", symbol="ETHR", quantity="1",
            ) for user_id in ("7", "8")
        ))
        self.assertEqual(sum(result.ok for result in results), 1)
        connection = sqlite3.connect(self.database.path)
        reserve = connection.execute(
            "SELECT balance FROM EconomySystemAccount WHERE guildId='1' AND accountCode='ECY_MARKET'"
        ).fetchone()[0]
        self.assertGreaterEqual(reserve, 0)
        self.assertEqual(connection.execute(
            "SELECT SUM(units) FROM CryptoHolding WHERE userId IN ('7','8')"
        ).fetchone()[0], 100_000_000)
        connection.close()

    async def test_trade_and_global_tick_serialize_to_committed_snapshot(self):
        await self.database.fund_user("10", 20_400)
        trade, tick = await asyncio.gather(
            execute_trade(
                self.database.path, guild_id="1", user_id="10", request_id="tick-race",
                side="BUY", symbol="ETHR", quantity="1",
            ),
            run_market_tick(
                self.database.path, scheduled_at=None, rng=DeterministicRng(44),
            ),
        )
        self.assertTrue(trade.ok)
        connection = sqlite3.connect(self.database.path)
        snapshot = connection.execute(
            "SELECT currentPriceEcy FROM CryptoPriceHistory WHERE tickId=? AND symbol='ETHR'",
            (trade.receipt["priceTickId"],),
        ).fetchone()
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot[0], trade.receipt["priceEcy"])
        self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        connection.close()
