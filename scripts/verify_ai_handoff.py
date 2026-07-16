"""Static, non-mutating verifier for the Living PRD handoff."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from generate_ai_handoff import render_handoff


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HEX_HASH = re.compile(r"^(?:PENDING|[0-9a-fA-F]{7,40})$")
CHECKSUM = re.compile(r"^[0-9a-fA-F]{64}$")
CATALOG_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
STATUS_VALUES = {
    "verified", "repository_observed", "historical_verified",
    "last_known_requires_verification", "documented_mismatch",
}
REQUIRED_TOP_LEVEL = {
    "schemaVersion", "project", "purpose", "sourceOfTruth", "repositorySnapshot",
    "phaseStatuses", "protectedSystems", "featureFlags", "commandOwnership",
    "capabilitiesByPhase", "economyConstants",
    "forbiddenAliases", "legacyCommands", "importantCommits", "migrations", "catalogs",
    "dealMiddlemanTrustedVouch", "interactionRecovery", "paymentConfiguration",
    "economyDesign", "phase1", "phase2", "phase3Rpg", "rpgBalance",
    "phase4Marketplace", "marketplaceHardening", "moduleOwnership",
    "marketplaceLifecycleDefinitions", "phase5Casino", "phase6Crypto", "phase7Mining",
    "phase8GiveawayOptions", "phase9aBackendSafety", "phase9bDashboardNotificationRouting",
    "phase9cFinalQa",
    "verificationHistory", "stagingStatus", "dashboardStatus", "productionStatus",
    "knownLimitations", "blockers", "pendingWork", "aiCoderOnboarding",
    "livingPrdWorkflow", "taskCompletionTemplate", "definitionOfDone",
    "latestCompletedTask", "taskHistory", "updateHistory", "currentHandoffSummary",
    "lastUpdatedAt",
}
FORBIDDEN_PREFIXES = {
    "vouch", "vouches", "rep", "trustlb", "trank", "vouchleaderboard",
    "vouchremove", "vouchreport",
}
FLAG_NAMES = (
    "ECONOMY_V1_ENABLED", "ECONOMY_PHASE2_ENABLED",
    "ECONOMY_PHASE3_ENABLED", "ECONOMY_PHASE4_ENABLED", "ECONOMY_PHASE5_ENABLED",
    "ECONOMY_PHASE6_ENABLED", "ECONOMY_PHASE7_ENABLED", "ECONOMY_PHASE8_ENABLED",
)


def _claim_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value and "verificationStatus" in value:
        return value["value"]
    return value


def _issues_for_claims(value: Any, path: str = "state") -> list[str]:
    issues: list[str] = []
    if isinstance(value, dict):
        if "verificationStatus" in value:
            status = value["verificationStatus"]
            if status not in STATUS_VALUES:
                issues.append(f"{path}: verificationStatus tidak valid")
            if status in {"verified", "repository_observed"} and not value.get("evidencePaths"):
                issues.append(f"{path}: claim terverifikasi tanpa evidencePaths")
        for key, child in value.items():
            issues.extend(_issues_for_claims(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(_issues_for_claims(child, f"{path}[{index}]"))
    return issues


def _parse_source(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _assignment_map(tree: ast.Module) -> dict[str, ast.AST]:
    assignments: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            assignments[node.target.id] = node.value
    return assignments


def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError) as exc:
        raise ValueError("literal source yang diperlukan tidak dapat diekstrak") from exc


def _extract_flag_defaults(path: Path) -> dict[str, bool]:
    values = _assignment_map(_parse_source(path))
    result: dict[str, bool] = {}
    for name in FLAG_NAMES:
        node = values.get(name)
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "_env_bool":
            raise ValueError(f"{name} bukan _env_bool literal")
        if len(node.args) != 2 or not isinstance(node.args[0], ast.Constant) or node.args[0].value != name:
            raise ValueError(f"{name} tidak memiliki nama literal yang benar")
        default = _literal(node.args[1])
        if not isinstance(default, bool):
            raise ValueError(f"{name} default bukan bool")
        result[name] = default
    return result


def _extract_phase_checksums(root: Path) -> dict[int, str]:
    phase3 = _assignment_map(_parse_source(root / "economy" / "phase3_schema.py"))
    phase4 = _assignment_map(_parse_source(root / "economy" / "phase4_schema.py"))
    phase3_sql = _literal(phase3["PHASE3_SCHEMA_SQL"])
    phase3_triggers = _literal(phase3["PHASE3_TRIGGER_SQL"])
    phase4_algorithm = _literal(phase4["STACK_MIGRATION_ALGORITHM"])
    phase4_sql = _literal(phase4["PHASE4_SCHEMA_SQL"])
    phase4_triggers = _literal(phase4["PHASE4_TRIGGER_SQL"])
    phase5 = _assignment_map(_parse_source(root / "economy" / "phase5_schema.py"))
    phase5_name = _literal(phase5["PHASE5_MIGRATION_NAME"])
    phase5_sql = _literal(phase5["PHASE5_TABLE_SQL"])
    phase5_indexes = _literal(phase5["PHASE5_INDEX_SQL"])
    phase5_triggers = _literal(phase5["PHASE5_TRIGGER_SQL"])
    phase6 = _assignment_map(_parse_source(root / "economy" / "phase6_schema.py"))
    phase6_name = _literal(phase6["PHASE6_MIGRATION_NAME"])
    phase6_sql = _literal(phase6["PHASE6_TABLE_SQL"])
    phase6_indexes = _literal(phase6["PHASE6_INDEX_SQL"])
    phase6_triggers = _literal(phase6["PHASE6_TRIGGER_SQL"])
    phase7 = _assignment_map(_parse_source(root / "economy" / "phase7_schema.py"))
    phase7_name = _literal(phase7["PHASE7_MIGRATION_NAME"])
    phase7_sql = _literal(phase7["PHASE7_TABLE_SQL"])
    phase7_indexes = _literal(phase7["PHASE7_INDEX_SQL"])
    phase7_triggers = _literal(phase7["PHASE7_TRIGGER_SQL"])
    phase8 = _assignment_map(_parse_source(root / "economy" / "phase8_schema.py"))
    phase8_name = _literal(phase8["PHASE8_MIGRATION_NAME"])
    phase8_sql = _literal(phase8["PHASE8_TABLE_SQL"])
    phase8_indexes = _literal(phase8["PHASE8_INDEX_SQL"])
    phase8_triggers = _literal(phase8["PHASE8_TRIGGER_SQL"])
    phase9a = _assignment_map(_parse_source(root / "economy" / "phase9a_schema.py"))
    phase9a_name = _literal(phase9a["PHASE9A_MIGRATION_NAME"])
    phase9a_sql = _literal(phase9a["PHASE9A_TABLE_SQL"])
    phase9a_indexes = _literal(phase9a["PHASE9A_INDEX_SQL"])
    phase9a_triggers = _literal(phase9a["PHASE9A_TRIGGER_SQL"])
    phase9b = _assignment_map(_parse_source(root / "economy" / "phase9b_schema.py"))
    phase9b_name = _literal(phase9b["PHASE9B_MIGRATION_NAME"])
    phase9b_sql = _literal(phase9b["PHASE9B_TABLE_SQL"])
    phase9b_indexes = _literal(phase9b["PHASE9B_INDEX_SQL"])
    phase9b_triggers = _literal(phase9b["PHASE9B_TRIGGER_SQL"])
    canonical = lambda value: " ".join(str(value).split())
    return {
        301: hashlib.sha256((phase3_sql + "\n" + "\n".join(phase3_triggers)).encode("utf-8")).hexdigest(),
        400: hashlib.sha256((phase4_algorithm + "\n" + phase4_sql + "\n" + "\n".join(phase4_triggers)).encode("utf-8")).hexdigest(),
        500: hashlib.sha256(
            (phase5_name + "\n" + canonical(phase5_sql) + "\n" +
             "\n".join(canonical(value) for value in phase5_indexes + phase5_triggers)).encode("utf-8")
        ).hexdigest(),
        600: hashlib.sha256(
            (phase6_name + "\n" + canonical(phase6_sql) + "\n" +
             "\n".join(canonical(value) for value in phase6_indexes + phase6_triggers)).encode("utf-8")
        ).hexdigest(),
        700: hashlib.sha256(
            (phase7_name + "\n" + canonical(phase7_sql) + "\n" +
             "\n".join(canonical(value) for value in phase7_indexes + phase7_triggers)).encode("utf-8")
        ).hexdigest(),
        800: hashlib.sha256(
            (phase8_name + "\n" + canonical(phase8_sql) + "\n" +
             "\n".join(canonical(value) for value in phase8_indexes + phase8_triggers)).encode("utf-8")
        ).hexdigest(),
        900: hashlib.sha256(
            (phase9a_name + "\n" + canonical(phase9a_sql) + "\n" +
             "\n".join(canonical(value) for value in phase9a_indexes + phase9a_triggers)).encode("utf-8")
        ).hexdigest(),
        910: hashlib.sha256(
            (phase9b_name + "\n" + canonical(phase9b_sql) + "\n" +
             "\n".join(canonical(value) for value in phase9b_indexes + phase9b_triggers)).encode("utf-8")
        ).hexdigest(),
    }


class _CatalogEvaluator:
    """Narrow AST evaluator for the literal catalog payload; no module import."""

    def __init__(self, tree: ast.Module):
        self.nodes = _assignment_map(tree)
        self.cache: dict[str, Any] = {}

    @staticmethod
    def _equipment(*args: Any, **kwargs: Any) -> dict[str, Any]:
        item_id, name, rarity, slot, level, value = args
        return {
            "item_id": item_id, "name": name, "type": "EQUIPMENT", "rarity": rarity,
            "slot": slot, "required_level": level, "base_value": value,
            "hp": kwargs.get("hp", 0), "attack": kwargs.get("attack", 0),
            "defense": kwargs.get("defense", 0), "crit_bps": kwargs.get("crit_bps", 0),
            "boss_damage_bps": kwargs.get("boss_damage_bps", 0), "set_id": kwargs.get("set_id"),
            "tradeable": rarity != "ETERNAL",
        }

    def name(self, name: str) -> Any:
        if name not in self.cache:
            if name not in self.nodes:
                raise ValueError(f"catalog name tidak dikenal: {name}")
            self.cache[name] = self.expression(self.nodes[name])
        return self.cache[name]

    def expression(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return self.name(node.id)
        if isinstance(node, ast.Tuple):
            return tuple(self.expression(item) for item in node.elts)
        if isinstance(node, ast.List):
            return [self.expression(item) for item in node.elts]
        if isinstance(node, ast.Dict):
            return {self.expression(key): self.expression(value) for key, value in zip(node.keys, node.values)}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -self.expression(node.operand)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_equipment":
            return self._equipment(*(self.expression(arg) for arg in node.args),
                                   **{kw.arg: self.expression(kw.value) for kw in node.keywords})
        if isinstance(node, ast.Subscript):
            return self.expression(node.value)[self.expression(node.slice)]
        if isinstance(node, ast.DictComp) and len(node.generators) == 1:
            generator = node.generators[0]
            if not isinstance(generator.target, ast.Name):
                raise ValueError("comprehension catalog tidak didukung")
            iterable = self.expression(generator.iter)
            result = {}
            for value in iterable:
                original = self.cache.get(generator.target.id, None)
                self.cache[generator.target.id] = value
                result[self.expression(node.key)] = self.expression(node.value)
                if original is None:
                    self.cache.pop(generator.target.id, None)
                else:
                    self.cache[generator.target.id] = original
            return result
        raise ValueError(f"AST catalog tidak didukung: {type(node).__name__}")


def _extract_catalog_checksum(root: Path) -> tuple[str, str]:
    constants = _assignment_map(_parse_source(root / "economy" / "constants.py"))
    version = _literal(constants["RPG_PHASE3_CATALOG_VERSION"])
    evaluator = _CatalogEvaluator(_parse_source(root / "economy" / "catalog.py"))
    names = {
        "equipment": "EQUIPMENT", "sets": "SETS", "pets": "PETS", "items": "STACK_ITEMS",
        "hunts": "HUNTS", "dungeons": "DUNGEONS", "bosses": "BOSSES",
        "hunt_drops": "HUNT_DROPS", "dungeon_drops": "DUNGEON_DROPS", "boss_drops": "BOSS_DROPS",
        "craft_recipes": "CRAFT_RECIPES", "pet_duplicate_essence": "PET_DUPLICATE_ESSENCE",
        "enhancement_materials": "ENHANCEMENT_MATERIALS",
    }
    payload = {key: evaluator.name(name) for key, name in names.items()}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return version, hashlib.sha256(encoded).hexdigest()


def _decorated_commands(path: Path) -> set[str]:
    commands: set[str] = set()
    for node in ast.walk(_parse_source(path)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "tree":
                continue
            if decorator.func.attr != "command":
                continue
            for keyword in decorator.keywords:
                if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                    commands.add(str(keyword.value.value))
    return commands


def _prefix_handlers(path: Path) -> set[str]:
    handlers: set[str] = set()
    for node in ast.walk(_parse_source(path)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id == "register_prefix_command_handler" and node.args and isinstance(node.args[0], ast.Constant):
            handlers.add(str(node.args[0].value))
    return handlers


def _static_command_issues(root: Path, state: dict) -> list[str]:
    issues: list[str] = []
    rpg = root / "cogs" / "rpg.py"
    deal = root / "cogs" / "deal.py"
    core_source = (root / "core.py").read_text(encoding="utf-8")
    deal_source = deal.read_text(encoding="utf-8")
    actual = {
        "/leaderboard": "RPG" if "leaderboard" in _decorated_commands(rpg) else None,
        "/rank": "Trusted Vouch" if "rank" in _decorated_commands(deal) else None,
        "/vouchleaderboard": "Trusted Vouch" if "vouchleaderboard" in _decorated_commands(deal) else None,
        "w!rank": "RPG" if "rank" in _prefix_handlers(rpg) else None,
        "w!leaderboard": "RPG",
        "w!deal rank": "Trusted Vouch",
        "w!deal leaderboard": "Trusted Vouch",
    }
    documented = _claim_value(state["commandOwnership"])
    for command, owner in actual.items():
        if owner is None:
            issues.append(f"command source tidak menemukan {command}")
        elif documented.get(command) != owner:
            issues.append(f"ownership {command} tidak cocok dengan source")
    cog_paths = tuple((root / "cogs").glob("*.py"))
    for command in ("leaderboard", "rank", "vouchleaderboard"):
        registrations = sum(command in _decorated_commands(path) for path in cog_paths)
        if registrations != 1:
            issues.append(f"protected slash ownership ambigu: /{command}")
    if sum("rank" in _prefix_handlers(path) for path in cog_paths) != 1:
        issues.append("protected prefix ownership ambigu: w!rank")
    if "tree.get_command(cmd_name)" not in core_source:
        issues.append("generic prefix Tree fallback tidak dapat diverifikasi")
    for subcommand in ("rank", "leaderboard"):
        if f'if subcommand == "{subcommand}"' not in deal_source:
            issues.append(f"deal prefix dispatcher tidak mendukung {subcommand}")
    rpg_commands = _decorated_commands(rpg)
    for legacy in ("sell", "shop", "buy", "buypet"):
        if legacy not in rpg_commands:
            issues.append(f"legacy slash /{legacy} tidak ditemukan")
    core_tree = _parse_source(root / "core.py")
    assignments = _assignment_map(core_tree)
    try:
        reserved = set(_literal(assignments["DEAL_PREFIX_RESERVED_TOP_LEVEL"]))
    except (KeyError, ValueError):
        issues.append("DEAL_PREFIX_RESERVED_TOP_LEVEL tidak dapat diverifikasi")
        reserved = set()
    if not FORBIDDEN_PREFIXES.issubset(reserved):
        issues.append("forbidden prefix aliases tidak seluruhnya reserved")
    for cog in cog_paths:
        overlap = FORBIDDEN_PREFIXES.intersection(_prefix_handlers(cog))
        if overlap:
            issues.append(f"forbidden aliases terdaftar pada {cog.name}: {sorted(overlap)}")
    return issues


def _secret_issues(text: str, label: str) -> list[str]:
    patterns = (
        r"(?i)(?:discord|gemini|dashboard)[_-]?(?:token|api[_-]?key)\s*[:=]\s*[\"']?(?!PENDING|REDACTED|<)[A-Za-z0-9_\-.]{12,}",
        r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"\b(?:sk|ghp)_[A-Za-z0-9]{16,}\b",
    )
    return [f"{label}: kemungkinan secret terdeteksi" for pattern in patterns if re.search(pattern, text)]


def _private_content_issues(text: str, label: str) -> list[str]:
    patterns = (
        r"(?i)(?:database_path|staging_guild_id|allowed_server_id)\s*[:=]\s*(?!\s*(?:null|false|PENDING|REDACTED))[\"']?[^\s\"',}]+",
        r"(?i)(?:payment(?:_|\s)+(?:account|destination)|paymentAccount|paymentDestination|payout(?:_|\s)+account|payoutAccount|proof(?:_|\s)+url|proofUrl|qris)[\"'`*]*\s*[:=]",
        r"(?i)\b(?:INSERT INTO|UPDATE\s+\w+\s+SET|DELETE FROM)\b",
    )
    return [f"{label}: private environment/data pattern terdeteksi" for pattern in patterns if re.search(pattern, text)]


def _phase5_planning_issues(root: Path, state: dict, phase5_status: str | None) -> list[str]:
    issues: list[str] = []
    supported_statuses = {"planning", "implemented_blocked_staging", "implemented_staging_ready"}
    if phase5_status not in supported_statuses:
        if phase5_status not in {"not_started", "not_implemented", "not_approved"}:
            issues.append("Phase 5 tidak berada pada guard status")
        return issues

    planning = _claim_value(state.get("phase5Casino", {}))
    implemented = phase5_status in {"implemented_blocked_staging", "implemented_staging_ready"}
    expected = {
        "implementationStatus": "implemented",
        "productionStatus": "not_approved",
        "productionMigrated": False,
        "productionEnabled": False,
        "runtimeFeatureFlagExists": True,
        "migrationExists": True,
        "planningDocument": "docs/PHASE5_CASINO_PRD.md",
    } if implemented else {
        "implementationStatus": "not_started",
        "productionStatus": "not_approved",
        "productionMigrated": False,
        "productionEnabled": False,
        "runtimeFeatureFlagExists": False,
        "migrationExists": False,
        "planningDocument": "docs/PHASE5_CASINO_PRD.md",
    }
    if not isinstance(planning, dict):
        return ["Phase 5 planning state tidak valid"]
    for field, value in expected.items():
        if planning.get(field) != value:
            issues.append(f"Phase 5 planning guard tidak valid: {field}")
    planning_document = root / str(planning.get("planningDocument", ""))
    if not planning_document.is_file():
        issues.append("Phase 5 planning document tidak ditemukan")
    if planning.get("ownerDecisionStatus") != "approved_with_conditions":
        issues.append("Phase 5 owner decision status tidak valid")
    unresolved = planning.get("unresolvedOwnerDecisions")
    if unresolved != []:
        issues.append("Phase 5 masih memiliki unresolved owner decisions")

    decisions = planning.get("ownerDecisionRecords")
    expected_ids = {f"D{number:02d}" for number in range(1, 21)}
    decision_ids = [row.get("id") for row in decisions if isinstance(row, dict)] if isinstance(decisions, list) else []
    if set(decision_ids) != expected_ids or len(decision_ids) != len(expected_ids):
        issues.append("Phase 5 decision records harus tepat D01-D20 dan unik")
    valid_statuses = {"approved_recommended", "approved_with_revision", "provisionally_approved"}
    if not isinstance(decisions, list) or any(
        not isinstance(row, dict)
        or row.get("status") not in valid_statuses
        or not isinstance(row.get("decision"), str)
        or not row["decision"].strip()
        for row in decisions
    ):
        issues.append("Phase 5 decision approval status tidak valid")
    d02 = next((row for row in decisions if isinstance(row, dict) and row.get("id") == "D02"), None) if isinstance(decisions, list) else None
    if not isinstance(d02, dict) or not isinstance(d02.get("condition"), str) or not d02["condition"].strip():
        issues.append("Phase 5 D02 simulation/reapproval gate tidak valid")
    gates = planning.get("simulationAcceptanceGates")
    if not isinstance(gates, list) or not any(
        isinstance(gate, dict)
        and gate.get("decisionId") == "D02"
        and isinstance(gate.get("gate"), str)
        and "simulation" in gate["gate"].lower()
        and ("owner approval" in gate["gate"].lower() or gate.get("status") == "passed")
        for gate in gates
    ):
        issues.append("Phase 5 D02 structured simulation gate tidak valid")

    if planning.get("wagerIncrementEcy") != 1000:
        issues.append("Phase 5 wager increment harus 1000 ECY")
    if planning.get("fixedPricesEcy") != {"gacha": 1000, "lootBox": 1000}:
        issues.append("Phase 5 fixed Casino prices harus 1000 ECY")
    expected_authorization = {
        "CASINO_CONTROL": ["pause", "resume", "status"],
        "CASINO_FINANCIAL": ["initial_seed", "bankroll_adjustment", "excess_distribution"],
        "CASINO_RECOVERY": ["reviewed_refund", "review_resolution", "compensating_settlement"],
    }
    if planning.get("authorizationClasses") != expected_authorization:
        issues.append("Phase 5 Casino authorization classes tidak valid")
    if planning.get("approvedMigration") != {"version": 500, "name": "phase5-casino"}:
        issues.append("Phase 5 approved migration identity tidak valid")
    if planning.get("migrationExists") is not implemented:
        issues.append("Phase 5 migration existence guard tidak valid")
    if planning.get("approvedFutureFeatureFlagName") != "ECONOMY_PHASE5_ENABLED":
        issues.append("Phase 5 approved feature flag identity tidak valid")
    if planning.get("runtimeFeatureFlagExists") is not implemented:
        issues.append("Phase 5 runtime feature flag existence guard tidak valid")

    simulation = planning.get("simulationResult")
    simulation_passed = isinstance(simulation, dict) and simulation.get("passed") is True
    simulation_shape_valid = isinstance(simulation, dict) and simulation.get("completed") is True
    if phase5_status == "implemented_staging_ready":
        blackjack = simulation.get("blackjack", {}) if isinstance(simulation, dict) else {}
        configuration = simulation.get("configuration", {}) if isinstance(simulation, dict) else {}
        metrics_valid = isinstance(blackjack, dict) \
            and blackjack.get("theoreticalRtp") == 0.975 \
            and isinstance(blackjack.get("simulatedRtp"), (int, float)) \
            and blackjack.get("tolerance") == 0.002 \
            and abs(blackjack["simulatedRtp"] - blackjack["theoreticalRtp"]) <= blackjack["tolerance"] \
            and isinstance(blackjack.get("seedsOutsideAcceptance"), int) \
            and blackjack["seedsOutsideAcceptance"] <= 1 \
            and configuration == {"seeds": 20, "roundsPerSeedFixedGames": 1_000_000,
                                  "blackjackSessionsPerSeed": 500_000} \
            and simulation.get("otherGamesPassed") is True \
            and simulation.get("invariantFailures") == 0 \
            and isinstance(simulation.get("artifactSha256"), str) \
            and re.fullmatch(r"[0-9a-f]{64}", simulation["artifactSha256"]) is not None
        simulation_shape_valid = simulation_shape_valid and simulation_passed \
            and simulation.get("stagingReady") is True and simulation.get("blockingDecision") is None \
            and isinstance(d02, dict) and d02.get("status") == "approved_recommended" \
            and d02.get("simulationGateStatus") == "passed" and metrics_valid
    elif phase5_status == "implemented_blocked_staging":
        simulation_shape_valid = simulation_shape_valid and not simulation_passed \
            and simulation.get("stagingReady") is False and simulation.get("blockingDecision") == "D02" \
            and isinstance(d02, dict) and d02.get("status") == "provisionally_approved"
    if implemented and not simulation_shape_valid:
        issues.append("Phase 5 D18/D02 implementation result tidak valid")

    blockers = _claim_value(state.get("blockers", []))
    if not isinstance(blockers, list):
        issues.append("Phase 5 blockers tidak valid")
    elif any(
        "phase 5" in str(item).lower()
        and "owner decision" in str(item).lower()
        and ("must be approved" in str(item).lower() or "unresolved" in str(item).lower())
        for item in blockers
    ):
        issues.append("Phase 5 stale owner-decision blocker masih ada")
    if not simulation_passed and (not isinstance(blockers, list) or not any(
        "d02" in str(item).lower() and "simulation" in str(item).lower() for item in blockers
    )):
        issues.append("Phase 5 D02 simulation gate tidak tercatat sebagai blocker")
    if simulation_passed and isinstance(blockers, list) and any("d02" in str(item).lower() for item in blockers):
        issues.append("Phase 5 D02 blocker masih tercatat setelah simulation pass")
    pending = _claim_value(state.get("pendingWork", []))
    if not isinstance(pending, list) or not any("phase 5" in str(item).lower() for item in pending):
        issues.append("Phase 5 follow-up tidak tercatat sebagai pending work")

    try:
        runtime_flag_found = "ECONOMY_PHASE5_ENABLED" in _assignment_map(
            _parse_source(root / "runtime_config.py")
        )
    except (OSError, SyntaxError):
        runtime_flag_found = False
    if runtime_flag_found is not implemented:
        issues.append("Phase 5 runtime flag existence tidak cocok state")
    runtime_modules_found = (root / "scripts" / "migrate_economy_phase5.py").exists() and any(
        path.is_file() for path in (root / "economy").glob("*phase5*")
    )
    if runtime_modules_found is not implemented:
        issues.append("Phase 5 migration/runtime module existence tidak cocok state")
    documented_versions = {
        row.get("version") for row in _claim_value(state.get("migrations", [])) if isinstance(row, dict)
    }
    if (500 in documented_versions) is not implemented:
        issues.append("Phase 5 migration 500 documentation tidak cocok state")
    return issues


def _phase6_issues(root: Path, state: dict, phase6_status: str | None) -> list[str]:
    issues: list[str] = []
    phase6 = _claim_value(state.get("phase6Crypto", {}))
    if phase6_status != "implemented_staging_ready" or phase6.get("status") != phase6_status:
        issues.append("Phase 6 status harus implemented_staging_ready")
    if phase6.get("implementationStatus") != "implemented":
        issues.append("Phase 6 implementation status tidak valid")
    if (phase6.get("productionStatus") != "not_approved" or
            phase6.get("productionMigrated") is not False or
            phase6.get("productionSeeded") is not False or
            phase6.get("productionEnabled") is not False):
        issues.append("Phase 6 production guard tidak valid")
    if phase6.get("featureFlag") != {"name": "ECONOMY_PHASE6_ENABLED", "default": False}:
        issues.append("Phase 6 feature flag state tidak valid")
    migration = phase6.get("migration", {})
    if migration.get("version") != 600 or migration.get("name") != "phase6-crypto" \
            or migration.get("startupAutomatic") is not False \
            or not CHECKSUM.fullmatch(str(migration.get("checksum", ""))):
        issues.append("Phase 6 migration identity tidak valid")
    simulation = phase6.get("simulation", {})
    if (simulation.get("completed") is not True or simulation.get("passed") is not True or
            simulation.get("seeds") != 20 or simulation.get("ticksPerSeed") != 43_200 or
            simulation.get("totalTicks") != 864_000 or simulation.get("invariantFailures") != 0 or
            not CHECKSUM.fullmatch(str(simulation.get("artifactSha256", "")))):
        issues.append("Phase 6 simulation result tidak valid")
    if phase6.get("marketScope") != {
        "prices": "one global authoritative series", "financialState": "guild-scoped",
        "tickIntervalSeconds": 60, "offlineBackfill": False,
    }:
        issues.append("Phase 6 global/guild scope tidak valid")
    pending = _claim_value(state.get("pendingWork", []))
    if not isinstance(pending, list) or not any("phase 6" in str(item).lower() for item in pending):
        issues.append("Phase 6 connected staging tidak tercatat sebagai pending work")
    if not (root / "docs" / "PHASE6_CRYPTO_PRD.md").is_file():
        issues.append("Phase 6 PRD tidak ditemukan")
    if not (root / "scripts" / "migrate_economy_phase6.py").is_file():
        issues.append("Phase 6 migration CLI tidak ditemukan")
    return issues


def _phase7_issues(root: Path, state: dict, phase7_status: str | None) -> list[str]:
    issues: list[str] = []
    phase7 = _claim_value(state.get("phase7Mining", {}))
    if phase7_status != "implemented_staging_ready" or phase7.get("status") != phase7_status:
        issues.append("Phase 7 status harus implemented_staging_ready")
    if phase7.get("implementationStatus") != "implemented":
        issues.append("Phase 7 implementation status tidak valid")
    if (phase7.get("productionStatus") != "not_approved" or
            phase7.get("productionMigrated") is not False or
            phase7.get("productionSeeded") is not False or
            phase7.get("productionEnabled") is not False):
        issues.append("Phase 7 production guard tidak valid")
    if phase7.get("featureFlag") != {"name": "ECONOMY_PHASE7_ENABLED", "default": False}:
        issues.append("Phase 7 feature flag state tidak valid")
    migration = phase7.get("migration", {})
    if (migration.get("version") != 700 or migration.get("name") != "phase7-mining" or
            migration.get("startupAutomatic") is not False or
            not CHECKSUM.fullmatch(str(migration.get("checksum", "")))):
        issues.append("Phase 7 migration identity tidak valid")
    dependencies = phase7.get("dependencies", {})
    if (dependencies.get("phase3ProfileCapability") is not True or
            dependencies.get("phase3RuntimeFlagRequired") is not False or
            dependencies.get("existingProfileRequired") is not True):
        issues.append("Phase 7 profile capability contract tidak valid")
    accounting = phase7.get("accounting", {})
    if (accounting.get("claimUsesEconomyTransaction") is not False or
            accounting.get("holdingCostBasisChangedByClaim") is not False):
        issues.append("Phase 7 asset-only claim contract tidak valid")
    simulation = phase7.get("simulation", {})
    if (simulation.get("completed") is not True or simulation.get("passed") is not True or
            simulation.get("seeds") != 20 or simulation.get("days") != 90 or
            simulation.get("scenarioCount") != 2240 or simulation.get("overflowAttempts") != 0 or
            simulation.get("duplicateOutput") != 0 or simulation.get("durabilityViolations") != 0 or
            simulation.get("invariantFailures") != 0 or
            not CHECKSUM.fullmatch(str(simulation.get("artifactSha256", "")))):
        issues.append("Phase 7 simulation result tidak valid")
    pending = _claim_value(state.get("pendingWork", []))
    if not isinstance(pending, list) or not any("phase 7" in str(item).lower() for item in pending):
        issues.append("Phase 7 connected staging tidak tercatat sebagai pending work")
    if not (root / "docs" / "PHASE7_MINING_PRD.md").is_file():
        issues.append("Phase 7 PRD tidak ditemukan")
    if not (root / "scripts" / "migrate_economy_phase7.py").is_file():
        issues.append("Phase 7 migration CLI tidak ditemukan")
    return issues


def _phase8_issues(root: Path, state: dict, phase8_status: str | None) -> list[str]:
    issues: list[str] = []
    phase8 = _claim_value(state.get("phase8GiveawayOptions", {}))
    if phase8_status != "implemented_staging_ready" or phase8.get("status") != phase8_status:
        issues.append("Phase 8 status harus implemented_staging_ready")
    if phase8.get("implementationStatus") != "implemented":
        issues.append("Phase 8 implementation status tidak valid")
    if (phase8.get("productionStatus") != "not_approved" or
            phase8.get("productionMigrated") is not False or
            phase8.get("productionSeeded") is not False or
            phase8.get("productionEnabled") is not False):
        issues.append("Phase 8 production guard tidak valid")
    if phase8.get("featureFlag") != {"name": "ECONOMY_PHASE8_ENABLED", "default": False}:
        issues.append("Phase 8 feature flag state tidak valid")
    migration = phase8.get("migration", {})
    if (migration.get("version") != 800 or migration.get("name") != "phase8-giveaway-options" or
            migration.get("startupAutomatic") is not False or
            not CHECKSUM.fullmatch(str(migration.get("checksum", "")))):
        issues.append("Phase 8 migration identity tidak valid")
    simulation = phase8.get("simulation", {})
    if (simulation.get("passed") is not True or simulation.get("optionsPositions") != 2_000_000 or
            simulation.get("giveawayDraws") != 10_000 or
            not CHECKSUM.fullmatch(str(simulation.get("artifactSha256", "")))):
        issues.append("Phase 8 simulation result tidak valid")
    pending = _claim_value(state.get("pendingWork", []))
    if not isinstance(pending, list) or not any("phase 8" in str(item).lower() for item in pending):
        issues.append("Phase 8 connected staging tidak tercatat sebagai pending work")
    for path in ("docs/PHASE8_GIVEAWAY_OPTIONS_PRD.md", "scripts/migrate_economy_phase8.py"):
        if not (root / path).is_file():
            issues.append(f"Artefak Phase 8 tidak ditemukan: {path}")
    return issues


def _phase9a_issues(root: Path, state: dict, phase9a_status: str | None) -> list[str]:
    issues: list[str] = []
    phase9a = _claim_value(state.get("phase9aBackendSafety", {}))
    if phase9a_status != "implemented_local_verification" or phase9a.get("status") != phase9a_status:
        issues.append("Phase 9A status harus implemented_local_verification")
    if phase9a.get("implementationStatus") != "implemented":
        issues.append("Phase 9A implementation status tidak valid")
    if (phase9a.get("productionStatus") != "not_approved" or
            phase9a.get("productionMigrated") is not False or
            phase9a.get("productionEnabled") is not False):
        issues.append("Phase 9A production guard tidak valid")
    if phase9a.get("featureFlagAdded") is not False:
        issues.append("Phase 9A tidak boleh memiliki Economy feature flag")
    migration = phase9a.get("migration", {})
    if (migration.get("version") != 900 or migration.get("name") != "phase9a-backend-safety" or
            migration.get("startupAutomatic") is not False or
            not CHECKSUM.fullmatch(str(migration.get("checksum", "")))):
        issues.append("Phase 9A migration identity tidak valid")
    public = phase9a.get("publicSurface", {})
    if public != {"healthPath": "/healthz", "healthBody": {"status": "ok"}, "otherPublicDataRoutes": 0}:
        issues.append("Phase 9A public surface tidak valid")
    if phase9a.get("connectedDiscordOauthStaging") != "pending":
        issues.append("Phase 9A connected OAuth staging harus pending")
    permissions = phase9a.get("permissionClasses", [])
    expected_permissions = {
        "DASHBOARD_VIEW", "DASHBOARD_CONFIGURATION", "ECONOMY_PAUSE_CONTROL",
        "REVIEWED_RECOVERY_CONTROL", "NOTIFICATION_ROUTING_CONTROL",
        "OPERATOR_AUDIT_READ", "DASHBOARD_SECURITY_ADMIN",
    }
    if set(permissions) != expected_permissions or len(permissions) != len(expected_permissions):
        issues.append("Phase 9A permission classes tidak valid")
    pending = _claim_value(state.get("pendingWork", []))
    if not isinstance(pending, list) or not any("phase 9a" in str(item).lower() for item in pending):
        issues.append("Phase 9A connected staging tidak tercatat sebagai pending work")
    for path in (
        "docs/PHASE9A_BACKEND_SAFETY_PRD.md",
        "scripts/migrate_phase9a_backend_safety.py",
        "dashboard-example/middleware.ts",
    ):
        if not (root / path).is_file():
            issues.append(f"Artefak Phase 9A tidak ditemukan: {path}")
    runtime_source = (root / "runtime_config.py").read_text(encoding="utf-8")
    if "ECONOMY_PHASE9" in runtime_source:
        issues.append("Phase 9A Economy feature flag tidak boleh ada")
    return issues


def _phase9b_issues(root: Path, state: dict, phase9b_status: str | None) -> list[str]:
    issues: list[str] = []
    phase9b = _claim_value(state.get("phase9bDashboardNotificationRouting", {}))
    if phase9b_status != "implemented_local_verification" or phase9b.get("status") != phase9b_status:
        issues.append("Phase 9B status harus implemented_local_verification")
    if phase9b.get("implementationStatus") != "implemented":
        issues.append("Phase 9B implementation status tidak valid")
    if (phase9b.get("productionStatus") != "not_approved" or
            phase9b.get("productionMigrated") is not False or
            phase9b.get("productionEnabled") is not False):
        issues.append("Phase 9B production guard tidak valid")
    if phase9b.get("featureFlagAdded") is not False:
        issues.append("Phase 9B tidak boleh memiliki feature flag")
    migration = phase9b.get("migration", {})
    if (migration.get("version") != 910 or migration.get("name") != "phase9b-dashboard-notification-routing" or
            migration.get("startupAutomatic") is not False or
            not CHECKSUM.fullmatch(str(migration.get("checksum", "")))):
        issues.append("Phase 9B migration identity tidak valid")
    delivery = phase9b.get("delivery", {})
    required_delivery = {
        "oneIdentityPerSource": True, "routeSnapshotImmutable": True, "markerAdoption": True,
        "uncertainSendState": "REVIEW_REQUIRED", "automaticReviewRetry": False,
        "testHistorySeparate": True, "centralWorkerOnly": True,
    }
    if delivery != required_delivery:
        issues.append("Phase 9B durable delivery contract tidak valid")
    if phase9b.get("connectedDiscordOauthStaging") != "pending":
        issues.append("Phase 9B connected staging harus pending")
    pending = _claim_value(state.get("pendingWork", []))
    if not isinstance(pending, list) or not any("phase 9b" in str(item).lower() for item in pending):
        issues.append("Phase 9B connected staging tidak tercatat sebagai pending work")
    for path in (
        "docs/PHASE9B_DASHBOARD_NOTIFICATION_ROUTING_PRD.md",
        "scripts/migrate_phase9b_dashboard.py",
        "dashboard-example/app/economy/page.tsx",
        "economy/notification_delivery.py",
    ):
        if not (root / path).is_file():
            issues.append(f"Artefak Phase 9B tidak ditemukan: {path}")
    runtime_source = (root / "runtime_config.py").read_text(encoding="utf-8")
    if "ECONOMY_PHASE9B_ENABLED" in runtime_source:
        issues.append("Phase 9B feature flag tidak boleh ada")
    return issues


def _phase9c_issues(root: Path, state: dict, phase9c_status: str | None) -> list[str]:
    issues: list[str] = []
    expected_credentials = [
        "DISCORD_TOKEN", "DASHBOARD_DISCORD_CLIENT_ID", "DASHBOARD_DISCORD_CLIENT_SECRET",
        "DASHBOARD_SESSION_HASH_KEY", "DASHBOARD_INTERNAL_SIGNING_KEY", "DASHBOARD_IP_HASH_KEY",
    ]
    phase9c = _claim_value(state.get("phase9cFinalQa", {}))
    if phase9c_status != "ready_for_connected_staging" or phase9c.get("status") != phase9c_status:
        issues.append("Phase 9C status harus ready_for_connected_staging")
    if phase9c.get("implementationStatus") != "implemented_local_qa":
        issues.append("Phase 9C implementation status tidak valid")
    baseline = phase9c.get("baseline", {})
    if (baseline.get("branch") != "codex/economy-v1-phase9b" or
            baseline.get("commit") != "1fbe1c52bff268e68794fd3006b7705a51f995b4" or
            baseline.get("immutable") is not True):
        issues.append("Phase 9C baseline Phase 9B tidak valid")
    if phase9c.get("migrationAdded") is not False or phase9c.get("featureFlagAdded") is not False:
        issues.append("Phase 9C tidak boleh menambah migrasi atau feature flag")
    simulation = phase9c.get("simulation", {})
    if (simulation.get("users") != 1000 or simulation.get("days") != 90 or
            simulation.get("runsRequired") != 2 or simulation.get("byteIdenticalRequired") is not True):
        issues.append("Phase 9C simulation contract tidak valid")
    for key in ("artifactHash", "fileSha256"):
        value = str(simulation.get(key, ""))
        if value != "PENDING" and not CHECKSUM.fullmatch(value):
            issues.append("Phase 9C simulation hash tidak valid")
    chain = phase9c.get("migrationChain", {})
    if chain.get("versions") != [100, 200, 300, 301, 400, 500, 600, 700, 800, 900, 910] or chain.get("newMigration") is not False:
        issues.append("Phase 9C migration chain tidak valid")
    staging = phase9c.get("connectedStaging", {})
    if (staging.get("status") != "pending" or staging.get("manifestAvailable") is not False or
            staging.get("networkAttempted") is not False or staging.get("remainingExternalBlocker") is not True):
        issues.append("Phase 9C connected staging guard tidak valid")
    if (staging.get("credentialEnvironment") != expected_credentials or
            staging.get("legacyOauthAliasesAccepted") is not False or
            staging.get("manifestStoresCredentials") is not False):
        issues.append("Phase 9C staging credential contract tidak valid")
    try:
        launcher = _assignment_map(_parse_source(root / "scripts" / "run_phase9c_staging.py"))
        observed_credentials = list(_literal(launcher["REQUIRED_CREDENTIAL_ENV"]))
        if observed_credentials != expected_credentials:
            issues.append("Phase 9C staging launcher credential contract tidak valid")
    except (OSError, KeyError, SyntaxError, ValueError):
        issues.append("Phase 9C staging launcher credential contract tidak dapat diverifikasi")
    production = phase9c.get("production", {})
    if production != {"status": "not_approved", "migrated": False, "seeded": False, "enabled": False, "accessed": False}:
        issues.append("Phase 9C production guard tidak valid")
    pending = _claim_value(state.get("pendingWork", []))
    if not isinstance(pending, list) or not any("phase 9c connected staging" in str(item).lower() for item in pending):
        issues.append("Phase 9C connected staging tidak tercatat sebagai pending work")
    for path in (
        "docs/PHASE9C_FINAL_QA_PRODUCTION_READINESS_PRD.md",
        "docs/PHASE9C_STAGING_EVIDENCE_SCHEMA.json",
        "scripts/simulate_phase9c_full_system.py",
        "scripts/reconcile_phase9c_full_system.py",
        "scripts/run_phase9c_local_qa.py",
        "scripts/run_phase9c_staging.py",
        "scripts/verify_phase9c_staging_evidence.py",
    ):
        if not (root / path).is_file():
            issues.append(f"Artefak Phase 9C tidak ditemukan: {path}")
    runtime_source = (root / "runtime_config.py").read_text(encoding="utf-8")
    if "ECONOMY_PHASE9C_ENABLED" in runtime_source:
        issues.append("Phase 9C feature flag tidak boleh ada")
    if any((root / "economy").glob("phase9c_schema.py")):
        issues.append("Phase 9C migration tidak boleh ada")
    return issues


def verify(root: Path = PROJECT_ROOT) -> list[str]:
    root = root.resolve()
    state_path = root / "docs" / "project_state.json"
    handoff_path = root / "docs" / "AI_CODER_HANDOFF.md"
    issues: list[str] = []
    if not state_path.exists():
        return ["docs/project_state.json tidak ditemukan"]
    try:
        raw_state = state_path.read_text(encoding="utf-8")
        state = json.loads(raw_state)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"project_state.json tidak valid: {exc}"]
    missing = REQUIRED_TOP_LEVEL.difference(state)
    if missing:
        issues.append(f"top-level field hilang: {sorted(missing)}")
    if state.get("schemaVersion") != 1:
        issues.append("schemaVersion tidak didukung")
    project = _claim_value(state.get("project", {}))
    snapshot = _claim_value(state.get("repositorySnapshot", {}))
    latest_task = _claim_value(state.get("latestCompletedTask", {}))
    workflow = _claim_value(state.get("livingPrdWorkflow", {}))
    for label, value, fields in (
        ("project", project, ("name", "repositoryPath")),
        ("repositorySnapshot", snapshot, ("lastKnownBranch", "observedBranch", "observedHead")),
        ("latestCompletedTask", latest_task, ("title", "status", "commit")),
        ("livingPrdWorkflow", workflow, ("status", "steps")),
    ):
        if not isinstance(value, dict) or any(field not in value for field in fields):
            issues.append(f"nested field wajib hilang: {label}")
    issues.extend(_issues_for_claims(state))
    phases = _claim_value(state.get("phaseStatuses", []))
    phase_ids = [row.get("id") for row in phases if isinstance(row, dict)]
    if len(phase_ids) != len(set(phase_ids)):
        issues.append("phase identifiers duplikat")
    migrations = _claim_value(state.get("migrations", []))
    versions = [row.get("version") for row in migrations if isinstance(row, dict)]
    if len(versions) != len(set(versions)):
        issues.append("migration versions duplikat")
    for row in migrations:
        if not isinstance(row, dict):
            continue
        checksum = row.get("checksum")
        if checksum is not None and not CHECKSUM.fullmatch(str(checksum)):
            issues.append(f"checksum migrasi invalid: {row.get('version')}")
    for row in _claim_value(state.get("catalogs", [])):
        if not CATALOG_VERSION.fullmatch(str(row.get("version", ""))):
            issues.append("catalog version invalid")
        if not CHECKSUM.fullmatch(str(row.get("checksum", ""))):
            issues.append("catalog checksum invalid")
    for row in (_claim_value(state.get("importantCommits", [])) + _claim_value(state.get("taskHistory", []))
                + _claim_value(state.get("updateHistory", [])) + [latest_task]):
        if isinstance(row, dict) and not HEX_HASH.fullmatch(str(row.get("commit", ""))):
            issues.append("commit reference invalid")
    documented_flags = _claim_value(state.get("featureFlags", {}))
    try:
        observed_flags = _extract_flag_defaults(root / "runtime_config.py")
        if any(observed_flags[name] is not False for name in FLAG_NAMES):
            issues.append("runtime feature flag default tidak false")
        if documented_flags != observed_flags:
            issues.append("feature flag documentation tidak cocok runtime_config.py")
        phase_checksums = _extract_phase_checksums(root)
        verified_migrations = {row.get("version"): row.get("checksum") for row in migrations if row.get("verificationStatus") == "verified"}
        for version, checksum in phase_checksums.items():
            if verified_migrations.get(version) != checksum:
                issues.append(f"checksum migrasi {version} tidak cocok source")
        catalog_version, catalog_checksum = _extract_catalog_checksum(root)
        catalogs = {row.get("version"): row.get("checksum") for row in _claim_value(state.get("catalogs", []))}
        if catalogs.get(catalog_version) != catalog_checksum:
            issues.append("catalog checksum tidak cocok source")
        if verified_migrations.get(300) != catalog_checksum:
            issues.append("checksum migrasi 300 tidak cocok catalog source")
        issues.extend(_static_command_issues(root, state))
    except (OSError, KeyError, SyntaxError, ValueError) as exc:
        issues.append(f"static inspection gagal: {exc}")
    mismatches = _claim_value(state.get("documentedMismatches", []))
    if not any(item.get("command") == "/rank" and item.get("repositoryObservedOwner") == "Trusted Vouch"
                   and item.get("verificationStatus") == "documented_mismatch" for item in mismatches if isinstance(item, dict)):
        issues.append("documented mismatch /rank tidak valid")
    production = _claim_value(state.get("productionStatus", {}))
    approved = bool(production.get("approvedProductionRecord"))
    if not approved and (production.get("migrated") or production.get("enabled") or production.get("cutoverApproved")):
        issues.append("production ditandai aktif tanpa approval eksplisit")
    phase5 = next((row for row in phases if isinstance(row, dict) and row.get("id") == "phase5"), {})
    issues.extend(_phase5_planning_issues(root, state, phase5.get("status")))
    phase6 = next((row for row in phases if isinstance(row, dict) and row.get("id") == "phase6"), {})
    issues.extend(_phase6_issues(root, state, phase6.get("status")))
    phase7 = next((row for row in phases if isinstance(row, dict) and row.get("id") == "phase7"), {})
    issues.extend(_phase7_issues(root, state, phase7.get("status")))
    phase8 = next((row for row in phases if isinstance(row, dict) and row.get("id") == "phase8"), {})
    issues.extend(_phase8_issues(root, state, phase8.get("status")))
    phase9a = next((row for row in phases if isinstance(row, dict) and row.get("id") == "phase9a"), {})
    issues.extend(_phase9a_issues(root, state, phase9a.get("status")))
    phase9b = next((row for row in phases if isinstance(row, dict) and row.get("id") == "phase9b"), {})
    issues.extend(_phase9b_issues(root, state, phase9b.get("status")))
    phase9c = next((row for row in phases if isinstance(row, dict) and row.get("id") == "phase9c"), {})
    issues.extend(_phase9c_issues(root, state, phase9c.get("status")))
    issues.extend(_secret_issues(raw_state, "project_state.json"))
    issues.extend(_private_content_issues(raw_state, "project_state.json"))
    if not handoff_path.exists():
        issues.append("docs/AI_CODER_HANDOFF.md tidak ditemukan")
    else:
        actual = handoff_path.read_bytes()
        expected = render_handoff(state)
        if actual != expected:
            issues.append("AI_CODER_HANDOFF.md stale atau diedit manual")
        if b"\r\n" in actual or not actual.endswith(b"\n") or actual.endswith(b"\n\n"):
            issues.append("format line ending/final newline handoff tidak deterministik")
        try:
            handoff_text = actual.decode("utf-8")
        except UnicodeDecodeError:
            issues.append("AI_CODER_HANDOFF.md bukan UTF-8")
        else:
            issues.extend(_secret_issues(handoff_text, "AI_CODER_HANDOFF.md"))
            issues.extend(_private_content_issues(handoff_text, "AI_CODER_HANDOFF.md"))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Living PRD state without mutating the repository.")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)
    issues = verify(args.root)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
        return 1
    print("Living PRD handoff valid and synchronized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
