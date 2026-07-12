import asyncio
import sqlite3
import unittest

from economy.controls import set_whitelist
from economy.database import initialize_database
from economy.ledger import AccountDelta, execute_transaction, reverse_committed_transaction
from economy.wallets import admin_mint, admin_remove
from tests.economy_test_utils import TempEconomyDatabase


class EconomyTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = TempEconomyDatabase()
        await initialize_database(self.db.path)
        await set_whitelist(self.db.path, guild_id="1", user_id="10", enabled=True,
                            actor_id="99", reason="test whitelist")

    async def asyncTearDown(self):
        self.db.close()

    async def test_header_ledger_commit_and_replay(self):
        first = await admin_mint(
            self.db.path, guild_id="1", actor_id="10", target_user_id="20",
            currency="ETM", amount=1000, reason="test mint", idempotency_key="mint-1",
        )
        second = await admin_mint(
            self.db.path, guild_id="1", actor_id="10", target_user_id="20",
            currency="ETM", amount=1000, reason="test mint", idempotency_key="mint-1",
        )
        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        self.assertTrue(second.replayed)
        self.assertEqual(first.transaction_id, second.transaction_id)
        connection = sqlite3.connect(self.db.path)
        status = connection.execute("SELECT status FROM EconomyTransaction").fetchone()[0]
        ledger_sum = connection.execute("SELECT SUM(amount) FROM EconomyLedger").fetchone()[0]
        balance = connection.execute("SELECT etmBalance FROM EconomyWallet WHERE userId='20'").fetchone()[0]
        connection.close()
        self.assertEqual(status, "COMMITTED")
        self.assertEqual(ledger_sum, 0)
        self.assertEqual(balance, 1000)

    async def test_pending_is_not_replayed(self):
        connection = sqlite3.connect(self.db.path)
        connection.execute(
            "INSERT INTO EconomyTransaction "
            "(transactionId,guildId,idempotencyKey,operation,source,metadataJson,status,createdAt) "
            "VALUES ('pending','1','pending-key','TEST','TEST','{}','PENDING','now')"
        )
        connection.commit()
        connection.close()
        result = await admin_mint(
            self.db.path, guild_id="1", actor_id="10", target_user_id="20",
            currency="ETM", amount=1, reason="test pending", idempotency_key="pending-key",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "idempotency_conflict")

    async def test_failure_rolls_back_pending_header(self):
        result = await execute_transaction(
            self.db.path, guild_id="1", idempotency_key="bad", operation="TEST", source="TEST",
            actor_id="10", reason="unbalanced test",
            deltas=(AccountDelta("SYSTEM", "ETM_ISSUANCE", "ETM", -100),),
        )
        self.assertFalse(result.ok)
        connection = sqlite3.connect(self.db.path)
        self.assertEqual(connection.execute(
            "SELECT COUNT(*) FROM EconomyTransaction WHERE idempotencyKey='bad'"
        ).fetchone()[0], 0)
        connection.close()

    async def test_concurrent_duplicate_key_commits_once(self):
        async def invoke():
            return await admin_mint(
                self.db.path, guild_id="1", actor_id="10", target_user_id="30",
                currency="ETM", amount=500, reason="concurrent duplicate", idempotency_key="same-key",
            )
        results = await asyncio.gather(*(invoke() for _ in range(20)))
        self.assertTrue(all(result.ok for result in results))
        connection = sqlite3.connect(self.db.path)
        self.assertEqual(connection.execute(
            "SELECT etmBalance FROM EconomyWallet WHERE userId='30'"
        ).fetchone()[0], 500)
        self.assertEqual(connection.execute(
            "SELECT COUNT(*) FROM EconomyTransaction WHERE idempotencyKey='same-key'"
        ).fetchone()[0], 1)
        connection.close()

    async def test_conflicting_removes_have_one_winner(self):
        await admin_mint(
            self.db.path, guild_id="1", actor_id="10", target_user_id="40",
            currency="ETM", amount=100, reason="fund test", idempotency_key="fund-remove",
        )
        async def remove(key):
            return await admin_remove(
                self.db.path, guild_id="1", actor_id="10", target_user_id="40",
                currency="ETM", amount=60, reason="remove race", idempotency_key=key,
            )
        results = await asyncio.gather(remove("remove-a"), remove("remove-b"))
        self.assertEqual(sum(1 for result in results if result.ok), 1)
        connection = sqlite3.connect(self.db.path)
        self.assertEqual(connection.execute(
            "SELECT etmBalance FROM EconomyWallet WHERE userId='40'"
        ).fetchone()[0], 40)
        connection.close()

    async def test_reversal_is_compensating_and_atomic(self):
        minted = await admin_mint(
            self.db.path, guild_id="1", actor_id="10", target_user_id="50",
            currency="ETM", amount=75, reason="reversal source", idempotency_key="reverse-source",
        )
        reversed_result = await reverse_committed_transaction(
            self.db.path, guild_id="1", actor_id="10",
            original_transaction_id=minted.transaction_id,
            reason="reverse test transaction", idempotency_key="reverse-result",
        )
        self.assertTrue(reversed_result.ok)
        connection = sqlite3.connect(self.db.path)
        original_status = connection.execute(
            "SELECT status FROM EconomyTransaction WHERE transactionId=?", (minted.transaction_id,)
        ).fetchone()[0]
        wallet = connection.execute("SELECT etmBalance FROM EconomyWallet WHERE userId='50'").fetchone()[0]
        ledger_sum = connection.execute("SELECT SUM(amount) FROM EconomyLedger").fetchone()[0]
        connection.close()
        self.assertEqual(original_status, "REVERSED")
        self.assertEqual(wallet, 0)
        self.assertEqual(ledger_sum, 0)


if __name__ == "__main__":
    unittest.main()
