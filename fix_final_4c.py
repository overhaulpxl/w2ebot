import sqlite3
def fix_4_final_again():
    conn = sqlite3.connect('w2ebot.db')
    try:
        conn.execute('DROP TABLE IF EXISTS RpgInventoryStack')
    except Exception:
        pass
    
    conn.execute('''
    CREATE TABLE RpgInventoryStack (
        guildId TEXT NOT NULL, userId TEXT NOT NULL, itemId TEXT NOT NULL,
        catalogVersion TEXT NOT NULL, bindingStatus TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVIEW_REQUIRED')),
        quantity INTEGER NOT NULL CHECK(quantity>=0), version INTEGER NOT NULL DEFAULT 0,
        createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
        PRIMARY KEY (guildId, userId, itemId, catalogVersion, bindingStatus)
    )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_rpg_inventory_user ON RpgInventoryStack(guildId, userId)')
    conn.commit()
if __name__ == '__main__': fix_4_final_again()
