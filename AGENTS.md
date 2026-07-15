# AGENTS.md

Way 2 Eternal Bot (W2E): single-guild Discord bot — Gemini AI chat + RPG/economy + Pillow image generation + small aiohttp web API.

Detailed architecture lives in `CLAUDE.md` (read it first). This file only captures the gotchas an agent would otherwise miss.

## Living PRD Workflow

`docs/project_state.json` is the repository's machine-readable Living PRD and
`docs/AI_CODER_HANDOFF.md` is generated output. Do not edit the generated file
manually. Every task that changes behavior, architecture, schema, migrations,
commands, tests, feature flags, rollout state, commits, blockers, staging,
production, or project progress is incomplete until the Living PRD is updated.

Before completing such a task:

1. Read `docs/AI_CODER_HANDOFF.md` and inspect Git status, branch, and the relevant baseline.
2. Implement the requested change and run its required verification.
3. Update `docs/project_state.json` with current state plus task history.
4. Run `python scripts/update_ai_handoff.py` and review the generated handoff.
5. Include `project_state.json` and `AI_CODER_HANDOFF.md` in the same change set and mention the Living PRD update in the final report.

If repository source, migration, tests, or command registration disagrees with
the handoff, investigate and report the mismatch before changing behavior. The
source-of-truth order is committed constraints, tests, service implementation,
runtime configuration/command registration, project state, generated handoff,
historical reports, then chat history.

## Commands

```bash
python main.py                 # run locally (entry point)
run_all.bat                    # Windows shortcut (same thing)
docker compose up -d --build   # Docker; mounts ./w2ebot.db as a volume
```

- No tests, no linter, no build/typecheck step. Verify changes by tracing code paths and, when possible, running the bot. Do not invent a test command.
- FFmpeg must be on PATH for voice/`listen` features.
- Web API/dashboard serves on port `8081`, launched as a background task in `on_ready`.
- Required `.env`: `DISCORD_TOKEN`, `GEMINI_API_KEY`, `ALLOWED_SERVER_ID` (default `887968847842402355`), `BOT_PREFIX` (default `w!`). The Phase 9A dashboard additionally requires HTTPS OAuth, session-hash, internal-signing, and IP-hash key configuration. Raw key material must never be committed.

## Where code goes

- `main.py` is entry point ONLY (`from core import *`, calls each cog's `setup(tree, client)`, then `client.run()`). Never add logic here.
- `core.py` (~1830 lines) = DB schema, helpers, all `@client.event` handlers, background `@tasks.loop` jobs, web API, the FakeInteraction prefix system. New shared utilities go here.
- Commands go inside the existing `setup(tree, client)` of the matching cog: `cogs/rpg.py` (game/economy/gambling/mining/boss), `cogs/ai.py` (Gemini/persona/memory), `cogs/utils.py` (ping/poll/giveaway/remindme/birthday).
- `w2e_help.py` must be updated when adding/removing commands. `w2e_views.py` / `embedder.py` hold shared UI views and embed helpers.

## Non-obvious rules

- **Every command parameter must be a typed annotation.** Prefix parsing (`w!cmd`) reads the callback signature via `FakeInteraction` to coerce string args into `int`/`float`/`discord.Member`/`discord.Role`. Untyped or complex Discord-native option types break prefix mode. `ephemeral` is silently stripped in prefix mode.
- **Prefix mode bypasses the slash framework.** `on_message` invokes the raw command callback directly, so `@app_commands.checks`, cooldowns, and `default_permissions` do NOT run for `w!` commands. Permission gates must be re-checked manually inside the callback (e.g. `interaction.user.guild_permissions.administrator`, as `kas`/`giveaway` do) — decorator-only checks are not enough.
- **`remindme` and `giveaway` are now persisted** to the `Reminder` / `Giveaway` tables and re-scheduled in `on_ready` via `resume_scheduled_jobs()`. Commands still `asyncio.sleep` for the live timer, but the DB row is the source of truth on restart (overdue reminders fire immediately). Use `add_reminder`/`schedule_reminder` and `add_giveaway`/`schedule_giveaway` in `core.py`; rows are deleted/marked `ended` after firing.
- **Async DB:** always `aiosqlite` inside async (`async with aiosqlite.connect(DB_PATH)`). The only sync `sqlite3` use is `_init_db()` at import. Never use sync `sqlite3` or `time.sleep()` in async paths.
- **Two persistence patterns:** structured player stats → `DiscordStat` table via `get_discord_stat`/`update_discord_stat` (these auto-run the level-up math — don't reimplement it; for XP gains use `check_level_up`). Game data → `json_store` key-value blobs via `load_json(FILE)`/`save_json(FILE, data)`, cached in `_json_cache`. File-name constants live at the top of `core.py`; add a constant for any new JSON file.
- **Coins are money — mutate them ATOMICALLY only.** Never do `stat = get_discord_stat()` → `stat['coins'] += x` → `update_discord_stat(...)`; that read-modify-write races (double-spend via concurrent prefix+slash) and `update_discord_stat`'s absolute write can resurrect already-spent coins. Use the atomic helpers in `core.py`: `try_spend(uid, amount)` (conditional debit, returns `False` if insufficient — use for ALL purchases/bets/costs), `add_coins(uid, amount)` (credit winnings/rewards), `add_xp(uid, name, xp)`, `set_last_daily(...)`. `update_discord_stat` is now only for non-coin fields. The single wallet of record is `DiscordStat.coins`; `users.json['balance']` is dead — do not write it.
- **Crypto/mining lives in `users.json`.** Rigs at `users[uid]['rigs']` (`{tier: count}`), holdings at `users[uid]['crypto']` (`{symbol: amount}`). The legacy `rigs.json`/`portfolio.json` files are unused — don't reintroduce them. Crypto is bought/sold with coins via `/buycoin`/`/sellcoin`: debit with `try_spend`, credit with `add_coins`, and a 2% fee (`CRYPTO_FEE_RATE`) goes to the treasury via `add_treasury`. Buy adds holding only after a successful atomic debit; sell decrements holding (and saves) before crediting coins.
- **Treasury (`treasury.json`, `{'balance': N}`)** is a JSON blob — use `add_treasury(amount)` to credit it. Not as atomic as `DiscordStat.coins`, but only fees flow in (low risk). `/kas` reads it.
- **Minigame tracking:** use `record_game(uid, game, won)` (in `core.py`) after every minigame result. Stores `users[uid]['games'][game] = {plays, wins, losses}`. Games tracked: `slot`, `blackjack`, `cf`, `rps`, `crash`, `tebak`, `gacha`, `box`, `hunt`. Exposed via `/api/user/{id}` as `games` + `top_games`.
- **Announcements:** always resolve target channel via `get_announce_channel(guild, category)`. Don't re-implement channel search. Categories: `market`, `levelup`, `birthday`, `boss`, `booster`, `binomo`.
- **Dashboard API safety:** `GET /healthz` is the only public data route. Legacy `/api/*` reads and writes are unconditional `410` tombstones. Sensitive reads are available only through strict signed `/internal/phase9a/*` routes after current session, Discord membership, and permission validation. Browser code must call authenticated Next.js proxies and must never call aiohttp directly. Security mutations use `DashboardControlledOperation` plus append-only Phase 9A audits; never restore `DASHBOARD_TOKEN` access or add arbitrary internal path forwarding. Full contract in `API.md`.
- New tables: add `CREATE TABLE IF NOT EXISTS` to `_init_db()`. New imports: add to `requirements.txt`.
- Embed colors: info `0x5865F2`, success `0x57F287`, warning `0xFEE75C`, error `0xED4245`, premium `0xFFD700`.

## Conventions

- Comments, command responses, and user-facing docs are written in **Indonesian** — keep that.

## Stale / do-not-run

- `setup_dashboard.py` and `lock_bot.py` are one-off codegen scripts that patch a file named `bot.py`. That file no longer exists (it became `core.py`). Do NOT run them — they will crash and their logic is already baked into `core.py`.
- `Dockerfile` line 11 `pip install`s extra packages (`yt-dlp`, `bs4`, etc.) not all of which are in `requirements.txt`. If adding imports, keep both in sync.
- `migrate_db.py` / `migrate_gemini.py` are one-off migrations, not part of normal runs.
