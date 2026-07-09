# Way 2 Eternal Bot (W2E)

Single-guild Discord bot — **Gemini AI chat** + **RPG/economy** + **Pillow image generation** + **aiohttp web API** for external dashboard integration.

Built with **discord.py** (App Commands + Prefix via FakeInteraction), **aiosqlite**, and **Google Gemini 2.5 Flash**.

---

## Quick Start

### Prerequisites
- Python 3.10+
- FFmpeg on PATH (for voice/listen features)
- Discord Bot Token + Gemini API Key

### Install & Run
```bash
git clone https://github.com/overhaulpxl/w2ebot.git
cd w2ebot
pip install -r requirements.txt
python main.py
```

On Windows: double-click `run_all.bat`.

### Docker
```bash
touch w2ebot.db
docker compose up -d --build
```

### Environment (`.env`)
```env
# Required
DISCORD_TOKEN=
GEMINI_API_KEY=
ALLOWED_SERVER_ID=887968847842402355
BOT_PREFIX=w!

# Optional — Web API & Dashboard
DASHBOARD_TOKEN=              # Auth token for write endpoints. Empty = write disabled (fail closed).
ALLOWED_ORIGINS=              # Comma-separated CORS whitelist. Empty = allow all (dev only).
AI_AUTO_REPLY_CHANNEL_ID=0    # Channel where bot auto-replies without prefix. 0 = disabled.
```

### Repository Hygiene
Local runtime files are intentionally ignored by git:
- `.env` and `.env.*` except `.env.example`
- SQLite runtime files such as `w2ebot.db`, `*.db-wal`, and `*.db-shm`
- logs, backups, Python caches, dashboard build output, and local agent/editor folders

Do not commit production tokens, live databases, proof/payment images, or bot logs.

---

## Architecture

| File | Role |
|---|---|
| `main.py` | Entry point only — imports `core`, registers cogs, calls `client.run()`. |
| `core.py` | DB schema, atomic economy helpers, event handlers, background loops, web API, FakeInteraction prefix system. |
| `cogs/rpg.py` | RPG/economy/gambling/mining/boss/crypto commands. |
| `cogs/ai.py` | Gemini AI chat, persona, roast/rate/shipper. |
| `cogs/utils.py` | Utilities: ping, poll, giveaway, remindme, birthday, marriage, bg. |
| `cogs/deal.py` | Middleman transaction system, trust profiles, vouches, and admin panels. |
| `w2e_help.py` | Interactive help menu (dropdown + buttons). |
| `w2e_views.py` | Shared UI views (shop/slot/market button callbacks). |

---

## Features

Most commands work as both **Slash** (`/daily`) and **Prefix** (`w!daily`) through the FakeInteraction dispatcher. Middleman fallback commands stay under `/deal ...` and `w!deal ...` so RPG and trust command ownership remains clear.

### RPG & Economy
`daily`, `weekly`, `work`, `profile`, `shop`, `buy`, `sell`, `inventory`, `rob`, `transfer`, `top`, `pray`, `curse`, `quest`

### Crypto Market
`market`, `portfolio`, `buycoin <symbol> <jumlah>`, `sellcoin <symbol> <jumlah>`, `buyrig <tier>`, `miner`

- 7 fictional coins with 10-min price updates + random pump/dump events.
- Buy/sell with coins as universal currency. **2% fee** (both directions) goes to community treasury.
- Mining rigs earn ETHR passively every hour.

### Gambling & Casino
`slot`, `blackjack`, `cf`, `rps`, `crash`, `tebak`, `gacha`, `box`

All bets use atomic `try_spend` (no double-spend via concurrent commands). Minigame statistics tracked per-player (plays, wins, losses).

### Boss Raid
`attack`, `buypet <slime/wolf/dragon>`

Boss spawns hourly (20% chance) or via admin API. Pets add bonus damage.

### Middleman & Trust System
`deal`, `vouches`, `vouchleaderboard`, `w!deal leaderboard`, `w!deal rank`

- **Secure Transactions & Access Model**: Full-featured middleman system for buyer, seller, assigned middleman, staff, admin, and owner-role workflows. Buttons remain the normal shared UI, while command fallback exists for stale/deleted/broken button messages.
- **Workflow & Proofs (Simplified)**: Deal form -> private payment instruction -> buyer payment proof -> Dana Masuk -> Buyer Confirm -> seller payout data -> transfer proof/Done. The legacy "Item Sent" stage is skipped for new deals and only retained for old-row compatibility.
- **Button + Command Fallbacks**: Staff can inspect or continue a deal with `/deal status`, `/deal next`, `/deal action`, `/deal refresh`, and `/deal recover`; prefix equivalents are available as `w!deal status`, `w!deal next`, `w!deal action`, `w!deal refresh`, and `w!deal recover`.
- **Per-User Payment Profile Config (`/deal payment-config`)**: Each middleman/admin configures their own payment profile by guild + user. Payment instructions can contain text, QRIS/image, or image-only details and are only posted in private deal channels or staff-only/ephemeral/DM previews.
- **Public Trust Panels (`/deal panel`)**: Set up public tracking boards including trusted vouch leaderboards, server trust stats, recent vouches feed, completed deals feed, middleman status panels, active deal queues, and dispute boards.
- **Vouch & Scam Panels**: Public vouch submission panel (`/deal vouch-panel setup`) and scam reporting panel (`/deal scam-report-panel setup`).
- **Button Recovery**: `/deal recover-buttons` performs broad recovery, while `/deal recover` targets one deal and repairs the current canonical UI without exposing payment, proof, payout, credentials, evidence, or notes.
- **Trust Profile**: Earn verified vouches from successful deals, increase Trust Score, and climb the Trust Rank ladder.
- **Admin & Safety**: Review manual vouches, resolve disputes, and monitor active deals.

### AI & Social
`ai`, `chat`, `setpersona`, `roast`, `rate`, `shipper`, `image`, `quiz`, `listen`

`marry`, `divorce`, `adopt`, `family` — virtual marriage + family tree (Pillow-rendered image).

### Utilities
`help`, `ping`, `poll`, `giveaway`, `find`, `checkbots`, `remindme`, `birthday`, `bg`, `kas`, `valo`, `hunt`

- **Reminders & giveaways are persisted** to DB and re-scheduled on restart (overdue reminders fire immediately).

---

## Web API & Dashboard

On startup the bot launches an HTTP server on port **8081**. Full endpoint contract with curl examples lives in **[`API.md`](API.md)**.

### Read endpoints (open, no token)
| Endpoint | Purpose |
|---|---|
| `GET /api/server` | Guild info (name, members, channels, roles, boosts) |
| `GET /api/radar` | Members in voice + duration |
| `GET /api/channels` | Text channel list (for dropdowns) |
| `GET /api/leaderboard` | Top players (sort by coins/level, limit 1-100) |
| `GET /api/user/{id}` | Full profile: coins, xp, level, rank, crypto, rigs, items, pet, achievements, marriage, cooldowns, games, top_games, persona, birthday, bounty, quest |
| `GET /api/market` | Crypto prices + 10-point history |
| `GET /api/treasury` | Community treasury balance |
| `GET /api/boss` | Boss raid state |
| `GET /api/bot/stats` | Latency, uptime, guild detail, economy aggregates |
| `GET /api/economy/stats` | Total coins, player count, avg level, top holder |
| `GET /api/economy/level-distribution` | Player count per level (for charts) |
| `GET /api/marriages` | Married pairs (names resolved) |
| `GET /api/stats/summary` | One-call summary (members, voice, boss, treasury, coins) |
| `GET /api/config` | Raw config.json |
| `GET /api/announce-config` | Announcement channel mapping |

### Write endpoints (require `X-Auth-Token`)
| Endpoint | Purpose |
|---|---|
| `POST /api/user/{id}/coins` | Adjust or set coins |
| `POST /api/user/{id}/xp` | Add XP (level-up auto) |
| `POST /api/user/{id}/give-item` | Grant shop item |
| `POST /api/user/{id}/reset-cooldown` | Reset work/rob/pray/curse/daily/all |
| `POST /api/user/{id}/persona` | Set/reset AI persona |
| `POST /api/user/{id}/birthday` | Set/remove birthday |
| `POST /api/user/{id}/bg` | Set/remove profile background (SSRF-guarded) |
| `POST /api/user/{id}/divorce` | Admin force-divorce |
| `POST /api/user/{id}/bounty` | Set/remove bounty |
| `POST /api/user/{id}/reset-weekly` | Reset weekly claim |
| `POST /api/user/{id}/reset-quest` | Reset quest progress |
| `POST /api/boss/spawn` | Force-spawn boss (409 if active) |
| `POST /api/announce` | Broadcast to announce category |
| `POST /api/announce-config` | Set channel per category |
| `POST /api/broadcast` | Send message to any channel |
| `POST /api/config` | Overwrite config.json |
| `GET /api/audit` | Audit log of all admin writes (token-gated) |

Every write action is logged to the `AuditLog` table with timestamp, action, target, and detail.

### Announcement Channels

6 categories (`market`, `levelup`, `birthday`, `boss`, `booster`, `binomo`) + `default` fallback. Resolution: category channel → default → auto-search `general`/`chat`.

### Integration Pattern

```
Browser (external dashboard)
   └─> Your backend (keeps DASHBOARD_TOKEN secret)
          └─> https://api.way2eternal.com/api/...
                 └─> W2E bot :8081
```

Never expose `DASHBOARD_TOKEN` to the browser. A Next.js example dashboard is included in `dashboard-example/`.

---

## Dashboard Example (`dashboard-example/`)

A ready-to-use **Next.js 14 App Router** admin dashboard with:
- Liquid glass UI (dark theme, glassmorphism, animated background blobs)
- CRM-style sidebar navigation (Ringkasan, Statistik Bot, Analitik, Pemain, Ekonomi, Server & Admin, Audit Log)
- Charts (recharts): market price trends + level distribution
- User detail page (`/user/[id]`): full profile + top 3 minigame + admin controls
- All write actions proxied through Next.js Route Handlers (token stays server-side)
- Zero external CSS frameworks (pure CSS design tokens)

Setup: see `dashboard-example/README.md`.

---

## Economy System

- **Single wallet**: `DiscordStat.coins` is the only source of truth.
- **Atomic operations**: `try_spend(uid, amount)` for purchases/bets, `add_coins(uid, amount)` for rewards. No read-modify-write races.
- **Crypto**: buy/sell via `/buycoin`/`/sellcoin` with 2% fee to treasury. Holdings in `users.json[uid]['crypto']`.
- **Mining**: rigs earn ETHR hourly, stored in `users.json[uid]['rigs']`.
- **Minigame tracking**: `record_game(uid, game, won)` after every game result → `users.json[uid]['games']`.

---

## Database

SQLite (`w2ebot.db`) with tables:
- `DiscordStat` — coins, xp, level, lastDaily per user
- `ChatMemory` — AI conversation history
- `Reminder` — persisted reminders (survive restart)
- `Giveaway` — persisted giveaways (survive restart)
- `AuditLog` — admin action audit trail
- `json_store` — key-value blob storage for JSON data files
- **Middleman & Reputation Tables**:
  - `Deal`, `DealLog`, `DealConfig`, `dealAuditLogConfig` — Core deal details, logs, configs, and audit channel settings
  - `dealPaymentProfiles` — Persistent payment configurations (payment instructions & QRIS images) per middleman/admin
  - `Vouch`, `VouchReport`, `UserReputation`, `trustModerationStatus` — User reputation details, vouches, vouch/reputation reports, and moderation settings
  - `dealPanels`, `dealPanelEvents`, `middlemanStatus` — Settings and state events for public trust boards & active middleman queue
  - `manualVouchReviewConfig`, `manualVouchPanelConfig` — Settings for manual vouch submission panels & review flows
  - `scammerReports`, `scamReportReviewConfig`, `scamReportPanelConfig` — Scam reports and review/submission panel configurations
  - `DealNote`, `DealReminderLog` — Staff notes and reminder dispatch logs for deals
  - `dealArchives` — Archival storage for ended/canceled deals
  - `rateLimitEvents` — Track rate limits to prevent reputation review spam

---

## Logging

All significant actions are logged to console with tags:
- `[CMD]` — command invocations (slash + prefix)
- `[ECONOMY]` — every coin mutation with resulting balance
- `[XP]` — XP gains
- `[LEVELUP]` — level-up events
- `[TREASURY]` — fee deposits
- `[BOSS]` — raid spawns
- `[MINING]` — hourly mining results
- `[MARKET]` — pump/dump events
- `[RESUME]` — reminders/giveaways re-scheduled on startup
- `[SETTING]` — persona/bg/bounty changes via API
- `[ITEM]` / `[COOLDOWN]` — admin item grants / cooldown resets

---

*Copyright © Way 2 Eternal Community.*
