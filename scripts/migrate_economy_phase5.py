"""CLI staging-only migration 500 / phase5-casino."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.phase5_migrations import (
    apply_phase5_staging, phase5_dry_run, reconcile_phase5_staging,
    restore_phase5_staging, verify_phase5_staging,
)


def parser():
    value = argparse.ArgumentParser(description="Migrasi Casino Phase 5 staging-only")
    value.add_argument("--database", required=True)
    value.add_argument("--production-database", default=str(ROOT / "w2ebot.db"))
    value.add_argument("--mode", choices=("dry-run", "apply", "verify", "reconcile", "restore"), required=True)
    value.add_argument("--guild-id", default="0")
    value.add_argument("--users-json")
    value.add_argument("--backup")
    value.add_argument("--confirm-restore", action="store_true")
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    if args.mode == "dry-run":
        result = phase5_dry_run(args.database)
    elif args.mode == "verify":
        result = verify_phase5_staging(args.database)
    elif args.mode == "reconcile":
        result = reconcile_phase5_staging(args.database)
    elif args.mode == "apply":
        result = apply_phase5_staging(
            args.database, production_db=args.production_database, guild_id=args.guild_id,
            users_json_path=args.users_json, backup_path=args.backup,
        )
    else:
        if not args.backup:
            raise SystemExit("--backup wajib untuk restore")
        result = restore_phase5_staging(
            args.database, backup_path=args.backup, production_db=args.production_database,
            confirm=args.confirm_restore,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
