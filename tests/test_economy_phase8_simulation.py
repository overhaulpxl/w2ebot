import unittest

from economy.phase8_simulation import run_phase8_simulation


class Phase8SimulationTests(unittest.TestCase):
    def test_deterministic_acceptance_artifact(self):
        first = run_phase8_simulation(giveaway_users=1000, giveaway_draws=10000,
                                      option_seeds=20, options_per_seed=100000)
        second = run_phase8_simulation(giveaway_users=1000, giveaway_draws=10000,
                                       option_seeds=20, options_per_seed=100000)
        self.assertEqual(first["artifactSha256"], second["artifactSha256"])
        self.assertTrue(first["passed"])
        self.assertGreaterEqual(first["giveaway"]["pValue"], 0.01)
        self.assertEqual(first["options"]["positions"], 2_000_000)
