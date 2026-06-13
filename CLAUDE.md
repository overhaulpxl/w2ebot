# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Way 2 Eternal Bot (W2E) — a single-guild Discord bot combining Gemini AI chat, an RPG/economy game (market, mining, boss raids, casino), and dynamic Pillow image generation. Code comments, command responses, and docs are written in Indonesian; keep that convention.

## Running & Deploying

```bash
python main.py                      # local run (entry point)
run_all.bat                         # Windows shortcut
docker compose up -d --build        # Docker (mounts w2ebot.db as volume)
```

- There is no test suite, linter, or build step. Verify changes by tracing code paths mentally and, when possible, running the bot.
- FFmpeg must be on PATH for voice/listen features.
- A web API/dashboard runs on port `8081` (started as a background task in `on_ready`).
- Required env vars (`.env`): `DISCORD_TOKEN`, `GEMINI_API_KEY`, `ALLOWED_SERVER_ID` (default `887968847842402355`), `BOT_PREFIX` (default `w!`). Optional: `DASHBOARD_TOKEN` (auth token for state-changing web endpoints; empty = those endpoints fail closed), `ALLOWED_ORIGINS` (comma-separated CORS whitelist; empty = allow all, dev only).

## Architecture

`main.py` is the entry point only: it does `from core import *`, then calls `setup(tree, client)` from each cog (`cogs/rpg.py`, `cogs/ai.py`, `cogs/utils.py`), then `client.run()`. Do not put logic in `main.py`.

`core.py` is the heart of the bot (~1830 lines): DB schema, helpers, all `@client.event` handlers, background `@tasks.loop` jobs, the web API, and the dual-invocation command system. The cog `setup()` functions register `@tree.command()`s onto the shared tree.

### Dual invocation: slash + prefix (FakeInteraction)

Every command is written once as an `app_commands` slash command but works both as `/command` and as `w!command`. The `on_message` handler in `core.py` parses prefix messages, builds a `FakeInteraction` (wrapping `message` to mimic `discord.Interaction` with `.user`, `.guild`, `.channel`, `.response`, `.followup`), and inspects the callback signature to coerce positional string args into the parameter's annotated type (`int`, `float`, `discord.Member`, `discord.Role`).

Consequences for writing commands:
- All command parameters **must be typed annotations** or prefix parsing breaks.
- `FakeResponse`/`FakeFollowup` strip `ephemeral` (prefix mode can't do ephemeral) — don't rely on ephemeral being honored.
- Keep parameters simple/positional; complex Discord-native option types won't parse from prefix text.

### Single-guild lock

`on_ready` and `on_guild_join` auto-leave any guild whose ID ≠ `ALLOWED_SERVER_ID`. Commands are synced per-guild via `tree.copy_global_to(...)` + `tree.sync(guild=...)`, so new commands appear immediately on the allowed server without waiting for global propagation.

### Persistence — two patterns

1. **`DiscordStat` table** (structured player stats: coins, xp, level, lastDaily). Access via `get_discord_stat(uid)` / `update_discord_stat(...)`. Both helpers run the **O(1) quadratic level-up math** (`a=50, b=100*level-50, c=-xp`) automatically — don't reimplement level-up; for XP gains from messages/activity use `check_level_up(channel, user, xp_gained)`.
2. **`json_store` table** (key-value JSON blobs for game data like `family.json`, `items.json`, `market.json`, `boss.json`, etc.). Access via `load_json(FILE)` / `save_json(FILE, data)`. These are cached in the in-memory `_json_cache` dict for O(1) reads and synced to SQLite on write. File-name constants live at the top of `core.py`.

A third table `ChatMemory` stores AI chat history.

### Async DB rule

Always use `aiosqlite` inside async functions (`async with aiosqlite.connect(DB_PATH) as db`). The only sync `sqlite3` use is `_init_db()` at import time for schema creation — never use sync `sqlite3` or `time.sleep()` in async code paths.

### Background loops

`on_ready` launches several `client.loop.create_task(...)` jobs: web server, birthday checker, market price updates, voice salary, boss raid, crypto mining. A `@tasks.loop(minutes=30)` `clean_caches` job prunes expired in-memory cooldown dicts (`rob_cooldowns`, `work_cooldowns`, `boss_cooldowns`, `voice_join_times`).

### AI

Gemini is called via `gemini_client.models.generate_content` wrapped in `asyncio.to_thread(...)` (the SDK is sync). Model: `gemini-2.5-flash`. `check_toxicity(text)` uses it for a SAFE/TOXIC moderation check.

### Announcement channels

For any announcement the bot posts (market events, level-ups, birthdays, boss raids, booster joins, Binomo results), resolve the target channel via `get_announce_channel(guild, category)` in `core.py` — do **not** re-implement the general/chat channel search. Categories are listed in `ANNOUNCE_CATEGORIES` = `['market', 'levelup', 'birthday', 'boss', 'booster', 'binomo']`. Resolution order: `config.json` → `announce_channels[category]` → `announce_channels['default']` → legacy `booster_channel_id` (booster only) → fallback search for a writable `general`/`chat` channel. Empty config = automatic fallback, so it's safe out of the box.

### Web API

Endpoints live in `core.py` and are registered in `start_web_server` (port `8081`). State-changing routes (`POST /api/config`, `POST /api/announce-config`, `POST /api/broadcast`) guard with `require_token(request)` (compares `X-Auth-Token` header to `DASHBOARD_TOKEN` via `hmac.compare_digest`, fail-closed when the token is unset). CORS is handled by `cors_middleware` using the `ALLOWED_ORIGINS` whitelist. See `API.md` for the full endpoint contract.

## File ownership

| File | Responsibility |
|---|---|
| `core.py` | DB, helpers, FakeInteraction, events, background loops, web API |
| `cogs/rpg.py` | Game mechanics, economy, gambling, mining, boss raid |
| `cogs/ai.py` | Gemini chat, persona, memory, roast/rate/image |
| `cogs/utils.py` | Non-game utilities (ping, poll, giveaway, remindme, birthday) |
| `main.py` | Entry point only |
| `w2e_help.py` | Help menu UI — update when adding commands |
| `w2e_views.py` / `embedder.py` | Shared Discord UI views/buttons and embed helpers |
| `migrate_db.py`, `migrate_gemini.py` | One-off migration scripts |

## Conventions

- New shared utilities go in `core.py`; cogs import what they need (`from core import *` is done once in `main.py`).
- Add new commands inside the existing `setup(tree, client)` of the appropriate cog.
- New JSON data: add a file-name constant in `core.py`; new tables: add `CREATE TABLE IF NOT EXISTS` to `_init_db()`.
- Shop items live in the `SHOP_ITEMS` dict; daily quest templates in `QUEST_TEMPLATES` — both in `core.py`.
- New imports must be added to `requirements.txt`.
- Embed color scheme: info `0x5865F2`, success `0x57F287`, warning `0xFEE75C`, error `0xED4245`, premium `0xFFD700`.
