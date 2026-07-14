import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

import aiosqlite

from economy.casino import (
    adjust_casino_bankroll, casino_status, is_casino_authorized, reserve_session,
    seed_casino_bankroll, set_casino_authorization, set_casino_paused,
)
from economy.casino_games import DeterministicRng
from economy.database import ensure_phase1_schema
from economy.ledger import AccountDelta, execute_transaction
from economy.phase5_migrations import apply_phase5_staging, reconcile_phase5_staging


class CasinoTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "casino.db")
        connection = sqlite3.connect(self.path)
        ensure_phase1_schema(connection)
        connection.commit()
        connection.close()
        apply_phase5_staging(self.path, production_db=self.path + ".production")
        await set_casino_authorization(
            self.path, guild_id="1", user_id="9", permission_class="CASINO_FINANCIAL",
            enabled=True, actor_id="99", reason="Test authorization",
        )
        seeded = await seed_casino_bankroll(self.path, guild_id="1", actor_id="9", active_members=0)
        self.assertTrue(seeded.ok)

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def fund(self, user_id, amount=2_000_000):
        result = await execute_transaction(
            self.path, guild_id="1", idempotency_key=f"fund:{user_id}", operation="TEST_FUND",
            source="TEST", actor_id="9", reason="Casino test funding", feature=None,
            deltas=(AccountDelta("SYSTEM", "ECY_ISSUANCE", "ECY", -amount),
                    AccountDelta("USER", str(user_id), "ECY", amount, str(user_id))),
        )
        self.assertTrue(result.ok)

    async def test_authorization_is_separate_and_has_no_owner_bypass(self):
        self.assertFalse(await is_casino_authorized(self.path, "1", "99", "CASINO_FINANCIAL"))
        self.assertTrue(await is_casino_authorized(self.path, "1", "9", "CASINO_FINANCIAL"))
        denied = await seed_casino_bankroll(self.path, guild_id="2", actor_id="99", active_members=0)
        self.assertEqual(denied.code, "unauthorized")

    async def test_pause_requires_control_authorization_in_service(self):
        denied = await set_casino_paused(
            self.path, guild_id="1", actor_id="99", paused=True, reason="Owner tanpa kelas kontrol",
        )
        self.assertEqual(denied.code, "unauthorized")
        await set_casino_authorization(
            self.path, guild_id="1", user_id="7", permission_class="CASINO_CONTROL",
            enabled=True, actor_id="99", reason="Kontrol test",
        )
        allowed = await set_casino_paused(
            self.path, guild_id="1", actor_id="7", paused=True, reason="Pause test",
        )
        self.assertTrue(allowed.ok)

    async def test_committed_retry_replays_one_receipt_and_ledger(self):
        await self.fund("2")
        first = await reserve_session(
            self.path, guild_id="1", user_id="2", request_id="same", game="SLOT", stake=1_000,
            rng=DeterministicRng(1),
        )
        second = await reserve_session(
            self.path, guild_id="1", user_id="2", request_id="same", game="SLOT", stake=1_000,
            rng=DeterministicRng(999),
        )
        self.assertTrue(first.ok)
        self.assertTrue(second.replayed)
        self.assertEqual(first.receipt, second.receipt)
        async with aiosqlite.connect(self.path) as db:
            self.assertEqual((await (await db.execute("SELECT COUNT(*) FROM CasinoSession")).fetchone())[0], 1)
            tx = (await (await db.execute("SELECT transactionId FROM CasinoSettlement")).fetchone())[0]
            total = (await (await db.execute("SELECT SUM(amount) FROM EconomyLedger WHERE transactionId=?", (tx,))).fetchone())[0]
            self.assertEqual(total, 0)

    async def test_invalid_payload_creates_no_session_and_consumes_no_rng(self):
        await self.fund("2")

        class FailingRng:
            def randbelow(self, upper):
                raise AssertionError("RNG tidak boleh dipakai saat preflight gagal")

        result = await reserve_session(
            self.path, guild_id="1", user_id="2", request_id="invalid-choice",
            game="COINFLIP", stake=1_000, payload={"choice": "sisi-ketiga"}, rng=FailingRng(),
        )
        self.assertEqual(result.code, "invalid_input")
        async with aiosqlite.connect(self.path) as db:
            count = (await (await db.execute("SELECT COUNT(*) FROM CasinoSession")).fetchone())[0]
        self.assertEqual(count, 0)

    async def test_different_request_race_keeps_one_unresolved_blackjack(self):
        await self.fund("2")
        results = await asyncio.gather(*(
            reserve_session(self.path, guild_id="1", user_id="2", request_id=f"request-{index}",
                            game="BLACKJACK", stake=10_000, rng=DeterministicRng(index))
            for index in range(8)
        ))
        self.assertEqual(sum(result.ok for result in results), 1)
        async with aiosqlite.connect(self.path) as db:
            count = (await (await db.execute(
                "SELECT COUNT(*) FROM CasinoSession WHERE status IN ('RESERVED','ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED')"
            )).fetchone())[0]
        self.assertEqual(count, 1)

    async def test_active_reservation_reduces_available_and_cap(self):
        await self.fund("2")
        await self.fund("3")
        first = await reserve_session(
            self.path, guild_id="1", user_id="2", request_id="bj-one", game="BLACKJACK", stake=100_000,
            rng=DeterministicRng(2),
        )
        self.assertTrue(first.ok)
        state = await casino_status(self.path, "1")
        self.assertEqual(state["reservedLiabilityEcy"], 400_000)
        self.assertEqual(state["availableBankrollEcy"], 24_700_000)
        self.assertEqual(state["exposureCapEcy"], 494_000)
        denied = await reserve_session(
            self.path, guild_id="1", user_id="3", request_id="bj-two", game="BLACKJACK", stake=124_000,
            rng=DeterministicRng(3),
        )
        self.assertEqual(denied.code, "exposure_limit")
        self.assertEqual(denied.receipt["effectiveMaximumStakeEcy"], 123_000)

    async def test_withdrawal_cannot_strand_active_liability(self):
        await self.fund("2")
        active = await reserve_session(
            self.path, guild_id="1", user_id="2", request_id="withdraw-guard",
            game="BLACKJACK", stake=100_000, rng=DeterministicRng(2),
        )
        self.assertTrue(active.ok)
        blocked = await adjust_casino_bankroll(
            self.path, guild_id="1", actor_id="9", amount=24_700_001,
            direction="withdraw", request_id="too-much", reason="Test reserve protection",
        )
        self.assertEqual(blocked.code, "reserved_exposure")

    async def test_blackjack_public_state_never_exposes_shoe_or_hole_card(self):
        await self.fund("2")
        active = await reserve_session(
            self.path, guild_id="1", user_id="2", request_id="hidden-state",
            game="BLACKJACK", stake=10_000, rng=DeterministicRng(2),
        )
        self.assertTrue(active.ok)
        self.assertNotIn("shoe", active.receipt)
        self.assertNotIn("dealer", active.receipt)
        self.assertEqual(len(active.receipt["dealerUpCard"].split("-")), 3)
        async with aiosqlite.connect(self.path) as db:
            state = __import__("json").loads((await (await db.execute(
                "SELECT stateJson FROM CasinoSession WHERE sessionId=?", (active.session_id,),
            )).fetchone())[0])
        self.assertIn("shoe", state)
        self.assertEqual(len(state["dealer"]), 2)

    async def test_gacha_has_zero_liability_but_committed_loss(self):
        await self.fund("2")
        result = await reserve_session(
            self.path, guild_id="1", user_id="2", request_id="gacha", game="GACHA", stake=1_000,
            rng=DeterministicRng(4),
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.receipt["grossPayoutEcy"], 0)
        async with aiosqlite.connect(self.path) as db:
            wallet = (await (await db.execute("SELECT ecyBalance FROM EconomyWallet WHERE guildId='1' AND userId='2'")).fetchone())[0]
            reservations = (await (await db.execute("SELECT COUNT(*) FROM CasinoBankrollReservation")).fetchone())[0]
        self.assertEqual(wallet, 1_999_000)
        self.assertEqual(reservations, 0)

    async def test_integrity_and_foreign_keys_after_concurrent_work(self):
        for user in range(10, 20):
            await self.fund(str(user), 20_000)
        await asyncio.gather(*(
            reserve_session(self.path, guild_id="1", user_id=str(user), request_id=f"slot-{user}",
                            game="SLOT", stake=1_000, rng=DeterministicRng(user))
            for user in range(10, 20)
        ))
        report = reconcile_phase5_staging(self.path)
        self.assertTrue(report["reconciled"], report)


if __name__ == "__main__":
    unittest.main()
