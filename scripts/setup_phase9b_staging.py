"""Backup-first Phase 9B setup for an explicit staging database."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.phase9b_migrations import apply_phase9b_staging, reconcile_phase9b_staging  # noqa: E402
from runtime_config import PRODUCTION_DATABASE_PATH  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--backup", required=True)
    parser.add_argument("--guild-id", required=True)
    parser.add_argument("--legacy-config")
    parser.add_argument("--channel-manifest")
    args = parser.parse_args(argv)
    result = apply_phase9b_staging(
        args.database, production_db=PRODUCTION_DATABASE_PATH, backup_path=args.backup,
        legacy_config_path=args.legacy_config, channel_manifest_path=args.channel_manifest,
        guild_id=args.guild_id,
    )
    reconciliation = reconcile_phase9b_staging(args.database, guild_id=args.guild_id)
    if not reconciliation["reconciled"]:
        raise RuntimeError("Rekonsiliasi Phase 9B gagal.")
    print(json.dumps({"migration": result, "reconciliation": reconciliation}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
