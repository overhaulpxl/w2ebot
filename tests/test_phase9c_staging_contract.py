import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts.run_phase9c_staging import (
    REQUIRED_CREDENTIAL_ENV, credentials_available, initialize_evidence, load_approved_manifest,
)
from scripts.verify_phase9c_staging_evidence import validate_evidence


class Phase9CStagingContractTests(unittest.TestCase):
    def _manifest(self, root: Path) -> dict:
        return {
            "approved": True,
            "environment": "staging",
            "databasePath": str(root / "phase9c-staging.db"),
            "productionDatabasePath": str(root / "production.db"),
            "resourceFingerprint": "a" * 64,
        }

    def test_pending_evidence_is_sanitized_and_complete_shape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "manifest.json"
            path.write_text(json.dumps(self._manifest(root)), encoding="utf-8")
            evidence = initialize_evidence(load_approved_manifest(path))
            self.assertEqual(validate_evidence(evidence, require_complete=False), [])
            self.assertEqual(len(evidence["steps"]), 22)
            self.assertTrue(validate_evidence(evidence, require_complete=True))

    def test_production_equivalent_path_and_secret_fields_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self._manifest(root)
            manifest["databasePath"] = manifest["productionDatabasePath"]
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_approved_manifest(path)
            evidence = initialize_evidence(self._manifest(root))
            evidence["discordToken"] = "forbidden"
            self.assertTrue(any("secret-like field" in issue for issue in validate_evidence(evidence, require_complete=False)))

    def test_credentials_must_be_explicit_staging_environment_values(self):
        self.assertFalse(credentials_available({}))
        values = {
            "DISCORD_TOKEN": "x", "DASHBOARD_DISCORD_CLIENT_ID": "x",
            "DASHBOARD_DISCORD_CLIENT_SECRET": "x",
            "DASHBOARD_SESSION_HASH_KEY": "x", "DASHBOARD_INTERNAL_SIGNING_KEY": "x",
            "DASHBOARD_IP_HASH_KEY": "x",
        }
        self.assertTrue(credentials_available(values))
        self.assertEqual(set(values), set(REQUIRED_CREDENTIAL_ENV))
        for missing in REQUIRED_CREDENTIAL_ENV:
            with self.subTest(missing=missing):
                incomplete = dict(values)
                incomplete.pop(missing)
                self.assertFalse(credentials_available(incomplete))

    def test_legacy_oauth_variable_aliases_are_rejected(self):
        values = {
            "DISCORD_TOKEN": "x", "DISCORD_CLIENT_ID": "x", "DISCORD_CLIENT_SECRET": "x",
            "DASHBOARD_SESSION_HASH_KEY": "x", "DASHBOARD_INTERNAL_SIGNING_KEY": "x",
            "DASHBOARD_IP_HASH_KEY": "x",
        }
        self.assertFalse(credentials_available(values))
        self.assertNotIn("DISCORD_CLIENT_ID", REQUIRED_CREDENTIAL_ENV)
        self.assertNotIn("DISCORD_CLIENT_SECRET", REQUIRED_CREDENTIAL_ENV)


if __name__ == "__main__":
    unittest.main()
