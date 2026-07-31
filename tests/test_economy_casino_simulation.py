import unittest

from economy.casino_simulation import TARGETS, run_d18_simulation


class CasinoSimulationTests(unittest.TestCase):
    def test_approved_targets_and_full_default_volume(self):
        self.assertEqual(TARGETS["BLACKJACK"], (0.975, 0.002))
        self.assertEqual(TARGETS["SLOT"], (0.950, 0.002))
        defaults = run_d18_simulation.__kwdefaults__
        self.assertEqual(defaults["rounds_per_seed"], 1_000_000)
        self.assertEqual(defaults["blackjack_sessions_per_seed"], 500_000)

    def test_small_simulation_is_byte_stable_data(self):
        first = run_d18_simulation(seeds=(1, 2), rounds_per_seed=2_000,
                                   blackjack_sessions_per_seed=1_000, workers=1)
        second = run_d18_simulation(seeds=(1, 2), rounds_per_seed=2_000,
                                    blackjack_sessions_per_seed=1_000, workers=1)
        self.assertEqual(first, second)
        self.assertEqual(first["invariantFailures"], 0)
        self.assertEqual(set(first["games"]), set(TARGETS))


if __name__ == "__main__":
    unittest.main()
