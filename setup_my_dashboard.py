import sqlite3
import hashlib
import time
import os
import sys

def main():
    try:
        from economy.phase9a_schema import PHASE9A_TABLE_SQL, PHASE9A_INDEX_SQL, PHASE9A_TRIGGER_SQL
        from economy.phase9b_schema import PHASE9B_TABLE_SQL, PHASE9B_INDEX_SQL
    except ImportError:
        print("Please run this script inside the w2ebot directory or container.")
        sys.exit(1)

    db_path = 'w2ebot.db'
    db = sqlite3.connect(db_path)
    
    # Enable WAL mode and foreign keys just in case
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    
    # Apply Schema
    db.executescript(PHASE9A_TABLE_SQL)
    for q in PHASE9A_INDEX_SQL: db.execute(q)
    for q in PHASE9A_TRIGGER_SQL: db.execute(q)
    db.executescript(PHASE9B_TABLE_SQL)
    for q in PHASE9B_INDEX_SQL: db.execute(q)

    import datetime
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    from economy.constants import PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION, PHASE9B_DASHBOARD_MIGRATION_VERSION
    from economy.phase9a_schema import PHASE9A_MIGRATION_NAME, PHASE9A_SCHEMA_CHECKSUM
    from economy.phase9b_schema import PHASE9B_MIGRATION_NAME, PHASE9B_SCHEMA_CHECKSUM
    
    db.execute("INSERT OR REPLACE INTO EconomySchemaMigration (version, name, checksum, status, appliedAt) VALUES (?, ?, ?, 'COMPLETED', ?)", 
               (PHASE9A_BACKEND_SAFETY_MIGRATION_VERSION, PHASE9A_MIGRATION_NAME, PHASE9A_SCHEMA_CHECKSUM, now_str))
    db.execute("INSERT OR REPLACE INTO EconomySchemaMigration (version, name, checksum, status, appliedAt) VALUES (?, ?, ?, 'COMPLETED', ?)", 
               (PHASE9B_DASHBOARD_MIGRATION_VERSION, PHASE9B_MIGRATION_NAME, PHASE9B_SCHEMA_CHECKSUM, now_str))

    keys = [
        ('phase9a-internal-v1', 'INTERNAL_REQUEST', b'w2e_internal_super_secret_9988776655'),
        ('phase9a-session-v1', 'SESSION_HASH', b'w2e_session_ultra_secure_hash_112233'),
        ('phase9a-ip-v1', 'IP_HASH', b'w2e_ip_hash_random_string_445566')
    ]
    
    for k, p, s in keys:
        fp = hashlib.sha256(s).hexdigest()
        db.execute(
            "INSERT OR IGNORE INTO DashboardSigningKeyVersion (keyId, purpose, fingerprintSha256, createdById, status, activatedAt) VALUES (?, ?, ?, 'SYSTEM', 'ACTIVE', ?)",
            (k, p, fp, now_str)
        )

    db.commit()
    db.close()
    print("Dashboard schema and keys initialized successfully!")

if __name__ == '__main__':
    main()
