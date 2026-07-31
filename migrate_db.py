import os
import sqlite3
from runtime_config import DATABASE_PATH_STRING
import json
import glob

def migrate():
    conn = sqlite3.connect(DATABASE_PATH_STRING)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS json_store (filename TEXT PRIMARY KEY, content TEXT)")
    
    json_files = glob.glob('*.json')
    migrated = 0
    for file in json_files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            c.execute("INSERT OR REPLACE INTO json_store (filename, content) VALUES (?, ?)", (file, json.dumps(data, ensure_ascii=False)))
            migrated += 1
            print(f"Migrated {file}")
        except Exception as e:
            print(f"Failed to migrate {file}: {e}")
            
    conn.commit()
    conn.close()
    print(f"Successfully migrated {migrated} files to SQLite.")

if __name__ == "__main__":
    migrate()
