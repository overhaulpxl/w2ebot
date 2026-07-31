from datetime import timedelta
import unittest

from economy.dashboard_auth import (
    consume_csrf, consume_oauth_attempt, create_oauth_attempt, establish_session, issue_csrf,
    revoke_session, rotate_session, validate_session,
)
from economy.dashboard_security import DashboardSecurityError, iso, keyed_hash, utc_now
from tests.phase9a_test_utils import ADMIN_ID, GUILD_ID, SESSION_KEY, TempPhase9ADatabase


class Phase9AAuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = TempPhase9ADatabase()

    async def asyncTearDown(self):
        self.database.close()

    async def _session(self, raw="session-one"):
        db = await self.database.connect()
        await db.execute("BEGIN IMMEDIATE")
        token_hash = keyed_hash(SESSION_KEY, raw)
        session_id = await establish_session(
            db, guild_id=GUILD_ID, user_id=ADMIN_ID, token_hash=token_hash,
            session_key_id="session-v1", discord_administrator=True,
        )
        await db.commit(); await db.close()
        return session_id, token_hash

    async def test_session_validation_expiry_and_revocation(self):
        session_id, token_hash = await self._session()
        db = await self.database.connect(); await db.execute("BEGIN IMMEDIATE")
        session = await validate_session(db, token_hash=token_hash, discord_member=True,
                                         discord_administrator=True, expected_version=0)
        self.assertEqual(session["userId"], ADMIN_ID)
        await revoke_session(db, session_id=session_id, reason_code="TEST", expected_version=0)
        await db.commit()
        with self.assertRaises(DashboardSecurityError):
            await validate_session(db, token_hash=token_hash, discord_member=True, discord_administrator=True)
        await db.close()

    async def test_idle_and_absolute_expiry_fail_closed(self):
        _, token_hash = await self._session("expired")
        db = await self.database.connect(); await db.execute("BEGIN IMMEDIATE")
        past = iso(utc_now() - timedelta(seconds=1))
        await db.execute("UPDATE DashboardSession SET idleExpiresAt=? WHERE tokenHash=?", (past, token_hash))
        with self.assertRaises(DashboardSecurityError) as caught:
            await validate_session(db, token_hash=token_hash, discord_member=True, discord_administrator=True)
        self.assertEqual(caught.exception.code, "expired")
        await db.rollback(); await db.close()

    async def test_csrf_is_bound_and_consumed_once(self):
        session_id, _ = await self._session("csrf")
        db = await self.database.connect(); await db.execute("BEGIN IMMEDIATE")
        issued = await issue_csrf(db, session_id=session_id, method="POST",
                                  canonical_route="/api/auth/logout", request_id="request-1",
                                  session_hash_key=SESSION_KEY)
        await consume_csrf(db, raw_token=issued["token"], session_id=session_id, method="POST",
                           canonical_route="/api/auth/logout", request_id="request-1",
                           session_hash_key=SESSION_KEY)
        with self.assertRaises(DashboardSecurityError):
            await consume_csrf(db, raw_token=issued["token"], session_id=session_id, method="POST",
                               canonical_route="/api/auth/logout", request_id="request-1",
                               session_hash_key=SESSION_KEY)
        await db.rollback(); await db.close()

    async def test_oauth_attempt_rejects_redirect_and_consumes_once(self):
        db = await self.database.connect(); await db.execute("BEGIN IMMEDIATE")
        with self.assertRaises(DashboardSecurityError):
            await create_oauth_attempt(
                db, state_hash="a" * 64, pkce_challenge="challenge", ip_hash="b" * 64,
                return_path="https://evil.example",
            )
        await create_oauth_attempt(
            db, state_hash="c" * 64, pkce_challenge="challenge", ip_hash="d" * 64,
        )
        consumed = await consume_oauth_attempt(
            db, state_hash="c" * 64, pkce_challenge="challenge",
        )
        self.assertEqual(consumed["ipHash"], "d" * 64)
        with self.assertRaises(DashboardSecurityError):
            await consume_oauth_attempt(db, state_hash="c" * 64, pkce_challenge="challenge")
        await db.rollback(); await db.close()

    async def test_insufficient_permission_and_rotation_absolute_cap(self):
        db = await self.database.connect(); await db.execute("BEGIN IMMEDIATE")
        token_hash = keyed_hash(SESSION_KEY, "limited")
        session_id = await establish_session(
            db, guild_id=GUILD_ID, user_id="923456789012345678", token_hash=token_hash,
            session_key_id="session-v1", discord_administrator=True,
        )
        with self.assertRaises(DashboardSecurityError) as caught:
            await validate_session(
                db, token_hash=token_hash, discord_member=True, discord_administrator=False,
            )
        self.assertEqual(caught.exception.code, "forbidden")
        absolute = iso(utc_now() + timedelta(seconds=5))
        await db.execute(
            "UPDATE DashboardSession SET absoluteExpiresAt=? WHERE sessionId=?", (absolute, session_id),
        )
        await rotate_session(
            db, session_id=session_id, new_token_hash=keyed_hash(SESSION_KEY, "rotated"),
            expected_version=0,
        )
        async with db.execute(
            "SELECT idleExpiresAt,absoluteExpiresAt FROM DashboardSession WHERE sessionId=?", (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
        self.assertLessEqual(row[0], row[1])
        await db.rollback(); await db.close()
