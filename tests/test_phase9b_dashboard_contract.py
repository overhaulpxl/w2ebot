from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Phase9BDashboardContractTests(unittest.TestCase):
    def test_phase9b_schema_contract(self):
        source = (ROOT / "economy" / "phase9b_schema.py").read_text(encoding="utf-8")
        self.assertIn("UNIQUE(guildId,deliveryKind,sourceType,sourceKey)", source)
        self.assertIn("REVIEW_REQUIRED", source)
        self.assertIn("phase9b-dashboard-notification-routing", source)

    def test_phase9a_protection_remains_authoritative(self):
        core = (ROOT / "core.py").read_text(encoding="utf-8")
        self.assertIn("_signed_internal", core)
        self.assertIn("permission='NOTIFICATION_ROUTING_CONTROL'", core)
