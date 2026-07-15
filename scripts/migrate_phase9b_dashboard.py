"""Manual migration CLI for Phase 9B. It is never imported by bot startup."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.phase9b_migrations import (  # noqa: E402
    apply_phase9b_staging, phase9b_dry_run, reconcile_phase9b_staging,
    restore_phase9b_staging, verify_phase9b_staging,
)


def parser():
    result = argparse.ArgumentParser(description="Migrasi Phase 9B dashboard dan routing notifikasi")
    result.add_argument("mode", choices=("dry-run", "apply", "verify", "reconcile", "restore"))
    result.add_argument("database")
    result.add_argument("--production-database", required=True)
    result.add_argument("--backup")
    result.add_argument("--legacy-config")
    result.add_argument("--channel-manifest")
    result.add_argument("--guild-id")
    result.add_argument("--failure-stage")
    result.add_argument("--confirm", action="store_true")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    common = {"legacy_config_path": args.legacy_config, "channel_manifest_path": args.channel_manifest,
              "guild_id": args.guild_id}
    if args.mode == "dry-run":
        output = phase9b_dry_run(args.database, **common)
    elif args.mode == "apply":
        output = apply_phase9b_staging(
            args.database, production_db=args.production_database, backup_path=args.backup,
            failure_stage=args.failure_stage, **common,
        )
    elif args.mode == "verify":
        output = verify_phase9b_staging(args.database)
    elif args.mode == "reconcile":
        if not args.guild_id:
            raise SystemExit("--guild-id wajib untuk reconcile")
        output = reconcile_phase9b_staging(args.database, guild_id=args.guild_id)
    else:
        if not args.backup:
            raise SystemExit("--backup wajib untuk restore")
        output = restore_phase9b_staging(
            args.database, backup_path=args.backup, production_db=args.production_database,
            confirm=args.confirm,
        )
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
