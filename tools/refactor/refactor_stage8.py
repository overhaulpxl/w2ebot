import glob
import re

def aggressive_unmatched_paren_fixer(filepath):
    print(f"Fixing stray close parens in {filepath}...")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Masalah utamanya adalah setelah tuple argument digabung, tanda kurung penutupnya kadang masih ada di baris berikutnya.
    # Terutama bentuk: \n        ) as cursor: -> kita hapus
    # Dan: \n        ) -> jika di atasnya diakhiri comma atau paren
    
    # Menghapus ") as cursor:"
    content = re.sub(r"\n\s*\)\s*as\s+cursor\s*:", "", content)
    
    # Hapus trailing kurung yg cuma berisi newline/whitespace (jika query udah ketutup)
    # Ini sangat berbahaya untuk direplace pakai regex biasa, jadi kita lakukan iterasi baris
    lines = content.split('\n')
    new_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == ")" or stripped == "),":
            # Cek baris atasnya, apakah itu sudah menutuk call db.execute / db.fetch?
            if len(new_lines) > 0:
                prev_line = new_lines[-1].strip()
                # Jika baris sebelumnya tidak diakhiri koma, kemungkinan besar () sudah ketutup di baris prev
                if not prev_line.endswith(",") and not prev_line.endswith("("):
                     continue # skip this line
                     
                # Jika prev_line diakhiri dengan ')', kemungkinan tuple unpack atau udah lengkap
                if prev_line.endswith(")"):
                    continue
                    
        new_lines.append(line)
        
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))


correct_args = ["core.py"] + glob.glob("cogs/*.py") + glob.glob("economy/*.py")
for f in correct_args:
    aggressive_unmatched_paren_fixer(f)

print("Tahap 8 selesai: Stray parens removed!")