"""CLI eksplisit migrasi Marketplace Phase 4; tidak pernah dijalankan saat startup."""

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.phase4_migrations import (
    apply_phase4_staging, phase4_dry_run, reconcile_phase4_staging,
    restore_phase4_staging, verify_phase4_staging,
)
from runtime_config import PRODUCTION_DATABASE_PATH


async def _run(args):
    target = Path(args.database).expanduser().resolve()
    if args.mode == "dry-run":
        return await phase4_dry_run(target)
    if args.mode == "verify":
        return await verify_phase4_staging(target)
    if args.mode == "reconcile":
        return await reconcile_phase4_staging(target)
    if args.mode == "restore":
        return await restore_phase4_staging(
            target, backup_path=Path(args.restore).expanduser().resolve(),
            production_db=PRODUCTION_DATABASE_PATH,
            confirm_restore_staging=args.confirm_restore_staging,
            safety_backup_path=(Path(args.safety_backup).expanduser().resolve()
                                if args.safety_backup else None),
        )
    return await apply_phase4_staging(
        target, production_db=PRODUCTION_DATABASE_PATH,
        backup_path=Path(args.backup).expanduser().resolve() if args.backup else None,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Migrasi staging Economy Phase 4")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--verify", action="store_true")
    modes.add_argument("--reconcile", action="store_true")
    modes.add_argument("--restore", metavar="BACKUP_PATH")
    parser.add_argument("--confirm-restore-staging", action="store_true")
    parser.add_argument("--safety-backup", help="Path safety backup sebelum restore")
    parser.add_argument("--database")
    parser.add_argument("--backup", help="Path backup SQLite API sebelum apply")
    parser.add_argument(
        "legacy", nargs="*", help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    selected = [
        name for name in ("dry_run", "apply", "verify", "reconcile", "restore")
        if getattr(args, name)
    ]
    if selected:
        if args.legacy:
            parser.error("Gunakan --database bersama mode eksplisit.")
        args.mode = selected[0].replace("_", "-")
        if not args.database:
            parser.error("--database wajib diisi.")
    else:
        if len(args.legacy) != 2 or args.legacy[0] not in (
            "dry-run", "apply", "verify", "reconcile"
        ):
            parser.error("Pilih satu mode eksplisit dan --database.")
        args.mode, args.database = args.legacy
    if args.backup and args.mode != "apply":
        parser.error("--backup hanya berlaku untuk mode apply")
    if args.mode == "restore" and not args.confirm_restore_staging:
        parser.error("--confirm-restore-staging wajib untuk restore")
    print(json.dumps(asyncio.run(_run(args)), indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
