import re
import glob
import os

def convert_query(match):
    """Mengonversi sqlite placeholder (?) ke postgres ($1, $2, dll)"""
    query = match.group(1)
    
    # Hitung jumlah ?
    count = query.count("?")
    
    # Ganti ? secara berurutan dengan $1, $2, dst
    # Karena kita pakai regex, kita replace manual
    parts = query.split("?")
    new_query = parts[0]
    for i in range(1, len(parts)):
        new_query += f"${i}" + parts[i]
        
    return '"{}"'.format(new_query) if match.group(0).startswith('"') else "'{}'".format(new_query)

def convert_multiline_query(match):
    """Mengonversi multiline docstring query"""
    query = match.group(1)
    parts = query.split("?")
    new_query = parts[0]
    for i in range(1, len(parts)):
        new_query += f"${i}" + parts[i]
        
    if match.group(0).startswith('"""'):
        return '"""{}"""'.format(new_query)
    else:
        return "'''{}'''".format(new_query)

def process_file(filepath):
    print(f"Translating SQLite to Postgres in {filepath}...")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Ganti "async with db.execute(" SELECT ... ")" -> menggunakan asyncpg
    # PENTING: Untuk asyncpg, kita tidak bisa pakai context manager 'async with db.execute() as cursor:'
    # Di asyncpg: 
    # rows = await db.fetch(query, args)
    # row = await db.fetchrow(query, args)
    # status = await db.execute(query, args)
    
    # Pola 1: async with db.execute(query, args) as cursor: \n row = await cursor.fetchone()
    # Menjadi: row = await db.fetchrow(query, args)
    content = re.sub(
        r"async with db\.execute\((.*?)\)\s*as\s+(\w+):\s*\n\s*(\w+)\s*=\s*await\s+\2\.fetchone\(\)",
        r"\3 = await db.fetchrow(\1)",
        content,
        flags=re.DOTALL
    )
    
    # Pola 2: async with db.execute(query, args) as cursor: \n rows = await cursor.fetchall()
    # Menjadi: rows = await db.fetch(query, args)
    content = re.sub(
        r"async with db\.execute\((.*?)\)\s*as\s+(\w+):\s*\n\s*(\w+)\s*=\s*await\s+\2\.fetchall\(\)",
        r"\3 = await db.fetch(\1)",
        content,
        flags=re.DOTALL
    )
    
    # Pola 3: await db.commit() -> hapus atau ganti komentar
    content = re.sub(r"await db\.commit\(\)", "# await db.commit() (managed by asyncpg/pool)", content)
    
    # Pola 4: await db.rollback() -> hapus atau ganti komentar (asyncpg otomatis rollback jika error)
    content = re.sub(r"await db\.rollback\(\)", "# await db.rollback()", content)
    
    # Pola 5: await db.execute("BEGIN IMMEDIATE") -> async with db.transaction():
    # Ini sangat rumit di regex. Biarkan manual jika ketemu. Untuk sekarang hapus saja pragma
    content = re.sub(r"await db\.execute\(['\"]PRAGMA foreign_keys=ON['\"]\)", "", content)
    content = re.sub(r"await db\.execute\(['\"]PRAGMA busy_timeout=5000['\"]\)", "", content)

    # Transform placeholders ? -> $1, $2
    # Kita cari string literal yang punya karakter '?' dan 'SELECT|INSERT|UPDATE|DELETE|WITH' di dalamnya
    def replace_placeholders(m):
        full_str = m.group(0)
        # Jangan replace kalau gak ada sql keyword
        if not re.search(r"\b(SELECT|INSERT|UPDATE|DELETE|WITH|ON CONFLICT|INTO|FROM)\b", full_str, re.IGNORECASE):
            return full_str
            
        parts = full_str.split("?")
        res = parts[0]
        for i in range(1, len(parts)):
            res += f"${i}" + parts[i]
        return res
        
    content = re.sub(r"\"[^\"]*?\?[^\"]*?\"", replace_placeholders, content)
    content = re.sub(r"'[^']*?\?[^']*?'", replace_placeholders, content)
    content = re.sub(r"\"\"\"(?:.|\n)*?\?(?:.|\n)*?\"\"\"", replace_placeholders, content)
    content = re.sub(r"'''(?:.|\n)*?\?(?:.|\n)*?'''", replace_placeholders, content)
    
    # Tuple parameter single item di python `(param,)` sering bermasalah saat diganti asyncpg
    # Di aiosqlite: execute(query, (a, b))
    # Di asyncpg: execute(query, a, b)
    # Ini adalah refactor paling berbahaya karena Python membedakan execute(query, args) dengan execute(query, *args)
    # Kita gunakan fungsi * unpack untuk amannya: db.execute(query, *args)
    content = re.sub(r"db\.execute\((.*?),\s*\((.*?)\)\s*\)", r"db.execute(\1, \2)", content)
    content = re.sub(r"db\.fetchrow\((.*?),\s*\((.*?)\)\s*\)", r"db.fetchrow(\1, \2)", content)
    content = re.sub(r"db\.fetch\((.*?),\s*\((.*?)\)\s*\)", r"db.fetch(\1, \2)", content)
    
    # Hapus trailing koma dari unpack tuple, e.g. execute(query, a,) -> execute(query, a)
    content = re.sub(r"db\.execute\((.*?),\s*([^,]+),\s*\)", r"db.execute(\1, \2)", content)
    content = re.sub(r"db\.fetchrow\((.*?),\s*([^,]+),\s*\)", r"db.fetchrow(\1, \2)", content)
    content = re.sub(r"db\.fetch\((.*?),\s*([^,]+),\s*\)", r"db.fetch(\1, \2)", content)

    # Simpan file
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

# File krusial W2E
files_to_process = ["economy/ledger.py", "economy/database.py", "economy/profile.py", "economy/wallets.py", "economy/treasury.py"]

for f in files_to_process:
    if os.path.exists(f):
        process_file(f)

print("Tahap 2 selesai: Translasi SQLite -> Postgres!")