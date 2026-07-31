import os
import tempfile
import unittest

import aiosqlite

from economy.database import initialize_database
from economy.phase3_migrations import apply_phase3_staging


class Phase3MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = handle.name
        handle.close()
        await initialize_database(self.db_path)

    async def asyncTearDown(self):
        os.unlink(self.db_path)

    async def test_apply_is_idempotent_on_temporary_database(self):
        production = os.path.join(os.path.dirname(self.db_path), "production.db")
        first = await apply_phase3_staging(self.db_path, production_db=production)
        second = await apply_phase3_staging(self.db_path, production_db=production)
        self.assertEqual(first["catalog_hash"], second["catalog_hash"])
        async with aiosqlite.connect(self.db_path) as db:
            manifests = (await (await db.execute("SELECT COUNT(*) FROM RpgCatalogManifest")).fetchone())[0]
        self.assertEqual(manifests, 1)

    async def test_production_path_is_refused(self):
        with self.assertRaises(ValueError):
            await apply_phase3_staging(self.db_path, production_db=self.db_path)


if __name__ == "__main__":
    unittest.main()
