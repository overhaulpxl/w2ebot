"""CLI migrasi Economy/RPG Phase 3 untuk dry-run dan staging."""

import argparse
import asyncio
import json
from pathlib import Path

from economy.phase3_migrations import apply_phase3_staging, phase3_dry_run
from runtime_config import DATABASE_PATH, PRODUCTION_DATABASE_PATH


def parser():
    result = argparse.ArgumentParser(description="Migrasi Economy RPG Phase 3")
    result.add_argument("--database", default=str(DATABASE_PATH))
    result.add_argument("--production-database", default=str(PRODUCTION_DATABASE_PATH))
    result.add_argument("--apply", action="store_true")
    result.add_argument("--no-seed", action="store_true")
    return result


async def run(args):
    if args.apply:
        return await apply_phase3_staging(
            args.database, production_db=args.production_database, seed=not args.no_seed,
        )
    return await phase3_dry_run(args.database)


if __name__ == "__main__":
    arguments = parser().parse_args()
    print(json.dumps(asyncio.run(run(arguments)), indent=2, sort_keys=True))
