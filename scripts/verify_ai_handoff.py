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
    "marketplaceLifecycleDefinitions",
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
    "ECONOMY_PHASE3_ENABLED", "ECONOMY_PHASE4_ENABLED",
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
    return {
        301: hashlib.sha256((phase3_sql + "\n" + "\n".join(phase3_triggers)).encode("utf-8")).hexdigest(),
        400: hashlib.sha256((phase4_algorithm + "\n" + phase4_sql + "\n" + "\n".join(phase4_triggers)).encode("utf-8")).hexdigest(),
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
        r"(?i)(?:payment(?:_account|destination)?|payout(?:_account)?|proof_url|qris)\s*[:=]",
        r"(?i)\b(?:INSERT INTO|UPDATE\s+\w+\s+SET|DELETE FROM)\b",
    )
    return [f"{label}: private environment/data pattern terdeteksi" for pattern in patterns if re.search(pattern, text)]


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
    if phase5.get("status") not in {"not_started", "not_implemented", "not_approved"}:
        issues.append("Phase 5 tidak berada pada guard status")
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
