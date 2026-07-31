"""Perkembangan XP pemain dan pet dengan batas yang eksplisit."""

import math

from .constants import RPG_MAX_LEVEL, RPG_MAX_PET_LEVEL


def player_xp_required(level):
    return max(1, round(100 * int(level) ** 1.60))


def apply_player_xp(level, xp, amount):
    level, xp, amount = int(level), int(xp), int(amount)
    if amount < 0 or level < 1 or level > RPG_MAX_LEVEL or xp < 0:
        raise ValueError("State XP pemain tidak valid.")
    discarded = 0
    if level >= RPG_MAX_LEVEL:
        return RPG_MAX_LEVEL, 0, amount + xp
    xp += amount
    while level < RPG_MAX_LEVEL:
        required = player_xp_required(level)
        if xp < required:
            break
        xp -= required
        level += 1
    if level >= RPG_MAX_LEVEL:
        discarded = xp
        xp = 0
    return level, xp, discarded


def pet_xp_required(level):
    return max(1, round(50 * int(level) ** 1.50))


def apply_pet_xp(level, xp, amount):
    level, xp, amount = int(level), int(xp), int(amount)
    if amount < 0 or not 1 <= level <= RPG_MAX_PET_LEVEL or xp < 0:
        raise ValueError("State XP pet tidak valid.")
    if level == RPG_MAX_PET_LEVEL:
        return level, 0
    xp += amount
    while level < RPG_MAX_PET_LEVEL and xp >= pet_xp_required(level):
        xp -= pet_xp_required(level)
        level += 1
    return (RPG_MAX_PET_LEVEL, 0) if level == RPG_MAX_PET_LEVEL else (level, xp)
