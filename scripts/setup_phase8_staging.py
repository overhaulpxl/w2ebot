"""Setup migration Phase 8 pada database staging eksplisit."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.phase8_migrations import apply_phase8_staging, reconcile_phase8_staging
from runtime_config import PRODUCTION_DATABASE_PATH


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--backup", required=True)
    args = parser.parse_args(argv)
    target = Path(args.database).resolve()
    result = apply_phase8_staging(target, production_db=PRODUCTION_DATABASE_PATH,
                                  backup_path=args.backup)
    reconciliation = reconcile_phase8_staging(target)
    if not reconciliation["reconciled"]:
        raise RuntimeError("Rekonsiliasi Phase 8 gagal.")
    print(json.dumps({"migration": result, "reconciliation": reconciliation}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
