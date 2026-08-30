import sqlite3
def fix_3():
    conn = sqlite3.connect('w2ebot.db')
    try:
        conn.execute('DROP TABLE IF EXISTS RpgProfile')
    except Exception:
        pass
    
    conn.execute('''
    CREATE TABLE IF NOT EXISTS RpgProfile (
        guildId TEXT NOT NULL,
        userId TEXT NOT NULL,
        level INTEGER NOT NULL DEFAULT 1 CHECK(level BETWEEN 1 AND 100),
        currentHp INTEGER NOT NULL DEFAULT 100 CHECK(currentHp >= 0),
        maxHp INTEGER NOT NULL DEFAULT 100,
        starterPackClaimed INTEGER NOT NULL DEFAULT 0,
        starterPackClaimedAt TEXT,
        PRIMARY KEY (guildId, userId)
    )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_rpg_profile_level ON RpgProfile(level)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_rpg_profile_user ON RpgProfile(userId)')
    conn.commit()
    print("Phase 3 RpgProfile fixed.")
if __name__ == '__main__': fix_3()
