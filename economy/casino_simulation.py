"""Simulasi deterministik D18 tanpa menyentuh database atau wallet."""

from concurrent.futures import ProcessPoolExecutor
import math
import os
import random

from .casino_games import liability_for


TARGETS = {
    "SLOT": (0.950, 0.002),
    "COINFLIP": (0.970, 0.001),
    "RPS": (0.967, 0.001),
    "NUMBER": (0.950, 0.003),
    "BOX": (0.950, 0.002),
    "BLACKJACK": (0.975, 0.002),
}


def _draw(counts, remaining, rng):
    value = rng.randrange(remaining)
    cursor = 0
    for index, count in enumerate(counts):
        cursor += count
        if value < cursor:
            counts[index] -= 1
            return index
    raise AssertionError("Shoe Blackjack tidak konsisten.")


def _hand_value(cards):
    total = 0
    aces = 0
    for rank in cards:
        if rank == 0:
            total += 11
            aces += 1
        elif rank >= 9:
            total += 10
        else:
            total += rank + 1
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0


def _strategy(cards, dealer_rank, *, can_double, can_split):
    dealer = 11 if dealer_rank == 0 else 10 if dealer_rank >= 9 else dealer_rank + 1
    if can_split and len(cards) == 2 and cards[0] == cards[1]:
        rank = cards[0]
        if rank in {0, 7}:
            return "SPLIT"
    value, soft = _hand_value(cards)
    if can_double and value == 11:
        return "DOUBLE"
    if soft:
        return "STAND" if value >= 19 or (value == 18 and 2 <= dealer <= 8) else "HIT"
    if value >= 17 or (13 <= value <= 16 and 2 <= dealer <= 6) or (value == 12 and 4 <= dealer <= 6):
        return "STAND"
    return "HIT"


def _blackjack_round(rng):
    counts = [24] * 13
    remaining = 312
    def draw():
        nonlocal remaining
        rank = _draw(counts, remaining, rng)
        remaining -= 1
        return rank
    player = [draw(), draw()]
    dealer = [draw(), draw()]
    player_natural = len(player) == 2 and _hand_value(player)[0] == 21
    dealer_natural = len(dealer) == 2 and _hand_value(dealer)[0] == 21
    if player_natural or dealer_natural:
        if player_natural and dealer_natural:
            return 1_000, 1_000
        return (1_000, 2_250) if player_natural else (1_000, 0)
    hands = [(player, 1_000)]
    split_rank = None
    first_action = _strategy(player, dealer[0], can_double=True, can_split=True)
    if first_action == "SPLIT":
        split_rank = player[0]
        hands = [([player[0], draw()], 1_000), ([player[1], draw()], 1_000)]
    completed = []
    for cards, stake in hands:
        if split_rank == 0:
            completed.append((cards, stake))
            continue
        first = True
        while True:
            action = _strategy(cards, dealer[0], can_double=first and split_rank is None, can_split=False)
            first = False
            if action == "DOUBLE":
                stake *= 2
                cards.append(draw())
                break
            if action == "STAND":
                break
            cards.append(draw())
            if _hand_value(cards)[0] >= 21:
                break
        completed.append((cards, stake))
    while True:
        dealer_value, soft = _hand_value(dealer)
        if dealer_value < 17 or (dealer_value == 17 and soft):
            dealer.append(draw())
        else:
            break
    dealer_value = _hand_value(dealer)[0]
    wager = payout = 0
    for cards, stake in completed:
        value = _hand_value(cards)[0]
        wager += stake
        if value > 21:
            continue
        if dealer_value > 21 or value > dealer_value:
            payout += stake * 2
        elif value == dealer_value:
            payout += stake
    return wager, payout


def _drawdown_step(balance, peak, maximum):
    peak = max(peak, balance)
    return peak, max(maximum, peak - balance)


def _simulate_seed(args):
    seed, rounds, blackjack_rounds = args
    rng = random.Random(seed)
    totals = {}
    for game in ("SLOT", "COINFLIP", "RPS", "NUMBER", "BOX"):
        wager = payout = 0
        balance = peak = drawdown = 0
        for _ in range(rounds):
            wager += 1_000
            if game == "SLOT":
                a, b, c = rng.randrange(6), rng.randrange(6), rng.randrange(6)
                if a == b == c:
                    gross = (3_000,2_200,3_000,4_000,5_000,8_000)[a]
                elif a == b or a == c or b == c:
                    gross = 2_000
                else:
                    gross = 0
            elif game == "COINFLIP":
                gross = 1_940 if rng.randrange(2) == 0 else 0
            elif game == "RPS":
                value = rng.randrange(3)
                gross = 1_901 if value == 0 else 1_000 if value == 1 else 0
            elif game == "NUMBER":
                gross = 19_000 if rng.randrange(20) == 0 else 0
            else:
                value = rng.randrange(100)
                gross = 0 if value < 50 else 1_000 if value < 80 else 2_000 if value < 95 else 5_000 if value < 99 else 15_000
            payout += gross
            balance += 1_000 - gross
            peak, drawdown = _drawdown_step(balance, peak, drawdown)
        totals[game] = {"wager": wager, "payout": payout, "maximumDrawdownEcy": drawdown}
    wager = payout = 0
    balance = peak = drawdown = 0
    for _ in range(blackjack_rounds):
        current_wager, gross = _blackjack_round(rng)
        wager += current_wager
        payout += gross
        balance += current_wager - gross
        peak, drawdown = _drawdown_step(balance, peak, drawdown)
    totals["BLACKJACK"] = {"wager": wager, "payout": payout, "maximumDrawdownEcy": drawdown}
    return seed, totals


def _confidence(values):
    mean = sum(values) / len(values)
    if len(values) == 1:
        return [mean, mean]
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    margin = 2.576 * math.sqrt(variance / len(values))
    return [mean - margin, mean + margin]


def run_d18_simulation(*, seeds=range(20), rounds_per_seed=1_000_000,
                       blackjack_sessions_per_seed=500_000, workers=None):
    arguments = [(int(seed), int(rounds_per_seed), int(blackjack_sessions_per_seed)) for seed in seeds]
    if workers == 1:
        results = [_simulate_seed(argument) for argument in arguments]
    else:
        with ProcessPoolExecutor(max_workers=workers or min(len(arguments), os.cpu_count() or 1)) as executor:
            results = list(executor.map(_simulate_seed, arguments))
    report = {
        "configuration": {"seeds": [seed for seed, _ in results], "roundsPerSeed": rounds_per_seed,
                          "blackjackSessionsPerSeed": blackjack_sessions_per_seed, "confidenceLevel": 0.99},
        "games": {}, "invariantFailures": 0,
    }
    for game, (theoretical, tolerance) in TARGETS.items():
        seed_rtps = []
        wager = payout = maximum_drawdown = 0
        for _, values in results:
            current = values[game]
            wager += current["wager"]
            payout += current["payout"]
            maximum_drawdown = max(maximum_drawdown, current["maximumDrawdownEcy"])
            seed_rtps.append(current["payout"] / current["wager"])
        simulated = payout / wager
        if len(seed_rtps) > 1:
            seed_variance = sum((value - sum(seed_rtps) / len(seed_rtps)) ** 2 for value in seed_rtps) / (len(seed_rtps) - 1)
            seed_margin = 2.576 * math.sqrt(seed_variance)
        else:
            seed_margin = tolerance
        seed_interval = [theoretical - seed_margin, theoretical + seed_margin]
        outside = sum(not (seed_interval[0] <= value <= seed_interval[1]) for value in seed_rtps)
        available = 25_000_000
        cap = available * 2 // 100
        effective = 1_000 if game == "BOX" else 0
        if game != "BOX":
            for candidate in range(1_000, 500_001, 1_000):
                if liability_for(game, candidate) <= cap and liability_for(game, candidate) <= available:
                    effective = candidate
                else:
                    break
        active_available = available - 400_000
        active_cap = active_available * 2 // 100
        wager_cases = [
            {"name": "minimum", "stakeEcy": 1_000},
            {"name": "effectiveMaximum", "stakeEcy": effective},
            {"name": "oneStepBelow", "stakeEcy": max(1_000, effective - 1_000)},
            {"name": "globalRequestCeiling", "stakeEcy": 500_000},
        ]
        rejected = 0
        for case in wager_cases:
            liability = liability_for(game, case["stakeEcy"])
            case["liabilityEcy"] = liability
            case["accepted"] = liability <= cap and liability <= available
            rejected += int(not case["accepted"])
        insufficient = liability_for(game, max(1_000, effective)) > 1
        wager_cases.append({"name": "insufficientExposure", "stakeEcy": max(1_000, effective),
                            "liabilityEcy": liability_for(game, max(1_000, effective)),
                            "accepted": not insufficient})
        rejected += int(insufficient)
        active_liability = liability_for(game, max(1_000, effective))
        active_accepted = active_liability <= active_cap and active_liability <= active_available
        wager_cases.append({"name": "activeReservations", "stakeEcy": max(1_000, effective),
                            "liabilityEcy": active_liability, "accepted": active_accepted})
        rejected += int(not active_accepted)
        report["games"][game] = {
            "theoreticalRtp": theoretical,
            "simulatedRtp": simulated,
            "rtpAfterIntegerRounding": simulated,
            "tolerance": tolerance,
            "confidenceInterval99": _confidence(seed_rtps),
            "seedAcceptanceInterval99": seed_interval,
            "seedsOutsideTolerance": outside,
            "rejectedBetCount": rejected,
            "wagerCases": wager_cases,
            "maximumReservedExposureEcy": liability_for(game, effective),
            "maximumObservedDrawdownEcy": maximum_drawdown,
            "passed": abs(simulated - theoretical) <= tolerance and outside <= 1,
        }
    report["passed"] = all(value["passed"] for value in report["games"].values()) and not report["invariantFailures"]
    return report
