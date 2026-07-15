"""Generate the deterministic Living PRD handoff from project state."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_PATH = PROJECT_ROOT / "docs" / "project_state.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "docs" / "AI_CODER_HANDOFF.md"


def _claim_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value and "verificationStatus" in value:
        return value["value"]
    return value


def _markdown_scalar(value: Any) -> str:
    if value is None:
        return "-"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value).replace("\n", "<br>")


def _render_value(value: Any, indent: int = 0) -> list[str]:
    value = _claim_value(value)
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key in sorted(value):
            item = _claim_value(value[key])
            label = key.replace("_", " ")
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}- **{label}:**")
                lines.extend(_render_value(item, indent + 2))
            else:
                lines.append(f"{prefix}- **{label}:** {_markdown_scalar(item)}")
        return lines or [f"{prefix}- -"]
    if isinstance(value, list):
        if not value:
            return [f"{prefix}- -"]
        rows = [_claim_value(item) for item in value]
        if all(isinstance(item, dict) for item in rows):
            keys = sorted({key for item in rows for key in item})
            if keys and all(not isinstance(_claim_value(item.get(key)), (dict, list)) for item in rows for key in keys):
                lines = [f"{prefix}| " + " | ".join(key.replace("_", " ") for key in keys) + " |",
                         f"{prefix}| " + " | ".join("---" for _ in keys) + " |"]
                for item in rows:
                    lines.append(f"{prefix}| " + " | ".join(_markdown_scalar(_claim_value(item.get(key))) for key in keys) + " |")
                return lines
        lines = []
        for item in rows:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(_render_value(item, indent + 2))
            else:
                lines.append(f"{prefix}- {_markdown_scalar(item)}")
        return lines
    return [f"{prefix}{_markdown_scalar(value)}"]


def _section(lines: list[str], title: str, value: Any) -> None:
    lines.extend((f"## {title}", ""))
    lines.extend(_render_value(value))
    lines.append("")


def render_handoff(state: dict) -> bytes:
    """Return deterministic UTF-8 Markdown bytes without performing I/O."""
    project = _claim_value(state["project"])
    lines = [
        "THIS FILE IS GENERATED.",
        "DO NOT EDIT IT MANUALLY.",
        "Update docs/project_state.json and run:",
        "python scripts/update_ai_handoff.py",
        "",
        f"# {project['name']} — AI Coder Handoff",
        "",
    ]
    ordered_sections = (
        ("Purpose", "purpose"),
        ("Source-Of-Truth Precedence", "sourceOfTruth"),
        ("Repository Snapshot", "repositorySnapshot"),
        ("Project Progress", "phaseStatuses"),
        ("Capabilities By Phase", "capabilitiesByPhase"),
        ("Protected Systems", "protectedSystems"),
        ("Feature Flags", "featureFlags"),
        ("Command Ownership", "commandOwnership"),
        ("Forbidden Aliases", "forbiddenAliases"),
        ("Legacy Commands", "legacyCommands"),
        ("Important Commits", "importantCommits"),
        ("Migrations And Checksums", "migrations"),
        ("Catalog Versions And Checksums", "catalogs"),
        ("Deal, Middleman, And Trusted Vouch", "dealMiddlemanTrustedVouch"),
        ("Interaction Safety And Persistent Recovery", "interactionRecovery"),
        ("Payment Configuration", "paymentConfiguration"),
        ("Economy Design", "economyDesign"),
        ("System Accounts And Constants", "economyConstants"),
        ("Phase 1", "phase1"),
        ("Phase 2", "phase2"),
        ("Phase 3 RPG", "phase3Rpg"),
        ("Complete RPG Balance Tables", "rpgBalance"),
        ("Phase 4 Marketplace", "phase4Marketplace"),
        ("Marketplace Recovery And Hardening", "marketplaceHardening"),
        ("Marketplace Lifecycle Definitions", "marketplaceLifecycleDefinitions"),
        ("Phase 5 Casino", "phase5Casino"),
        ("Phase 6 Crypto", "phase6Crypto"),
        ("Phase 7 Mining", "phase7Mining"),
        ("Phase 8 Giveaway And Eternal Options", "phase8GiveawayOptions"),
        ("Phase 9A Backend Safety Foundation", "phase9aBackendSafety"),
        ("Phase 9B Economy Dashboard And Notification Routing", "phase9bDashboardNotificationRouting"),
        ("Module Ownership", "moduleOwnership"),
        ("Verification History", "verificationHistory"),
        ("Staging", "stagingStatus"),
        ("Dashboard", "dashboardStatus"),
        ("Production", "productionStatus"),
        ("Known Limitations", "knownLimitations"),
        ("Blockers", "blockers"),
        ("Pending Work", "pendingWork"),
        ("AI Coder Onboarding", "aiCoderOnboarding"),
        ("Mandatory Update Workflow", "livingPrdWorkflow"),
        ("Task Completion Template", "taskCompletionTemplate"),
        ("Definition Of Done", "definitionOfDone"),
        ("Update History", "updateHistory"),
        ("Current Handoff Summary", "currentHandoffSummary"),
    )
    for title, key in ordered_sections:
        _section(lines, title, state[key])
    return ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8")


def load_state(path: Path = DEFAULT_STATE_PATH) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def generate(state_path: Path = DEFAULT_STATE_PATH, output_path: Path = DEFAULT_OUTPUT_PATH) -> None:
    output_path.write_bytes(render_handoff(load_state(state_path)))


def main() -> int:
    generate()
    print(f"Generated {DEFAULT_OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
