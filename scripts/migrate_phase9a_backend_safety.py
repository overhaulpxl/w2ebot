"""CLI migrasi manual Phase 9A. Tidak dipanggil saat startup bot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.phase9a_migrations import (  # noqa: E402
    apply_phase9a_staging, bootstrap_admin, phase9a_dry_run, reconcile_phase9a_staging,
    register_signing_key, restore_phase9a_staging, verify_phase9a_staging,
)


def parser():
    result = argparse.ArgumentParser(description="Migrasi staging Phase 9A backend safety")
    result.add_argument("mode", choices=("dry-run", "apply", "verify", "reconcile", "restore",
                                         "bootstrap-admin", "register-key", "rotate-key"))
    result.add_argument("database")
    result.add_argument("--production-database", required=True)
    result.add_argument("--backup")
    result.add_argument("--failure-stage")
    result.add_argument("--guild-id")
    result.add_argument("--user-id")
    result.add_argument("--actor-id", default="STAGING_CLI")
    result.add_argument("--key-id")
    result.add_argument("--key-purpose", choices=("INTERNAL_REQUEST", "SESSION_HASH", "IP_HASH"))
    result.add_argument("--key-file")
    result.add_argument("--confirm", action="store_true")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.mode == "dry-run":
        output = phase9a_dry_run(args.database)
    elif args.mode == "apply":
        output = apply_phase9a_staging(args.database, production_db=args.production_database,
                                       backup_path=args.backup, failure_stage=args.failure_stage)
    elif args.mode == "verify":
        output = verify_phase9a_staging(args.database)
    elif args.mode == "reconcile":
        output = reconcile_phase9a_staging(args.database)
    elif args.mode == "restore":
        output = restore_phase9a_staging(args.database, backup_path=args.backup,
                                         production_db=args.production_database, confirm=args.confirm)
    elif args.mode == "bootstrap-admin":
        if not args.guild_id or not args.user_id:
            raise SystemExit("--guild-id dan --user-id wajib untuk bootstrap-admin")
        output = bootstrap_admin(args.database, guild_id=args.guild_id, user_id=args.user_id,
                                 actor_id=args.actor_id)
    else:
        if not args.key_id or not args.key_purpose or not args.key_file:
            raise SystemExit("--key-id, --key-purpose, dan --key-file wajib")
        key = Path(args.key_file).read_bytes()
        if len(key) < 32:
            raise SystemExit("Signing key minimal 32 byte")
        register_signing_key(args.database, key_id=args.key_id, purpose=args.key_purpose,
                             fingerprint_sha256=hashlib.sha256(key).hexdigest(), actor_id=args.actor_id)
        output = {"registered": True, "keyId": args.key_id, "purpose": args.key_purpose}
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
