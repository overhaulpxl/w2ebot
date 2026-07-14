import unittest

from economy.mining_simulation import run_mining_simulation


class MiningSimulationTests(unittest.TestCase):
    def test_deterministic_small_simulation_and_roi(self):
        first = run_mining_simulation(seeds=2, days=3)
        second = run_mining_simulation(seeds=2, days=3)
        self.assertEqual(first["artifactHash"], second["artifactHash"])
        self.assertTrue(first["passed"])
        self.assertGreaterEqual(first["artifact"]["summary"]["minimumRoiDays"], 66)
        self.assertLessEqual(first["artifact"]["summary"]["maximumRoiDays"], 68)
