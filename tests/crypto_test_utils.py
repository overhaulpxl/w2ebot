import sqlite3
from pathlib import Path

from economy.crypto import seed_market_reserve
from economy.ledger import AccountDelta, execute_transaction
from economy.phase6_migrations import apply_phase6_staging
from tests.economy_test_utils import TempEconomyDatabase


class TempCryptoDatabase(TempEconomyDatabase):
    def __init__(self, guild_id="1", migrate=True):
        super().__init__()
        self.guild_id = str(guild_id)
        connection = sqlite3.connect(self.path)
        connection.execute(
            "INSERT INTO EconomyMigrationRun "
            "(runId,migrationVersion,mode,status,guildId,sourceDbSha256,startedAt,completedAt) "
            "VALUES ('phase1-run',100,'APPLY','COMPLETED',?,'source','2026-01-01','2026-01-01')",
            (self.guild_id,),
        )
        connection.commit()
        connection.close()
        if migrate:
            apply_phase6_staging(
                self.path, production_db=str(Path(self.path).with_name("production.db")),
                guild_id=self.guild_id,
            )

    async def seed(self, amount=5_000_000):
        return await seed_market_reserve(
            self.path, guild_id=self.guild_id, amount=amount, staging_override=True,
        )

    async def fund_user(self, user_id, amount, key=None):
        user_id = str(user_id)
        return await execute_transaction(
            self.path, guild_id=self.guild_id,
            idempotency_key=key or f"fund:{user_id}:{amount}", operation="TEST_FUND",
            source="TEST", actor_id=None, reason="test funding",
            deltas=(
                AccountDelta("SYSTEM", "ECY_ISSUANCE", "ECY", -int(amount)),
                AccountDelta("USER", user_id, "ECY", int(amount), user_id),
            ),
        )
