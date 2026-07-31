import ast
from pathlib import Path
import unittest

from economy.constants import ECONOMY_PHASE6_ENABLED
from runtime_config import StartupConfiguration


ROOT = Path(__file__).resolve().parents[1]


class CryptoCommandContractTests(unittest.TestCase):
    def test_flag_defaults_false_and_depends_on_v1(self):
        self.assertFalse(ECONOMY_PHASE6_ENABLED)
        config = StartupConfiguration(
            ROOT / "stage.db", ROOT / "prod.db", True, 1, True,
            True, False, False, False, False, True,
        )
        self.assertTrue(config.crypto_flags_enabled)
        self.assertFalse(config.casino_flags_enabled)

    def test_legacy_command_names_and_typed_parameters_are_preserved(self):
        tree = ast.parse((ROOT / "cogs" / "rpg.py").read_text(encoding="utf-8"))
        commands = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "command":
                    name = next((value.value.value for value in decorator.keywords
                                 if value.arg == "name" and isinstance(value.value, ast.Constant)), None)
                    if name:
                        commands[name] = node
        self.assertTrue({"market", "portfolio", "buycoin", "sellcoin"}.issubset(commands))
        for name in ("buycoin", "sellcoin"):
            annotations = {arg.arg: arg.annotation for arg in commands[name].args.args}
            self.assertEqual(getattr(annotations["symbol"], "id", None), "str")
            self.assertEqual(getattr(annotations["jumlah"], "id", None), "str")

    def test_staff_commands_autocomplete_and_no_write_api(self):
        economy_source = (ROOT / "cogs" / "economy.py").read_text(encoding="utf-8")
        rpg_source = (ROOT / "cogs" / "rpg.py").read_text(encoding="utf-8")
        core_source = (ROOT / "core.py").read_text(encoding="utf-8")
        for command in ("crypto-auth", "crypto-status", "crypto-seed", "crypto-recover"):
            self.assertIn(f'name="{command}"', economy_source)
        for permission in ("CRYPTO_CONTROL", "CRYPTO_FINANCIAL", "CRYPTO_RECOVERY"):
            self.assertIn(f'"{permission}"', economy_source)
        self.assertIn('autocomplete("symbol")', rpg_source)
        self.assertIn("/api/economy/v1-crypto", core_source)
        self.assertNotIn("/api/crypto/action", core_source)


if __name__ == "__main__":
    unittest.main()
