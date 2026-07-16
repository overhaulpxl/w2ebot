import os
import sqlite3
import tempfile
import unittest

from economy.database import SCHEMA_SQL
from economy.phase9a_migrations import apply_phase9a_staging
from economy.phase9b_migrations import (
    apply_phase9b_staging,
    reconcile_phase9b_staging,
    verify_phase9b_staging,
)
from scripts.run_phase9c_local_qa import migration_chain, verify_migration_chain


class Phase9CMigrationChainTests(unittest.TestCase):
    def test_complete_ordered_chain_and_checksums(self):
        result = verify_migration_chain()
        self.assertTrue(result["passed"], result)
        self.assertEqual([item["version"] for item in migration_chain()],
                         [100, 200, 300, 301, 400, 500, 600, 700, 800, 900, 910])
        self.assertEqual(len({item["version"] for item in migration_chain()}), 11)

    def test_phase9_boundary_apply_replay_reconcile_and_production_refusal(self):
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        production = path + ".production"
        try:
            connection = sqlite3.connect(path)
            connection.executescript(SCHEMA_SQL)
            connection.commit()
            connection.close()
            apply_phase9a_staging(path, production_db=production)
            first = apply_phase9b_staging(path, production_db=production)
            replay = apply_phase9b_staging(path, production_db=production)
            verified = verify_phase9b_staging(path)
            reconciled = reconcile_phase9b_staging(path, guild_id="1")
            self.assertTrue(first["applied"])
            self.assertTrue(replay["replayed"])
            self.assertTrue(verified["schemaCapable"])
            self.assertEqual(verified["integrityCheck"], "ok")
            self.assertEqual(verified["foreignKeyErrors"], 0)
            self.assertTrue(reconciled["reconciled"], reconciled)
            with self.assertRaises(ValueError):
                apply_phase9b_staging(path, production_db=path)
        finally:
            for candidate in (path, production):
                if os.path.exists(candidate):
                    os.remove(candidate)


if __name__ == "__main__":
    unittest.main()
