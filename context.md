# W2E Bot — Project Context

## Overview
**Way 2 Eternal Bot (W2E)** adalah Discord bot enterprise/cloud-ready yang menggabungkan:
- 🤖 **AI Chat** via Google Gemini 2.5 Flash
- 🎮 **RPG & Ekonomi** (Market, Mining, Boss Raid, Casino)
- 🖼️ **Dynamic Image Generation** via Pillow
- 🗃️ **Persistent storage** via SQLite (`w2ebot.db`) + aiosqlite

---

## Tech Stack

| Layer | Teknologi |
|---|---|
| Language | Python 3.10+ |
| Discord SDK | discord.py (app_commands) |
| AI | Google GenAI SDK (`google-genai`) — Gemini 2.5 Flash |
| Database | SQLite via `aiosqlite` |
| Image | Pillow (PIL) |
| TTS | gTTS |
| Audio | FFmpeg + PyNaCl |
| HTTP | aiohttp |
| Env | python-dotenv |

---

## Project Structure

```
w2ebot/
├── main.py              # Entry point — loads core + registers all cogs
├── core.py              # Heart of the bot: DB, helpers, FakeInteraction, events
├── cogs/
│   ├── rpg.py           # RPG, ekonomi, judi, mining, boss raid
│   ├── ai.py            # Gemini AI, persona, memory, roast, rate, shipper
│   └── utils.py         # Utilitas: ping, poll, giveaway, remindme, birthday
├── embedder.py          # Embed helpers
├── w2e_help.py          # Help menu UI
├── w2e_views.py         # Discord UI Views/Buttons
├── setup_dashboard.py   # Web dashboard setup
├── dashboard.html       # Dashboard UI
├── lock_bot.py          # Bot lock utilities
├── migrate_db.py        # DB migration scripts
├── migrate_gemini.py    # Gemini migration scripts
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── Procfile
└── .env                 # Secrets (gitignored)
```

---

## Environment Variables

```env
DISCORD_TOKEN=          # Discord bot token
GEMINI_API_KEY=         # Google Gemini API key
ALLOWED_SERVER_ID=      # Guild ID yang diizinkan (default: 887968847842402355)
BOT_PREFIX=             # Prefix command (default: w!)
DASHBOARD_TOKEN=        # Token auth untuk endpoint web yang mengubah state (kosong = endpoint fail closed)
ALLOWED_ORIGINS=        # CORS whitelist, dipisah koma (kosong = izinkan semua, dev only)
```

---

## Database Schema

### `DiscordStat` — Data player
| Column | Type | Keterangan |
|---|---|---|
| id | TEXT PK | Discord user ID |
| displayName | TEXT | Nama tampil user |
| coins | INTEGER | Saldo koin |
| xp | INTEGER | Experience points |
| level | INTEGER | Level saat ini |
| lastDaily | TEXT | Timestamp daily terakhir |
| updatedAt | TEXT | Timestamp update terakhir |

### `ChatMemory` — Memori chat AI
| Column | Type | Keterangan |
|---|---|---|
| id | INTEGER PK | Auto increment |
| timestamp | TEXT | Waktu pesan |
| content | TEXT | Isi pesan/memori |

### `json_store` — Key-value store untuk data JSON
| Column | Type | Keterangan |
|---|---|---|
| filename | TEXT PK | Nama file (key) |
| content | TEXT | JSON serialized data |

---

## JSON Data Files (stored in `json_store` table)

| File Key | Isi |
|---|---|
| `family.json` | Data pernikahan & adopsi |
| `items.json` | Inventori item player |
| `weekly.json` | Data klaim mingguan |
| `quests.json` | Quest harian player |
| `custom_roles.json` | Custom role server |
| `market.json` | Data pasar kripto fiktif |
| `portfolio.json` | Portofolio investasi player |
| `personas.json` | Persona AI per user/server |
| `boss.json` | Status boss raid |
| `rigs.json` | Data mining rig player |
| `treasury.json` | Kas/brankas server |
| `binomo.json` | Data crash game |

> Catatan: `config.json` TIDAK disimpan di `json_store`, melainkan file biasa di disk
> (dibaca via `_load_config()` di `core.py`).

---

## Config File (`config.json`)

File terpisah di disk untuk pengaturan operasional dashboard/announcement:

```json
{
  "booster_channel_id": "",
  "announce_channels": {
    "default": "",
    "market": "",
    "levelup": "",
    "birthday": "",
    "boss": "",
    "booster": "",
    "binomo": ""
  }
}
```

`announce_channels` memetakan tiap kategori announcement ke channel ID. Diresolusi oleh
`get_announce_channel(guild, category)`; kosong = fallback ke `default`, lalu fallback ke
pencarian channel `general`/`chat`. Key `booster_channel_id` lama tetap dibaca untuk
kompatibilitas.

---

## Web API (port 8081)

Dijalankan di `start_web_server` (`core.py`), dipakai dashboard & web main way2eternal.
Endpoint yang mengubah state diproteksi `require_token` (header `X-Auth-Token` =
`DASHBOARD_TOKEN`). Detail lengkap ada di `API.md`.

| Method | Path | Auth |
|---|---|---|
| GET | `/` (dashboard.html) | — |
| GET | `/api/server` | — |
| GET | `/api/radar` | — |
| GET | `/api/channels` | — |
| GET | `/api/config` | — |
| POST | `/api/config` | token |
| GET | `/api/announce-config` | — |
| POST | `/api/announce-config` | token |
| POST | `/api/broadcast` | token |

---

## Core Architecture

### FakeInteraction
Kelas di `core.py` yang mengkonversi pesan prefix (`w!command`) menjadi objek yang kompatibel dengan `discord.Interaction`. Ini memungkinkan satu implementasi slash command berfungsi untuk keduanya — slash (`/command`) dan prefix (`w!command`).

### Level Up Formula
Menggunakan quadratic formula O(1) untuk menghitung level up:
```
a = 50, b = 100*level - 50, c = -xp
n = floor((-b + sqrt(b²-4ac)) / 2a)
```

### JSON Cache
`_json_cache` dict in-memory untuk O(1) lookup, di-sync ke SQLite saat ada perubahan.

---

## Command Categories (54 total)

- **RPG & Ekonomi**: daily, weekly, work, profile, shop, buy, sell, inventory, rob, transfer, top, buyrig, miner, market, portfolio, quest, attack, buypet
- **Judi & Casino**: cf, flip, slot, blackjack, tebak, crash, gacha, box, rps
- **AI & Sosial**: ai, chat, setpersona, listen, roast, rate, image, shipper, marry, divorce, adopt, family
- **Utilitas**: help, ping, poll, giveaway, find, checkbots, remindme, birthday, bg, kas, valo

---

## Running the Bot

```bash
# Local
python main.py

# Windows shortcut
run_all.bat

# Docker
docker compose up -d --build
```
