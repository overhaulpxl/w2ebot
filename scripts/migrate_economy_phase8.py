"""CLI migration staging Phase 8."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.phase8_migrations import (
    apply_phase8_staging, phase8_dry_run, reconcile_phase8_staging,
    restore_phase8_staging, verify_phase8_staging,
)
from runtime_config import PRODUCTION_DATABASE_PATH


def main(argv=None):
    parser = argparse.ArgumentParser(description="Migrasi eksplisit Phase 8 Giveaway dan Options")
    parser.add_argument("mode", choices=("dry-run", "apply", "verify", "reconcile", "restore"))
    parser.add_argument("--database", required=True)
    parser.add_argument("--production-database", default=str(PRODUCTION_DATABASE_PATH))
    parser.add_argument("--backup")
    parser.add_argument("--confirm-restore", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "dry-run":
        result = phase8_dry_run(args.database)
    elif args.mode == "apply":
        result = apply_phase8_staging(args.database, production_db=args.production_database,
                                      backup_path=args.backup)
    elif args.mode == "verify":
        result = verify_phase8_staging(args.database)
    elif args.mode == "reconcile":
        result = reconcile_phase8_staging(args.database)
    else:
        if not args.backup:
            parser.error("--backup wajib untuk restore")
        result = restore_phase8_staging(args.database, backup_path=args.backup,
                                        production_db=args.production_database,
                                        confirm=args.confirm_restore)
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
