import re

with open("supabase_schema.sql", "r", encoding="utf-8") as f:
    sql = f.read()

# Masalah ForeignKey: MarketplaceSale me-referensikan MarketplaceEscrow (di baris 790), 
# tapi blok "CREATE TABLE MarketplaceSale" diletakkan di atas "CREATE TABLE MarketplaceEscrow" secara alfabetis atau acak.
# Kita perlu mengurutkan tabel-tabel ini. Cara termudah tanpa topological sort kompleks:
# Hapus semua "FOREIGN KEY(...) REFERENCES ..." dari setiap CREATE TABLE.
# Lalu, kumpulkan semua relasi FOREIGN KEY tersebut dan jadikan baris-baris ALTER TABLE di bawah file.

# 1. Temukan dan pindahkan foreign keys
fk_pattern = re.compile(r"(\s*FOREIGN KEY\s*\([^\)]+\)\s*REFERENCES\s+[a-zA-Z0-9_]+\s*\([^)]+\)(?:\s*DEFERRABLE INITIALLY DEFERRED)?),?")

fks_to_add = []

def extract_fks(match):
    block = match.group(0)
    # Temukan nama tabel
    table_match = re.search(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z0-9_]+)", block, re.IGNORECASE)
    if not table_match:
        return block
    table_name = table_match.group(1)
    
    # Kumpulkan FKs
    fks = fk_pattern.findall(block)
    for fk in fks:
        # Bersihkan koma di ujung string jika ada
        clean_fk = fk.strip()
        if clean_fk.endswith(","):
             clean_fk = clean_fk[:-1]
        
        # Simpan perintah ALTER
        fks_to_add.append(f"ALTER TABLE {table_name} ADD {clean_fk};")
        
    # Hapus FKs dari blok tabel
    clean_block = fk_pattern.sub("", block)
    
    # Kalau sisa koma di akhir kolom tabel sebelum penutup kurung, bersihkan (misal: "col TEXT,\n);")
    clean_block = re.sub(r",(\s*\);)", r"\1", clean_block)
    
    return clean_block

# Terapkan fungsi pembersihan ke setiap definisi tabel
sql = re.sub(r"CREATE TABLE IF NOT EXISTS\s+[a-zA-Z0-9_]+\s*\([^;]+?\);", extract_fks, sql, flags=re.DOTALL|re.IGNORECASE)

# Tulis kembali dengan urutan baru (Tables -> FKs)
with open("supabase_schema.sql", "w", encoding="utf-8") as f:
    f.write(sql)
    f.write("\n\n-- Deferred Foreign Keys --\n")
    for fk in fks_to_add:
        f.write(fk + "\n")

print("Fixed Foreign Key Ordering!")