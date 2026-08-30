import sys, sqlite3
sys.path.append('/app')
from economy.constants import ECONOMY_PHASE6_MIGRATION_VERSION
from economy.phase6_schema import PHASE6_SCHEMA_CHECKSUM, REQUIRED_PHASE6_TABLES, REQUIRED_PHASE6_INDEXES, REQUIRED_PHASE6_TRIGGERS, REQUIRED_PHASE6_COLUMNS

def debug_cap(connection):
    marker = connection.execute(
        "SELECT checksum,status FROM EconomySchemaMigration WHERE version=?",
        (ECONOMY_PHASE6_MIGRATION_VERSION,),
    ).fetchone()
    if not marker or marker != (PHASE6_SCHEMA_CHECKSUM, "COMPLETED"):
        print("Marker failed", marker, PHASE6_SCHEMA_CHECKSUM)
        return False
    objects = dict(connection.execute(
        "SELECT name,type FROM sqlite_master WHERE name LIKE 'Crypto%' OR name LIKE 'idx_crypto_%' OR name LIKE 'uq_crypto_%' OR name LIKE 'trg_crypto_%'"
    ).fetchall())
    
    structure_ready = True
    for name in REQUIRED_PHASE6_TABLES:
        if objects.get(name) != "table": print("Table fail:", name); structure_ready = False
    for name in REQUIRED_PHASE6_INDEXES:
        if objects.get(name) != "index": print("Index fail:", name); structure_ready = False
    for name in REQUIRED_PHASE6_TRIGGERS:
        if objects.get(name) != "trigger": print("Trigger fail:", name); structure_ready = False
        
    if not structure_ready:
        return False
        
    for table, required in REQUIRED_PHASE6_COLUMNS.items():
        row = connection.execute(f"PRAGMA table_info({table})").fetchall()
        cols = {r[1] for r in row}
        if not required.issubset(cols):
            print("Col fail:", table, required - cols)
            return False
            
    # Are there any other checks?
    # No other checks in the function text.
    return True

conn = sqlite3.connect('w2ebot.db')
print('Debug:', debug_cap(conn))
