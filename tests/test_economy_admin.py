import sqlite3
import unittest

from economy.controls import is_whitelisted, set_whitelist
from economy.database import initialize_database
from economy.treasury import system_seed, treasury_grant
from economy.wallets import admin_mint, admin_remove
from tests.economy_test_utils import TempEconomyDatabase


class EconomyAdminTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = TempEconomyDatabase()
        await initialize_database(self.db.path)

    async def asyncTearDown(self):
        self.db.close()

    async def test_unlisted_owner_or_admin_has_no_service_bypass(self):
        result = await admin_mint(
            self.db.path, guild_id="1", actor_id="999", target_user_id="20",
            currency="ETM", amount=100, reason="must be denied", idempotency_key="no-bypass",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "unauthorized")

    async def test_disabled_whitelist_is_denied(self):
        await set_whitelist(self.db.path, guild_id="1", user_id="10", enabled=False,
                            actor_id="999", reason="disabled for test")
        self.assertFalse(await is_whitelisted(self.db.path, "1", "10"))
        result = await admin_mint(
            self.db.path, guild_id="1", actor_id="10", target_user_id="20",
            currency="ETM", amount=100, reason="must be denied", idempotency_key="disabled",
        )
        self.assertEqual(result.code, "unauthorized")
        connection = sqlite3.connect(self.db.path)
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM AuditLog WHERE action='economy-whitelist-disable' AND source='economy_v1'"
        ).fetchone()[0]
        connection.close()
        self.assertEqual(audit_count, 1)

    async def test_remove_moves_value_to_burn(self):
        await set_whitelist(self.db.path, guild_id="1", user_id="10", enabled=True,
                            actor_id="999", reason="enable test")
        await admin_mint(
            self.db.path, guild_id="1", actor_id="10", target_user_id="20",
            currency="ETM", amount=100, reason="fund test", idempotency_key="fund-burn",
        )
        result = await admin_remove(
            self.db.path, guild_id="1", actor_id="10", target_user_id="20",
            currency="ETM", amount=40, reason="burn test", idempotency_key="burn-test",
        )
        self.assertTrue(result.ok)
        connection = sqlite3.connect(self.db.path)
        wallet = connection.execute("SELECT etmBalance FROM EconomyWallet WHERE userId='20'").fetchone()[0]
        burned = connection.execute(
            "SELECT balance FROM EconomySystemAccount WHERE accountCode='ETM_BURN'"
        ).fetchone()[0]
        connection.close()
        self.assertEqual((wallet, burned), (60, 40))

    async def test_seed_once_and_treasury_grant_whitelist(self):
        seed = await system_seed(
            self.db.path, guild_id="1", account_code="ETM_GENERAL", amount=1000,
            seed_key="staging-general", reason="temporary test seed", idempotency_key="seed-once",
        )
        replay = await system_seed(
            self.db.path, guild_id="1", account_code="ETM_GENERAL", amount=1000,
            seed_key="staging-general", reason="temporary test seed", idempotency_key="different-key",
        )
        self.assertTrue(seed.ok)
        self.assertTrue(replay.ok and replay.replayed)
        denied = await treasury_grant(
            self.db.path, guild_id="1", actor_id="10", target_user_id="20", currency="ETM",
            amount=100, account_code="ETM_GENERAL", reason="grant denied", idempotency_key="grant-denied",
        )
        self.assertEqual(denied.code, "unauthorized")
        await set_whitelist(self.db.path, guild_id="1", user_id="10", enabled=True,
                            actor_id="999", reason="enable grant")
        granted = await treasury_grant(
            self.db.path, guild_id="1", actor_id="10", target_user_id="20", currency="ETM",
            amount=100, account_code="ETM_GENERAL", reason="grant test", idempotency_key="grant-ok",
        )
        self.assertTrue(granted.ok)

    async def test_reserve_cannot_grant(self):
        await set_whitelist(self.db.path, guild_id="1", user_id="10", enabled=True,
                            actor_id="999", reason="enable test")
        result = await treasury_grant(
            self.db.path, guild_id="1", actor_id="10", target_user_id="20", currency="ETM",
            amount=1, account_code="ETM_RESERVE", reason="invalid source", idempotency_key="reserve-grant",
        )
        self.assertEqual(result.code, "invalid_account")


if __name__ == "__main__":
    unittest.main()
