import re
import os
import glob

def correct_args_in_file(filepath):
    print(f"Correcting $ args in {filepath}...")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Hanya refactor file yang memiliki _pool (tanda sudah di-refactor stage 1)
    if "_pool" not in content and "asyncpg" not in content:
        return

    # Reset all $ back to ? for safety (idempotent run)
    content = re.sub(r"\$(\d+)", "?", content)

    # Smart placeholder replacer
    def replace_smart(m):
        full_str = m.group(0)
        # Abaikan string yang gak ada keywords SQL, jangan sampai ngerusak string bahasa manusia
        if not re.search(r"\b(SELECT|INSERT|UPDATE|DELETE|WITH|ON CONFLICT|INTO|FROM)\b", full_str, re.IGNORECASE):
            return full_str
            
        parts = full_str.split("?")
        if len(parts) == 1:
            return full_str
            
        res = parts[0]
        for i in range(1, len(parts)):
            res += f"${i}" + parts[i]
        return res
        
    content = re.sub(r"\"[^\"]*?\?[^\"]*?\"", replace_smart, content)
    content = re.sub(r"'[^']*?\?[^']*?'", replace_smart, content)
    content = re.sub(r"\"\"\"(?:.|\n)*?\?(?:.|\n)*?\"\"\"", replace_smart, content)
    content = re.sub(r"'''(?:.|\n)*?\?(?:.|\n)*?'''", replace_smart, content)
    
    # 1. Ganti fetchone dan fetchall context manager
    content = re.sub(
        r"async with db\.execute\((.*?)\)\s*as\s+(\w+):\s*\n\s*(\w+)\s*=\s*await\s+\2\.fetchone\(\)",
        r"\3 = await db.fetchrow(\1)",
        content,
        flags=re.DOTALL
    )
    content = re.sub(
        r"async with db\.execute\((.*?)\)\s*as\s+(\w+):\s*\n\s*(\w+)\s*=\s*await\s+\2\.fetchall\(\)",
        r"\3 = await db.fetch(\1)",
        content,
        flags=re.DOTALL
    )
    # Hapus sisa-sisa
    content = re.sub(r"await cursor\.close\(\)", "", content)
    
    # 2. Supabase / asyncpg does NOT support `BEGIN IMMEDIATE` or `await configure_connection(db)`
    content = content.replace("await db.execute(\"BEGIN IMMEDIATE\")", "async with db.transaction():")
    content = content.replace("await db.execute('BEGIN IMMEDIATE')", "async with db.transaction():")
    content = content.replace("await configure_connection(db)", "")

    # 3. aiosqlite tuple flattening
    # PENTING: Karena bisa multi line, kita pakai format paling dasar saja atau biarkan tuple dan minta asyncpg unpack
    content = re.sub(r"db\.execute\((.*?),\s*\(\s*(.*?)\s*,\s*\)\s*\)", r"db.execute(\1, \2)", content)
    content = re.sub(r"db\.fetchrow\((.*?),\s*\(\s*(.*?)\s*,\s*\)\s*\)", r"db.fetchrow(\1, \2)", content)
    content = re.sub(r"db\.fetch\((.*?),\s*\(\s*(.*?)\s*,\s*\)\s*\)", r"db.fetch(\1, \2)", content)

    # 4. hapus .rowcount dari result object, karena asyncpg execute me-return string 'UPDATE 1', dsb.
    content = re.sub(r"(\w+)\s*=\s*(\w+)\.rowcount\s*>\s*0", r"\1 = \2 == 'UPDATE 1' or \2 == 'INSERT 0 1'", content)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

# Cari semua file python
for file in glob.glob("cogs/*.py") + glob.glob("economy/*.py"):
    correct_args_in_file(file)

print("Tahap 4 selesai: Semua file Cogs & Economy diterjemahkan ke Postgres!")