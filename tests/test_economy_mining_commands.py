from pathlib import Path
import unittest

import runtime_config
from economy.constants import ECONOMY_PHASE7_ENABLED


ROOT = Path(__file__).resolve().parents[1]


class MiningCommandContractTests(unittest.TestCase):
    def test_flag_defaults_false_and_no_write_api(self):
        self.assertFalse(ECONOMY_PHASE7_ENABLED)
        self.assertFalse(runtime_config.ECONOMY_PHASE7_ENABLED)
        core = (ROOT / "core.py").read_text(encoding="utf-8")
        self.assertIn("api_mining_v1_status", core)
        self.assertNotIn("api_mining_v1_action", core)

    def test_complete_group_and_legacy_adapters_exist(self):
        source = (ROOT / "cogs" / "mining.py").read_text(encoding="utf-8")
        for command in ("status", "catalog", "buy", "rigs", "target", "maintenance", "claim", "details", "history"):
            self.assertIn(f'name="{command}"', source)
        legacy = (ROOT / "cogs" / "rpg.py").read_text(encoding="utf-8")
        for command in ("buyrig", "miner", "moverig"):
            self.assertIn(f'name="{command}"', legacy)
        self.assertIn('register_prefix_command_handler("mining"', source)

    def test_autocomplete_fails_closed_before_query(self):
        source = (ROOT / "cogs" / "mining.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("if not phase7_enabled() or not interaction.guild_id"), 3)

    def test_deal_cog_has_no_mining_reference(self):
        source = (ROOT / "cogs" / "deal.py").read_text(encoding="utf-8")
        self.assertNotIn("phase7", source.lower())
        self.assertNotIn("mining", source.lower())
