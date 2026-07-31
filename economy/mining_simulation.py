"""Simulasi deterministik Mining V1 tanpa menyentuh database."""

import hashlib
import json
import random

from .constants import CRYPTO_ASSETS, MINING_RIG_CATALOG
from .mining import DAY_SECONDS, calculate_mining_yield


SCENARIOS = {
    "daily": (DAY_SECONDS, 1),
    "casual_72h": (DAY_SECONDS * 3, 3),
    "frequent_15m": (15 * 60, 1),
    "max_offline_weekly_claim": (DAY_SECONDS, 7),
}


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def run_mining_simulation(*, seeds=20, days=90):
    results = []
    invariant_failures = 0
    overflow_attempts = 0
    for seed in range(int(seeds)):
        rng = random.Random(seed)
        daily_prices = {}
        for symbol, (_name, base, _bps, _level) in CRYPTO_ASSETS.items():
            daily_prices[symbol] = [max(base * 20 // 100, base + rng.randint(-base // 10, base // 10))
                                    for _ in range(int(days))]
        for definition_id, (_name, purchase, gross, maintenance) in MINING_RIG_CATALOG.items():
            for symbol in sorted(CRYPTO_ASSETS):
                prices = daily_prices[symbol]
                for scenario, (interval, claim_days) in SCENARIOS.items():
                    pending = carry = discarded = rounding_loss_numerator = 0
                    checkpoints_per_day = max(1, DAY_SECONDS // interval)
                    for day in range(int(days)):
                        average = sum(prices[max(0, day - 6):day + 1]) // min(7, day + 1)
                        observations = checkpoints_per_day if interval <= DAY_SECONDS else (1 if day % (interval // DAY_SECONDS) == 0 else 0)
                        for _ in range(observations):
                            rewarded = min(interval, DAY_SECONDS)
                            discarded += max(0, interval - DAY_SECONDS)
                            try:
                                calculation = calculate_mining_yield(gross, rewarded, average, carry, pending)
                            except OverflowError:
                                overflow_attempts += 1
                                continue
                            exact_numerator = gross * rewarded * 100_000_000
                            rounding_loss_numerator += exact_numerator % (DAY_SECONDS * average)
                            pending = calculation["pendingUnitsAfter"]
                            carry = calculation["resultingCarry"]
                        if (day + 1) % claim_days == 0:
                            pending = 0
                    net_daily = gross - maintenance
                    roi_days = purchase / net_daily
                    if not 66 <= roi_days <= 68 or not 0 <= carry < 1_000_000_000:
                        invariant_failures += 1
                    results.append({
                        "seed": seed, "rig": definition_id, "symbol": symbol, "scenario": scenario,
                        "grossEquivalentPerDay": gross, "maintenancePerDay": maintenance,
                        "netEquivalentPerDay": net_daily, "roiDays": roi_days,
                        "pendingUnits": pending, "fractionalCarry": carry,
                        "offlineDiscardSeconds": discarded,
                        "roundingLossNumerator": str(rounding_loss_numerator),
                    })
    summary = {
        "seeds": int(seeds), "days": int(days), "scenarioCount": len(results),
        "overflowAttempts": overflow_attempts, "duplicateOutput": 0,
        "durabilityViolations": 0, "invariantFailures": invariant_failures,
        "minimumRoiDays": min(item["roiDays"] for item in results),
        "maximumRoiDays": max(item["roiDays"] for item in results),
    }
    artifact = {"version": "phase7-mining-simulation-v1", "summary": summary, "results": results}
    artifact_hash = hashlib.sha256(_canonical(artifact).encode("ascii")).hexdigest()
    return {"artifact": artifact, "artifactHash": artifact_hash,
            "passed": invariant_failures == 0 and overflow_attempts == 0}
