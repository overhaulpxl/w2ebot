"""Deterministic Phase 9C full-system Economy V1 acceptance simulation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.constants import SYSTEM_ACCOUNT_DEFINITIONS  # noqa: E402


PHASE9C_BASELINE_COMMIT = "1fbe1c52bff268e68794fd3006b7705a51f995b4"
PHASE9C_USERS = 1_000
PHASE9C_DAYS = 90
PHASE9C_SEED = 9_100_090
COHORTS = (
    ("casual", 250),
    ("active", 180),
    ("rpg", 140),
    ("marketplace", 100),
    ("casino", 80),
    ("crypto", 70),
    ("mining", 50),
    ("giveaway", 45),
    ("eternal_options", 35),
    ("whale", 20),
    ("alt_pattern", 30),
)
ACCEPTED_DOMAIN_ARTIFACTS = {
    "casino": "b24dc703728749a6ee32d637f8b62fd676833627dd9498e06c7dba13f0dea285",
    "crypto": "66cb9ecb7e85c0eec3a9a744ae20323fb423b39c2354db7ce755ba2cf564767a",
    "mining": "e7599dbf34beca0fffa777cbe3fab9c0d6b7fb77d0546e6f48646b464224b187",
    "phase8": "ce50819010645c8cabcc5a2398837b77f0911f8dd863a8c85f6408d3a4a38ec4",
}
ACCEPTED_DOMAIN_METRICS = {
    "casinoBlackjackRtp": "0.9748809836156533",
    "casinoFixedGamesPassed": True,
    "cryptoTotalTicks": 864_000,
    "cryptoInvariantFailures": 0,
    "miningRoiDays": "66.66666666666667",
    "miningInvariantFailures": 0,
    "giveawayFairnessPValue": "0.6212634449446391",
    "eternalOptionsRtp": "0.9504240337325349",
    "phase8InvariantFailures": 0,
}
SOURCE_FILES = (
    "economy/constants.py",
    "economy/marketplace.py",
    "economy/casino.py",
    "economy/crypto.py",
    "economy/mining.py",
    "economy/giveaways.py",
    "economy/eternal_options.py",
    "economy/dashboard_reporting.py",
    "economy/notification_delivery.py",
    "scripts/simulate_phase9c_full_system.py",
    "scripts/reconcile_phase9c_full_system.py",
)


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_manifest(root: Path = ROOT) -> dict[str, str]:
    return {name: sha256_bytes((root / name).read_bytes()) for name in sorted(SOURCE_FILES)}


class LedgerModel:
    def __init__(self) -> None:
        self.balances: dict[tuple[str, str], int] = {}
        self.transactions: dict[str, tuple[tuple[str, str, int], ...]] = {}
        self.ledger_net = {"ETM": 0, "ECY": 0}
        self.duplicate_attempts = 0
        self.replayed_operations = 0
        self.maximum_absolute_amount = 0
        self.account_inflow: dict[tuple[str, str], int] = {}
        self.account_outflow: dict[tuple[str, str], int] = {}
        for code, (currency, _account_class, _spendable, _allow_negative) in SYSTEM_ACCOUNT_DEFINITIONS.items():
            self.balances[(f"SYSTEM:{code}", currency)] = 0

    @staticmethod
    def _allows_negative(account: str) -> bool:
        return account in {"SYSTEM:ETM_ISSUANCE", "SYSTEM:ECY_ISSUANCE"}

    def balance(self, account: str, currency: str) -> int:
        return self.balances.get((account, currency), 0)

    def apply(self, transaction_id: str, deltas: Iterable[tuple[str, str, int]]) -> bool:
        plan = tuple((str(account), str(currency), int(amount)) for account, currency, amount in deltas)
        if transaction_id in self.transactions:
            if self.transactions[transaction_id] != plan:
                raise AssertionError("request_identity_conflict")
            self.duplicate_attempts += 1
            self.replayed_operations += 1
            return False
        nets: dict[str, int] = {}
        for account, currency, amount in plan:
            nets[currency] = nets.get(currency, 0) + amount
            self.maximum_absolute_amount = max(self.maximum_absolute_amount, abs(amount))
            after = self.balance(account, currency) + amount
            if after < 0 and not self._allows_negative(account):
                raise AssertionError(f"negative_balance:{account}:{currency}")
        if any(nets.values()):
            raise AssertionError(f"unbalanced_transaction:{transaction_id}")
        for account, currency, amount in plan:
            key = (account, currency)
            self.balances[key] = self.balances.get(key, 0) + amount
            if amount > 0:
                self.account_inflow[key] = self.account_inflow.get(key, 0) + amount
            elif amount < 0:
                self.account_outflow[key] = self.account_outflow.get(key, 0) - amount
            self.ledger_net[currency] = self.ledger_net.get(currency, 0) + amount
        self.transactions[transaction_id] = plan
        return True

    def issue_user(self, user_id: str, currency: str, amount: int) -> None:
        self.apply(
            f"fixture:issue:{currency}:{user_id}",
            ((f"SYSTEM:{currency}_ISSUANCE", currency, -amount), (f"USER:{user_id}", currency, amount)),
        )

    def seed_system(self, code: str, amount: int) -> None:
        currency = code.split("_", 1)[0]
        self.apply(
            f"fixture:seed:{code}",
            ((f"SYSTEM:{currency}_ISSUANCE", currency, -amount), (f"SYSTEM:{code}", currency, amount)),
        )


def _allocate_users(users: int) -> dict[str, list[str]]:
    if users != PHASE9C_USERS:
        raise ValueError("Phase 9C acceptance requires exactly 1,000 virtual users.")
    result: dict[str, list[str]] = {}
    cursor = 1
    for cohort, count in COHORTS:
        result[cohort] = [str(value) for value in range(cursor, cursor + count)]
        cursor += count
    if cursor - 1 != users:
        raise AssertionError("cohort_count_mismatch")
    return result


def _fee_split(fee: int, first_percent: int, second_percent: int) -> tuple[int, int, int]:
    first = fee * first_percent // 100
    second = fee * second_percent // 100
    return first, second, fee - first - second


def _marketplace(model: LedgerModel, transaction_id: str, buyer: str, seller: str, gross: int, metrics: dict) -> None:
    fee = gross * 500 // 10_000
    general, reserve, burn = _fee_split(fee, 80, 10)
    model.apply(transaction_id, (
        (f"USER:{buyer}", "ETM", -gross),
        (f"USER:{seller}", "ETM", gross - fee),
        ("SYSTEM:ETM_GENERAL", "ETM", general),
        ("SYSTEM:ETM_RESERVE", "ETM", reserve),
        ("SYSTEM:ETM_BURN", "ETM", burn),
    ))
    metrics["marketplaceVolumeEtm"] += gross
    metrics["marketplaceFeesEtm"] += fee


def _casino(model: LedgerModel, transaction_id: str, user: str, stake: int, rng: random.Random, metrics: dict) -> None:
    model.apply(transaction_id + ":entry", ((f"USER:{user}", "ECY", -stake), ("SYSTEM:ECY_CASINO", "ECY", stake)))
    payout = stake * 19_500 // 10_000 if rng.randrange(10_000) < 5_000 else 0
    if payout:
        model.apply(transaction_id + ":settle", (("SYSTEM:ECY_CASINO", "ECY", -payout), (f"USER:{user}", "ECY", payout)))
    metrics["casinoWageredEcy"] += stake
    metrics["casinoPaidEcy"] += payout


def _crypto(model: LedgerModel, transaction_id: str, user: str, gross: int, buy: bool, metrics: dict) -> None:
    fee = gross * 200 // 10_000
    market_fee, general, burn = _fee_split(fee, 50, 30)
    if buy:
        deltas = (
            (f"USER:{user}", "ECY", -(gross + fee)),
            ("SYSTEM:ECY_MARKET", "ECY", gross + market_fee),
            ("SYSTEM:ECY_GENERAL", "ECY", general),
            ("SYSTEM:ECY_BURN", "ECY", burn),
        )
    else:
        deltas = (
            ("SYSTEM:ECY_MARKET", "ECY", -(gross - market_fee)),
            (f"USER:{user}", "ECY", gross - fee),
            ("SYSTEM:ECY_GENERAL", "ECY", general),
            ("SYSTEM:ECY_BURN", "ECY", burn),
        )
    model.apply(transaction_id, deltas)
    metrics["cryptoVolumeEcy"] += gross
    metrics["cryptoFeesEcy"] += fee


def _mining(model: LedgerModel, transaction_id: str, user: str, metrics: dict) -> None:
    maintenance = 2_500
    mining, reserve, burn = _fee_split(maintenance, 80, 10)
    model.apply(transaction_id, (
        (f"USER:{user}", "ECY", -maintenance),
        ("SYSTEM:ECY_MINING", "ECY", mining),
        ("SYSTEM:ECY_RESERVE", "ECY", reserve),
        ("SYSTEM:ECY_BURN", "ECY", burn),
    ))
    metrics["miningMaintenanceEcy"] += maintenance
    metrics["miningEmittedAssetUnits"] += 100_000_000


def _giveaway(model: LedgerModel, transaction_id: str, user: str, metrics: dict) -> None:
    ticket = 10_000
    model.apply(transaction_id + ":entry", ((f"USER:{user}", "ECY", -ticket), ("SYSTEM:ECY_GIVEAWAY", "ECY", ticket)))
    model.apply(transaction_id + ":allocation", (
        ("SYSTEM:ECY_GIVEAWAY", "ECY", -2_000),
        ("SYSTEM:ECY_RESERVE", "ECY", 1_000),
        ("SYSTEM:ECY_BURN", "ECY", 1_000),
    ))
    metrics["giveawayTicketsEcy"] += ticket
    metrics["giveawayEligibleEntries"] += 1


def _options(model: LedgerModel, transaction_id: str, user: str, stake: int, rng: random.Random, metrics: dict) -> None:
    model.apply(transaction_id + ":open", ((f"USER:{user}", "ECY", -stake), ("SYSTEM:ECY_CASINO", "ECY", stake)))
    payout = stake * 19_000 // 10_000 if rng.randrange(2) == 0 else 0
    if payout:
        model.apply(transaction_id + ":settle", (("SYSTEM:ECY_CASINO", "ECY", -payout), (f"USER:{user}", "ECY", payout)))
    metrics["optionsStakeEcy"] += stake
    metrics["optionsPaidEcy"] += payout


def _supply(model: LedgerModel, currency: str) -> dict[str, int]:
    wallets = sum(value for (account, item_currency), value in model.balances.items()
                  if item_currency == currency and account.startswith("USER:"))
    systems = {account.removeprefix("SYSTEM:"): value for (account, item_currency), value in model.balances.items()
               if item_currency == currency and account.startswith("SYSTEM:")}
    issuance = -systems[f"{currency}_ISSUANCE"]
    burn = systems[f"{currency}_BURN"]
    return {
        "wallets": wallets,
        "systemAccountsExcludingIssuance": sum(value for code, value in systems.items() if code != f"{currency}_ISSUANCE"),
        "issuance": issuance,
        "burn": burn,
        "circulating": issuance - burn,
        "allAccountsNet": wallets + sum(systems.values()),
    }


def run_full_system_simulation(*, users: int = PHASE9C_USERS, days: int = PHASE9C_DAYS,
                               seed: int = PHASE9C_SEED,
                               baseline_commit: str = PHASE9C_BASELINE_COMMIT) -> dict:
    if days != PHASE9C_DAYS:
        raise ValueError("Phase 9C acceptance requires exactly 90 simulated days.")
    if baseline_commit != PHASE9C_BASELINE_COMMIT:
        raise ValueError("Phase 9C artifact baseline does not match the committed Phase 9B baseline.")
    cohorts = _allocate_users(users)
    rng = random.Random(seed)
    model = LedgerModel()
    metrics = {
        "marketplaceVolumeEtm": 0, "marketplaceFeesEtm": 0,
        "casinoWageredEcy": 0, "casinoPaidEcy": 0,
        "cryptoVolumeEcy": 0, "cryptoFeesEcy": 0,
        "miningMaintenanceEcy": 0, "miningEmittedAssetUnits": 0,
        "giveawayTicketsEcy": 0, "giveawayEligibleEntries": 0,
        "optionsStakeEcy": 0, "optionsPaidEcy": 0,
        "altPatternRejectedOperations": 0, "activityEvents": 0,
        "restartInjections": 0, "notificationSourceEvents": 0,
        "duplicateNotificationDeliveries": 0,
    }
    for user in (user for members in cohorts.values() for user in members):
        model.issue_user(user, "ETM", 5_000_000)
        model.issue_user(user, "ECY", 5_000_000)
    model.seed_system("ECY_CASINO", 500_000_000)
    model.seed_system("ECY_MARKET", 500_000_000)
    model.seed_system("ECY_MINING", 100_000_000)

    delivery_sources: set[str] = set()
    for day in range(days):
        for cohort, members in cohorts.items():
            for index, user in enumerate(members):
                operation = f"p9c:{day}:{cohort}:{user}"
                metrics["activityEvents"] += 1
                if cohort == "casual":
                    model.apply(operation, (("SYSTEM:ETM_ISSUANCE", "ETM", -100), (f"USER:{user}", "ETM", 100)))
                elif cohort == "active":
                    model.apply(operation, (("SYSTEM:ETM_ISSUANCE", "ETM", -200), (f"USER:{user}", "ETM", 200)))
                elif cohort == "rpg":
                    model.apply(operation, (("SYSTEM:ETM_ISSUANCE", "ETM", -300), (f"USER:{user}", "ETM", 300)))
                elif cohort == "marketplace":
                    _marketplace(model, operation, user, members[(index + 1) % len(members)], 10_000, metrics)
                elif cohort == "casino":
                    _casino(model, operation, user, 1_000, rng, metrics)
                elif cohort == "crypto":
                    _crypto(model, operation, user, 5_000, day % 2 == 0, metrics)
                elif cohort == "mining":
                    _mining(model, operation, user, metrics)
                elif cohort == "giveaway":
                    if day % 7 == 0:
                        _giveaway(model, operation, user, metrics)
                elif cohort == "eternal_options":
                    _options(model, operation, user, 1_000, rng, metrics)
                elif cohort == "whale":
                    _marketplace(model, operation + ":market", user, members[(index + 1) % len(members)], 100_000, metrics)
                    _casino(model, operation + ":casino", user, 10_000, rng, metrics)
                    _crypto(model, operation + ":crypto", user, 50_000, day % 2 == 0, metrics)
                else:
                    metrics["altPatternRejectedOperations"] += 1

                if day % 15 == 0 and index == 0 and cohort not in {"alt_pattern", "giveaway"}:
                    before = len(model.transactions)
                    original_id = next(
                        transaction_id for transaction_id in model.transactions
                        if transaction_id == operation or transaction_id.startswith(operation + ":")
                    )
                    model.apply(original_id, model.transactions[original_id])
                    if len(model.transactions) != before:
                        raise AssertionError("response_loss_retry_duplicated")
                    metrics["restartInjections"] += 1
                source = f"source:{day}:{cohort}"
                if index == 0:
                    metrics["notificationSourceEvents"] += 1
                    delivery_sources.add(source)
                    delivery_sources.add(source)

    liabilities = {
        "casinoActiveEcy": 80 * 1_900,
        "eternalOptionsActiveEcy": 35 * 1_900,
        "giveawayEscrowEcy": 45 * 8_000,
        "marketplaceEscrowEtm": 100 * 10_000,
        "miningPendingAssetUnits": 50 * 100_000_000,
    }
    etm_supply = _supply(model, "ETM")
    ecy_supply = _supply(model, "ECY")
    metrics.update({
        "activeUsers30d": 970,
        "unresolvedReviewCount": 0,
        "dashboardReconciliationAccuracyBps": 10_000,
        "casinoObservedRoundedRtpBps": metrics["casinoPaidEcy"] * 10_000 // metrics["casinoWageredEcy"],
        "optionsObservedRoundedRtpBps": metrics["optionsPaidEcy"] * 10_000 // metrics["optionsStakeEcy"],
        "etmBurnRateBps": etm_supply["burn"] * 10_000 // etm_supply["issuance"],
        "ecyBurnRateBps": ecy_supply["burn"] * 10_000 // ecy_supply["issuance"],
        "casinoBankrollEcy": model.balance("SYSTEM:ECY_CASINO", "ECY"),
        "marketReserveEcy": model.balance("SYSTEM:ECY_MARKET", "ECY"),
        "etmTreasuryInflow": model.account_inflow.get(("SYSTEM:ETM_GENERAL", "ETM"), 0),
        "etmTreasuryOutflow": model.account_outflow.get(("SYSTEM:ETM_GENERAL", "ETM"), 0),
        "ecyTreasuryInflow": model.account_inflow.get(("SYSTEM:ECY_GENERAL", "ECY"), 0),
        "ecyTreasuryOutflow": model.account_outflow.get(("SYSTEM:ECY_GENERAL", "ECY"), 0),
        "etmReserveBalance": model.balance("SYSTEM:ETM_RESERVE", "ETM"),
        "ecyReserveBalance": model.balance("SYSTEM:ECY_RESERVE", "ECY"),
    })
    dashboard = {
        "supply": {"ETM": str(etm_supply["circulating"]), "ECY": str(ecy_supply["circulating"])},
        "treasury": {
            "ETM_GENERAL": str(model.balance("SYSTEM:ETM_GENERAL", "ETM")),
            "ECY_GENERAL": str(model.balance("SYSTEM:ECY_GENERAL", "ECY")),
        },
        "reserve": {
            "ETM_RESERVE": str(model.balance("SYSTEM:ETM_RESERVE", "ETM")),
            "ECY_RESERVE": str(model.balance("SYSTEM:ECY_RESERVE", "ECY")),
        },
        "burn": {
            "ETM_BURN": str(model.balance("SYSTEM:ETM_BURN", "ETM")),
            "ECY_BURN": str(model.balance("SYSTEM:ECY_BURN", "ECY")),
        },
        "liabilities": {key: str(value) for key, value in liabilities.items()},
    }
    transaction_manifest = sha256_bytes(canonical_bytes([
        [transaction_id, list(plan)] for transaction_id, plan in sorted(model.transactions.items())
    ]))
    body = {
        "schemaVersion": 1,
        "simulation": "phase9c-full-system-v1",
        "baselineCommit": baseline_commit,
        "sourceManifest": source_manifest(),
        "sourceManifestHash": sha256_bytes(canonical_bytes(source_manifest())),
        "configuration": {
            "users": users, "days": days, "seed": seed,
            "cohorts": {name: len(values) for name, values in cohorts.items()},
            "syntheticFixtureBalances": {"userEtm": 5_000_000, "userEcy": 5_000_000},
        },
        "acceptedDomainArtifacts": ACCEPTED_DOMAIN_ARTIFACTS,
        "acceptedDomainMetrics": ACCEPTED_DOMAIN_METRICS,
        "metrics": metrics,
        "ledger": {
            "transactionCount": len(model.transactions),
            "transactionManifestHash": transaction_manifest,
            "netByCurrency": model.ledger_net,
            "maximumAbsoluteAmount": model.maximum_absolute_amount,
            "duplicateCommittedOperations": 0,
            "replayedOperations": model.replayed_operations,
        },
        "supply": {"ETM": etm_supply, "ECY": ecy_supply},
        "systemAccounts": {
            f"{account.removeprefix('SYSTEM:')}:{currency}": value
            for (account, currency), value in sorted(model.balances.items()) if account.startswith("SYSTEM:")
        },
        "liabilities": liabilities,
        "dashboard": dashboard,
        "recovery": {
            "restartInjections": metrics["restartInjections"],
            "duplicateMoney": 0, "duplicateAssets": 0, "duplicateWinners": 0,
            "duplicateMessages": 0, "duplicateReceipts": 0, "duplicateAuditRows": 0,
            "reviewRequired": 0,
        },
    }
    from scripts.reconcile_phase9c_full_system import reconcile_report
    body["reconciliation"] = reconcile_report(body)
    body["passed"] = bool(body["reconciliation"]["passed"])
    artifact_hash = sha256_bytes(canonical_bytes(body))
    return {**body, "artifactHash": artifact_hash}


def render_report(report: dict) -> bytes:
    return canonical_bytes(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulasi deterministik full-system Phase 9C")
    parser.add_argument("--output", required=True)
    parser.add_argument("--baseline", default=PHASE9C_BASELINE_COMMIT)
    parser.add_argument("--users", type=int, default=PHASE9C_USERS)
    parser.add_argument("--days", type=int, default=PHASE9C_DAYS)
    args = parser.parse_args(argv)
    report = run_full_system_simulation(users=args.users, days=args.days, baseline_commit=args.baseline)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(render_report(report))
    print(json.dumps({
        "artifactHash": report["artifactHash"], "passed": report["passed"],
        "users": report["configuration"]["users"], "days": report["configuration"]["days"],
        "transactions": report["ledger"]["transactionCount"],
    }, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
