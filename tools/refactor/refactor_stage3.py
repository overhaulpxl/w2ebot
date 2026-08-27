import re
import os

def correct_args_in_file(filepath):
    print(f"Correcting $ args in {filepath}...")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Reset all $ back to ?
    content = re.sub(r"\$(\d+)", "?", content)

    # Let's write a smarter placeholder replacer
    def replace_smart(m):
        full_str = m.group(0)
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
    
    # Supabase / asyncpg does NOT support `BEGIN IMMEDIATE` or `await configure_connection(db)`
    content = content.replace("await db.execute(\"BEGIN IMMEDIATE\")", "async with db.transaction():")
    content = content.replace("await db.execute('BEGIN IMMEDIATE')", "async with db.transaction():")
    content = content.replace("await configure_connection(db)", "")

    # aiosqlite tuple flattening
    content = re.sub(r"db\.execute\((.*?),\s*\(\s*(.*?)\s*,\s*\)\s*\)", r"db.execute(\1, \2)", content)
    content = re.sub(r"db\.fetchrow\((.*?),\s*\(\s*(.*?)\s*,\s*\)\s*\)", r"db.fetchrow(\1, \2)", content)
    content = re.sub(r"db\.fetch\((.*?),\s*\(\s*(.*?)\s*,\s*\)\s*\)", r"db.fetch(\1, \2)", content)
    content = re.sub(r"db\.execute\((.*?),\s*\(\s*(.*?)\s*\)\s*\)", r"db.execute(\1, \2)", content)
    content = re.sub(r"db\.fetchrow\((.*?),\s*\(\s*(.*?)\s*\)\s*\)", r"db.fetchrow(\1, \2)", content)
    content = re.sub(r"db\.fetch\((.*?),\s*\(\s*(.*?)\s*\)\s*\)", r"db.fetch(\1, \2)", content)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

for f in ["economy/ledger.py", "economy/database.py", "economy/profile.py", "economy/wallets.py", "economy/treasury.py"]:
    if os.path.exists(f):
        correct_args_in_file(f)