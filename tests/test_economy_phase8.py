import hashlib
import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

import aiosqlite

from economy.giveaways import (
    build_eligibility_evidence, cancel_giveaway, create_giveaway, draw_giveaway,
    enter_giveaway, record_winner_review, redraw_giveaway,
)
from economy.phase8_voice import reconcile_voice_snapshot
from tests.phase8_test_utils import TempPhase8Database


class ZeroRandom:
    @staticmethod
    def randbelow(value):
        return 0


class Phase8GiveawayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = TempPhase8Database()
        await self.database.fund_user("10")

    async def asyncTearDown(self):
        self.database.close()

    async def evidence(self, user="10", now=None):
        now = now or datetime(2026, 7, 14, tzinfo=timezone.utc)
        connection = sqlite3.connect(self.database.path)
        for index in range(20):
            occurred = (now - timedelta(days=index + 1)).isoformat()
            connection.execute(
                "INSERT INTO EconomyActivityEvent(eventId,guildId,userId,eventType,eventKey,points,metricValue,occurredAt,createdAt) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (f"e{user}-{index}", "1", user, "DAILY_QUEST_COMPLETED", f"q:{user}:{index}", 4, 1,
                 occurred, occurred),
            )
        connection.commit(); connection.close()
        async with aiosqlite.connect(self.database.path) as db:
            return await build_eligibility_evidence(
                db, guild_id="1", user_id=user, account_created_at=now-timedelta(days=100),
                guild_joined_at=now-timedelta(days=50), present=True, is_bot=False,
                blacklisted=False, as_of=now,
            )

    async def test_entry_draw_and_allocation_are_atomic_and_idempotent(self):
        now = datetime(2026, 7, 14, tzinfo=timezone.utc)
        evidence = await self.evidence(now=now)
        giveaway = await create_giveaway(
            self.database.path, guild_id="1", channel_id="2", host_id="3",
            request_id="create", prize="Hadiah", duration_minutes=5, now=now,
        )
        first = await enter_giveaway(
            self.database.path, guild_id="1", user_id="10", giveaway_id=giveaway.entity_id,
            request_id="entry", evidence=evidence, now=now,
        )
        replay = await enter_giveaway(
            self.database.path, guild_id="1", user_id="10", giveaway_id=giveaway.entity_id,
            request_id="entry-2", evidence=evidence, now=now,
        )
        draw = await draw_giveaway(
            self.database.path, guild_id="1", giveaway_id=giveaway.entity_id,
            request_id="draw", eligible_user_ids=["10"], participant_evidence={"10": evidence},
            random_source=ZeroRandom(), now=now,
        )
        self.assertTrue(first.ok and replay.ok and replay.replayed and draw.ok)
        self.assertEqual(draw.receipt["winnerId"], "10")
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM GiveawayTicket").fetchone()[0], 1)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM GiveawayEligibilityEvidence").fetchone()[0], 2)
        self.assertEqual(connection.execute("SELECT retainedEcy,reserveEcy,burnEcy FROM GiveawayFundAllocation").fetchone(), (8000, 1000, 1000))
        self.assertEqual(connection.execute("SELECT SUM(amount) FROM EconomyLedger WHERE transactionId=?", (first.transaction_id,)).fetchone()[0], 0)
        connection.close()

    async def test_cancellation_refunds_exact_ticket_once(self):
        now = datetime(2026, 7, 14, tzinfo=timezone.utc)
        evidence = await self.evidence(now=now)
        giveaway = await create_giveaway(self.database.path, guild_id="1", channel_id="2", host_id="3",
                                         request_id="c", prize="P", duration_minutes=5, now=now)
        await enter_giveaway(self.database.path, guild_id="1", user_id="10", giveaway_id=giveaway.entity_id,
                             request_id="e", evidence=evidence, now=now)
        result = await cancel_giveaway(self.database.path, guild_id="1", giveaway_id=giveaway.entity_id,
                                       actor_id="3", request_id="x", reason="dibatalkan", now=now)
        replay = await cancel_giveaway(self.database.path, guild_id="1", giveaway_id=giveaway.entity_id,
                                       actor_id="3", request_id="x", reason="dibatalkan", now=now)
        self.assertTrue(result.ok and replay.replayed)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT ecyBalance FROM EconomyWallet WHERE guildId='1' AND userId='10'").fetchone()[0], 1_000_000)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM GiveawayRefund").fetchone()[0], 1)
        connection.close()

    async def test_voice_blocks_are_non_overlapping_and_restart_safe(self):
        start = datetime(2026, 7, 14, tzinfo=timezone.utc)
        await reconcile_voice_snapshot(self.database.path, "1", {"10": "20", "11": "20"}, observed_at=start)
        report = await reconcile_voice_snapshot(self.database.path, "1", {"10": "20", "11": "20"},
                                                observed_at=start + timedelta(minutes=60))
        retry = await reconcile_voice_snapshot(self.database.path, "1", {"10": "20", "11": "20"},
                                               observed_at=start + timedelta(minutes=60))
        self.assertEqual(report["awarded"], 4)
        self.assertEqual(retry["awarded"], 0)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM GiveawayVoiceBlock WHERE userId='10'").fetchone()[0], 2)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM EconomyActivityEvent WHERE userId='10' AND eventType='VOICE_ACTIVITY_30M'").fetchone()[0], 2)
        connection.close()

    async def test_redraw_consumes_structured_expiry_evidence_and_excludes_prior_winner(self):
        await self.database.fund_user("11")
        now = datetime(2026, 7, 14, tzinfo=timezone.utc)
        evidence10, evidence11 = await self.evidence("10", now), await self.evidence("11", now)
        giveaway = await create_giveaway(self.database.path, guild_id="1", channel_id="2", host_id="3",
                                         request_id="rg", prize="P", duration_minutes=5, now=now)
        for user, evidence in (("10", evidence10), ("11", evidence11)):
            await enter_giveaway(self.database.path, guild_id="1", user_id=user,
                                 giveaway_id=giveaway.entity_id, request_id=f"re-{user}",
                                 evidence=evidence, now=now)
        first = await draw_giveaway(self.database.path, guild_id="1", giveaway_id=giveaway.entity_id,
                                    request_id="rd1", eligible_user_ids=["10", "11"],
                                    participant_evidence={"10": evidence10, "11": evidence11},
                                    random_source=ZeroRandom(), now=now)
        review = await record_winner_review(
            self.database.path, guild_id="1", giveaway_id=giveaway.entity_id, reviewer_id="3",
            reason_code="CLAIM_EXPIRED", evidence_reference="authoritative-deadline",
            evidence_type="AUTHORITATIVE_TIME", prior_winner_state=first.receipt,
            now=now + timedelta(hours=25),
        )
        redrawn = await redraw_giveaway(
            self.database.path, guild_id="1", giveaway_id=giveaway.entity_id, reviewer_id="3",
            review_id=review.entity_id, request_id="rd2", eligible_user_ids=["10", "11"],
            participant_evidence={"10": evidence10, "11": evidence11}, random_source=ZeroRandom(),
            now=now + timedelta(hours=25),
        )
        self.assertTrue(review.ok and redrawn.ok)
        self.assertEqual(redrawn.receipt["winnerId"], "11")
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT consumed FROM GiveawayWinnerReview").fetchone()[0], 1)
        connection.close()
