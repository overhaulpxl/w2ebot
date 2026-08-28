#!/usr/bin/env python3
"""
One-shot production database initializer.
Creates ALL economy schemas (Phase 1-9B) on a fresh database.
Idempotent — safe to run multiple times.
"""
import sqlite3
import hashlib
import datetime
import os
import sys

DB_PATH = os.getenv('BOT_DB_PATH', 'w2ebot.db')


def main():
    try:
        from economy.database import ensure_phase1_schema
        from economy.constants import (
            ECONOMY_MIGRATION_VERSION,
            ECONOMY_PHASE2_MIGRATION_VERSION,
            ECONOMY_PHASE3_MIGRATION_VERSION,
            ECONOMY_PHASE4_MIGRATION_VERSION,
            ECONOMY_PHASE5_MIGRATION_VERSION,
            ECONOMY_PHASE6_MIGRATION_VERSION,
            ECONOMY_PHASE7_MIGRATION_VERSION,
            ECONOMY_PHASE8_MIGRATION_VERSION,
            PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION,
            PHASE9B_DASHBOARD_MIGRATION_VERSION,
        )
        from economy.phase3_schema import (
            PHASE3_SCHEMA_SQL,
            PHASE3_TRIGGER_SQL,
            PHASE3_HARDENING_VERSION,
            PHASE3_HARDENING_CHECKSUM,
        )
        from economy.phase4_schema import (
            PHASE4_SCHEMA_SQL,
            PHASE4_TRIGGER_SQL,
            PHASE4_MIGRATION_CHECKSUM,
        )
        from economy.phase5_schema import (
            PHASE5_TABLE_SQL,
            PHASE5_INDEX_SQL,
            PHASE5_TRIGGER_SQL,
            PHASE5_MIGRATION_NAME,
            PHASE5_SCHEMA_CHECKSUM,
        )
        from economy.phase6_schema import (
            PHASE6_TABLE_SQL,
            PHASE6_INDEX_SQL,
            PHASE6_TRIGGER_SQL,
            PHASE6_MIGRATION_NAME,
            PHASE6_SCHEMA_CHECKSUM,
        )
        from economy.phase7_schema import (
            PHASE7_TABLE_SQL,
            PHASE7_INDEX_SQL,
            PHASE7_TRIGGER_SQL,
            PHASE7_MIGRATION_NAME,
            PHASE7_SCHEMA_CHECKSUM,
        )
        from economy.phase8_schema import (
            PHASE8_TABLE_SQL,
            PHASE8_INDEX_SQL,
            PHASE8_TRIGGER_SQL,
            PHASE8_MIGRATION_NAME,
            PHASE8_SCHEMA_CHECKSUM,
        )
        from economy.phase9a_schema import (
            PHASE9A_TABLE_SQL,
            PHASE9A_INDEX_SQL,
            PHASE9A_TRIGGER_SQL,
            PHASE9A_MIGRATION_NAME,
            PHASE9A_SCHEMA_CHECKSUM,
        )
        from economy.phase9b_schema import (
            PHASE9B_TABLE_SQL,
            PHASE9B_INDEX_SQL,
            PHASE9B_TRIGGER_SQL,
            PHASE9B_MIGRATION_NAME,
            PHASE9B_SCHEMA_CHECKSUM,
        )
    except ImportError as e:
        print(f"Import error: {e}")
        print("Run this script from the w2ebot directory or inside the container.")
        sys.exit(1)

    db = sqlite3.connect(DB_PATH)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    auto_checksum = 'auto-init'

    def mark(version, name, checksum):
        db.execute(
            "INSERT OR REPLACE INTO EconomySchemaMigration "
            "(version, name, checksum, status, completedAt) "
            "VALUES (?, ?, ?, 'COMPLETED', ?)",
            (version, name, checksum, now)
        )

    # === Phase 1: Foundation ===
    print("[Phase 1] Creating foundation tables...")
    ensure_phase1_schema(db)
    mark(ECONOMY_MIGRATION_VERSION, 'economy_foundation_v1', auto_checksum)

    # === Phase 2: Core data (tables already exist from Phase 1) ===
    print("[Phase 2] Marking core data migration...")
    mark(ECONOMY_PHASE2_MIGRATION_VERSION, 'economy_core_phase2', auto_checksum)

    # === Phase 3: RPG ===
    print("[Phase 3] Creating RPG tables...")
    db.executescript(PHASE3_SCHEMA_SQL)
    for t in PHASE3_TRIGGER_SQL:
        db.execute(t)
    mark(ECONOMY_PHASE3_MIGRATION_VERSION, 'phase3-rpg', auto_checksum)
    mark(PHASE3_HARDENING_VERSION, 'phase3-hardening', PHASE3_HARDENING_CHECKSUM)

    # === Phase 4: Marketplace ===
    print("[Phase 4] Creating marketplace tables...")
    db.executescript(PHASE4_SCHEMA_SQL)
    for t in PHASE4_TRIGGER_SQL:
        db.execute(t)
    mark(ECONOMY_PHASE4_MIGRATION_VERSION, 'phase4-marketplace', PHASE4_MIGRATION_CHECKSUM)

    # === Phase 5: Casino ===
    print("[Phase 5] Creating casino tables...")
    db.executescript(PHASE5_TABLE_SQL)
    for idx in PHASE5_INDEX_SQL:
        db.execute(idx)
    for t in PHASE5_TRIGGER_SQL:
        db.execute(t)
    mark(ECONOMY_PHASE5_MIGRATION_VERSION, PHASE5_MIGRATION_NAME, PHASE5_SCHEMA_CHECKSUM)

    # === Phase 6: Crypto ===
    print("[Phase 6] Creating crypto tables...")
    db.executescript(PHASE6_TABLE_SQL)
    for idx in PHASE6_INDEX_SQL:
        db.execute(idx)
    for t in PHASE6_TRIGGER_SQL:
        db.execute(t)
    mark(ECONOMY_PHASE6_MIGRATION_VERSION, PHASE6_MIGRATION_NAME, PHASE6_SCHEMA_CHECKSUM)

    # === Phase 7: Mining ===
    print("[Phase 7] Creating mining tables...")
    db.executescript(PHASE7_TABLE_SQL)
    for idx in PHASE7_INDEX_SQL:
        db.execute(idx)
    for t in PHASE7_TRIGGER_SQL:
        db.execute(t)
    mark(ECONOMY_PHASE7_MIGRATION_VERSION, PHASE7_MIGRATION_NAME, PHASE7_SCHEMA_CHECKSUM)

    # === Phase 8: Giveaway & Options ===
    print("[Phase 8] Creating giveaway/options tables...")
    db.executescript(PHASE8_TABLE_SQL)
    for idx in PHASE8_INDEX_SQL:
        db.execute(idx)
    for t in PHASE8_TRIGGER_SQL:
        db.execute(t)
    mark(ECONOMY_PHASE8_MIGRATION_VERSION, PHASE8_MIGRATION_NAME, PHASE8_SCHEMA_CHECKSUM)

    # === Phase 9A: Dashboard backend safety ===
    print("[Phase 9A] Creating dashboard schema...")
    db.executescript(PHASE9A_TABLE_SQL)
    for idx in PHASE9A_INDEX_SQL:
        db.execute(idx)
    for t in PHASE9A_TRIGGER_SQL:
        db.execute(t)
    mark(PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION, PHASE9A_MIGRATION_NAME, PHASE9A_SCHEMA_CHECKSUM)

    # === Phase 9B: Dashboard triggers ===
    print("[Phase 9B] Creating dashboard triggers...")
    db.executescript(PHASE9B_TABLE_SQL)
    for idx in PHASE9B_INDEX_SQL:
        db.execute(idx)
    for t in PHASE9B_TRIGGER_SQL:
        db.execute(t)
    mark(PHASE9B_DASHBOARD_MIGRATION_VERSION, PHASE9B_MIGRATION_NAME, PHASE9B_SCHEMA_CHECKSUM)

    # === Signing Keys ===
    print("[Keys] Registering signing keys...")
    keys = [
        ('phase9a-internal-v1', 'INTERNAL_REQUEST', b'w2e_internal_super_secret_9988776655'),
        ('phase9a-session-v1', 'SESSION_HASH', b'w2e_session_ultra_secure_hash_112233'),
        ('phase9a-ip-v1', 'IP_HASH', b'w2e_ip_hash_random_string_445566')
    ]
    for k, p, s in keys:
        fp = hashlib.sha256(s).hexdigest()
        db.execute(
            "INSERT OR IGNORE INTO DashboardSigningKeyVersion "
            "(keyId, purpose, fingerprintSha256, createdById, status, activatedAt) "
            "VALUES (?, ?, ?, 'SYSTEM', 'ACTIVE', ?)",
            (k, p, fp, now)
        )

    db.commit()
    db.close()
    print(f"\nAll economy schemas initialized successfully in {DB_PATH}!")


if __name__ == '__main__':
    main()
