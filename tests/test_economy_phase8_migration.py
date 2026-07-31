import sqlite3
import unittest

from economy.phase8_migrations import (
    apply_phase8_staging, reconcile_phase8_staging, verify_phase8_staging,
)
from economy.phase8_schema import PHASE8_MIGRATION_NAME, PHASE8_SCHEMA_CHECKSUM
from tests.phase8_test_utils import TempPhase8Database


class Phase8MigrationTests(unittest.TestCase):
    def test_apply_replay_integrity_and_checksum(self):
        database = TempPhase8Database()
        try:
            replay = apply_phase8_staging(database.path, production_db=database.production)
            verified = verify_phase8_staging(database.path)
            reconciliation = reconcile_phase8_staging(database.path)
            self.assertTrue(replay["replayed"] and verified["schemaCapable"] and reconciliation["reconciled"])
            self.assertEqual(verified["migrationName"], PHASE8_MIGRATION_NAME)
            self.assertEqual(verified["migrationChecksum"], PHASE8_SCHEMA_CHECKSUM)
            self.assertEqual(verified["integrityCheck"], "ok")
            self.assertEqual(verified["foreignKeyErrors"], 0)
        finally:
            database.close()

    def test_failure_rolls_back_complete_migration(self):
        database = TempPhase8Database(migrate=False)
        try:
            with self.assertRaises(RuntimeError):
                apply_phase8_staging(database.path, production_db=database.production,
                                     failure_stage="after_tables")
            connection = sqlite3.connect(database.path)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='GiveawayV1'").fetchone())
            self.assertIsNone(connection.execute("SELECT version FROM EconomySchemaMigration WHERE version=800").fetchone())
            connection.close()
        finally:
            database.close()

    def test_production_path_refused(self):
        database = TempPhase8Database(migrate=False)
        try:
            with self.assertRaises(ValueError):
                apply_phase8_staging(database.path, production_db=database.path)
        finally:
            database.close()

    def test_direct_sql_enforces_giveaway_and_option_limits(self):
        database = TempPhase8Database()
        connection = sqlite3.connect(database.path)
        try:
            for index in range(3):
                connection.execute(
                    "INSERT INTO GiveawayV1 (giveawayId,requestId,guildId,channelId,hostId,prize,status,startsAt,endsAt,createdAt,updatedAt) "
                    "VALUES (?,?,?,?,?,?,'ACTIVE',?,?,?,?)",
                    (f"g{index}", f"r{index}", "1", f"c{index}", "host", "P", "2026-01-01", "2026-01-02", "2026-01-01", "2026-01-01"),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO GiveawayV1 (giveawayId,requestId,guildId,channelId,hostId,prize,status,startsAt,endsAt,createdAt,updatedAt) "
                    "VALUES ('g4','r4','1','c4','host','P','ACTIVE','2026-01-01','2026-01-02','2026-01-01','2026-01-01')"
                )
            connection.execute("UPDATE GiveawayV1 SET status='COMPLETED' WHERE giveawayId='g0'")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE GiveawayV1 SET status='ACTIVE' WHERE giveawayId='g0'")

            history_id, symbol, price = connection.execute(
                "SELECT historyId,symbol,currentPriceEcy FROM CryptoPriceHistory ORDER BY occurredAt LIMIT 1"
            ).fetchone()
            for index, stake in enumerate((200000, 200000)):
                transaction_id = f"option-tx-{index}"
                connection.execute(
                    "INSERT INTO EconomyTransaction (transactionId,guildId,idempotencyKey,operation,source,referenceId,actorId,reasonText,metadataJson,status,createdAt) "
                    "VALUES (?,?,?,?,?,?,?,?,?,'PENDING','2026-01-01')",
                    (transaction_id, "1", f"option-key-{index}", "OPTIONS_OPEN", "phase8", f"p{index}", "user", "test", "{}"),
                )
                connection.execute(
                    "INSERT INTO EternalOptionPosition (positionId,requestId,guildId,userId,symbol,direction,stakeEcy,liabilityEcy,durationMinutes,entryHistoryId,entryPriceEcy,expiresAt,openingTransactionId,status,createdAt) "
                    "VALUES (?,?,?,?,?,'UP',?,?,?,?,?,?,?,'ACTIVE','2026-01-01')",
                    (f"p{index}", f"option-r{index}", "1", "user", symbol, stake, stake * 19000 // 10000,
                     5, history_id, price, "2026-01-01T00:05:00+00:00", transaction_id),
                )
            transaction_id = "option-tx-limit"
            connection.execute(
                "INSERT INTO EconomyTransaction (transactionId,guildId,idempotencyKey,operation,source,referenceId,actorId,reasonText,metadataJson,status,createdAt) "
                "VALUES (?,?,?,?,?,?,?,?,?,'PENDING','2026-01-01')",
                (transaction_id, "1", "option-key-limit", "OPTIONS_OPEN", "phase8", "p-limit", "user", "test", "{}"),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO EternalOptionPosition (positionId,requestId,guildId,userId,symbol,direction,stakeEcy,liabilityEcy,durationMinutes,entryHistoryId,entryPriceEcy,expiresAt,openingTransactionId,status,createdAt) "
                    "VALUES ('p-limit','option-r-limit','1','user',?,'UP',200000,380000,5,?,?,'2026-01-01T00:05:00+00:00',?,'ACTIVE','2026-01-01')",
                    (symbol, history_id, price, transaction_id),
                )
        finally:
            connection.close()
            database.close()
