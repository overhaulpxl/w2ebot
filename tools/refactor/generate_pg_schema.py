import re
import glob

# Baca semua file schema.py
schema_files = glob.glob("economy/*_schema.py")
full_sql = ""

for file in schema_files:
    with open(file, "r", encoding="utf-8") as f:
        full_sql += "\n" + f.read()

# Ekstrak manual
blocks = []
parts = full_sql.split("CREATE TABLE IF NOT EXISTS")

for part in parts[1:]:
    block = "CREATE TABLE IF NOT EXISTS" + part
    
    # Ambil baris sampai penutup ');' atau '")' atau "')"
    lines = block.split("\n")
    final_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Stop case
        if "CREATE INDEX" in stripped or "CREATE TRIGGER" in stripped or "\"\"\"" in stripped or "'''" in stripped:
            # pastikan kita menangkap the last line kalau itu penutup tabel
            if ");" in stripped or ")\"" in stripped or ")'" in stripped:
                final_lines.append(line.split(';')[0] + ";")
            break
            
        final_lines.append(line)
        
    final_block = "\n".join(final_lines).strip()
    
    # Bersihkan kutipan sisa
    final_block = re.sub(r"[\"']+$", "", final_block)
    
    # Tambahkan titik koma jika gak ada
    if not final_block.endswith(";"):
        final_block += ";"
            
    blocks.append(final_block)

# Append to supabase_schema.sql
with open("supabase_schema.sql", "a", encoding="utf-8") as f:
    seen = set()
    for block in blocks:
        pg_block = block.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        pg_block = pg_block.replace("TEXT PRIMARY KEY", "VARCHAR(255) PRIMARY KEY")
        pg_block = pg_block.replace("DATETIME DEFAULT CURRENT_TIMESTAMP", "TIMESTAMPTZ DEFAULT NOW()")
        
        match = re.search(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", pg_block, re.IGNORECASE)
        if match:
            tname = match.group(1).lower()
            if tname in seen:
                continue
            seen.add(tname)
        
        f.write(pg_block + "\n\n")

print("Appended Phase 3-9 tables to supabase_schema.sql, total added:", len(seen))