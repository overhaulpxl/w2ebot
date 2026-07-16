import copy
import unittest

from scripts.reconcile_phase9c_full_system import reconcile_report
from scripts.simulate_phase9c_full_system import (
    PHASE9C_BASELINE_COMMIT,
    render_report,
    run_full_system_simulation,
)


class Phase9CFullSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = run_full_system_simulation()
        cls.second = run_full_system_simulation()

    def test_acceptance_volume_and_reproducible_artifact(self):
        self.assertEqual(self.first["configuration"]["users"], 1_000)
        self.assertEqual(self.first["configuration"]["days"], 90)
        self.assertEqual(self.first["baselineCommit"], PHASE9C_BASELINE_COMMIT)
        self.assertEqual(render_report(self.first), render_report(self.second))
        self.assertEqual(self.first["artifactHash"], self.second["artifactHash"])
        self.assertTrue(self.first["passed"], self.first["reconciliation"])

    def test_ledger_supply_liability_and_dashboard_reconcile(self):
        result = reconcile_report(self.first)
        self.assertTrue(result["passed"], result)
        self.assertEqual(self.first["ledger"]["netByCurrency"], {"ETM": 0, "ECY": 0})
        self.assertEqual(result["duplicateOutcomeCount"], 0)
        self.assertTrue(result["dashboardExact"])
        self.assertTrue(result["liabilitiesExact"])

    def test_tampering_fails_closed(self):
        changed = copy.deepcopy(self.first)
        changed["dashboard"]["supply"]["ECY"] = "1"
        result = reconcile_report(changed)
        self.assertFalse(result["passed"])
        self.assertIn("ECY dashboard supply mismatch", result["issues"])


if __name__ == "__main__":
    unittest.main()
