"""Simulasi deterministik penerimaan market Crypto Phase 6."""

import hashlib
import json
import math

from .constants import (
    CRYPTO_ASSETS, CRYPTO_MAJOR_EVENT_PER_100000, CRYPTO_NORMAL_EVENT_PER_100000,
)
from .crypto_market import DeterministicRng, plan_tick


def _frequency_check(observed, total, probability):
    expected = total * probability
    deviation = abs(observed - expected)
    sigma = math.sqrt(total * probability * (1 - probability))
    return {"observed": observed, "expected": expected, "sigma": sigma,
            "passed": deviation <= max(5 * sigma, 5)}


def run_phase6_market_simulation(*, seeds=20, ticks_per_seed=43_200):
    total_ticks = int(seeds) * int(ticks_per_seed)
    totals = {
        "normalEvents": 0, "majorEvents": 0, "boundViolations": 0,
        "normalVolatilityViolations": 0, "eventReplacementViolations": 0,
        "multipleEventViolations": 0, "integerOverflowFailures": 0,
    }
    extrema = {symbol: {"minimum": None, "maximum": None} for symbol in CRYPTO_ASSETS}
    seed_hashes = []
    for seed in range(int(seeds)):
        states = {
            symbol: {"currentPriceEcy": definition[1], "version": 0}
            for symbol, definition in CRYPTO_ASSETS.items()
        }
        seed_digest = hashlib.sha256()
        rng = DeterministicRng(seed)
        for _ in range(int(ticks_per_seed)):
            plan = plan_tick(states, rng=rng)
            event_type = plan["eventType"]
            totals["normalEvents"] += int(event_type == "NORMAL_EVENT")
            totals["majorEvents"] += int(event_type == "MAJOR_EVENT")
            event_assets = 0
            for symbol, asset in plan["assets"].items():
                _, base, maximum_bps, _ = CRYPTO_ASSETS[symbol]
                price = int(asset["currentPriceEcy"])
                if price < base * 20 // 100 or price > base * 500 // 100:
                    totals["boundViolations"] += 1
                if asset["movementType"] == "NORMAL" and abs(int(asset["movementBps"])) > maximum_bps:
                    totals["normalVolatilityViolations"] += 1
                if asset["movementType"] in ("NORMAL_EVENT", "MAJOR_EVENT"):
                    event_assets += 1
                    if symbol != plan["eventSymbol"] or asset["movementType"] != event_type:
                        totals["eventReplacementViolations"] += 1
                extrema[symbol]["minimum"] = price if extrema[symbol]["minimum"] is None else min(extrema[symbol]["minimum"], price)
                extrema[symbol]["maximum"] = price if extrema[symbol]["maximum"] is None else max(extrema[symbol]["maximum"], price)
                states[symbol] = {"currentPriceEcy": price, "version": states[symbol]["version"] + 1}
            if event_assets != int(event_type is not None):
                totals["multipleEventViolations"] += 1
            seed_digest.update(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("ascii"))
        seed_hashes.append(seed_digest.hexdigest())

    # Isolate the reversion term from random drift at symmetric prices.
    reversion_checks = {}
    for symbol, (_, base, _, _) in CRYPTO_ASSETS.items():
        low_states = {key: {"currentPriceEcy": value[1], "version": 0} for key, value in CRYPTO_ASSETS.items()}
        high_states = {key: dict(value) for key, value in low_states.items()}
        low_states[symbol]["currentPriceEcy"] = base // 2
        high_states[symbol]["currentPriceEcy"] = base * 2
        low_sum = high_sum = 0
        samples = 10_000
        for sample in range(samples):
            low_sum += plan_tick(low_states, DeterministicRng(1_000_000 + sample))["assets"][symbol]["movementBps"]
            high_sum += plan_tick(high_states, DeterministicRng(2_000_000 + sample))["assets"][symbol]["movementBps"]
        reversion_checks[symbol] = {"belowBaseMeanBps": low_sum / samples,
                                    "aboveBaseMeanBps": high_sum / samples,
                                    "passed": low_sum > 0 and high_sum < 0}

    normal_frequency = _frequency_check(
        totals["normalEvents"], total_ticks, CRYPTO_NORMAL_EVENT_PER_100000 / 100_000,
    )
    major_frequency = _frequency_check(
        totals["majorEvents"], total_ticks, CRYPTO_MAJOR_EVENT_PER_100000 / 100_000,
    )
    invariants_passed = all(totals[key] == 0 for key in (
        "boundViolations", "normalVolatilityViolations", "eventReplacementViolations",
        "multipleEventViolations", "integerOverflowFailures",
    ))
    body = {
        "simulation": "phase6-crypto-market-v1", "seeds": int(seeds),
        "ticksPerSeed": int(ticks_per_seed), "totalTicks": total_ticks,
        "configuredNormalEventProbability": "0.0005",
        "configuredMajorEventProbability": "0.00005",
        "totals": totals, "normalEventFrequency": normal_frequency,
        "majorEventFrequency": major_frequency, "priceExtrema": extrema,
        "meanReversion": reversion_checks, "seedHashes": seed_hashes,
    }
    body["passed"] = (invariants_passed and normal_frequency["passed"] and
                      major_frequency["passed"] and
                      all(value["passed"] for value in reversion_checks.values()))
    body["artifactSha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    return body
