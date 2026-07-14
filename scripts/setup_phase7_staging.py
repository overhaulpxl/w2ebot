"""Siapkan schema Phase 7 pada database staging eksplisit."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.phase7_migrations import apply_phase7_staging, reconcile_phase7_staging
from runtime_config import PRODUCTION_DATABASE_PATH


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--guild-id", required=True)
    parser.add_argument("--users-json")
    parser.add_argument("--backup", required=True)
    args = parser.parse_args(argv)
    target = Path(args.database).resolve()
    if target == PRODUCTION_DATABASE_PATH:
        parser.error("Database production ditolak.")
    result = apply_phase7_staging(
        target, production_db=PRODUCTION_DATABASE_PATH, guild_id=args.guild_id,
        users_json_path=args.users_json, backup_path=args.backup,
    )
    reconciliation = reconcile_phase7_staging(target)
    if not reconciliation["reconciled"]:
        raise RuntimeError("Rekonsiliasi Mining staging gagal.")
    print(json.dumps({"migration": result, "reconciliation": reconciliation}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
