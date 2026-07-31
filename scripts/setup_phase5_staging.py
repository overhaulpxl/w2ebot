"""Siapkan salinan staging Casino dan verifikasi apply migration 500 dua kali."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.phase5_migrations import apply_phase5_staging, phase5_dry_run, verify_phase5_staging
from economy.staging import create_logical_sqlite_backup
from runtime_config import PRODUCTION_DATABASE_PATH


def prepare_phase5_staging(source, target, *, guild_id, users_json=None, replace=False):
    source = Path(source).expanduser().resolve()
    target = Path(target).expanduser().resolve()
    if target == PRODUCTION_DATABASE_PATH or source == target:
        raise RuntimeError("Target Phase 5 harus berupa database staging terpisah.")
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.exists() and not replace:
        raise RuntimeError("Target staging sudah ada; gunakan --replace-staging.")
    if target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    copied = create_logical_sqlite_backup(source, target)
    backup_path = target.with_suffix(".pre-phase5.backup.db")
    if backup_path.exists():
        backup_path.unlink()
    backup = create_logical_sqlite_backup(target, backup_path)
    dry_run = phase5_dry_run(target)
    first = apply_phase5_staging(
        target, production_db=PRODUCTION_DATABASE_PATH, guild_id=guild_id,
        users_json_path=users_json,
    )
    first_verify = verify_phase5_staging(target)
    second = apply_phase5_staging(target, production_db=PRODUCTION_DATABASE_PATH, guild_id=guild_id)
    second_verify = verify_phase5_staging(target)
    if not second["replayed"] or first_verify["rowTotals"] != second_verify["rowTotals"]:
        raise RuntimeError("Apply migration 500 kedua bukan no-op terverifikasi.")
    return {"sourceCopy": copied, "preMigrationBackup": backup, "dryRun": dry_run,
            "firstApply": first, "secondApplyIdempotent": True,
            "verification": second_verify, "productionCutover": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Siapkan database staging Phase 5")
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--guild-id", required=True)
    parser.add_argument("--users-json")
    parser.add_argument("--replace-staging", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(prepare_phase5_staging(
        args.source, args.target, guild_id=args.guild_id,
        users_json=args.users_json, replace=args.replace_staging,
    ), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
