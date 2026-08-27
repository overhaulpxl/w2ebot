import os
import re

def safe_replace(filepath):
    print(f"Refactoring basics in {filepath}...")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Hapus import aiosqlite, ganti dengan import_pool
    content = re.sub(r"import\s+aiosqlite\n", "", content)
    
    # DB_PATH hapus, pastikan ada import _pool dari core
    content = re.sub(r"from\s+core\s+import[\s\\]*(.*?)DB_PATH,?", r"from core import _pool, \1", content)
    
    # 1. Ganti context manager aiosqlite dengan asyncpg pool
    content = content.replace("async with aiosqlite.connect(DB_PATH) as db:", "async with _pool.acquire() as db:")
    content = content.replace("async with aiosqlite.connect(db_path) as db:", "async with _pool.acquire() as db:")
    
    # 2. Hapus PRAGMA yang tidak jalan di asyncpg
    content = content.replace("await db.execute('PRAGMA foreign_keys=ON')", "")
    content = content.replace('await db.execute("PRAGMA foreign_keys=ON")', "")
    content = content.replace("await db.execute('PRAGMA busy_timeout=5000')", "")
    
    # 3. Ganti BEGIN IMMEDIATE -> async with db.transaction():
    # Ini bahaya karena butuh indentasi, untuk sekarang saya ubah ke BEGIN dan manual commit agar indentasinya tetap sama
    content = content.replace("await db.execute('BEGIN IMMEDIATE')", "await db.execute('BEGIN')")
    content = content.replace('await db.execute("BEGIN IMMEDIATE")', "await db.execute('BEGIN')")
    
    # 4. Hapus manual db.commit() karena kita akan bergantung ke auto-commit asyncpg untuk non-transaction
    # Atau kita biarkan `await db.execute('COMMIT')` jika sebelumnya ada BEGIN IMMEDIATE
    content = content.replace("await db.commit()", "await db.execute('COMMIT')")
    content = content.replace("await db.rollback()", "await db.execute('ROLLBACK')")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

# File yang perlu pondasi awal
files = ["core.py", "economy/database.py", "economy/ledger.py", "economy/profile.py", "economy/wallets.py", "economy/treasury.py"]
for f in files:
    safe_replace(f)
