import sqlite3
def debug_4():
    conn = sqlite3.connect('w2ebot.db')
    from economy.phase4_schema import REQUIRED_TABLES, REQUIRED_INDEXES, REQUIRED_TRIGGERS, STACK_MIGRATION_ALGORITHM
    objects = dict(conn.execute("SELECT name,type FROM sqlite_master").fetchall())
    print("Tables:", [t for t in REQUIRED_TABLES if objects.get(t) != 'table'])
    print("Indexes:", [i for i in REQUIRED_INDEXES if objects.get(i) != 'index'])
    print("Triggers:", [t for t in REQUIRED_TRIGGERS if objects.get(t) != 'trigger'])
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='RpgInventoryStack'").fetchone()
    print("Stack OK?", "catalogVersion" in row[0] if row else False)
if __name__ == '__main__': debug_4()
