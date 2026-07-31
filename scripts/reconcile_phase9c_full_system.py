"""Independent reconciliation for Phase 9C full-system artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _integer_strings(value, path="dashboard") -> list[str]:
    issues: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            issues.extend(_integer_strings(child, f"{path}.{key}"))
    elif not isinstance(value, str) or not value.lstrip("-").isdigit():
        issues.append(f"{path} is not an exact decimal string")
    return issues


def reconcile_report(report: dict) -> dict:
    issues: list[str] = []
    ledger = report.get("ledger", {})
    supply = report.get("supply", {})
    liabilities = report.get("liabilities", {})
    dashboard = report.get("dashboard", {})
    recovery = report.get("recovery", {})
    if any(int(value) != 0 for value in ledger.get("netByCurrency", {}).values()):
        issues.append("ledger imbalance")
    if int(ledger.get("duplicateCommittedOperations", -1)) != 0:
        issues.append("duplicate committed operation")
    for currency in ("ETM", "ECY"):
        current = supply.get(currency, {})
        if int(current.get("allAccountsNet", -1)) != 0:
            issues.append(f"{currency} accounts do not reconcile to issuance")
        expected = int(current.get("issuance", 0)) - int(current.get("burn", 0))
        if int(current.get("circulating", -1)) != expected:
            issues.append(f"{currency} circulating supply mismatch")
        if dashboard.get("supply", {}).get(currency) != str(expected):
            issues.append(f"{currency} dashboard supply mismatch")
    dashboard_liabilities = dashboard.get("liabilities", {})
    for key, value in liabilities.items():
        if dashboard_liabilities.get(key) != str(value):
            issues.append(f"dashboard liability mismatch: {key}")
    issues.extend(_integer_strings(dashboard))
    duplicate_keys = (
        "duplicateMoney", "duplicateAssets", "duplicateWinners", "duplicateMessages",
        "duplicateReceipts", "duplicateAuditRows",
    )
    for key in duplicate_keys:
        if int(recovery.get(key, -1)) != 0:
            issues.append(f"{key} is nonzero")
    artifacts = report.get("acceptedDomainArtifacts", {})
    if set(artifacts) != {"casino", "crypto", "mining", "phase8"}:
        issues.append("accepted domain artifact set mismatch")
    return {
        "passed": not issues,
        "issues": issues,
        "ledgerBalanced": not any("ledger imbalance" in issue for issue in issues),
        "supplyExact": not any("supply mismatch" in issue or "issuance" in issue for issue in issues),
        "liabilitiesExact": not any("liability mismatch" in issue for issue in issues),
        "dashboardExact": not any("dashboard" in issue for issue in issues),
        "duplicateOutcomeCount": sum(int(recovery.get(key, 0)) for key in duplicate_keys),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rekonsiliasi artifact full-system Phase 9C")
    parser.add_argument("artifact")
    args = parser.parse_args(argv)
    report = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    result = reconcile_report(report)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
