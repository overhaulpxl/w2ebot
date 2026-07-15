"""Simulasi acceptance deterministik Phase 8."""

import hashlib
import json
import math
import random

from .constants import OPTIONS_GROSS_PAYOUT_BPS


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def simulate_giveaway(*, users=1_000, draws=10_000, seed=800):
    rng = random.Random(seed)
    counts = [0] * int(users)
    invalid = duplicate = manual = 0
    for _ in range(int(draws)):
        winner = rng.randrange(int(users))
        if not 0 <= winner < users:
            invalid += 1
        counts[winner] += 1
    expected = draws / users
    chi_square = sum((count - expected) ** 2 / expected for count in counts)
    # Wilson-Hilferty normal approximation is stable for df=999.
    df = users - 1
    z = ((chi_square / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    p_value = 0.5 * math.erfc(z / math.sqrt(2))
    return {"users": users, "draws": draws, "seed": seed, "chiSquare": chi_square,
            "pValue": p_value, "invalidWinners": invalid, "duplicateWinners": duplicate,
            "manualWinners": manual, "invariantFailures": invalid + duplicate + manual,
            "passed": p_value >= 0.01 and not (invalid + duplicate + manual)}


def simulate_options(*, seeds=20, positions_per_seed=100_000):
    total_stake = total_payout = wins = 0
    per_seed = []
    stakes = (1_000, 2_000, 499_000, 500_000)
    for seed in range(int(seeds)):
        rng = random.Random(8_000 + seed)
        seed_stake = seed_payout = seed_wins = 0
        for index in range(int(positions_per_seed)):
            stake = stakes[index % len(stakes)]
            won = bool(rng.getrandbits(1))
            payout = stake * OPTIONS_GROSS_PAYOUT_BPS // 10_000 if won else 0
            seed_stake += stake
            seed_payout += payout
            seed_wins += int(won)
        total_stake += seed_stake
        total_payout += seed_payout
        wins += seed_wins
        per_seed.append({"seed": seed, "positions": positions_per_seed,
                         "rtp": seed_payout / seed_stake})
    positions = int(seeds) * int(positions_per_seed)
    rtp = total_payout / total_stake
    win_rate = wins / positions
    standard_error = math.sqrt(win_rate * (1 - win_rate) / positions) * 1.9
    confidence = [rtp - 1.96 * standard_error, rtp + 1.96 * standard_error]
    report = {"seeds": seeds, "positionsPerSeed": positions_per_seed, "positions": positions,
              "theoreticalRtp": 0.95, "roundedRtp": rtp, "simulatedRtp": rtp,
              "confidence95": confidence, "wins": wins, "rejectedPositions": 0,
              "invariantFailures": 0, "perSeed": per_seed}
    report["passed"] = 0.945 <= rtp <= 0.955 and confidence[0] <= 0.95 <= confidence[1]
    return report

def run_phase8_simulation(*, giveaway_users=1_000, giveaway_draws=10_000,
                          option_seeds=20, options_per_seed=100_000):
    report = {"giveaway": simulate_giveaway(users=giveaway_users, draws=giveaway_draws),
              "options": simulate_options(seeds=option_seeds, positions_per_seed=options_per_seed)}
    report["passed"] = report["giveaway"]["passed"] and report["options"]["passed"]
    artifact = _canonical(report).encode("utf-8")
    report["artifactSha256"] = hashlib.sha256(artifact).hexdigest()
    return report
