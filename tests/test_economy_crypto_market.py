from datetime import datetime, timedelta, timezone
import sqlite3
import unittest

import aiosqlite

from economy.constants import CRYPTO_ASSETS
from economy.crypto_market import (
    DeterministicRng, _create_news, market_snapshot, plan_tick, run_market_tick,
)
from economy.crypto_simulation import run_phase6_market_simulation
from economy.database import configure_connection
from tests.crypto_test_utils import TempCryptoDatabase


class CryptoMarketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = TempCryptoDatabase()

    async def asyncTearDown(self):
        self.database.close()

    async def test_global_prices_are_shared_across_guild_finances(self):
        before = await market_snapshot(self.database.path)
        at = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
        first, replayed = await run_market_tick(
            self.database.path, scheduled_at=at, rng=DeterministicRng(7),
        )
        second, duplicate = await run_market_tick(
            self.database.path, scheduled_at=at, rng=DeterministicRng(999),
        )
        self.assertFalse(replayed)
        self.assertTrue(duplicate)
        self.assertEqual(first, second)
        after = await market_snapshot(self.database.path)
        self.assertNotEqual(before["coins"], after["coins"])
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute(
            "SELECT COUNT(*) FROM CryptoPriceHistory WHERE tickId=?", (first["tickId"],)
        ).fetchone()[0], 7)
        connection.close()

    def test_normal_bounds_and_event_replacement(self):
        states = {symbol: {"currentPriceEcy": value[1], "version": 0} for symbol, value in CRYPTO_ASSETS.items()}
        for seed in range(2_000):
            plan = plan_tick(states, DeterministicRng(seed))
            event_rows = [value for value in plan["assets"].values() if value["movementType"] != "NORMAL"]
            self.assertEqual(len(event_rows), int(plan["eventType"] is not None))
            for symbol, value in plan["assets"].items():
                if value["movementType"] == "NORMAL":
                    self.assertLessEqual(abs(value["movementBps"]), CRYPTO_ASSETS[symbol][2])

    def test_reduced_simulation_is_deterministic_and_valid(self):
        first = run_phase6_market_simulation(seeds=2, ticks_per_seed=20_000)
        second = run_phase6_market_simulation(seeds=2, ticks_per_seed=20_000)
        self.assertEqual(first["artifactSha256"], second["artifactSha256"])
        self.assertEqual(first["totals"]["boundViolations"], 0)
        self.assertEqual(first["totals"]["normalVolatilityViolations"], 0)

    async def test_news_uses_30_minute_window_and_global_cooldown(self):
        await self.database.seed()
        connection = sqlite3.connect(self.database.path)
        initial_at = connection.execute(
            "SELECT occurredAt FROM CryptoPriceHistory WHERE symbol='ETHR' ORDER BY occurredAt LIMIT 1"
        ).fetchone()[0]
        connection.close()
        occurred_at = (datetime.fromisoformat(initial_at) + timedelta(minutes=31)).isoformat()
        async with aiosqlite.connect(self.database.path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            first = await _create_news(
                db, tick_id="news-tick-1", symbol="ETHR", current_price=12_000,
                occurred_at=occurred_at,
            )
            second = await _create_news(
                db, tick_id="news-tick-2", symbol="ETHR", current_price=13_000,
                occurred_at=occurred_at,
            )
            await db.commit()
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM CryptoNewsOutbox").fetchone()[0], 1)
        connection.close()
