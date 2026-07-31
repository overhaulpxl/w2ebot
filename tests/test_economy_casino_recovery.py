import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from economy.casino import (
    reserve_session, resolve_review_session, seed_casino_bankroll, set_casino_authorization,
)
from economy.casino_games import DeterministicRng
from economy.database import ensure_phase1_schema
from economy.ledger import AccountDelta, execute_transaction
from economy.phase5_migrations import apply_phase5_staging
from economy.phase5_recovery import (
    claim_casino_outbox, finalize_casino_outbox, recover_phase5_runtime,
)


class CasinoRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "recovery.db")
        connection = sqlite3.connect(self.path)
        ensure_phase1_schema(connection)
        connection.commit()
        connection.close()
        apply_phase5_staging(self.path, production_db=self.path + ".prod")
        await set_casino_authorization(
            self.path, guild_id="1", user_id="9", permission_class="CASINO_FINANCIAL",
            enabled=True, actor_id="99", reason="Test authorization",
        )
        await seed_casino_bankroll(self.path, guild_id="1", actor_id="9", active_members=0)
        await execute_transaction(
            self.path, guild_id="1", idempotency_key="fund", operation="TEST", source="TEST",
            actor_id="9", reason="Casino recovery funding", feature=None,
            deltas=(AccountDelta("SYSTEM", "ECY_ISSUANCE", "ECY", -1_000_000),
                    AccountDelta("USER", "2", "ECY", 1_000_000, "2")),
        )

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_restart_reuses_static_outcome(self):
        result = await reserve_session(
            self.path, guild_id="1", user_id="2", request_id="done", game="BOX", stake=1_000,
            rng=DeterministicRng(5),
        )
        self.assertTrue(result.ok)
        recovery = await recover_phase5_runtime(self.path, guild_id="1")
        self.assertEqual(recovery["scanned"], 0)
        async with aiosqlite.connect(self.path) as db:
            self.assertEqual((await (await db.execute("SELECT COUNT(*) FROM CasinoSession")).fetchone())[0], 1)

    async def test_stale_blackjack_auto_stands_and_releases_reservation(self):
        stale = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
        result = await reserve_session(
            self.path, guild_id="1", user_id="2", request_id="stale", game="BLACKJACK", stake=1_000,
            rng=DeterministicRng(9), now=stale,
        )
        self.assertTrue(result.ok)
        recovery = await recover_phase5_runtime(self.path, guild_id="1")
        self.assertEqual(recovery["settled"], 1, recovery)
        async with aiosqlite.connect(self.path) as db:
            session = await (await db.execute("SELECT status,reservationKey FROM CasinoSession")).fetchone()
            reservation = await (await db.execute("SELECT status FROM CasinoBankrollReservation")).fetchone()
        self.assertEqual(session, ("COMMITTED", None))
        self.assertEqual(reservation[0], "RELEASED")

    async def test_outbox_lease_and_finalize_are_idempotent(self):
        await reserve_session(
            self.path, guild_id="1", user_id="2", request_id="outbox", game="GACHA", stake=1_000,
            rng=DeterministicRng(4),
        )
        rows = await claim_casino_outbox(self.path, lease_owner="worker")
        self.assertEqual(len(rows), 1)
        self.assertEqual(await claim_casino_outbox(self.path, lease_owner="other"), [])
        self.assertTrue(await finalize_casino_outbox(
            self.path, event_id=rows[0]["eventId"], lease_owner="worker", sent=True, message_id="7",
        ))
        self.assertFalse(await finalize_casino_outbox(
            self.path, event_id=rows[0]["eventId"], lease_owner="worker", sent=True, message_id="8",
        ))

    async def test_reviewed_refund_is_authorized_balanced_and_terminal(self):
        result = await reserve_session(
            self.path, guild_id="1", user_id="2", request_id="review", game="BLACKJACK", stake=10_000,
            rng=DeterministicRng(12),
        )
        self.assertTrue(result.ok)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE CasinoSession SET status='REVIEW_REQUIRED' WHERE sessionId=?", (result.session_id,))
            await db.execute("UPDATE CasinoSettlement SET status='REVIEW_REQUIRED' WHERE sessionId=?", (result.session_id,))
            await db.execute("UPDATE CasinoBankrollReservation SET status='REVIEW_REQUIRED' WHERE sessionId=?", (result.session_id,))
            await db.commit()
        denied = await resolve_review_session(
            self.path, guild_id="1", actor_id="8", session_id=result.session_id,
            resolution="REFUND", request_id="denied", reason="Denied test",
        )
        self.assertEqual(denied.code, "unauthorized")
        await set_casino_authorization(
            self.path, guild_id="1", user_id="8", permission_class="CASINO_RECOVERY",
            enabled=True, actor_id="99", reason="Recovery test authorization",
        )
        refunded = await resolve_review_session(
            self.path, guild_id="1", actor_id="8", session_id=result.session_id,
            resolution="REFUND", request_id="refund", reason="Reviewed refund test",
        )
        self.assertTrue(refunded.ok, refunded)
        async with aiosqlite.connect(self.path) as db:
            session = await (await db.execute("SELECT status,reservationKey FROM CasinoSession WHERE sessionId=?", (result.session_id,))).fetchone()
            wallet = await (await db.execute("SELECT ecyBalance FROM EconomyWallet WHERE guildId='1' AND userId='2'")).fetchone()
            unbalanced = await (await db.execute(
                "SELECT COUNT(*) FROM (SELECT transactionId,SUM(amount) total FROM EconomyLedger GROUP BY transactionId HAVING total<>0)"
            )).fetchone()
        self.assertEqual(session, ("VOID", None))
        self.assertEqual(wallet[0], 1_000_000)
        self.assertEqual(unbalanced[0], 0)


if __name__ == "__main__":
    unittest.main()
