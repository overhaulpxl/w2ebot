import re
import glob

def refactor_endpoints(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if "_pool" not in content:
        return

    # Kita masih memiliki ratusan sisa dari eksekusi context manager fetchall / fetchone 
    # karena Regex sebelumnya kurang kuat untuk menangkap yang ada multiline parameters (tuple unpack di bawahnya)
    # Mari kita ubah yang belum tertangkap
    content = re.sub(
        r"async with db\.execute\(\s*([^\)]+?)\s*\)\s*as\s+(\w+):\s*\n\s*(\w+)\s*=\s*await\s+\2\.fetchone\(\)",
        r"\3 = await db.fetchrow(\1)",
        content,
        flags=re.DOTALL
    )
    content = re.sub(
        r"async with db\.execute\(\s*([^\)]+?)\s*\)\s*as\s+(\w+):\s*\n\s*(\w+)\s*=\s*await\s+\2\.fetchall\(\)",
        r"\3 = await db.fetch(\1)",
        content,
        flags=re.DOTALL
    )

    # Convert sisa ? -> $1 yang belum tertangkap karena format parameter aneh
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
    
    # Supabase tidak butuh commit manual
    content = re.sub(r"await db\.commit\(\)", "", content)

    # Flatten tuple parameters in fetch/fetchrow
    content = re.sub(r"db\.fetchrow\((.*?),\s*\(\s*(.*?)\s*,\s*\)\s*\)", r"db.fetchrow(\1, \2)", content, flags=re.DOTALL)
    content = re.sub(r"db\.fetch\((.*?),\s*\(\s*(.*?)\s*,\s*\)\s*\)", r"db.fetch(\1, \2)", content, flags=re.DOTALL)
    content = re.sub(r"db\.fetchrow\((.*?),\s*\(\s*(.*?)\s*\)\s*\)", r"db.fetchrow(\1, \2)", content, flags=re.DOTALL)
    content = re.sub(r"db\.fetch\((.*?),\s*\(\s*(.*?)\s*\)\s*\)", r"db.fetch(\1, \2)", content, flags=re.DOTALL)
    content = re.sub(r"db\.execute\((.*?),\s*\(\s*(.*?)\s*,\s*\)\s*\)", r"db.execute(\1, \2)", content, flags=re.DOTALL)
    content = re.sub(r"db\.execute\((.*?),\s*\(\s*(.*?)\s*\)\s*\)", r"db.execute(\1, \2)", content, flags=re.DOTALL)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

correct_args = ["core.py"] + glob.glob("cogs/*.py") + glob.glob("economy/*.py")
for f in correct_args:
    refactor_endpoints(f)

print("Tahap 5 selesai: Eksekusi SQL di API dan Cogs dibersihkan!")