import os
from pathlib import Path
import sqlite3
import tempfile

from economy.database import initialize_database
from economy.ledger import AccountDelta, execute_transaction
from economy.phase3_migrations import apply_phase3_staging
from economy.phase6_migrations import apply_phase6_staging
from economy.phase7_migrations import apply_phase7_staging


class TempMiningDatabase:
    def __init__(self, guild_id="1", user_id="2"):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "mining-test.db")
        self.production = str(Path(self.temp.name) / "production.db")
        self.guild_id, self.user_id = str(guild_id), str(user_id)

    async def initialize(self, *, level=70, migrate_phase7=True, users_json_path=None):
        await initialize_database(self.path)
        await apply_phase3_staging(self.path, production_db=self.production)
        connection = sqlite3.connect(self.path)
        connection.execute(
            "INSERT INTO EconomyMigrationRun "
            "(runId,migrationVersion,mode,status,guildId,sourceDbSha256,startedAt,completedAt) "
            "VALUES ('phase1-run',100,'APPLY','COMPLETED',?,'source','2026-01-01','2026-01-01')",
            (self.guild_id,),
        )
        columns = [row[1] for row in connection.execute("PRAGMA table_info(RpgProfile)")]
        values = {
            "guildId": self.guild_id, "userId": self.user_id, "level": level, "xp": 0,
            "maxHp": 1000, "currentHp": 1000, "attack": 50, "defense": 25,
            "critBps": 500, "energy": 100, "energyUpdatedAt": "2026-01-01T00:00:00+00:00",
            "starterPackClaimed": 0, "version": 0,
            "createdAt": "2026-01-01T00:00:00+00:00", "updatedAt": "2026-01-01T00:00:00+00:00",
        }
        selected = [column for column in columns if column in values]
        connection.execute(
            f"INSERT INTO RpgProfile ({','.join(selected)}) VALUES ({','.join('?' for _ in selected)})",
            [values[column] for column in selected],
        )
        connection.commit()
        connection.close()
        apply_phase6_staging(self.path, production_db=self.production, guild_id=self.guild_id)
        if migrate_phase7:
            apply_phase7_staging(
                self.path, production_db=self.production, guild_id=self.guild_id,
                users_json_path=users_json_path,
            )
        return self

    async def fund_user(self, amount=100_000_000):
        return await execute_transaction(
            self.path, guild_id=self.guild_id, idempotency_key=f"fund:{self.user_id}:{amount}",
            operation="TEST_FUND", source="TEST", actor_id=None, reason="test funding",
            deltas=(AccountDelta("SYSTEM", "ECY_ISSUANCE", "ECY", -int(amount)),
                    AccountDelta("USER", self.user_id, "ECY", int(amount), self.user_id)),
        )

    def close(self):
        self.temp.cleanup()
