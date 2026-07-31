import ast
from pathlib import Path
import unittest

import runtime_config
from economy.constants import ECONOMY_PHASE8_ENABLED


ROOT = Path(__file__).resolve().parents[1]


class Phase8CommandTests(unittest.TestCase):
    def test_flag_defaults_false(self):
        self.assertFalse(ECONOMY_PHASE8_ENABLED)
        self.assertFalse(runtime_config.ECONOMY_PHASE8_ENABLED)

    def test_command_groups_and_legacy_fences_are_present(self):
        source = (ROOT / "cogs" / "phase8.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertIn('name="giveaway"', source)
        self.assertIn('name="eternal-options"', source)
        for action in ("create", "end", "cancel", "redraw", "history", "list", "info", "enter", "status"):
            self.assertIn(f'name="{action}"', source)
        core = (ROOT / "core.py").read_text(encoding="utf-8")
        self.assertIn("{} if ECONOMY_PHASE8_ENABLED else await load_json(BINOMO_FILE)", core)
        self.assertIn('tree.get_command("giveaway")', source)
        self.assertIn('raise RuntimeError("Duplikasi command Phase 8', source)
        self.assertIsNotNone(tree)

    def test_no_phase8_write_api(self):
        core = (ROOT / "core.py").read_text(encoding="utf-8")
        self.assertNotIn("add_post('/api/economy/v1-phase8", core)
        self.assertIn("'economy/phase8': api_phase8_status", core)
        self.assertIn("'/api/economy/v1-phase8'", core)
        self.assertIn("app.router.add_get(route, legacy_dashboard_read_disabled)", core)
