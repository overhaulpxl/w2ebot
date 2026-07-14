import sqlite3
import unittest

from economy.crypto import (
    execute_trade, is_crypto_authorized, list_crypto_authorizations,
    parse_asset_units, portfolio, set_crypto_authorization, trade_amounts,
)
from economy.constants import ASSET_UNIT_SCALE
from tests.crypto_test_utils import TempCryptoDatabase


class CryptoTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = TempCryptoDatabase()
        await self.database.seed()

    async def asyncTearDown(self):
        self.database.close()

    def test_exact_unit_parsing_and_checked_fees(self):
        self.assertEqual(parse_asset_units("1.00000001"), 100_000_001)
        self.assertIsNone(parse_asset_units("all"))
        with self.assertRaises(ValueError):
            parse_asset_units("0.000000001")
        amounts = trade_amounts(ASSET_UNIT_SCALE, 10_000)
        self.assertEqual((amounts["gross"], amounts["fee"]), (10_000, 200))
        self.assertEqual(amounts["marketFee"] + amounts["treasuryFee"] + amounts["burnFee"], 200)

    async def test_buy_all_replay_sell_all_and_profit(self):
        await self.database.fund_user("2", 100_000)
        buy = await execute_trade(
            self.database.path, guild_id="1", user_id="2", request_id="buy-1",
            side="BUY", symbol="ETHR", quantity="all",
        )
        self.assertTrue(buy.ok)
        self.assertEqual(buy.receipt["gross"] + buy.receipt["fee"], 100_000)
        replay = await execute_trade(
            self.database.path, guild_id="1", user_id="2", request_id="buy-1",
            side="BUY", symbol="ETHR", quantity="1",
        )
        self.assertTrue(replay.ok)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.receipt, buy.receipt)
        sell = await execute_trade(
            self.database.path, guild_id="1", user_id="2", request_id="sell-1",
            side="SELL", symbol="ETHR", quantity="all",
        )
        self.assertTrue(sell.ok)
        self.assertEqual(sell.receipt["holdingUnits"], 0)
        self.assertEqual(sell.receipt["realizedProfitDeltaEcy"], -3_920)
        data = await portfolio(self.database.path, guild_id="1", user_id="2")
        self.assertEqual(data["holdings"], [])
        self.assertEqual(len(data["history"]), 2)

    async def test_partial_basis_uses_integer_floor(self):
        await self.database.fund_user("3", 20_400)
        buy = await execute_trade(
            self.database.path, guild_id="1", user_id="3", request_id="buy",
            side="BUY", symbol="ETHR", quantity="2",
        )
        self.assertTrue(buy.ok)
        sell = await execute_trade(
            self.database.path, guild_id="1", user_id="3", request_id="sell",
            side="SELL", symbol="ETHR", quantity="0.5",
        )
        self.assertTrue(sell.ok)
        self.assertEqual(sell.receipt["costBasisDeltaEcy"], 5_100)
        self.assertEqual(sell.receipt["holdingCostBasisEcy"], 15_300)

    async def test_failed_trade_has_no_partial_state(self):
        await self.database.fund_user("4", 49)
        result = await execute_trade(
            self.database.path, guild_id="1", user_id="4", request_id="small",
            side="BUY", symbol="ETHR", quantity="all",
        )
        self.assertFalse(result.ok)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM CryptoTrade").fetchone()[0], 0)
        self.assertEqual(connection.execute("SELECT ecyBalance FROM EconomyWallet WHERE userId='4'").fetchone()[0], 49)
        connection.close()

    async def test_forced_crash_rolls_back_envelope_holding_wallet_and_ledger(self):
        for stage in ("after_envelope", "after_holding", "after_ledger"):
            with self.subTest(stage=stage):
                user_id = {"after_envelope": "61", "after_holding": "62", "after_ledger": "63"}[stage]
                await self.database.fund_user(user_id, 10_200, key=f"fund:{stage}")
                with self.assertRaises(RuntimeError):
                    await execute_trade(
                        self.database.path, guild_id="1", user_id=user_id,
                        request_id=f"crash:{stage}", side="BUY", symbol="ETHR", quantity="1",
                        _failure_stage=stage,
                    )
                connection = sqlite3.connect(self.database.path)
                self.assertEqual(connection.execute(
                    "SELECT ecyBalance FROM EconomyWallet WHERE guildId='1' AND userId=?", (user_id,)
                ).fetchone()[0], 10_200)
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM CryptoTrade WHERE requestId=?", (f"crash:{stage}",)
                ).fetchone()[0], 0)
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM CryptoHolding WHERE userId=?", (user_id,)
                ).fetchone()[0], 0)
                connection.close()

    async def test_direct_trade_plan_mutation_is_rejected(self):
        await self.database.fund_user("5", 10_200)
        result = await execute_trade(
            self.database.path, guild_id="1", user_id="5", request_id="immutable",
            side="BUY", symbol="ETHR", quantity="1",
        )
        self.assertTrue(result.ok)
        connection = sqlite3.connect(self.database.path)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("UPDATE CryptoTrade SET grossEcy=grossEcy+1 WHERE requestId='immutable'")
        connection.close()

    async def test_guild_scoped_authorization_is_audited(self):
        await set_crypto_authorization(
            self.database.path, guild_id="1", user_id="9",
            permission_class="CRYPTO_RECOVERY", enabled=True,
            actor_id="owner", reason="staging recovery operator",
        )
        self.assertTrue(await is_crypto_authorized(
            self.database.path, "1", "9", "CRYPTO_RECOVERY",
        ))
        self.assertFalse(await is_crypto_authorized(
            self.database.path, "2", "9", "CRYPTO_RECOVERY",
        ))
        rows = await list_crypto_authorizations(self.database.path, "1")
        self.assertEqual(rows[0][:3], ("9", "CRYPTO_RECOVERY", 1))
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM CryptoAuthorizationAudit").fetchone()[0], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM CryptoAuthorizationAudit")
        connection.close()
