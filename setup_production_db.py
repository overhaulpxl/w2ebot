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
            ECONOMY_MIGRATION_VERSION, ECONOMY_PHASE2_MIGRATION_VERSION,
            ECONOMY_PHASE3_MIGRATION_VERSION, ECONOMY_PHASE4_MIGRATION_VERSION,
            ECONOMY_PHASE5_MIGRATION_VERSION, ECONOMY_PHASE6_MIGRATION_VERSION,
            ECONOMY_PHASE7_MIGRATION_VERSION, ECONOMY_PHASE8_MIGRATION_VERSION,
            PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION, PHASE9B_DASHBOARD_MIGRATION_VERSION,
            CRYPTO_ASSETS, MINING_RIG_CATALOG
        )
        from economy.phase3_schema import PHASE3_SCHEMA_SQL, PHASE3_TRIGGER_SQL, PHASE3_HARDENING_VERSION, PHASE3_HARDENING_CHECKSUM
        from economy.phase4_schema import PHASE4_SCHEMA_SQL, PHASE4_TRIGGER_SQL, PHASE4_MIGRATION_CHECKSUM
        from economy.phase5_schema import PHASE5_TABLE_SQL, PHASE5_INDEX_SQL, PHASE5_TRIGGER_SQL, PHASE5_MIGRATION_NAME, PHASE5_SCHEMA_CHECKSUM
        from economy.phase6_schema import PHASE6_TABLE_SQL, PHASE6_INDEX_SQL, PHASE6_TRIGGER_SQL, PHASE6_MIGRATION_NAME, PHASE6_SCHEMA_CHECKSUM
        from economy.phase7_schema import PHASE7_TABLE_SQL, PHASE7_INDEX_SQL, PHASE7_TRIGGER_SQL, PHASE7_MIGRATION_NAME, PHASE7_SCHEMA_CHECKSUM
        from economy.phase8_schema import PHASE8_TABLE_SQL, PHASE8_INDEX_SQL, PHASE8_TRIGGER_SQL, PHASE8_MIGRATION_NAME, PHASE8_SCHEMA_CHECKSUM
        from economy.phase9a_schema import PHASE9A_TABLE_SQL, PHASE9A_INDEX_SQL, PHASE9A_TRIGGER_SQL, PHASE9A_MIGRATION_NAME, PHASE9A_SCHEMA_CHECKSUM
        from economy.phase9b_schema import PHASE9B_TABLE_SQL, PHASE9B_INDEX_SQL, PHASE9B_TRIGGER_SQL, PHASE9B_MIGRATION_NAME, PHASE9B_SCHEMA_CHECKSUM
    except ImportError as e:
        print(f"Import error: {e}")
        sys.exit(1)

    db = sqlite3.connect(DB_PATH)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    auto_checksum = 'auto-init'

    def mark(version, name, checksum):
        db.execute(
            "INSERT OR REPLACE INTO EconomySchemaMigration (version, name, checksum, status, completedAt) VALUES (?, ?, ?, 'COMPLETED', ?)",
            (version, name, checksum, now)
        )

    # Phase 1 & 2
    ensure_phase1_schema(db)
    mark(ECONOMY_MIGRATION_VERSION, 'economy_foundation_v1', auto_checksum)
    mark(ECONOMY_PHASE2_MIGRATION_VERSION, 'economy_core_phase2', auto_checksum)

    # Phase 3
    try: db.execute('DROP TABLE IF EXISTS RpgProfile')
    except Exception: pass
    db.executescript(PHASE3_SCHEMA_SQL)
    for t in PHASE3_TRIGGER_SQL: db.execute(t)
    mark(ECONOMY_PHASE3_MIGRATION_VERSION, 'phase3-rpg', auto_checksum)
    mark(PHASE3_HARDENING_VERSION, 'phase3-hardening', PHASE3_HARDENING_CHECKSUM)

    # Phase 4
    try: db.execute('DROP TABLE IF EXISTS RpgInventoryStack')
    except Exception: pass
    db.execute('''
    CREATE TABLE RpgInventoryStack (
        guildId TEXT NOT NULL, userId TEXT NOT NULL, itemId TEXT NOT NULL,
        catalogVersion TEXT NOT NULL, bindingStatus TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVIEW_REQUIRED')),
        quantity INTEGER NOT NULL CHECK(quantity>=0), version INTEGER NOT NULL DEFAULT 0,
        createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
        PRIMARY KEY (guildId, userId, itemId, catalogVersion, bindingStatus)
    )
    ''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_rpg_inventory_user ON RpgInventoryStack(guildId, userId)')
    db.execute('''
    CREATE TRIGGER IF NOT EXISTS trg_market_profile_no_escrow_equip
    BEFORE INSERT ON RpgEquipmentInstance
    FOR EACH ROW BEGIN
        SELECT RAISE(ABORT, 'Cannot equip an item that is locked in escrow.')
        WHERE EXISTS (
            SELECT 1 FROM MarketplaceEscrow
            WHERE guildId = NEW.guildId AND sellerId = NEW.userId AND itemId = NEW.itemId
            AND status = 'LOCKED' AND quantity > 0
        );
    END;
    ''')
    db.executescript(PHASE4_SCHEMA_SQL)
    for t in PHASE4_TRIGGER_SQL: db.execute(t)
    mark(ECONOMY_PHASE4_MIGRATION_VERSION, 'phase4-marketplace', PHASE4_MIGRATION_CHECKSUM)

    # Phase 5
    db.executescript(PHASE5_TABLE_SQL)
    for idx in PHASE5_INDEX_SQL: db.execute(idx)
    for t in PHASE5_TRIGGER_SQL: db.execute(t)
    mark(ECONOMY_PHASE5_MIGRATION_VERSION, PHASE5_MIGRATION_NAME, PHASE5_SCHEMA_CHECKSUM)

    # Phase 6
    db.executescript(PHASE6_TABLE_SQL)
    for idx in PHASE6_INDEX_SQL: db.execute(idx)
    for t in PHASE6_TRIGGER_SQL: db.execute(t)
    mark(ECONOMY_PHASE6_MIGRATION_VERSION, PHASE6_MIGRATION_NAME, PHASE6_SCHEMA_CHECKSUM)
    
    import uuid
    initial_tick = "phase6-initial"
    if not db.execute("SELECT 1 FROM CryptoAssetDefinition LIMIT 1").fetchone():
        db.execute("INSERT INTO CryptoMarketTick (tickId,scheduledAt,outcomeJson,status,resultJson,createdAt,committedAt) VALUES (?,?,?,'COMMITTED',?,?,?)",
            (initial_tick, now, '{"type":"INITIAL"}', '{"initialized":true}', now, now))
        for symbol, (name, price, maximum_bps, level) in CRYPTO_ASSETS.items():
            db.execute("INSERT INTO CryptoAssetDefinition (symbol,name,basePriceEcy,minimumPriceEcy,maximumPriceEcy,maximumNormalChangeBps,volatilityLevel,catalogVersion,createdAt) VALUES (?,?,?,?,?,?,?,'crypto-v1.0.0',?)",
                (symbol, name, price, price * 20 // 100, price * 500 // 100, maximum_bps, level, now))
            db.execute("INSERT INTO CryptoMarketState (symbol,currentPriceEcy,lastTickId,version,updatedAt) VALUES (?,?,?,0,?)", (symbol, price, initial_tick, now))
            db.execute("INSERT INTO CryptoPriceHistory (historyId,tickId,symbol,previousPriceEcy,currentPriceEcy,movementBps,movementType,occurredAt) VALUES (?,?,?,?,?,0,'INITIAL',?)",
                (str(uuid.uuid4()), initial_tick, symbol, price, price, now))

    # Phase 7
    db.executescript(PHASE7_TABLE_SQL)
    for idx in PHASE7_INDEX_SQL: db.execute(idx)
    for t in PHASE7_TRIGGER_SQL: db.execute(t)
    mark(ECONOMY_PHASE7_MIGRATION_VERSION, PHASE7_MIGRATION_NAME, PHASE7_SCHEMA_CHECKSUM)
    if not db.execute("SELECT 1 FROM MiningRigCatalog LIMIT 1").fetchone():
        for tier, details in MINING_RIG_CATALOG.items():
            db.execute("INSERT INTO MiningRigCatalog (rigDefinitionId,name,purchasePriceEcy,grossEquivalentPerDay,maintenancePriceEcy,catalogVersion,createdAt) VALUES (?,?,?,?,?,?,?)",
                (tier, details[0], details[1], details[2], details[3], 'mining-v1.0.0', now))

    # Phase 8
    db.executescript(PHASE8_TABLE_SQL)
    for idx in PHASE8_INDEX_SQL: db.execute(idx)
    for t in PHASE8_TRIGGER_SQL: db.execute(t)
    mark(ECONOMY_PHASE8_MIGRATION_VERSION, PHASE8_MIGRATION_NAME, PHASE8_SCHEMA_CHECKSUM)

    # Phase 9A & 9B
    db.executescript(PHASE9A_TABLE_SQL)
    for idx in PHASE9A_INDEX_SQL: db.execute(idx)
    for t in PHASE9A_TRIGGER_SQL: db.execute(t)
    mark(PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION, PHASE9A_MIGRATION_NAME, PHASE9A_SCHEMA_CHECKSUM)

    db.executescript(PHASE9B_TABLE_SQL)
    for idx in PHASE9B_INDEX_SQL: db.execute(idx)
    for t in PHASE9B_TRIGGER_SQL: db.execute(t)
    mark(PHASE9B_DASHBOARD_MIGRATION_VERSION, PHASE9B_MIGRATION_NAME, PHASE9B_SCHEMA_CHECKSUM)

    # Keys
    keys = [
        ('phase9a-internal-v1', 'INTERNAL_REQUEST', b'w2e_internal_super_secret_9988776655'),
        ('phase9a-session-v1', 'SESSION_HASH', b'w2e_session_ultra_secure_hash_112233'),
        ('phase9a-ip-v1', 'IP_HASH', b'w2e_ip_hash_random_string_445566')
    ]
    for k, p, s in keys:
        fp = hashlib.sha256(s).hexdigest()
        db.execute("INSERT OR IGNORE INTO DashboardSigningKeyVersion (keyId, purpose, fingerprintSha256, createdById, status, activatedAt) VALUES (?, ?, ?, 'SYSTEM', 'ACTIVE', ?)", (k, p, fp, now))

    db.commit()
    db.close()
    print(f"\nAll economy schemas initialized successfully in {DB_PATH}!")

if __name__ == '__main__':
    main()
