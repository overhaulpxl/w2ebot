"""Siapkan database staging Phase 4 dengan backup API dan verifikasi dua kali."""

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.phase4_migrations import apply_phase4_staging, phase4_dry_run, verify_phase4_staging
from economy.staging import create_logical_sqlite_backup
from runtime_config import PRODUCTION_DATABASE_PATH


def _safe_target(path):
    resolved = Path(path).expanduser().resolve()
    if resolved == PRODUCTION_DATABASE_PATH:
        raise RuntimeError("Setup Phase 4 menolak path production.")
    return resolved


async def prepare_phase4_staging(source, target, *, replace=False):
    source = Path(source).expanduser().resolve()
    target = _safe_target(target)
    if source == target:
        raise RuntimeError("Source dan target staging harus berbeda.")
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.exists() and not replace:
        raise RuntimeError("Target staging sudah ada; gunakan --replace-staging secara eksplisit.")
    if target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    source_backup = create_logical_sqlite_backup(source, target)
    pre_migration_backup = target.with_suffix(".pre-phase4.backup.db")
    if pre_migration_backup.exists():
        pre_migration_backup.unlink()
    backup = create_logical_sqlite_backup(target, pre_migration_backup)
    dry_run = await phase4_dry_run(target)
    first = await apply_phase4_staging(target, production_db=PRODUCTION_DATABASE_PATH)
    first_verify = await verify_phase4_staging(target)
    second = await apply_phase4_staging(target, production_db=PRODUCTION_DATABASE_PATH)
    second_verify = await verify_phase4_staging(target)
    if not second["migration"]["idempotent"]:
        raise RuntimeError("Apply Phase 4 kedua bukan no-op.")
    if first_verify["manifest"]["row_counts"] != second_verify["manifest"]["row_counts"]:
        raise RuntimeError("Apply Phase 4 kedua mengubah row count.")
    return {
        "source_copy": source_backup, "pre_migration_backup": backup, "dry_run": dry_run,
        "first_apply": first, "second_apply_idempotent": True,
        "verification": second_verify, "production_cutover": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Siapkan database staging Phase 4")
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--replace-staging", action="store_true")
    args = parser.parse_args(argv)
    result = asyncio.run(prepare_phase4_staging(args.source, args.target, replace=args.replace_staging))
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
