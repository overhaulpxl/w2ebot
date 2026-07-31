import sqlite3
import tempfile
import unittest
from pathlib import Path

from economy.casino import effective_maximum_stake, validate_stake
from economy.casino_games import (
    DeterministicRng, GACHA_LABELS, basic_strategy_action,
    blackjack_allowed_actions, checked_payout, liability_for, roll_box,
    roll_coinflip, roll_gacha, roll_number, roll_rps, roll_slot,
    settle_blackjack_plan,
)
from economy.database import ensure_phase1_schema
from economy.phase5_migrations import apply_phase5_staging
from economy.phase5_schema import PHASE5_SCHEMA_CHECKSUM


class CasinoEngineTests(unittest.TestCase):
    def test_liability_and_effective_maximum(self):
        self.assertEqual(liability_for("BLACKJACK", 100_000), 400_000)
        self.assertEqual(liability_for("COINFLIP", 100_000), 194_000)
        self.assertEqual(liability_for("RPS", 100_000), 190_100)
        self.assertEqual(liability_for("NUMBER", 100_000), 1_900_000)
        self.assertEqual(liability_for("BOX", 1_000), 15_000)
        self.assertEqual(liability_for("GACHA", 1_000), 0)
        self.assertEqual(effective_maximum_stake("BLACKJACK", 25_000_000), 125_000)

    def test_wager_increment_and_fixed_prices(self):
        self.assertEqual(validate_stake("SLOT", 1_000), 8_000)
        for invalid in (999, 1_001, 501_000):
            with self.assertRaises(ValueError):
                validate_stake("SLOT", invalid)
        with self.assertRaises(ValueError):
            validate_stake("GACHA", 2_000)

    def test_all_random_outcomes_are_deterministic(self):
        first = DeterministicRng(77)
        second = DeterministicRng(77)
        functions = (
            lambda rng: roll_slot(1_000, rng),
            lambda rng: roll_coinflip(1_000, "angka", rng),
            lambda rng: roll_rps(1_000, "batu", rng),
            lambda rng: roll_number(1_000, 7, rng),
            roll_gacha,
            roll_box,
        )
        self.assertEqual([fn(first) for fn in functions], [fn(second) for fn in functions])
        self.assertEqual(len(GACHA_LABELS), 8)

    def test_revised_blackjack_double_and_split_rules(self):
        def plan(cards, dealer="6-hearts"):
            return {
                "state": "PLAYER_TURN",
                "hands": [{"cards": cards, "stakeEcy": 1_000, "stood": False, "doubled": False}],
                "activeHand": 0,
                "splitUsed": False,
                "dealer": [dealer, "10-clubs"],
            }

        self.assertNotIn("DOUBLE", blackjack_allowed_actions(plan(["4-hearts", "5-clubs"])))
        self.assertNotIn("DOUBLE", blackjack_allowed_actions(plan(["4-hearts", "6-clubs"])))
        self.assertIn("DOUBLE", blackjack_allowed_actions(plan(["5-hearts", "6-clubs"])))
        self.assertNotIn("SPLIT", blackjack_allowed_actions(plan(["9-hearts", "9-clubs"])))
        self.assertIn("SPLIT", blackjack_allowed_actions(plan(["A-hearts", "A-clubs"])))
        self.assertIn("SPLIT", blackjack_allowed_actions(plan(["8-hearts", "8-clubs"])))
        self.assertEqual(basic_strategy_action(plan(["4-hearts", "5-clubs"])), "HIT")
        self.assertEqual(basic_strategy_action(plan(["4-hearts", "6-clubs"])), "HIT")

    def test_natural_blackjack_uses_checked_five_to_four_payout(self):
        plan = {
            "state": "DEALER_TURN",
            "hands": [{"cards": ["A-hearts", "K-clubs"], "stakeEcy": 1_000}],
            "dealer": ["10-hearts", "7-clubs"],
            "shoe": [],
        }
        result = settle_blackjack_plan(plan)
        self.assertEqual(result["grossPayoutEcy"], 2_250)
        self.assertEqual(result["hands"][0]["result"], "BLACKJACK")
        with self.assertRaises(OverflowError):
            checked_payout(9_000_000_000_000_000, 22_500)

    def test_schema_checksum_shape(self):
        self.assertEqual(len(PHASE5_SCHEMA_CHECKSUM), 64)
        int(PHASE5_SCHEMA_CHECKSUM, 16)


if __name__ == "__main__":
    unittest.main()
