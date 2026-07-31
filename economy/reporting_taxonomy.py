"""Stable Phase 9B reporting and notification taxonomies."""

from __future__ import annotations


NOTIFICATION_EVENT_TYPES = {
    "GENERAL": ("GENERAL_ANNOUNCEMENT",),
    "MARKET_CRYPTO": ("CRYPTO_MARKET_ALERT", "CRYPTO_MARKET_SURGE", "CRYPTO_MARKET_CRASH"),
    "MARKETPLACE": ("MARKETPLACE_WATCH_MATCH", "MARKETPLACE_REVIEW"),
    "GIVEAWAY": ("GIVEAWAY_CREATED", "GIVEAWAY_DRAWN", "GIVEAWAY_CANCELLED"),
    "CASINO": ("CASINO_REVIEW", "CASINO_RECOVERY"),
    "ETERNAL_OPTIONS": ("OPTION_SETTLED", "OPTION_REVIEW"),
    "MINING": ("MINING_REVIEW", "MINING_RECOVERY"),
    "BOSS": ("BOSS_STARTED", "BOSS_DEFEATED"),
    "LEVEL_UP": ("LEVEL_UP",),
    "BIRTHDAY": ("BIRTHDAY",),
    "BOOSTER": ("BOOSTER_STARTED",),
    "RECOVERY": ("RECOVERY_REQUIRED", "RECOVERY_COMPLETED"),
    "SECURITY": ("SECURITY_ALERT",),
    "OPERATOR_AUDIT": ("OPERATOR_ACTION",),
}

EMERGENCY_OPERATION_TYPES = {
    "TRANSFER", "EXCHANGE", "CRAFT", "ENHANCE", "MARKETPLACE", "CASINO",
    "CRYPTO", "MINING", "GIVEAWAY", "ETERNAL_OPTIONS",
}


def normalize_event_filter(category, event_types):
    allowed = set(NOTIFICATION_EVENT_TYPES.get(str(category), ()))
    values = sorted({str(item).strip().upper() for item in (event_types or ()) if str(item).strip()})
    if any(value not in allowed for value in values):
        raise ValueError("event_type_not_allowed")
    return values


def classify_operation(operation):
    value = str(operation or "").upper()
    groups = {
        "TRANSFER": ("TRANSFER",),
        "EXCHANGE": ("EXCHANGE",),
        "MARKETPLACE": ("MARKETPLACE", "MARKET_"),
        "CASINO_OPTIONS": ("CASINO", "ETERNAL_OPTION", "OPTION_"),
        "CRYPTO_MINING": ("CRYPTO", "MINING"),
        "GIVEAWAY": ("GIVEAWAY",),
        "RPG": ("RPG", "CRAFT", "ENHANCE", "QUEST", "HUNT", "DUNGEON", "BOSS"),
        "SYSTEM": ("SYSTEM_SEED", "MINT", "BURN", "ADJUST"),
    }
    for category, prefixes in groups.items():
        if value.startswith(prefixes):
            return category
    return "UNCLASSIFIED"
