# W2E Bot — Web API Reference

This document is the integration contract between the **way2eternal main website** and the
**W2E Discord bot**. The bot exposes a small HTTP API (aiohttp) so the external site can
read live server state and configure announcement channels.

> All endpoints, request bodies, and response shapes below are taken directly from the
> handlers in `core.py` (`start_web_server` router + the `api_*` / `*_config_api` functions).

---

## Base URL & Authentication

- **Base URL (local):** `http://localhost:8081`
- **Base URL (production):** behind a reverse proxy, e.g. `https://api.way2eternal.com`
  (see [Hosting](#hosting--cors-separate-domains)).
- **Auth:** state-changing endpoints require the HTTP header:
  ```
  X-Auth-Token: <DASHBOARD_TOKEN>
  ```
  The bot compares it to the `DASHBOARD_TOKEN` env var via `hmac.compare_digest`.
  If `DASHBOARD_TOKEN` is **unset/empty**, those endpoints **fail closed** and always
  return `401` — set the token to enable them.
- Read-only `GET` endpoints currently require no token.

---

## Endpoint Reference

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | — | Serves `dashboard.html` (HTML). |
| GET | `/api/server` | — | Guild info: name, icon, member count, channels, roles. |
| GET | `/api/radar` | — | Members currently in voice channels + minutes. |
| GET | `/api/channels` | — | Text channels of the guild (for dropdowns). |
| GET | `/api/config` | — | Raw `config.json` contents. |
| POST | `/api/config` | ✅ token | Overwrite raw `config.json`. |
| GET | `/api/announce-config` | — | Current announcement-channel mapping. |
| POST | `/api/announce-config` | ✅ token | Set announcement-channel mapping (validated). |
| POST | `/api/broadcast` | ✅ token | Send a message to a channel as the bot. |
| GET | `/api/leaderboard` | — | Top players. Query: `sort=coins\|level` (default `level`), `limit=1..100` (default 10). |
| GET | `/api/user/{id}` | — | Full player profile (coins, xp, level, rank, crypto, rigs, items, pet, achievements, marriage, cooldowns, bg_url, games, top_games, persona, birthday, bounty, weekly, quest). |
| GET | `/api/market` | — | Full crypto market: price + 10-point history per coin. |
| GET | `/api/treasury` | — | Community treasury balance. |
| GET | `/api/boss` | — | Current boss-raid state. |
| GET | `/api/economy/stats` | — | Aggregates: player count, coins in circulation, avg level, top holder, treasury. |
| GET | `/api/marriages` | — | List of married pairs (de-duplicated, names resolved). |
| GET | `/api/stats/summary` | — | One-call dashboard summary (members, in-voice, boss, treasury, total coins). |
| GET | `/api/bot/stats` | — | Detailed bot stats: latency, uptime, guild detail, economy aggregates. |
| GET | `/api/economy/level-distribution` | — | Player count grouped by level (for bar chart). |
| GET | `/api/audit` | ✅ token | Admin audit log (recent write actions). Query `limit=1..500` (default 100). |
| POST | `/api/user/{id}/coins` | ✅ token | Adjust coins. Body `{"delta": N}` (relative) or `{"set": N}` (absolute, ≥0). |
| POST | `/api/user/{id}/xp` | ✅ token | Add XP. Body `{"delta": N}` (level-up auto-resolved). |
| POST | `/api/user/{id}/give-item` | ✅ token | Grant item. Body `{"item_id": "shield", "qty": 1}` (item_id must exist in shop). |
| POST | `/api/user/{id}/reset-cooldown` | ✅ token | Reset cooldown. Body `{"type": "work\|rob\|pray\|curse\|daily\|all"}`. |
| POST | `/api/user/{id}/persona` | ✅ token | Set/reset persona AI. Body `{"persona": "..."}` (kosong = reset). |
| POST | `/api/user/{id}/birthday` | ✅ token | Set/hapus birthday. Body `{"date": "DD-MM"}` (kosong = hapus). |
| POST | `/api/user/{id}/bg` | ✅ token | Set/hapus background profil (SSRF-guarded). Body `{"url": "..."}`. |
| POST | `/api/user/{id}/divorce` | ✅ token | Admin paksa cerai. Body `{}`. |
| POST | `/api/user/{id}/bounty` | ✅ token | Set/hapus bounty. Body `{"amount": N}` (0 = hapus). |
| POST | `/api/user/{id}/reset-weekly` | ✅ token | Reset klaim weekly. Body `{}`. |
| POST | `/api/user/{id}/reset-quest` | ✅ token | Reset progress quest. Body `{}`. |
| POST | `/api/boss/spawn` | ✅ token | Force-spawn a boss raid (409 if one is already active). |
| POST | `/api/announce` | ✅ token | Broadcast to an announce category. Body `{"category": "market", "message": "..."}`. |

---

## Extra dashboard endpoints

All READ endpoints below are open (no token), follow the same CORS rules, and return JSON.
All WRITE endpoints require the `X-Auth-Token` header and fail closed when `DASHBOARD_TOKEN` is unset.

> ⚠️ The write endpoints under `/api/user/...` can mint coins/items and reset limits.
> Keep `DASHBOARD_TOKEN` server-side only (never in browser JS), and set a real
> `ALLOWED_ORIGINS` in production (not `*`).

### GET `/api/bot/stats`
Detailed bot stats: `online`, `latency_ms`, `uptime_seconds`, `guild` (member/human/bot
counts, in-voice, boosts+tier, channel/role counts), `economy` (players, total_coins,
average_level, max_level, total_xp), `treasury_balance`, `boss_active`,
`commands_registered`, `announce_channels_configured`, `prefix`.

### GET `/api/economy/level-distribution`
```json
{ "buckets": [ { "level": 1, "count": 65 }, { "level": 2, "count": 18 } ] }
```

## Economy V1 Phase 1 Supply

`GET /api/economy/v1-supply` bersifat read-only. Response menyertakan status
enable dan supply ETM/ECY dengan definisi yang sama dengan verification CLI:

- `net_issued_supply`: wallet user + treasury spendable + reserve + burn.
- `circulating_supply`: wallet user + treasury spendable.
- `non_circulating_supply`: locked reserve.
- `burned_supply`: burn account.
- `issuance_balance`: balancing account yang tidak masuk supply display.
- `issuance_matches`: `-issuance_balance == net_issued_supply`.
- `ledger_zero_sum`: jumlah seluruh entry ledger committed per currency adalah 0.

Endpoint legacy tetap tersedia dan `/api/economy/stats` menambahkan field
`v1_enabled` serta `v1_supply` tanpa menghapus field lama. Phase 1 tidak
mengaktifkan mutasi wallet production.

### GET `/api/audit?limit=100` (token)
Recent admin write actions. Token required (fail-closed when `DASHBOARD_TOKEN` unset).
```json
{ "limit": 100, "entries": [
  { "id": 1, "ts": "2026-06-16T01:17:34Z", "action": "coins",
    "target_id": "529168872696446988", "detail": "delta=5000 -> 11167", "source": "api" }
]}
```
Actions logged: `coins`, `xp`, `give-item`, `reset-cooldown`, `persona`, `birthday`, `bg`, `divorce`, `bounty`, `reset-weekly`, `reset-quest`, `boss-spawn`, `announce`, `announce-config`.


### GET `/api/leaderboard?sort=level&limit=10`
```json
{ "sort": "level", "limit": 10, "entries": [
  { "rank": 1, "id": "123", "displayName": "naykeren", "coins": 99000, "xp": 40, "level": 12 }
]}
```

### GET `/api/user/{id}`
```json
{
  "id": "123", "displayName": "naykeren",
  "coins": 12345, "xp": 40, "level": 12, "xp_to_next": 1200, "rank": 3,
  "lastDaily": "2026-06-15T09:00:00",
  "crypto": { "ETHR": 14 }, "rigs": { "1": 2 }, "items": { "shield": 1 },
  "pet": "wolf", "achievements": ["no_lifer"], "total_vc_minutes": 1500,
  "married_to": "456", "children": [], "bg_url": null,
  "cooldowns": { "work": 0, "rob": 5400, "pray": 0, "curse": 12000 },
  "games": { "slot": { "plays": 20, "wins": 8, "losses": 12 }, "cf": { "plays": 5, "wins": 3, "losses": 2 } },
  "top_games": [
    { "game": "slot", "plays": 20, "wins": 8, "win_rate": 40.0 },
    { "game": "cf", "plays": 5, "wins": 3, "win_rate": 60.0 }
  ],
  "persona": "Gen-Z gaul",
  "birthday": "25-12",
  "bounty": 5000,
  "weekly_claimed": "2026-06-10",
  "quest": { "date": "2026-06-16", "quests": [...], "claimed": false }
}
```
- `cooldowns` values are seconds remaining (0 = ready).
- `games` only appears after player has played (starts from 0).
- `top_games` is the top 3 games by play count.
- Errors: `400 {"error":"invalid user id"}` if id isn't digits.

### POST `/api/user/{id}/coins`
```bash
curl -X POST http://localhost:8081/api/user/123/coins \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"delta": 5000}'      # or {"set": 12345}
# -> {"status":"success","id":"123","coins":17345}
```

### POST `/api/user/{id}/give-item`
```bash
curl -X POST http://localhost:8081/api/user/123/give-item \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"item_id":"shield","qty":2}'
```
Valid `item_id`: `shield`, `double_xp`, `lucky_charm`.

### POST `/api/user/{id}/reset-cooldown`
```bash
curl -X POST http://localhost:8081/api/user/123/reset-cooldown \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"type":"all"}'
```

### POST `/api/boss/spawn`
`200 {"status":"success","boss":{...}}` or `409 {"error":"boss already active"}`.

### POST `/api/announce`
```bash
curl -X POST http://localhost:8081/api/announce \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"category":"market","message":"Pengumuman dari dashboard!"}'
```
`category` is one of `market`, `levelup`, `birthday`, `boss`, `booster`, `binomo`, `default`.

### POST `/api/user/{id}/persona`
```bash
curl -X POST http://localhost:8081/api/user/123/persona \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"persona":"Gen-Z gaul savage"}'
# Reset: {"persona":""}
```

### POST `/api/user/{id}/birthday`
```bash
curl -X POST http://localhost:8081/api/user/123/birthday \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"date":"25-12"}'
# Hapus: {"date":""}
```

### POST `/api/user/{id}/bg`
```bash
curl -X POST http://localhost:8081/api/user/123/bg \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"url":"https://example.com/bg.jpg"}'
# Hapus: {"url":""}
# SSRF-guarded: host privat/loopback ditolak; harus gambar valid.
```

### POST `/api/user/{id}/divorce`
```bash
curl -X POST http://localhost:8081/api/user/123/divorce \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{}'
# -> {"status":"success","id":"123","divorced_from":"456"}
# Error jika user tidak menikah: 400 {"error":"user tidak menikah"}
```

### POST `/api/user/{id}/bounty`
```bash
curl -X POST http://localhost:8081/api/user/123/bounty \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"amount":5000}'
# Hapus: {"amount":0}
```

### POST `/api/user/{id}/reset-weekly`
```bash
curl -X POST http://localhost:8081/api/user/123/reset-weekly \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{}'
```

### POST `/api/user/{id}/reset-quest`
```bash
curl -X POST http://localhost:8081/api/user/123/reset-quest \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{}'
```

---

### GET `/api/channels`

Returns all text channels in the allowed guild — use to populate channel dropdowns.

```json
[
  { "id": "1332113600894079131", "name": "general" },
  { "id": "1332111384523309156", "name": "market-news" }
]
```

Errors: `404 {"error": "Bot is not in the allowed server"}` if the bot isn't in the guild.

---

### GET `/api/announce-config`

Returns the current announcement-channel mapping. Always includes every key (empty string
means "auto — fall back to a `general`/`chat` channel").

```json
{
  "default": "",
  "market": "1332111384523309156",
  "levelup": "",
  "birthday": "",
  "boss": "",
  "booster": "",
  "binomo": ""
}
```

The 6 categories: `market` (price pump/dump), `levelup` (voice XP level-ups),
`birthday`, `boss` (raid spawn), `booster` (server-booster joins VC), `binomo`
(gambling results). `default` applies to any category left empty.

---

### POST `/api/announce-config`

Sets the announcement-channel mapping. Body accepts `default` + the 6 category keys; each
value is a Discord channel **ID string** (digits only) or `""` to use the fallback.

Request:
```json
{ "default": "", "market": "1332111384523309156", "levelup": "", "birthday": "",
  "boss": "", "booster": "", "binomo": "" }
```

Responses:
- `200 {"status": "success", "announce_channels": { ... }}`
- `400 {"error": "Invalid channel id for <key>"}` — a value was non-empty and not all digits.
- `401 {"error": "unauthorized"}` — missing/invalid token.

Only the `announce_channels` block is rewritten; other `config.json` keys are preserved.

---

### POST `/api/broadcast`

Sends a message to a channel as the bot.

Request:
```json
{ "channel": "1332113600894079131", "message": "Halo dari web main!" }
```

Responses:
- `200 {"status": "sent"}`
- `400 {"error": "Missing channel or message"}` / `{"error": "Invalid channel ID format"}`
- `404 {"error": "Channel not found by bot"}`
- `401 {"error": "unauthorized"}`

---

### GET `/api/server`

```json
{
  "id": "887968847842402355",
  "name": "Way 2 Eternal",
  "icon_url": "https://cdn.discordapp.com/...",
  "member_count": 1234,
  "description": null,
  "premium_subscription_count": 7,
  "text_channels": [{ "id": "...", "name": "..." }],
  "voice_channels": [{ "id": "...", "name": "...", "connected_members": 3 }],
  "roles": [{ "id": "...", "name": "...", "color": "#5865f2" }]
}
```

### GET `/api/radar`

```json
[
  { "user_id": "123", "username": "naykeren", "channel": "camat oagi", "minutes": 42 }
]
```

### GET / POST `/api/config`

`GET` returns raw `config.json` (`{}` if missing). `POST` (token required) overwrites the
whole file — prefer `POST /api/announce-config` for channel settings so you don't clobber
other keys.

---

## Integration Pattern (recommended)

```
Browser (way2eternal site)
   └─> way2eternal BACKEND  (stores DASHBOARD_TOKEN secretly)
          └─> https://api.way2eternal.com/api/...   (X-Auth-Token header)
                 └─> W2E bot :8081
```

**Never put `DASHBOARD_TOKEN` in client-side JavaScript.** The browser should call your own
backend, and your backend (server-to-server) calls the bot API with the token. If the main
site is fully static, add one small serverless function as a proxy.

### Example: backend fetch (Node)

```js
await fetch("https://api.way2eternal.com/api/announce-config", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-Auth-Token": process.env.DASHBOARD_TOKEN },
  body: JSON.stringify({ market: "1332111384523309156", default: "", levelup: "",
                         birthday: "", boss: "", booster: "", binomo: "" }),
});
```

---

## Hosting & CORS (separate domains)

The main site and bot run on different hosts, so:

1. **Reverse proxy + HTTPS**: put the bot behind nginx/Caddy, e.g.
   `api.way2eternal.com → 127.0.0.1:8081`. (Ops setup, not part of the bot code.)
2. **CORS whitelist**: set `ALLOWED_ORIGINS` (comma-separated) to your site's origin(s):
   ```env
   ALLOWED_ORIGINS=https://way2eternal.com,https://app.way2eternal.com
   ```
   Empty `ALLOWED_ORIGINS` = allow all origins (`*`) — **dev only**. With a token + browser
   credentials, a wildcard origin is rejected, so a real whitelist is required in production.
3. **Token**: set `DASHBOARD_TOKEN` to a long random secret on the bot host.

---

## curl Examples

```bash
# Read channels (open)
curl http://localhost:8081/api/channels

# Read current announcement config (open)
curl http://localhost:8081/api/announce-config

# Read user profile (open)
curl http://localhost:8081/api/user/529168872696446988

# Read bot stats (open)
curl http://localhost:8081/api/bot/stats

# Read level distribution (open)
curl http://localhost:8081/api/economy/level-distribution

# Read audit log (needs token)
curl http://localhost:8081/api/audit?limit=50 \
  -H "X-Auth-Token: YOUR_TOKEN"

# Set announcement config (needs token)
curl -X POST http://localhost:8081/api/announce-config \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"market":"1332111384523309156","default":"","levelup":"","birthday":"","boss":"","booster":"","binomo":""}'

# Adjust coins (needs token)
curl -X POST http://localhost:8081/api/user/123/coins \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"delta": 5000}'

# Set persona (needs token)
curl -X POST http://localhost:8081/api/user/123/persona \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"persona":"Gen-Z savage"}'

# Set bounty (needs token)
curl -X POST http://localhost:8081/api/user/123/bounty \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"amount":5000}'

# Spawn boss (needs token)
curl -X POST http://localhost:8081/api/boss/spawn \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{}'

# Broadcast a message (needs token)
curl -X POST http://localhost:8081/api/broadcast \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"channel":"1332113600894079131","message":"Halo!"}'

# Without token -> 401
curl -X POST http://localhost:8081/api/announce-config \
  -H "Content-Type: application/json" -d '{}'
# {"error": "unauthorized"}
```

## Economy V1 Phase 2 Profile

`GET /api/economy/v1-profile/{id}` adalah endpoint read-only. Endpoint ini tidak
membuat profile atau wallet baru. Response memuat level/XP, ETM/ECY, HP, stat
combat, Energy, Power Score, Activity Score rolling 30 hari, dan placeholder
instance equipment/pet. `404` berarti profile staging belum tersedia.

Phase 2 tetap nonaktif secara default dan membutuhkan
`ECONOMY_V1_ENABLED=true` serta `ECONOMY_PHASE2_ENABLED=true` hanya pada staging.

## Economy V1 Phase 3 RPG

Phase 3 belum menambahkan endpoint mutation publik. Command Discord baru hanya
aktif jika ketiga flag Economy Phase 1-3 bernilai `true`. Schema/catalog Phase 3
diterapkan menggunakan `scripts/migrate_economy_phase3.py` pada database
temporary atau staging; script menolak database production.

Migrasi hardening bersifat additive dan fail-closed jika checksum versi schema yang
sudah selesai tidak cocok. Recovery hanya mengubah lifecycle/retry metadata; planned
outcome tidak dapat ditulis ulang. Legacy quarantine tidak memetakan item atau pet
lama ke equipment/pet V1 dan tidak mengubah blob sumber.

Runtime database bot, Economy, Deal, dan dashboard memakai `DATABASE_PATH` terpusat.
Default-nya tetap database production repository. Ketiga flag economy tidak dapat
aktif kecuali guard staging memvalidasi mode staging, guild khusus, token tersedia,
dan path SQLite non-production yang sudah ada. Nilai token tidak pernah masuk log.

Setup lokal staging:

```powershell
python scripts/setup_phase3_staging.py
```

Isi hanya `STAGING_GUILD_ID` dan `DISCORD_TOKEN` pada `.env.staging`, lalu mulai
bot dengan:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_phase3_staging.ps1
```

Gunakan `python scripts/setup_phase3_staging.py --verify` untuk memastikan path,
checksum, catalog, integrity, dan foreign-key database staging tanpa membuka
database production.

Profile Phase 3 menghitung effective HP/Attack/Defense dari base profile,
equipment, set, enhancement, dan pet. Boss status bersifat read-only melalui
Discord dan menampilkan apakah settlement perlu diulang setelah treasury
`ETM_BOSS_DUNGEON` tersedia. API internal untuk Boss start/settle harus memakai
autentikasi dashboard yang sudah ada sebelum adapter HTTP ditambahkan.

Saat Phase 3 aktif, `GET /api/economy/v1-profile/{id}` menambahkan field
`effective_max_hp`, `effective_attack`, `effective_defense`,
`effective_crit_bps`, `effective_power_score`, dan `active_loadout`. Read ini
tidak membuat profile, wallet, item, atau attempt baru.

Endpoint internal yang sudah token-gated:

- `POST /api/boss/spawn` menerima `{"tier":"normal|elite|world","request_id":"..."}` ketika Phase 3 aktif; saat nonaktif tetap memakai Boss legacy.
- `POST /api/boss/settle` mengulang reward plan persisted untuk raid `AWAITING_FUNDS` dan tidak membuat drop atau payout plan baru.
- `GET /api/boss` menampilkan status raid Phase 3 hanya ketika ketiga flag aktif; selain itu tetap mengembalikan status legacy.

## Economy V1 Phase 4 Marketplace

`GET /api/economy/v1-marketplace` bersifat read-only dan mengembalikan status
flag, kesiapan schema, pause global, jumlah listing unresolved, dan purchase yang
memerlukan review. Endpoint tidak membuat row marketplace.

`POST /api/economy/v1-marketplace/action` wajib memakai `X-Auth-Token` dan fail
closed saat `DASHBOARD_TOKEN` kosong. Action staff yang didukung adalah
`reconcile`, `pause`, `resume`, `return`, dan `user-state`. Action `return` hanya
menerima listing ID; recipient selalu dibaca dari escrow authoritative. Semua
action memakai service yang sama dengan adapter Discord dan mencatat audit generik.
Principal internal marketplace dibuat server-side hanya setelah token valid. Payload
tidak dapat menetapkan Administrator, bot owner, atau `authorizationSource` sendiri.

Phase 4 tetap `false` secara default. Migration 400 tidak pernah dijalankan oleh
startup bot dan CLI menolak target database production.

## Economy V1 Phase 5 Casino

`GET /api/economy/v1-casino` bersifat read-only dan menampilkan status flag,
capability migration 500, bankroll, reservasi liability, exposure cap, sesi
unresolved, serta recovery review. Phase 5 tidak menambahkan API mutasi Casino.
Seed, adjustment, distribusi, pause, authorization, dan recovery hanya tersedia
melalui command staff Discord dan shared service layer.

`ECONOMY_PHASE5_ENABLED=false` adalah default. Migration `500 / phase5-casino`
bersifat eksplisit dan staging-only; startup tidak membuat schema Casino.

## Economy V1 Phase 6 Crypto

`GET /api/market` mengembalikan seri harga Crypto V1 global ketika Economy V1
dan Phase 6 aktif; saat Phase 6 nonaktif, respons legacy tetap dipertahankan.

`GET /api/economy/v1-crypto` bersifat read-only dan menampilkan capability
migration 600, kesiapan seed `ECY_MARKET`, Market Reserve guild utama, dan
snapshot harga. Tidak ada route API mutasi Crypto. Default
`ECONOMY_PHASE6_ENABLED=false`; migration `600 / phase6-crypto` tidak berjalan
otomatis saat startup.

## Economy V1 Phase 7 Mining

`GET /api/economy/v1-mining` adalah endpoint read-only untuk capability dan
status Mining guild utama. Tidak ada endpoint API mutasi Mining. Pembelian,
maintenance, target, klaim, authorization, pause, dan recovery hanya melalui
command Discord dan shared service layer. Default
`ECONOMY_PHASE7_ENABLED=false`; migration `700 / phase7-mining` eksplisit,
staging-only, dan tidak berjalan otomatis saat startup.

## Economy V1 Phase 8 Giveaway dan Eternal Options

`GET /api/economy/v1-phase8` adalah endpoint read-only untuk capability Eternal
Options, active positions, dan shared Casino exposure. Endpoint ini tidak memiliki
pasangan write API. Default `ECONOMY_PHASE8_ENABLED=false`; migration
`800 / phase8-giveaway-options` hanya dijalankan eksplisit pada staging.
