# W2E Bot — Agent Instructions

## Role
Kamu adalah AI coding assistant yang membantu develop dan maintain **Way 2 Eternal Bot (W2E)**. Baca `context.md` terlebih dahulu sebelum melakukan perubahan apapun.

---

## Ground Rules

1. **Baca sebelum menulis** — Selalu baca file yang relevan sebelum mengedit. Jangan asumsikan konten file.
2. **Jaga konsistensi arsitektur** — Ikuti pola yang sudah ada: FakeInteraction, aiosqlite async, load_json/save_json, cog pattern.
3. **Jangan duplikasi kode** — Gunakan helper functions yang sudah ada di `core.py` (`get_discord_stat`, `update_discord_stat`, `load_json`, `save_json`, `check_level_up`).
4. **Preserve komentar** — Jangan hapus docstring atau komentar yang ada kecuali diminta.
5. **Test mental** — Sebelum submit, trace alur kode secara mental untuk memastikan tidak ada bug logika.

---

## Code Conventions

### Imports
- Semua shared utilities diimpor dari `core.py` via `from core import *` di `main.py`
- Cog files hanya perlu import yang diperlukan, tidak perlu reimport dari core

### Command Pattern
Setiap command menggunakan `@tree.command()` dan harus kompatibel dengan `FakeInteraction`:

```python
@tree.command(name="commandname", description="Deskripsi command")
async def command_name(interaction: discord.Interaction, param: str):
    uid = str(interaction.user.id)
    stat = await get_discord_stat(uid)
    # ... logic ...
    await interaction.response.send_message("Response")
```

### Database Access
**Selalu** gunakan `aiosqlite` untuk operasi DB, **jangan pernah** gunakan `sqlite3` sync di dalam async function:

```python
# ✅ BENAR
async with aiosqlite.connect(DB_PATH) as db:
    await db.execute("...", (params,))
    await db.commit()

# ❌ SALAH — blocking
conn = sqlite3.connect(DB_PATH)
conn.execute("...")
```

### JSON Data
Gunakan helper yang sudah ada:

```python
data = await load_json(FILENAME)   # Load dari DB (cached)
data[key] = value
await save_json(FILENAME, data)    # Save ke DB + update cache
```

### Error Handling
Semua operasi DB dan API harus di-wrap dengan try/except:

```python
try:
    # operation
except Exception as e:
    logging.error(f"Context: {e}")
    await interaction.response.send_message("Terjadi error.", ephemeral=True)
```

### Embeds
Gunakan `discord.Embed` untuk response yang kaya. Ikuti color scheme yang konsisten:
- Info/neutral: `0x5865F2` (Discord Blurple)
- Success: `0x57F287`
- Warning: `0xFEE75C`
- Error: `0xED4245`
- Special/Premium: `0xFFD700`

---

## Adding New Features

### Menambah Command Baru
1. Tentukan cog yang tepat: RPG/ekonomi → `cogs/rpg.py`, AI → `cogs/ai.py`, util → `cogs/utils.py`
2. Tambahkan command di dalam fungsi `setup(tree, client)` yang sudah ada
3. Gunakan pattern `FakeInteraction`-compatible (parameter harus typed)
4. Jika butuh data baru, tambahkan konstanta file di `core.py` dan buat struktur JSON-nya

### Menambah Tabel DB Baru
Tambahkan CREATE TABLE di fungsi `_init_db()` di `core.py`:

```python
conn.execute('''
    CREATE TABLE IF NOT EXISTS NamaTabel (
        id TEXT PRIMARY KEY,
        field1 TEXT,
        field2 INTEGER DEFAULT 0
    )
''')
```

### Menambah Shop Item Baru
Edit dict `SHOP_ITEMS` di `core.py`:

```python
'item_key': {'name': '🎁 Nama Item', 'price': 1000, 'desc': 'Deskripsi efek item'}
```

---

## Anti-Patterns — Jangan Lakukan Ini

| ❌ Jangan | ✅ Lakukan |
|---|---|
| `sqlite3.connect()` dalam async function | `aiosqlite.connect()` |
| Hardcode user ID atau token | Gunakan env vars atau parameter |
| `time.sleep()` dalam async | `await asyncio.sleep()` |
| Buka file langsung (`open()`) untuk data game | `load_json()` / `save_json()` |
| Duplikasi logic level up | Gunakan `check_level_up()` dari core |
| `interaction.response.send_message()` tanpa await | Selalu `await` |
| Import baru yang tidak ada di requirements.txt | Tambahkan ke requirements.txt dulu |
| Cari channel announcement manual (loop `general`/`chat`) | Gunakan `get_announce_channel(guild, category)` dari core |
| Endpoint web yang mengubah state tanpa proteksi | Guard dengan `require_token(request)` di `start_web_server` |

---

## File Ownership

| File | Tanggung Jawab |
|---|---|
| `core.py` | DB schema, helpers, FakeInteraction, bot config, events |
| `cogs/rpg.py` | Semua game mechanics, economy, gambling |
| `cogs/ai.py` | Gemini integration, persona, memory |
| `cogs/utils.py` | Non-game utilities |
| `main.py` | Entry point saja — jangan tambahkan logic di sini |
| `w2e_help.py` | Help menu UI — update saat ada command baru |
| `w2e_views.py` | Shared Discord UI components (buttons, selects) |

---

## When Asked to Debug

1. Baca file yang relevan — identifikasi fungsi yang bermasalah
2. Cek apakah ada penggunaan `sqlite3` sync di dalam konteks async
3. Cek apakah `await` digunakan dengan benar
4. Cek apakah `FakeInteraction` meneruskan semua atribut yang dibutuhkan command
5. Cek apakah `interaction.response` sudah di-respond sebelum `followup` dipanggil

---

## Deployment Notes

- **Local**: `python main.py` atau `run_all.bat`
- **Docker**: `docker compose up -d --build`
- **Heroku/Railway**: `Procfile` sudah dikonfigurasi (`worker: python main.py`)
- Database file `w2ebot.db` harus di-mount sebagai volume di Docker agar data persisten
- FFmpeg harus tersedia di PATH untuk fitur voice/listen
