from datetime import datetime, timedelta, timezone
import sqlite3
import unittest

from economy.mining import (
    calculate_mining_yield, change_target, claim_rig, mining_allocation,
    pay_maintenance, purchase_rig,
)
from tests.mining_test_utils import TempMiningDatabase


class MiningArithmeticTests(unittest.TestCase):
    def test_eternal_full_day_minimum_price_avoids_intermediate_overflow(self):
        result = calculate_mining_yield(1_500_000, 86_400, 2_000)
        self.assertEqual(result["numerator"], "12960000000000000000")
        self.assertEqual(result["creditedUnits"], 75_000_000_000)
        self.assertLessEqual(result["creditedUnits"], 9_223_372_036_854_775_807)

    def test_fractional_carry_is_bounded_across_repeated_checkpoints(self):
        pending = carry = 0
        for _ in range(96):
            result = calculate_mining_yield(10_000, 900, 13_000, carry, pending)
            pending, carry = result["pendingUnitsAfter"], result["resultingCarry"]
        self.assertGreater(pending, 0)
        self.assertGreaterEqual(carry, 0)
        self.assertLess(carry, 1_000_000_000)

    def test_pending_overflow_rejected(self):
        with self.assertRaises(OverflowError):
            calculate_mining_yield(1_500_000, 86_400, 2_000, pending_units=9_223_372_036_854_775_807)

    def test_eternal_full_day_maximum_phase6_price(self):
        result = calculate_mining_yield(1_500_000, 86_400, 65_000)
        self.assertGreater(result["creditedUnits"], 0)
        self.assertLessEqual(result["creditedUnits"], 9_223_372_036_854_775_807)

    def test_allocation_is_exact(self):
        self.assertEqual(mining_allocation(500_000), (400_000, 50_000, 50_000))


class MiningSettlementTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = await TempMiningDatabase().initialize()
        await self.database.fund_user()
        self.now = datetime.now(timezone.utc)

    async def asyncTearDown(self):
        self.database.close()

    async def _active_rig(self):
        purchase = await purchase_rig(
            self.database.path, guild_id="1", user_id="2", request_id="purchase",
            rig_definition_id="rig_basic", observed_at=self.now.isoformat(),
        )
        self.assertTrue(purchase.ok)
        rig_id = purchase.receipt["rigInstanceId"]
        maintenance = await pay_maintenance(
            self.database.path, guild_id="1", user_id="2", request_id="maintenance",
            rig_instance_id=rig_id, observed_at=(self.now + timedelta(seconds=1)).isoformat(),
        )
        self.assertTrue(maintenance.ok)
        return rig_id

    async def test_purchase_is_atomic_and_replays_same_receipt(self):
        first = await purchase_rig(
            self.database.path, guild_id="1", user_id="2", request_id="same",
            rig_definition_id="rig_basic", observed_at=self.now.isoformat(),
        )
        second = await purchase_rig(
            self.database.path, guild_id="1", user_id="2", request_id="same",
            rig_definition_id="rig_basic", observed_at=self.now.isoformat(),
        )
        self.assertTrue(first.ok)
        self.assertTrue(second.replayed)
        self.assertEqual(first.receipt, second.receipt)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM MiningRigInstance").fetchone()[0], 1)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM MiningPurchase").fetchone()[0], 1)
        connection.close()

    async def test_asset_claim_has_no_currency_transaction_and_zero_cost_basis(self):
        rig_id = await self._active_rig()
        result = await claim_rig(
            self.database.path, guild_id="1", user_id="2", request_id="claim",
            rig_instance_id=rig_id, observed_at=(self.now + timedelta(hours=24)).isoformat(),
        )
        self.assertTrue(result.ok)
        self.assertIsNone(result.receipt["currencyTransaction"])
        connection = sqlite3.connect(self.database.path)
        operation = connection.execute(
            "SELECT transactionId FROM MiningOperation WHERE operationType='CLAIM'"
        ).fetchone()
        holding = connection.execute(
            "SELECT units,totalCostBasisEcy,realizedProfitEcy FROM CryptoHolding WHERE guildId='1' AND userId='2' AND symbol='ETHR'"
        ).fetchone()
        balance = connection.execute(
            "SELECT SUM(unitsDelta) FROM MiningAssetLedger GROUP BY claimId,symbol"
        ).fetchone()[0]
        connection.close()
        self.assertIsNone(operation[0])
        self.assertGreater(holding[0], 0)
        self.assertEqual(holding[1:], (0, 0))
        self.assertEqual(balance, 0)

    async def test_target_change_preserves_old_pending_symbol(self):
        rig_id = await self._active_rig()
        result = await change_target(
            self.database.path, guild_id="1", user_id="2", request_id="target",
            rig_instance_id=rig_id, target_symbol="ORCL",
            observed_at=(self.now + timedelta(hours=12)).isoformat(),
        )
        self.assertTrue(result.ok)
        connection = sqlite3.connect(self.database.path)
        old_pending = connection.execute(
            "SELECT pendingUnits FROM MiningPendingAsset WHERE rigInstanceId=? AND symbol='ETHR'", (rig_id,)
        ).fetchone()[0]
        target = connection.execute(
            "SELECT targetSymbol FROM MiningRigInstance WHERE rigInstanceId=?", (rig_id,)
        ).fetchone()[0]
        connection.close()
        self.assertGreater(old_pending, 0)
        self.assertEqual(target, "ORCL")

    async def test_missing_profile_fails_before_debit_or_operation(self):
        connection = sqlite3.connect(self.database.path)
        before = connection.execute("SELECT ecyBalance FROM EconomyWallet WHERE guildId='1' AND userId='2'").fetchone()[0]
        connection.execute("DELETE FROM RpgProfile WHERE guildId='1' AND userId='2'")
        connection.commit()
        connection.close()
        result = await purchase_rig(
            self.database.path, guild_id="1", user_id="2", request_id="missing",
            rig_definition_id="rig_basic",
        )
        connection = sqlite3.connect(self.database.path)
        after = connection.execute("SELECT ecyBalance FROM EconomyWallet WHERE guildId='1' AND userId='2'").fetchone()[0]
        operations = connection.execute("SELECT COUNT(*) FROM MiningOperation WHERE requestId='missing'").fetchone()[0]
        connection.close()
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "invalid_profile")
        self.assertEqual((before, operations), (after, 0))

    async def test_level_below_ten_fails_before_operation(self):
        connection = sqlite3.connect(self.database.path)
        connection.execute("UPDATE RpgProfile SET level=9 WHERE guildId='1' AND userId='2'")
        connection.commit()
        connection.close()
        result = await purchase_rig(
            self.database.path, guild_id="1", user_id="2", request_id="low-level",
            rig_definition_id="rig_basic",
        )
        self.assertEqual(result.code, "level_required")
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute(
            "SELECT COUNT(*) FROM MiningOperation WHERE requestId='low-level'"
        ).fetchone()[0], 0)
        connection.close()

    async def test_offline_accrual_is_capped_at_twenty_four_hours(self):
        rig_id = await self._active_rig()
        result = await claim_rig(
            self.database.path, guild_id="1", user_id="2", request_id="offline-cap",
            rig_instance_id=rig_id, observed_at=(self.now + timedelta(hours=72)).isoformat(),
        )
        self.assertTrue(result.ok)
        checkpoint = result.receipt["checkpoint"]
        self.assertEqual(checkpoint["rewardedSeconds"], 86_400)
        self.assertGreater(checkpoint["discardedSeconds"], 0)
        connection = sqlite3.connect(self.database.path)
        durability = connection.execute(
            "SELECT durabilityBps FROM MiningRigInstance WHERE rigInstanceId=?", (rig_id,)
        ).fetchone()[0]
        connection.close()
        self.assertEqual(durability, 10_000)
