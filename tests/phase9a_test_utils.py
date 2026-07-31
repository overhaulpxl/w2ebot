import hashlib
import os
import sqlite3
import tempfile

import aiosqlite

from economy.database import SCHEMA_SQL
from economy.phase9a_migrations import apply_phase9a_staging, bootstrap_admin, register_signing_key


INTERNAL_KEY = "i" * 32
SESSION_KEY = "s" * 32
IP_KEY = "p" * 32
GUILD_ID = "887968847842402355"
ADMIN_ID = "123456789012345678"


class TempPhase9ADatabase:
    def __init__(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.production = self.path + ".production"
        connection = sqlite3.connect(self.path)
        connection.executescript(SCHEMA_SQL)
        connection.commit()
        connection.close()
        apply_phase9a_staging(self.path, production_db=self.production)
        for key_id, purpose, secret in (
            ("internal-v1", "INTERNAL_REQUEST", INTERNAL_KEY),
            ("session-v1", "SESSION_HASH", SESSION_KEY),
            ("ip-v1", "IP_HASH", IP_KEY),
        ):
            register_signing_key(
                self.path, key_id=key_id, purpose=purpose,
                fingerprint_sha256=hashlib.sha256(secret.encode()).hexdigest(), actor_id="test",
            )
        bootstrap_admin(self.path, guild_id=GUILD_ID, user_id=ADMIN_ID)

    async def connect(self):
        db = await aiosqlite.connect(self.path, isolation_level=None)
        await db.execute("PRAGMA foreign_keys=ON")
        return db

    def close(self):
        if os.path.exists(self.path):
            os.remove(self.path)
