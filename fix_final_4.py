import sqlite3
def fix_4():
    conn = sqlite3.connect('w2ebot.db')
    try:
        conn.execute('DROP TABLE IF EXISTS RpgInventoryStack')
    except Exception:
        pass
        
    from economy.phase4_schema import PHASE4_SCHEMA_SQL
    conn.executescript(PHASE4_SCHEMA_SQL)
    conn.commit()
    print("Phase 4 RpgInventoryStack fixed.")
if __name__ == '__main__': fix_4()
