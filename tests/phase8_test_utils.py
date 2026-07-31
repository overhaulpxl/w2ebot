import sqlite3
from pathlib import Path

from economy.ledger import AccountDelta, execute_transaction
from economy.phase5_migrations import apply_phase5_staging
from economy.phase6_migrations import apply_phase6_staging
from economy.phase8_migrations import apply_phase8_staging
from tests.economy_test_utils import TempEconomyDatabase


class TempPhase8Database(TempEconomyDatabase):
    def __init__(self, guild_id="1", migrate=True):
        super().__init__()
        self.guild_id = str(guild_id)
        self.production = str(Path(self.path).with_name("production.db"))
        connection = sqlite3.connect(self.path)
        connection.execute(
            "INSERT INTO EconomyMigrationRun "
            "(runId,migrationVersion,mode,status,guildId,sourceDbSha256,startedAt,completedAt) "
            "VALUES ('phase1-run',100,'APPLY','COMPLETED',?,'source','2026-01-01','2026-01-01')",
            (self.guild_id,),
        )
        connection.commit()
        connection.close()
        apply_phase5_staging(self.path, production_db=self.production)
        apply_phase6_staging(self.path, production_db=self.production, guild_id=self.guild_id)
        if migrate:
            apply_phase8_staging(self.path, production_db=self.production)

    async def fund_user(self, user_id, amount=1_000_000):
        return await execute_transaction(
            self.path, guild_id=self.guild_id, idempotency_key=f"fund:{user_id}:{amount}",
            operation="TEST_FUND", source="TEST", actor_id=None, reason="test fund",
            deltas=(AccountDelta("SYSTEM", "ECY_ISSUANCE", "ECY", -int(amount)),
                    AccountDelta("USER", str(user_id), "ECY", int(amount), str(user_id))),
        )

    async def seed_casino(self, amount=100_000_000):
        result = await execute_transaction(
            self.path, guild_id=self.guild_id, idempotency_key=f"casino-seed:{amount}",
            operation="SYSTEM_SEED", source="TEST", actor_id=None, reason="test casino seed",
            deltas=(AccountDelta("SYSTEM", "ECY_ISSUANCE", "ECY", -int(amount)),
                    AccountDelta("SYSTEM", "ECY_CASINO", "ECY", int(amount))),
        )
        connection = sqlite3.connect(self.path)
        connection.execute(
            "INSERT INTO EconomySeedMarker (guildId,seedKey,accountCode,currency,amount,transactionId,appliedAt) "
            "VALUES (?,?,?,?,?,?,?)",
            (self.guild_id, "phase8-test-casino", "ECY_CASINO", "ECY", int(amount),
             result.transaction_id, "2026-01-01T00:00:00+00:00"),
        )
        connection.commit()
        connection.close()
        return result
