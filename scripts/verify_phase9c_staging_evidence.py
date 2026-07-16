"""Validate sanitized Phase 9C connected-staging evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


BASELINE_COMMIT = "1fbe1c52bff268e68794fd3006b7705a51f995b4"
STEP_IDS = tuple(f"S{index:02d}" for index in range(1, 23))
ALLOWED_STATUSES = {"PENDING", "PASSED", "FAILED", "SKIPPED"}
SECRET_KEYS = re.compile(r"(?i)(token|secret|password|cookie|authorization|private.?key|client.?secret)")


def _walk(value, path="evidence"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield f"{path}.{key}", key, child
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def validate_evidence(evidence: dict, *, require_complete: bool = True) -> list[str]:
    issues: list[str] = []
    if evidence.get("schemaVersion") != 1:
        issues.append("unsupported schemaVersion")
    if evidence.get("baselineCommit") != BASELINE_COMMIT:
        issues.append("baseline commit mismatch")
    if evidence.get("environment") != "staging" or evidence.get("approved") is not True:
        issues.append("staging approval missing")
    resources = evidence.get("resources", {})
    if resources.get("productionEquivalent") is not False:
        issues.append("production-equivalent resources are forbidden")
    if not re.fullmatch(r"[0-9a-f]{64}", str(resources.get("manifestHash", ""))):
        issues.append("resource manifest hash missing")
    steps = evidence.get("steps", [])
    identifiers = [item.get("id") for item in steps if isinstance(item, dict)]
    if identifiers != list(STEP_IDS):
        issues.append("staging steps must be S01-S22 in order")
    for item in steps:
        if not isinstance(item, dict):
            issues.append("invalid step record")
            continue
        if item.get("status") not in ALLOWED_STATUSES:
            issues.append(f"invalid step status:{item.get('id')}")
        if require_complete and item.get("status") != "PASSED":
            issues.append(f"incomplete step:{item.get('id')}")
        evidence_hash = item.get("evidenceHash")
        if item.get("status") == "PASSED" and not re.fullmatch(r"[0-9a-f]{64}", str(evidence_hash or "")):
            issues.append(f"missing evidence hash:{item.get('id')}")
    for path, key, child in _walk(evidence):
        if SECRET_KEYS.search(str(key)):
            issues.append(f"secret-like field forbidden:{path}")
        if isinstance(child, str) and re.search(r"(?i)(discord(?:\.|_|-)?gg/|bot\s+[A-Za-z0-9._-]{20,}|oauth2?\s+[A-Za-z0-9._-]{20,})", child):
            issues.append(f"secret-like value forbidden:{path}")
    return sorted(set(issues))


def sanitized_manifest_hash(manifest: dict) -> str:
    payload = json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verifikasi evidence staging Phase 9C")
    parser.add_argument("evidence")
    parser.add_argument("--allow-pending", action="store_true")
    args = parser.parse_args(argv)
    value = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    issues = validate_evidence(value, require_complete=not args.allow_pending)
    print(json.dumps({"valid": not issues, "issues": issues}, indent=2, sort_keys=True))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
