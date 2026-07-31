import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime_config import DATABASE_PATH, PRODUCTION_DATABASE_PATH
from economy.constants import ECONOMY_BACKUP_DIR, ECONOMY_REPORT_DIR
from economy.migrations import (
    apply_staging_migration,
    build_dry_run,
    restore_staging_backup,
    verify_staging_migration,
)


def main():
    parser = argparse.ArgumentParser(description="W2E Economy V1 Phase 1 migration verifier")
    parser.add_argument("--database", default=str(DATABASE_PATH))
    parser.add_argument("--guild-id", default=os.getenv("ALLOWED_SERVER_ID", "887968847842402355"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--backup")
    parser.add_argument("--manifest")
    parser.add_argument("--allow-staging-apply", action="store_true")
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify_staging_migration(args.database, guild_id=args.guild_id), indent=2, sort_keys=True))
        return
    if args.rollback:
        if not args.backup:
            parser.error("--rollback requires --backup")
        result = restore_staging_backup(
            args.backup, args.database, production_path=PRODUCTION_DATABASE_PATH,
            allow_staging_restore=args.allow_staging_apply,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    if args.apply or args.resume:
        if not args.manifest:
            parser.error("--apply/--resume requires --manifest")
        totals, replayed = apply_staging_migration(
            args.database, args.manifest,
            production_path=PRODUCTION_DATABASE_PATH,
            allow_staging_apply=args.allow_staging_apply,
        )
        print(json.dumps({"status": "ok", "replayed": replayed, "totals": totals}, indent=2))
        return
    report, manifest = build_dry_run(
        args.database, guild_id=args.guild_id,
        backup_dir=ECONOMY_BACKUP_DIR, report_dir=ECONOMY_REPORT_DIR,
    )
    summary = dict(report)
    summary["wallet_projection"] = {k: v for k, v in report["wallet_projection"].items() if k != "items"}
    summary["binomo_refunds"] = {k: v for k, v in report["binomo_refunds"].items() if k != "items"}
    summary["manifest_path"] = manifest
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
