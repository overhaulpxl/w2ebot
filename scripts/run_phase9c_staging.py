"""Production-refusing Phase 9C connected-staging evidence orchestrator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_phase9c_staging_evidence import (  # noqa: E402
    BASELINE_COMMIT, STEP_IDS, sanitized_manifest_hash, validate_evidence,
)


STEP_NAMES = (
    "path_and_production_refusal", "backup", "migrations_100_910", "staging_seed",
    "signing_key_fingerprints", "bootstrap_security_admin", "oauth_and_origins",
    "enable_flags_sequentially", "command_sync", "stale_command_removal",
    "dashboard_production_build", "oauth_login", "permission_assignment_revocation",
    "session_csrf_signed_requests", "notification_routes", "test_notifications",
    "future_only_route_update", "failed_and_uncertain_delivery", "restart_active_operations",
    "persistent_recovery_and_adoption", "dashboard_reconciliation", "disable_all_flags",
)
REQUIRED_CREDENTIAL_ENV = (
    "DISCORD_TOKEN", "DASHBOARD_DISCORD_CLIENT_ID", "DASHBOARD_DISCORD_CLIENT_SECRET",
    "DASHBOARD_SESSION_HASH_KEY", "DASHBOARD_INTERNAL_SIGNING_KEY", "DASHBOARD_IP_HASH_KEY",
)


def _resolved(value: str) -> Path:
    return Path(value).expanduser().resolve()


def load_approved_manifest(path: str | Path) -> dict:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"approved", "environment", "databasePath", "productionDatabasePath", "resourceFingerprint"}
    if set(manifest) != required:
        raise ValueError("Manifest staging harus memakai schema allowlist yang tepat.")
    if manifest["approved"] is not True or manifest["environment"] != "staging":
        raise ValueError("Manifest belum disetujui khusus staging.")
    target = _resolved(manifest["databasePath"])
    production = _resolved(manifest["productionDatabasePath"])
    if target == production or target.name.lower() == "w2ebot.db":
        raise ValueError("Path production atau production-equivalent ditolak.")
    if not isinstance(manifest["resourceFingerprint"], str) or len(manifest["resourceFingerprint"]) != 64:
        raise ValueError("Fingerprint resource staging tidak valid.")
    return manifest


def credentials_available(environment: dict[str, str] | None = None) -> bool:
    current = os.environ if environment is None else environment
    return all(bool(current.get(name, "").strip()) for name in REQUIRED_CREDENTIAL_ENV)


def initialize_evidence(manifest: dict) -> dict:
    sanitized = {
        "environment": manifest["environment"],
        "resourceFingerprint": manifest["resourceFingerprint"],
        "databaseFingerprint": hashlib.sha256(str(_resolved(manifest["databasePath"])).encode()).hexdigest(),
    }
    return {
        "schemaVersion": 1,
        "baselineCommit": BASELINE_COMMIT,
        "environment": "staging",
        "approved": True,
        "resources": {"productionEquivalent": False, "manifestHash": sanitized_manifest_hash(sanitized)},
        "steps": [
            {"id": identifier, "name": name, "status": "PENDING", "evidenceHash": None}
            for identifier, name in zip(STEP_IDS, STEP_NAMES)
        ],
        "readiness": "CONNECTED_STAGING_PENDING",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Orkestrasi evidence connected staging Phase 9C")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    manifest = load_approved_manifest(args.manifest)
    if not credentials_available():
        raise SystemExit("Credential staging belum lengkap; connected staging tidak dijalankan.")
    evidence = initialize_evidence(manifest)
    issues = validate_evidence(evidence, require_complete=False)
    if issues:
        raise SystemExit("Evidence staging awal tidak valid: " + ", ".join(issues))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print("Evidence staging Phase 9C diinisialisasi; tidak ada koneksi Discord/OAuth yang dilakukan oleh CLI ini.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
