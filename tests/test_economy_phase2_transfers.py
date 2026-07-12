import asyncio
import sqlite3
import unittest
from datetime import datetime, timezone

from economy.exchange import exchange_etm_to_ecy, get_exchange_info
from economy.ledger import AccountDelta, execute_transaction
from economy.profile import ensure_profile
from economy.transfers import transfer_etm
from tests.economy_test_utils import TempEconomyDatabase


async def fund_user(db_path, guild_id, user_id, amount, key):
    return await execute_transaction(
        db_path, guild_id=guild_id, idempotency_key=key,
        operation="TEST_FUND", source="TEST", actor_id=None, reason="test funding",
        deltas=(
            AccountDelta("SYSTEM", "ETM_ISSUANCE", "ETM", -amount),
            AccountDelta("USER", str(user_id), "ETM", amount, str(user_id)),
        ),
    )


class Phase2TransferTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = TempEconomyDatabase()
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    async def asyncTearDown(self):
        self.database.close()

    async def test_transfer_fee_and_daily_usage_are_atomic(self):
        await fund_user(self.database.path, "1", "10", 100_000, "fund:transfer")
        result = await transfer_etm(
            self.database.path, guild_id="1", sender_id="10", recipient_id="20",
            amount=100_000, request_id="one", now=self.now,
        )
        self.assertTrue(result.ok)
        connection = sqlite3.connect(self.database.path)
        sender = connection.execute("SELECT etmBalance FROM EconomyWallet WHERE userId='10'").fetchone()[0]
        receiver = connection.execute("SELECT etmBalance FROM EconomyWallet WHERE userId='20'").fetchone()[0]
        systems = dict(connection.execute(
            "SELECT accountCode,balance FROM EconomySystemAccount WHERE accountCode IN ('ETM_GENERAL','ETM_RESERVE','ETM_BURN')"
        ).fetchall())
        usage = connection.execute(
            "SELECT usageType,submittedAmount FROM EconomyDailyUsage"
        ).fetchone()
        connection.close()
        self.assertEqual((sender, receiver), (0, 95_000))
        self.assertEqual(systems, {"ETM_GENERAL": 4_000, "ETM_RESERVE": 500, "ETM_BURN": 500})
        self.assertEqual(usage, ("TRANSFER_ETM", 100_000))

    async def test_concurrent_transfer_daily_limit_has_one_winner(self):
        await fund_user(self.database.path, "1", "10", 3_000_000, "fund:race")
        results = await asyncio.gather(
            transfer_etm(
                self.database.path, guild_id="1", sender_id="10", recipient_id="20",
                amount=1_200_000, request_id="a", now=self.now,
            ),
            transfer_etm(
                self.database.path, guild_id="1", sender_id="10", recipient_id="30",
                amount=1_200_000, request_id="b", now=self.now,
            ),
        )
        self.assertEqual(sum(result.ok for result in results), 1)
        connection = sqlite3.connect(self.database.path)
        usage = connection.execute("SELECT submittedAmount FROM EconomyDailyUsage").fetchone()[0]
        committed = connection.execute(
            "SELECT COUNT(*) FROM EconomyTransaction WHERE operation='PLAYER_TRANSFER_ETM' AND status='COMMITTED'"
        ).fetchone()[0]
        connection.close()
        self.assertEqual(usage, 1_200_000)
        self.assertEqual(committed, 1)

    async def test_exchange_info_mode_is_read_only(self):
        before = sqlite3.connect(self.database.path)
        before_counts = (
            before.execute("SELECT COUNT(*) FROM RpgProfile").fetchone()[0],
            before.execute("SELECT COUNT(*) FROM EconomyDailyUsage").fetchone()[0],
            before.execute("SELECT COUNT(*) FROM EconomyTransaction").fetchone()[0],
        )
        before.close()
        info = await get_exchange_info(self.database.path, "1", "10", enabled=False, now=self.now)
        self.assertEqual((info.level, info.used_today, info.remaining), (1, 0, 0))
        after = sqlite3.connect(self.database.path)
        after_counts = (
            after.execute("SELECT COUNT(*) FROM RpgProfile").fetchone()[0],
            after.execute("SELECT COUNT(*) FROM EconomyDailyUsage").fetchone()[0],
            after.execute("SELECT COUNT(*) FROM EconomyTransaction").fetchone()[0],
        )
        after.close()
        self.assertEqual(before_counts, after_counts)

    async def test_exchange_example_and_supply_accounting(self):
        await ensure_profile(self.database.path, "1", "10", now=self.now)
        connection = sqlite3.connect(self.database.path)
        connection.execute("UPDATE RpgProfile SET level=20 WHERE guildId='1' AND userId='10'")
        connection.commit()
        connection.close()
        await fund_user(self.database.path, "1", "10", 100_000, "fund:exchange")
        result = await exchange_etm_to_ecy(
            self.database.path, guild_id="1", user_id="10", amount=100_000,
            request_id="exchange-one", now=self.now,
        )
        self.assertTrue(result.ok)
        connection = sqlite3.connect(self.database.path)
        wallet = connection.execute(
            "SELECT etmBalance,ecyBalance FROM EconomyWallet WHERE userId='10'"
        ).fetchone()
        systems = dict(connection.execute(
            "SELECT accountCode,balance FROM EconomySystemAccount WHERE accountCode IN "
            "('ETM_GENERAL','ETM_RESERVE','ETM_BURN')"
        ).fetchall())
        usage = connection.execute(
            "SELECT usageType,submittedAmount FROM EconomyDailyUsage"
        ).fetchone()
        unbalanced = connection.execute(
            "SELECT COUNT(*) FROM (SELECT transactionId,currency,SUM(amount) total FROM EconomyLedger "
            "GROUP BY transactionId,currency HAVING total<>0)"
        ).fetchone()[0]
        connection.close()
        self.assertEqual(wallet, (0, 9_500))
        self.assertEqual(systems, {"ETM_GENERAL": 4_000, "ETM_RESERVE": 500, "ETM_BURN": 95_500})
        self.assertEqual(usage, ("EXCHANGE_ETM", 100_000))
        self.assertEqual(unbalanced, 0)

    async def test_exchange_rejects_non_multiple_and_low_level(self):
        bad = await exchange_etm_to_ecy(
            self.database.path, guild_id="1", user_id="10", amount=150,
            request_id="bad", now=self.now,
        )
        self.assertEqual(bad.code, "invalid_multiple")
        await fund_user(self.database.path, "1", "10", 100_000, "fund:locked")
        locked = await exchange_etm_to_ecy(
            self.database.path, guild_id="1", user_id="10", amount=100_000,
            request_id="locked", now=self.now,
        )
        self.assertEqual(locked.code, "level_locked")


if __name__ == "__main__":
    unittest.main()
