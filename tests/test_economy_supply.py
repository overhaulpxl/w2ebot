import unittest

from economy.controls import set_whitelist
from economy.database import initialize_database
from economy.treasury import get_supply_report, system_seed
from economy.wallets import admin_mint, admin_remove
from tests.economy_test_utils import TempEconomyDatabase


class EconomySupplyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = TempEconomyDatabase()
        await initialize_database(self.db.path)
        await set_whitelist(self.db.path, guild_id="1", user_id="10", enabled=True,
                            actor_id="99", reason="supply test")

    async def asyncTearDown(self):
        self.db.close()

    async def test_exact_supply_definitions(self):
        await admin_mint(
            self.db.path, guild_id="1", actor_id="10", target_user_id="20",
            currency="ETM", amount=1000, reason="supply mint", idempotency_key="supply-mint",
        )
        await admin_remove(
            self.db.path, guild_id="1", actor_id="10", target_user_id="20",
            currency="ETM", amount=100, reason="supply burn", idempotency_key="supply-burn",
        )
        await system_seed(
            self.db.path, guild_id="1", account_code="ETM_GENERAL", amount=500,
            seed_key="supply-seed", reason="temporary supply test", idempotency_key="supply-seed",
        )
        report = await get_supply_report(self.db.path, "1")
        etm = report["ETM"]
        self.assertEqual(etm["user_wallet_balances"], 900)
        self.assertEqual(etm["spendable_treasury_balances"], 500)
        self.assertEqual(etm["burn_account_balance"], 100)
        self.assertEqual(etm["net_issued_supply"], 1500)
        self.assertEqual(etm["circulating_supply"], 1400)
        self.assertEqual(etm["non_circulating_supply"], 0)
        self.assertEqual(etm["burned_supply"], 100)
        self.assertEqual(etm["issuance_balance"], -1500)
        self.assertTrue(etm["issuance_matches"])
        self.assertTrue(report["ledger_zero_sum"])


if __name__ == "__main__":
    unittest.main()
