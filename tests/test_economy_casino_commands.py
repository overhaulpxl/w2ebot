import ast
import inspect
from pathlib import Path
import unittest

from economy.constants import ECONOMY_PHASE5_ENABLED
from runtime_config import StartupConfiguration
from w2e_views import CasinoConfirmationView, CasinoBlackjackView


ROOT = Path(__file__).resolve().parents[1]


class CasinoCommandContractTests(unittest.TestCase):
    def test_runtime_flag_defaults_false_and_dependencies_are_phase1_phase2(self):
        self.assertFalse(ECONOMY_PHASE5_ENABLED)
        config = StartupConfiguration(
            ROOT / "stage.db", ROOT / "prod.db", True, 1, True,
            True, True, False, False, True,
        )
        self.assertTrue(config.casino_flags_enabled)
        self.assertFalse(config.marketplace_flags_enabled)

    def test_legacy_command_names_and_typed_number_wager_are_preserved(self):
        tree = ast.parse((ROOT / "cogs" / "rpg.py").read_text(encoding="utf-8"))
        commands = set()
        tebak = None
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "command":
                    for keyword in decorator.keywords:
                        if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                            commands.add(keyword.value.value)
                            if keyword.value.value == "tebak":
                                tebak = node
        self.assertTrue({"blackjack", "slot", "cf", "rps", "tebak", "gacha", "box"}.issubset(commands))
        self.assertIsNotNone(tebak)
        arguments = {arg.arg: arg.annotation for arg in tebak.args.args}
        self.assertIsInstance(arguments["tebakan"], ast.Name)
        self.assertEqual(arguments["tebakan"].id, "int")
        self.assertEqual(arguments["bet"].id, "int")

    def test_confirmation_is_actor_bound_and_expires_without_service_call(self):
        user = type("User", (), {"id": 2})()
        view = CasinoConfirmationView(user, request_id="request", game="SLOT", stake=1_000, payload={})
        self.assertEqual(view.timeout, 90)
        self.assertEqual(view.request_id, "request")
        self.assertFalse(view.completed)
        self.assertIsInstance(CasinoBlackjackView(user, "session"), CasinoBlackjackView)

    def test_staff_commands_and_authorization_classes_are_registered_in_source(self):
        source = (ROOT / "cogs" / "economy.py").read_text(encoding="utf-8")
        for command in ("casino-auth", "casino-status", "casino-seed", "casino-adjust", "casino-distribute", "casino-recover"):
            self.assertIn(f'name="{command}"', source)
        self.assertIn('"CASINO_CONTROL"', source)
        self.assertIn('"CASINO_FINANCIAL"', source)
        self.assertIn('"CASINO_RECOVERY"', source)
        self.assertNotIn("/api/casino/action", (ROOT / "core.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
