import os
import sqlite3
import tempfile
import unittest

import aiosqlite

from economy.dashboard_economy_operations import controlled_feature_pause, controlled_route_update
from economy.dashboard_security import DashboardSecurityError
from economy.database import SCHEMA_SQL, configure_connection
from economy.phase9a_migrations import apply_phase9a_staging
from economy.phase9b_migrations import apply_phase9b_staging
from economy.phase9b_recovery import finalize_reviewed_recovery, reserve_reviewed_recovery


class Phase9BOperationsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db"); os.close(handle)
        connection = sqlite3.connect(self.path); connection.executescript(SCHEMA_SQL); connection.commit(); connection.close()
        apply_phase9a_staging(self.path, production_db=self.path + ".prod")
        apply_phase9b_staging(self.path, production_db=self.path + ".prod")
        self.db = await aiosqlite.connect(self.path); await configure_connection(self.db)
        await self.db.execute("INSERT INTO DashboardIdentity VALUES ('1','9','ACTIVE','2026-01-01','2026-01-01',0)")
        for permission in ("NOTIFICATION_ROUTING_CONTROL", "ECONOMY_PAUSE_CONTROL", "REVIEWED_RECOVERY_CONTROL"):
            await self.db.execute(
                "INSERT INTO DashboardOperatorPermission "
                "(assignmentId,guildId,userId,permissionClass,status,grantedById,grantedAt) VALUES (?,?,?,?,'ACTIVE','9','2026-01-01')",
                (permission, "1", "9", permission),
            )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close(); os.remove(self.path)

    async def test_route_update_replay_and_identity_conflict(self):
        args = dict(guild_id="1", actor_id="9", request_id="r1", category="GENERAL", enabled=True,
                    channel_id="12345678901234567", role_mention_id=None,
                    event_types=["GENERAL_ANNOUNCEMENT"], expected_version=0,
                    source_route="/api/economy/notifications/routes/GENERAL")
        first = await controlled_route_update(self.db, **args); await self.db.commit()
        replay = await controlled_route_update(self.db, **args)
        self.assertEqual(first, replay)
        with self.assertRaises(DashboardSecurityError):
            await controlled_route_update(self.db, **{**args, "channel_id": "12345678901234568"})

    async def test_pause_commits_audit_once(self):
        result = await controlled_feature_pause(
            self.db, guild_id="1", actor_id="9", request_id="p1", feature="economy", paused=True,
            reason="incident", expected_version=0, source_route="/api/economy/controls/pause",
        )
        await self.db.commit()
        self.assertTrue(result["paused"])
        count = await (await self.db.execute("SELECT COUNT(*) FROM DashboardOperatorAudit WHERE requestId='p1'")).fetchone()
        self.assertEqual(count[0], 1)

    async def test_reviewed_recovery_reuses_controlled_identity_and_audits(self):
        await self.db.execute(
            "CREATE TABLE RpgOperation (operationId TEXT PRIMARY KEY,guildId TEXT NOT NULL,status TEXT NOT NULL)"
        )
        await self.db.execute("INSERT INTO RpgOperation VALUES ('operation-1','1','REVIEW_REQUIRED')")
        reserved = await reserve_reviewed_recovery(
            self.db, guild_id="1", actor_id="9", request_id="recovery-1",
            target_type="RPG_OPERATION", target_id="operation-1", resolution="RETRY",
            expected_version=0, reason="reviewed evidence",
        )
        replay = await reserve_reviewed_recovery(
            self.db, guild_id="1", actor_id="9", request_id="recovery-1",
            target_type="RPG_OPERATION", target_id="operation-1", resolution="RETRY",
            expected_version=0, reason="reviewed evidence",
        )
        self.assertEqual(reserved["operationId"], replay["operationId"])
        receipt = await finalize_reviewed_recovery(
            self.db, operation_id=reserved["operationId"], success=True, result_code="resumed",
        )
        await self.db.commit()
        self.assertEqual(receipt["status"], "COMMITTED")
        audit = await (await self.db.execute(
            "SELECT COUNT(*) FROM DashboardOperatorAudit WHERE requestId='recovery-1'"
        )).fetchone()
        self.assertEqual(audit[0], 1)
