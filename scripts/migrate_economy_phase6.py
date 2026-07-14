"""CLI staging-only migration 600 / phase6-crypto."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.phase6_migrations import (
    apply_phase6_staging, phase6_dry_run, reconcile_phase6_staging,
    restore_phase6_staging, verify_phase6_staging,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Migrasi Crypto Phase 6 staging-only")
    parser.add_argument("--database", required=True)
    parser.add_argument("--production-database", default=str(ROOT / "w2ebot.db"))
    parser.add_argument("--mode", choices=("dry-run", "apply", "verify", "reconcile", "restore"), required=True)
    parser.add_argument("--guild-id")
    parser.add_argument("--users-json")
    parser.add_argument("--backup")
    parser.add_argument("--confirm-restore", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "dry-run":
        result = phase6_dry_run(args.database)
    elif args.mode == "verify":
        result = verify_phase6_staging(args.database)
    elif args.mode == "reconcile":
        result = reconcile_phase6_staging(args.database)
    elif args.mode == "apply":
        result = apply_phase6_staging(
            args.database, production_db=args.production_database, guild_id=args.guild_id,
            users_json_path=args.users_json, backup_path=args.backup,
        )
    else:
        if not args.backup:
            raise SystemExit("--backup wajib untuk restore")
        result = restore_phase6_staging(
            args.database, backup_path=args.backup, production_db=args.production_database,
            confirm=args.confirm_restore,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
