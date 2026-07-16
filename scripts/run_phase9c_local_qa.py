"""Run the final Phase 9C local QA matrix and emit sanitized evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.catalog import catalog_hash
from economy.constants import (
    ECONOMY_MIGRATION_VERSION,
    ECONOMY_PHASE2_MIGRATION_VERSION,
    ECONOMY_PHASE3_MIGRATION_VERSION,
    ECONOMY_PHASE4_MIGRATION_VERSION,
    ECONOMY_PHASE5_MIGRATION_VERSION,
    ECONOMY_PHASE6_MIGRATION_VERSION,
    ECONOMY_PHASE7_MIGRATION_VERSION,
    ECONOMY_PHASE8_MIGRATION_VERSION,
    PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION,
    PHASE9B_DASHBOARD_MIGRATION_VERSION,
)
from economy.phase3_schema import PHASE3_HARDENING_CHECKSUM, PHASE3_HARDENING_VERSION
from economy.phase4_schema import PHASE4_MIGRATION_CHECKSUM
from economy.phase5_schema import PHASE5_MIGRATION_NAME, PHASE5_SCHEMA_CHECKSUM
from economy.phase6_schema import PHASE6_MIGRATION_NAME, PHASE6_SCHEMA_CHECKSUM
from economy.phase7_schema import PHASE7_MIGRATION_NAME, PHASE7_SCHEMA_CHECKSUM
from economy.phase8_schema import PHASE8_MIGRATION_NAME, PHASE8_SCHEMA_CHECKSUM
from economy.phase9a_schema import PHASE9A_MIGRATION_NAME, PHASE9A_SCHEMA_CHECKSUM
from economy.phase9b_schema import PHASE9B_MIGRATION_NAME, PHASE9B_SCHEMA_CHECKSUM


BASELINE_COMMIT = "1fbe1c52bff268e68794fd3006b7705a51f995b4"


def migration_chain() -> list[dict]:
    return [
        {"version": ECONOMY_MIGRATION_VERSION, "name": "economy-foundation",
         "checksumContract": "source-manifest", "checksum": None},
        {"version": ECONOMY_PHASE2_MIGRATION_VERSION, "name": "economy_core_phase2",
         "checksumContract": "source-manifest", "checksum": None},
        {"version": ECONOMY_PHASE3_MIGRATION_VERSION, "name": "phase3-rpg",
         "checksumContract": "catalog", "checksum": catalog_hash()},
        {"version": PHASE3_HARDENING_VERSION, "name": "phase3-hardening",
         "checksumContract": "canonical-schema", "checksum": PHASE3_HARDENING_CHECKSUM},
        {"version": ECONOMY_PHASE4_MIGRATION_VERSION, "name": "phase4-marketplace",
         "checksumContract": "canonical-schema", "checksum": PHASE4_MIGRATION_CHECKSUM},
        {"version": ECONOMY_PHASE5_MIGRATION_VERSION, "name": PHASE5_MIGRATION_NAME,
         "checksumContract": "canonical-schema", "checksum": PHASE5_SCHEMA_CHECKSUM},
        {"version": ECONOMY_PHASE6_MIGRATION_VERSION, "name": PHASE6_MIGRATION_NAME,
         "checksumContract": "canonical-schema", "checksum": PHASE6_SCHEMA_CHECKSUM},
        {"version": ECONOMY_PHASE7_MIGRATION_VERSION, "name": PHASE7_MIGRATION_NAME,
         "checksumContract": "canonical-schema", "checksum": PHASE7_SCHEMA_CHECKSUM},
        {"version": ECONOMY_PHASE8_MIGRATION_VERSION, "name": PHASE8_MIGRATION_NAME,
         "checksumContract": "canonical-schema", "checksum": PHASE8_SCHEMA_CHECKSUM},
        {"version": PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION, "name": PHASE9A_MIGRATION_NAME,
         "checksumContract": "canonical-schema", "checksum": PHASE9A_SCHEMA_CHECKSUM},
        {"version": PHASE9B_DASHBOARD_MIGRATION_VERSION, "name": PHASE9B_MIGRATION_NAME,
         "checksumContract": "canonical-schema", "checksum": PHASE9B_SCHEMA_CHECKSUM},
    ]


def verify_migration_chain() -> dict:
    chain = migration_chain()
    versions = [item["version"] for item in chain]
    expected = [100, 200, 300, 301, 400, 500, 600, 700, 800, 900, 910]
    issues = []
    if versions != expected:
        issues.append("migration_order_mismatch")
    for item in chain:
        checksum = item["checksum"]
        if checksum is not None and not re.fullmatch(r"[0-9a-f]{64}", checksum):
            issues.append(f"invalid_checksum:{item['version']}")
    return {"passed": not issues, "issues": issues, "migrations": chain}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _run(name: str, command: list[str], *, cwd: Path = ROOT, env: dict | None = None) -> dict:
    completed = subprocess.run(
        command, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, encoding="utf-8", errors="replace", check=False,
    )
    output = completed.stdout or ""
    counts = [int(value) for value in re.findall(r"Ran\s+(\d+)\s+tests?", output)]
    result = {
        "name": name,
        "command": command,
        "exitCode": completed.returncode,
        "passed": completed.returncode == 0,
        "testCount": sum(counts),
        "outputSha256": _sha(output),
    }
    if not result["passed"]:
        result["failureTail"] = output.splitlines()[-20:]
    print(f"[{name}] {'PASS' if result['passed'] else 'FAIL'} tests={result['testCount']}")
    return result


def _python_files() -> list[str]:
    return [str(path) for folder in ("economy", "cogs", "scripts")
            for path in sorted((ROOT / folder).glob("*.py"))]


def run_local_qa() -> dict:
    npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
    commands: list[tuple[str, list[str], Path, dict | None]] = [
        ("economy_phase1_to8", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_economy_*.py"], ROOT, None),
        ("marketplace", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_marketplace*.py"], ROOT, None),
        ("phase9a", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_phase9a*.py"], ROOT, None),
        ("phase9b", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_phase9b*.py"], ROOT, None),
        ("phase9c", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_phase9c*.py"], ROOT, None),
        ("living_prd", [sys.executable, "-m", "unittest", "tests.test_ai_handoff_tools", "-v"], ROOT, None),
        ("living_prd_verify", [sys.executable, "scripts/verify_ai_handoff.py"], ROOT, None),
        ("python_compile", [sys.executable, "-m", "py_compile", *_python_files()], ROOT, None),
        ("dashboard_typecheck", [npm, "run", "typecheck"], ROOT / "dashboard-example", None),
        ("dashboard_vitest", [npm, "test"], ROOT / "dashboard-example", None),
        ("dashboard_build", [npm, "run", "build"], ROOT / "dashboard-example", None),
        ("dashboard_dependency_audit", [npm, "audit", "--omit=dev"], ROOT / "dashboard-example", None),
        ("git_diff_check", ["git", "diff", "--check"], ROOT, None),
    ]
    with tempfile.TemporaryDirectory() as temporary:
        env = os.environ.copy()
        env["DATABASE_PATH"] = str(Path(temporary) / "main-import.db")
        env["PRODUCTION_DATABASE_PATH"] = str(ROOT / "w2ebot.db")
        for flag in (
            "ECONOMY_V1_ENABLED", "ECONOMY_PHASE2_ENABLED", "ECONOMY_PHASE3_ENABLED",
            "ECONOMY_PHASE4_ENABLED", "ECONOMY_PHASE5_ENABLED", "ECONOMY_PHASE6_ENABLED",
            "ECONOMY_PHASE7_ENABLED", "ECONOMY_PHASE8_ENABLED",
        ):
            env[flag] = "false"
        commands.insert(8, ("temporary_main_import", [sys.executable, "-c", "import main; print('main import ok')"], ROOT, env))
        results = [_run(name, command, cwd=cwd, env=command_env) for name, command, cwd, command_env in commands]
    migration = verify_migration_chain()
    total_tests = sum(item["testCount"] for item in results)
    return {
        "schemaVersion": 1,
        "baselineCommit": BASELINE_COMMIT,
        "migrationChain": migration,
        "results": results,
        "exactTestTotal": total_tests,
        "commandOwnership": "passed" if next(item for item in results if item["name"] == "living_prd_verify")["passed"] else "failed",
        "forbiddenAliases": "absent" if next(item for item in results if item["name"] == "living_prd_verify")["passed"] else "unverified",
        "passed": migration["passed"] and all(item["passed"] for item in results),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Final local QA Phase 9C")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = run_local_qa()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"passed": report["passed"], "exactTestTotal": report["exactTestTotal"]}, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
