import os
import glob
import re

# Fungsi untuk mencari dan mengganti semua koneksi database di file Python
def refactor_postgres(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Lewati file yang tidak mengimpor aiosqlite
    if "aiosqlite" not in content:
        return

    print(f"Refactoring {file_path}...")

    # 1. Hapus import aiosqlite, ganti dengan import pool dari core
    content = re.sub(r"import\s+aiosqlite\n", "", content)
    
    # 2. Ganti pembuatan koneksi
    content = content.replace("async with aiosqlite.connect(DB_PATH) as db:", "async with _pool.acquire() as db:")
    content = content.replace("async with aiosqlite.connect(db_path) as db:", "async with _pool.acquire() as db:")
    
    # 3. Hapus DB_PATH import dari core
    content = re.sub(r"from\s+core\s+import[\s\\]*(.*?)DB_PATH,?", r"from core import \1", content)
    content = re.sub(r",\s*DB_PATH\b", "", content)
    
    # Masukkan import _pool jika belum ada
    if "_pool" not in content and "from core import" in content:
        content = re.sub(r"from\s+core\s+import\s+", "from core import _pool, ", content, count=1)
    elif "_pool" not in content:
        content = "from core import _pool\n" + content
        
    # Tulis kembali
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)


# Cari semua file python
for file in glob.glob("cogs/*.py") + glob.glob("economy/*.py"):
    refactor_postgres(file)

print("Tahap 1 selesai: Context managers diubah ke asyncpg pool!")