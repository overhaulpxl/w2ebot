import asyncio
import hashlib
import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from economy.giveaways import create_giveaway, enter_giveaway
from economy.eternal_options import open_option
from tests.phase8_test_utils import TempPhase8Database


class Phase8ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = TempPhase8Database()
        await self.database.fund_user("10")
        await self.database.seed_casino()

    async def asyncTearDown(self):
        self.database.close()

    async def test_different_entry_requests_create_one_ticket_and_debit(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        giveaway = await create_giveaway(self.database.path, guild_id="1", channel_id="2",
                                         host_id="3", request_id="g", prize="P", duration_minutes=5, now=now)
        evidence = {"eligible": True}
        evidence["evidenceHash"] = hashlib.sha256(json.dumps(evidence, sort_keys=True,
                                                              separators=(",", ":")).encode()).hexdigest()
        results = await asyncio.gather(*(
            enter_giveaway(self.database.path, guild_id="1", user_id="10", giveaway_id=giveaway.entity_id,
                           request_id=f"entry-{index}", evidence=evidence, now=now)
            for index in range(8)
        ))
        self.assertTrue(all(result.ok for result in results))
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM GiveawayTicket").fetchone()[0], 1)
        self.assertEqual(connection.execute("SELECT ecyBalance FROM EconomyWallet WHERE guildId='1' AND userId='10'").fetchone()[0], 990000)
        connection.close()

    async def test_option_race_respects_count_and_combined_stake(self):
        connection = sqlite3.connect(self.database.path)
        now = datetime.fromisoformat(connection.execute("SELECT MAX(occurredAt) FROM CryptoPriceHistory").fetchone()[0])
        connection.close()
        now += timedelta(seconds=1)
        results = await asyncio.gather(*(
            open_option(self.database.path, guild_id="1", user_id="10", request_id=f"option-{index}",
                        symbol="ETHR", direction="UP", stake_ecy=250000,
                        duration_minutes=30, accepted_at=now)
            for index in range(4)
        ))
        self.assertEqual(sum(result.ok for result in results), 2)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM EternalOptionPosition").fetchone()[0], 2)
        self.assertEqual(connection.execute("SELECT SUM(stakeEcy) FROM EternalOptionPosition").fetchone()[0], 500000)
        connection.close()
