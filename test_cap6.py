import sys, sqlite3
sys.path.append('/app')
from economy.constants import ECONOMY_PHASE6_MIGRATION_VERSION
from economy.phase6_schema import PHASE6_SCHEMA_CHECKSUM, REQUIRED_PHASE6_TABLES, REQUIRED_PHASE6_INDEXES, REQUIRED_PHASE6_TRIGGERS, REQUIRED_PHASE6_COLUMNS

conn = sqlite3.connect('w2ebot.db')
marker = conn.execute('SELECT checksum,status FROM EconomySchemaMigration WHERE version=?', (ECONOMY_PHASE6_MIGRATION_VERSION,)).fetchone()
print('Marker:', marker)
print('Expected Checksum:', PHASE6_SCHEMA_CHECKSUM)

objects = dict(conn.execute("SELECT name,type FROM sqlite_master WHERE name LIKE 'Crypto%' OR name LIKE 'idx_crypto_%' OR name LIKE 'uq_crypto_%' OR name LIKE 'trg_crypto_%'").fetchall())
for name in REQUIRED_PHASE6_TABLES:
    if objects.get(name) != 'table': print('Missing table:', name)
for name in REQUIRED_PHASE6_INDEXES:
    if objects.get(name) != 'index': print('Missing index:', name)
for name in REQUIRED_PHASE6_TRIGGERS:
    if objects.get(name) != 'trigger': print('Missing trigger:', name)

for table, required in REQUIRED_PHASE6_COLUMNS.items():
    row = conn.execute(f'PRAGMA table_info({table})').fetchall()
    cols = {r[1] for r in row}
    missing = required - cols
    if missing:
        print('Missing columns in', table, ':', missing)
