import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

import aiosqlite

from economy.dashboard_reporting import flows_report, overview_report, supply_report
from economy.database import SCHEMA_SQL, configure_connection
from economy.phase9a_migrations import apply_phase9a_staging
from economy.phase9b_migrations import apply_phase9b_staging


class Phase9BReportingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db"); os.close(handle)
        connection = sqlite3.connect(self.path); connection.executescript(SCHEMA_SQL); connection.commit(); connection.close()
        apply_phase9a_staging(self.path, production_db=self.path + ".prod")
        apply_phase9b_staging(self.path, production_db=self.path + ".prod")
        self.db = await aiosqlite.connect(self.path); await configure_connection(self.db)
        await self.db.execute("INSERT INTO EconomyWallet VALUES ('1','2',3,4,0,'2026-01-01','2026-01-01')")
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close(); os.remove(self.path)

    async def test_transport_integers_are_decimal_strings(self):
        report = await supply_report(self.db, "1")
        self.assertEqual(report["schemaVersion"], "1")
        self.assertEqual(report["data"]["supply"]["ETM"], "3")
        self.assertEqual(report["data"]["walletCount"], "1")

    async def test_exact_windows_and_health(self):
        flows = await flows_report(self.db, "1", window_days=7)
        self.assertEqual(flows["data"]["windowDays"], "7")
        with self.assertRaises(Exception): await flows_report(self.db, "1", window_days=8)
        overview = await overview_report(self.db, "1")
        self.assertIn(overview["data"]["health"], {"HEALTHY", "NEEDS_ATTENTION", "UNBALANCED"})

    async def test_overflow_safe_balance_and_both_active_user_definitions(self):
        occurred = "2026-01-01T00:00:00+00:00"
        await self.db.execute(
            "INSERT INTO EconomyTransaction VALUES "
            "('large','1','large','PLAYER_TRANSFER_ETM','TEST',NULL,'2',NULL,NULL,'{}','COMMITTED',?,?)",
            (occurred, occurred),
        )
        for sequence, amount in enumerate((9_000_000_000_000_000_000, -9_000_000_000_000_000_000), 1):
            await self.db.execute(
                "INSERT INTO EconomyLedger (transactionId,sequence,guildId,accountKind,accountId,userId,currency,"
                "transactionType,amount,balanceBefore,balanceAfter,source,createdAt) "
                "VALUES ('large',?,'1','USER','2','2','ETM','TEST',?,0,0,'TEST',?)",
                (sequence, amount, occurred),
            )
        await self.db.execute(
            "INSERT INTO EconomyActivityEvent VALUES "
            "('event','1','2','WORK','work:1',1,1,NULL,NULL,?,?)", (occurred, occurred),
        )
        await self.db.commit()
        report = await overview_report(
            self.db, "1", current_non_bot_user_ids={"2"},
            now=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(report["data"]["unbalancedTransactions"], "0")
        self.assertEqual(report["data"]["activeUsers30d"]["committedLedgerUsers"], "1")
        self.assertEqual(report["data"]["activeUsers30d"]["currentNonBotApprovedActivityUsers"], "1")

    async def test_transfer_fee_uses_shared_integer_calculator(self):
        occurred = "2026-01-01T00:00:00+00:00"
        await self.db.execute(
            "INSERT INTO EconomyTransaction VALUES "
            "('fee','1','fee','PLAYER_TRANSFER_ETM','TEST',NULL,'2',NULL,NULL,'{}','COMMITTED',?,?)",
            (occurred, occurred),
        )
        await self.db.execute(
            "INSERT INTO EconomyLedger (transactionId,sequence,guildId,accountKind,accountId,userId,currency,"
            "transactionType,amount,balanceBefore,balanceAfter,source,createdAt) "
            "VALUES ('fee',1,'1','USER','2','2','ETM','TEST',-10000,10000,0,'TEST',?)", (occurred,),
        )
        await self.db.commit()
        report = await flows_report(
            self.db, "1", window_days=7, now=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        fee = next(row for row in report["data"]["fees"] if row["category"] == "TRANSFER")
        self.assertEqual(fee, {"category": "TRANSFER", "currency": "ETM", "amount": "500"})
