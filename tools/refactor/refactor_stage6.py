import re
import glob

def strip_all_aiosqlite(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Paksa buang semua baris 'async with aiosqlite.connect(DB_PATH) as db:' 
    # karena dari awal refactor 1 sampai 5 ini membandel karena indentasi Python
    
    if "aiosqlite.connect" in content:
        content = content.replace("async with aiosqlite.connect(DB_PATH) as db:", "async with _pool.acquire() as db:")
        
    # Ganti context manager as cur:
    content = re.sub(
        r"async with db\.execute\((.*?)\)\s*as\s+\w+:\s*\n\s*(\w+)\s*=\s*await\s+\w+\.fetchall\(\)",
        r"\2 = await db.fetch(\1)",
        content,
        flags=re.DOTALL
    )
    content = re.sub(
        r"async with db\.execute\((.*?)\)\s*as\s+\w+:\s*\n\s*(\w+)\s*=\s*await\s+\w+\.fetchone\(\)",
        r"\2 = await db.fetchrow(\1)",
        content,
        flags=re.DOTALL
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

correct_args = ["core.py"] + glob.glob("cogs/*.py") + glob.glob("economy/*.py")
for f in correct_args:
    strip_all_aiosqlite(f)

print("Tahap 6 selesai: Pembasmi aiosqlite membandel!")