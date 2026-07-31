"""Backup-first setup for a dedicated Phase 9A staging database."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.phase9a_migrations import (  # noqa: E402
    apply_phase9a_staging, bootstrap_admin, reconcile_phase9a_staging, register_signing_key,
)
from runtime_config import PRODUCTION_DATABASE_PATH  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--backup", required=True)
    parser.add_argument("--guild-id", required=True)
    parser.add_argument("--admin-user-id", required=True)
    parser.add_argument("--internal-key-file", required=True)
    parser.add_argument("--session-key-file", required=True)
    parser.add_argument("--ip-key-file", required=True)
    args = parser.parse_args(argv)
    target = Path(args.database).resolve()
    result = apply_phase9a_staging(target, production_db=PRODUCTION_DATABASE_PATH, backup_path=args.backup)
    for key_id, purpose, path in (
        ("phase9a-internal-v1", "INTERNAL_REQUEST", args.internal_key_file),
        ("phase9a-session-v1", "SESSION_HASH", args.session_key_file),
        ("phase9a-ip-v1", "IP_HASH", args.ip_key_file),
    ):
        secret = Path(path).read_bytes()
        if len(secret) < 32:
            raise RuntimeError(f"Key {purpose} minimal 32 byte.")
        register_signing_key(target, key_id=key_id, purpose=purpose,
                             fingerprint_sha256=hashlib.sha256(secret).hexdigest(), actor_id="STAGING_SETUP")
    bootstrap = bootstrap_admin(target, guild_id=args.guild_id, user_id=args.admin_user_id)
    reconciliation = reconcile_phase9a_staging(target)
    if not reconciliation["reconciled"]:
        raise RuntimeError("Rekonsiliasi Phase 9A gagal.")
    print(json.dumps({"migration": result, "bootstrap": bootstrap, "reconciliation": reconciliation},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
