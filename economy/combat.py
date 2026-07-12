"""Perhitungan combat integer-only Phase 3."""

from .constants import RPG_CRITICAL_MULTIPLIER_BPS, RPG_MAX_DAMAGE_REDUCTION_BPS


def damage_reduction_bps(defense, attacker_level):
    denominator = int(defense) + 500 + 20 * int(attacker_level)
    if denominator <= 0:
        return 0
    return min(RPG_MAX_DAMAGE_REDUCTION_BPS, int(defense) * 10_000 // denominator)


def final_damage(*, attack, attacker_level, defender_defense, variance_bps,
                 skill_bps=10_000, critical=False, context_damage_bps=0):
    if not 9_000 <= int(variance_bps) <= 11_000:
        raise ValueError("Variance combat tidak valid.")
    raw = int(attack) * int(skill_bps) // 10_000
    raw = raw * int(variance_bps) // 10_000
    reduction = damage_reduction_bps(defender_defense, attacker_level)
    damage = raw * (10_000 - reduction) // 10_000
    if critical:
        damage = damage * RPG_CRITICAL_MULTIPLIER_BPS // 10_000
    damage = damage * (10_000 + int(context_damage_bps)) // 10_000
    return max(1, damage)
