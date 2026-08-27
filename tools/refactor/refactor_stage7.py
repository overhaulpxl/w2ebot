import re
import glob

def aggressive_replace(filepath):
    print(f"Refactoring aggressive in {filepath}...")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Paksa ubah 'async with db.execute' yang masih tertinggal karena if statement
    content = re.sub(
        r"async with db\.execute\((.*?)\)\s*as\s+\w+:\s*\n\s*if\s+await\s+\w+\.fetchone\(\):",
        r"row = await db.fetchrow(\1)\n                        if row:",
        content,
        flags=re.DOTALL
    )

    # Convert ? -> $1, $2, $3 ...
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

    # Flatten tuples
    content = re.sub(r"db\.execute\((.*?),\s*\(\s*(.*?)\s*,\s*\)\s*\)", r"db.execute(\1, \2)", content, flags=re.DOTALL)
    content = re.sub(r"db\.fetchrow\((.*?),\s*\(\s*(.*?)\s*,\s*\)\s*\)", r"db.fetchrow(\1, \2)", content, flags=re.DOTALL)
    content = re.sub(r"db\.fetch\((.*?),\s*\(\s*(.*?)\s*,\s*\)\s*\)", r"db.fetch(\1, \2)", content, flags=re.DOTALL)
    content = re.sub(r"db\.execute\((.*?),\s*\(\s*(.*?)\s*\)\s*\)", r"db.execute(\1, \2)", content, flags=re.DOTALL)
    content = re.sub(r"db\.fetchrow\((.*?),\s*\(\s*(.*?)\s*\)\s*\)", r"db.fetchrow(\1, \2)", content, flags=re.DOTALL)
    content = re.sub(r"db\.fetch\((.*?),\s*\(\s*(.*?)\s*\)\s*\)", r"db.fetch(\1, \2)", content, flags=re.DOTALL)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


correct_args = ["core.py"] + glob.glob("cogs/*.py") + glob.glob("economy/*.py")
for f in correct_args:
    aggressive_replace(f)

print("Tahap 7 selesai: Aggressive replacer!")