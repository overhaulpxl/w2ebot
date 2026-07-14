"""Phase 1 economy foundation.

The package is intentionally isolated from the legacy RPG economy. Importing it
does not migrate balances or enable V1 wallet mutations.
"""

from .amounts import AmountParseError, format_economy_amount, parse_economy_amount
from .constants import (
    ECONOMY_PHASE2_ENABLED, ECONOMY_PHASE3_ENABLED, ECONOMY_PHASE4_ENABLED,
    ECONOMY_PHASE5_ENABLED, ECONOMY_PHASE6_ENABLED, ECONOMY_V1_ENABLED,
)
from .ledger import EconomyResult
from .treasury import get_supply_report

__all__ = [
    "AmountParseError",
    "ECONOMY_V1_ENABLED",
    "ECONOMY_PHASE2_ENABLED",
    "ECONOMY_PHASE3_ENABLED",
    "ECONOMY_PHASE4_ENABLED",
    "ECONOMY_PHASE5_ENABLED",
    "ECONOMY_PHASE6_ENABLED",
    "EconomyResult",
    "format_economy_amount",
    "get_supply_report",
    "parse_economy_amount",
]
