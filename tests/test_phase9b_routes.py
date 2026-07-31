import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Phase9BRoutesTests(unittest.TestCase):
    def test_explicit_internal_routes_and_no_write_api(self):
        source = (ROOT / "core.py").read_text(encoding="utf-8")
        for route in ("dashboard/overview", "dashboard/supply", "dashboard/flows", "dashboard/liabilities",
                      "notifications/routes/update", "notifications/routes/test", "features/pause", "features/resume"):
            self.assertIn(f"/internal/phase9b/{route}", source)
        self.assertNotIn("/api/economy/phase9b/write", source)

    def test_no_new_direct_send_in_domain_services(self):
        for name in ("notification_routing.py", "notification_delivery.py", "dashboard_economy_operations.py"):
            tree = ast.parse((ROOT / "economy" / name).read_text(encoding="utf-8"))
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute) and node.func.attr == "send"]
            self.assertEqual(calls, [], name)
