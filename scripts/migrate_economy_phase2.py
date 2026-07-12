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
from economy.migrations import apply_phase2_staging_migration, build_phase2_dry_run


def main():
    parser = argparse.ArgumentParser(description="W2E Economy Phase 2 migration verifier")
    parser.add_argument("--database", default=str(DATABASE_PATH))
    parser.add_argument("--guild-id", default=os.getenv("ALLOWED_SERVER_ID", "887968847842402355"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--manifest")
    parser.add_argument("--allow-staging-apply", action="store_true")
    args = parser.parse_args()
    if args.apply:
        if not args.manifest:
            parser.error("--apply requires --manifest")
        totals, replayed = apply_phase2_staging_migration(
            args.database, args.manifest, production_path=PRODUCTION_DATABASE_PATH,
            allow_staging_apply=args.allow_staging_apply,
        )
        print(json.dumps({"status": "ok", "replayed": replayed, "totals": totals}, indent=2))
        return
    report, manifest = build_phase2_dry_run(
        args.database, guild_id=args.guild_id,
        backup_dir=ECONOMY_BACKUP_DIR, report_dir=ECONOMY_REPORT_DIR,
    )
    summary = dict(report)
    summary["profile_projection"] = {
        "totals": report["profile_projection"]["totals"],
        "item_count": len(report["profile_projection"]["items"]),
    }
    summary["manifest_path"] = manifest
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
