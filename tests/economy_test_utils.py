import sqlite3
import tempfile
from pathlib import Path

from economy.database import ensure_phase1_schema


class TempEconomyDatabase:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "economy-test.db")
        connection = sqlite3.connect(self.path)
        connection.execute(
            "CREATE TABLE AuditLog (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, action TEXT, target_id TEXT, detail TEXT, source TEXT)"
        )
        ensure_phase1_schema(connection)
        connection.commit()
        connection.close()

    def close(self):
        self.temp.cleanup()
