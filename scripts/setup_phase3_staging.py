"""Buat dan verifikasi database staging Phase 3 tanpa menyentuh production."""

import argparse
import asyncio
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.catalog import catalog_hash
from economy.database import initialize_database
from economy.phase3_migrations import apply_phase3_staging
from economy.phase3_schema import PHASE3_HARDENING_CHECKSUM, PHASE3_HARDENING_VERSION
from economy.staging import logical_sqlite_manifest


PRODUCTION_DATABASE = (ROOT / "w2ebot.db").resolve()
STAGING_DIRECTORY = ROOT / "staging"
STAGING_DATABASE = (STAGING_DIRECTORY / "w2ebot-staging.db").resolve()
STAGING_ENV = ROOT / ".env.staging"
EXPECTED_CATALOG_ITEMS = 49
EXPECTED_CATALOG_DEFINITIONS = 96


def _assert_staging_database(path):
    path = Path(path).expanduser().resolve()
    if path == PRODUCTION_DATABASE:
        raise RuntimeError("Refusing staging setup against the production database.")
    if PRODUCTION_DATABASE in path.parents:
        raise RuntimeError("Staging database must not be inside the production database path.")
    return path


def staging_paths(root=ROOT):
    root = Path(root).resolve()
    staging_directory = root / "staging"
    return (
        root,
        (root / "w2ebot.db").resolve(),
        (staging_directory / "w2ebot-staging.db").resolve(),
        root / ".env.staging",
    )


def _write_env_if_absent(path, database):
    if path.exists():
        return False
    path.write_text(
        "STAGING_MODE=true\n"
        "STAGING_GUILD_ID=REPLACE_WITH_DEDICATED_STAGING_GUILD_ID\n"
        f"DATABASE_PATH={database}\n"
        "ECONOMY_V1_ENABLED=true\n"
        "ECONOMY_PHASE2_ENABLED=true\n"
        "ECONOMY_PHASE3_ENABLED=true\n"
        "DISCORD_TOKEN=REPLACE_WITH_DEDICATED_STAGING_BOT_TOKEN\n",
        encoding="utf-8",
        newline="\n",
    )
    return True


def _database_checks(path):
    connection = sqlite3.connect(path)
    try:
        catalog_row = connection.execute(
            "SELECT catalogVersion,catalogHash FROM RpgCatalogManifest ORDER BY catalogVersion DESC LIMIT 1"
        ).fetchone()
        migration_row = connection.execute(
            "SELECT version,checksum,status FROM EconomySchemaMigration "
            "WHERE version=?", (PHASE3_HARDENING_VERSION,),
        ).fetchone()
        item_count = connection.execute("SELECT COUNT(*) FROM RpgCatalogItem").fetchone()[0]
        definition_count = connection.execute("SELECT COUNT(*) FROM RpgCatalogDefinition").fetchone()[0]
        blocking_reviews = connection.execute(
            "SELECT COUNT(*) FROM RpgPhase3MigrationReview"
        ).fetchone()[0] + connection.execute(
            "SELECT COUNT(*) FROM RpgRecoveryReview WHERE status='OPEN'"
        ).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        connection.close()
    if not migration_row or migration_row[1] != PHASE3_HARDENING_CHECKSUM or migration_row[2] != "COMPLETED":
        raise RuntimeError("Phase 3 hardening migration checksum/status is invalid.")
    if not catalog_row or catalog_row[1] != catalog_hash():
        raise RuntimeError("Staging catalog checksum is invalid.")
    if (item_count, definition_count) != (EXPECTED_CATALOG_ITEMS, EXPECTED_CATALOG_DEFINITIONS):
        raise RuntimeError("Staging catalog row totals are invalid.")
    if integrity != "ok" or foreign_keys:
        raise RuntimeError("Staging SQLite integrity verification failed.")
    return {
        "migration": {"version": migration_row[0], "checksum": migration_row[1], "status": migration_row[2]},
        "catalog": {"version": catalog_row[0], "checksum": catalog_row[1],
                     "items": item_count, "definitions": definition_count},
        "blocking_review_rows": blocking_reviews,
        "integrity_check": integrity,
        "foreign_key_errors": foreign_keys,
    }


async def prepare_staging(root=ROOT, *, reset=False, confirm_reset=False, verify_only=False):
    root, production, database, env_path = staging_paths(root)
    database = _assert_staging_database(database)
    if reset:
        if not confirm_reset:
            raise RuntimeError("--reset requires --confirm-reset-staging.")
        if database.exists():
            database.unlink()
    if verify_only and not database.exists():
        raise FileNotFoundError(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    if verify_only:
        checks = _database_checks(database)
        return {
            "database_path": str(database),
            "database_size": database.stat().st_size,
            "verify_only": True,
            "checks": checks,
            "env_staging_path": str(env_path),
            "env_staging_present": env_path.exists(),
        }
    if not database.exists():
        await initialize_database(database)
    before = logical_sqlite_manifest(database)
    first = await apply_phase3_staging(database, production_db=production, seed=True)
    first_manifest = logical_sqlite_manifest(database)
    second = await apply_phase3_staging(database, production_db=production, seed=True)
    second_manifest = logical_sqlite_manifest(database)
    checks = _database_checks(database)
    if first_manifest["row_counts"] != second_manifest["row_counts"]:
        raise RuntimeError("Second Phase 3 migration changed row counts.")
    if first_manifest["table_checksums"] != second_manifest["table_checksums"]:
        raise RuntimeError("Second Phase 3 migration changed deterministic data checksums.")
    env_created = _write_env_if_absent(env_path, database)
    return {
        "database_path": str(database),
        "database_size": database.stat().st_size,
        "database_logical_before": {"objects": before["object_count"], "tables": len(before["row_counts"])},
        "first_migration": {"version": first["migration_version"], "catalog_hash": first["catalog_hash"]},
        "second_migration_idempotent": True,
        "checks": checks,
        "env_staging_path": str(env_path),
        "env_staging_created": env_created,
        "next_steps": [
            "Edit only .env.staging: STAGING_GUILD_ID and DISCORD_TOKEN.",
            "Run powershell -ExecutionPolicy Bypass -File scripts/run_phase3_staging.ps1",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare local W2E Phase 3 staging")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--confirm-reset-staging", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.confirm_reset_staging and not args.reset:
        parser.error("--confirm-reset-staging hanya valid bersama --reset")
    result = asyncio.run(prepare_staging(
        reset=args.reset, confirm_reset=args.confirm_reset_staging, verify_only=args.verify,
    ))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
