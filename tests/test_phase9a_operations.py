import sqlite3
import unittest

from economy.dashboard_operations import change_permission
from economy.dashboard_security import DashboardSecurityError
from tests.phase9a_test_utils import ADMIN_ID, GUILD_ID, TempPhase9ADatabase


class Phase9AOperationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): self.database = TempPhase9ADatabase()
    async def asyncTearDown(self): self.database.close()

    async def test_permission_commit_replay_and_audit_immutability(self):
        db = await self.database.connect(); await db.execute("BEGIN IMMEDIATE")
        receipt = await change_permission(
            db, action="GRANT", guild_id=GUILD_ID, actor_id=ADMIN_ID,
            target_user_id="223456789012345678", permission_class="DASHBOARD_VIEW",
            request_id="grant-request", expected_version=0, source_route="/api/admin/operators/grant",
        )
        await db.commit()
        self.assertEqual(receipt["status"], "COMMITTED")
        replay = await change_permission(
            db, action="GRANT", guild_id=GUILD_ID, actor_id=ADMIN_ID,
            target_user_id="223456789012345678", permission_class="DASHBOARD_VIEW",
            request_id="grant-request", expected_version=0, source_route="/api/admin/operators/grant",
        )
        self.assertEqual(replay, receipt)
        with self.assertRaises(sqlite3.IntegrityError):
            await db.execute("UPDATE DashboardOperatorAudit SET resultStatus='VOID'")
        await db.close()

    async def test_conflicting_request_identity_fails(self):
        db = await self.database.connect(); await db.execute("BEGIN IMMEDIATE")
        await change_permission(db, action="GRANT", guild_id=GUILD_ID, actor_id=ADMIN_ID,
                                target_user_id="323456789012345678", permission_class="DASHBOARD_VIEW",
                                request_id="same", expected_version=0, source_route="/grant")
        await db.commit()
        with self.assertRaises(DashboardSecurityError) as caught:
            await change_permission(db, action="GRANT", guild_id=GUILD_ID, actor_id=ADMIN_ID,
                                    target_user_id="423456789012345678", permission_class="DASHBOARD_VIEW",
                                    request_id="same", expected_version=0, source_route="/grant")
        self.assertEqual(caught.exception.code, "request_identity_conflict")
        await db.close()

    async def test_direct_service_requires_security_admin(self):
        db = await self.database.connect(); await db.execute("BEGIN IMMEDIATE")
        with self.assertRaises(DashboardSecurityError) as caught:
            await change_permission(
                db, action="GRANT", guild_id=GUILD_ID, actor_id="999999999999999999",
                target_user_id="823456789012345678", permission_class="DASHBOARD_VIEW",
                request_id="unauthorized", expected_version=0,
                source_route="/api/admin/operators/grant",
            )
        self.assertEqual(caught.exception.code, "forbidden")
        await db.rollback(); await db.close()
