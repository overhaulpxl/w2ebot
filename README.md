# Way 2 Eternal Bot (W2E) 🤖✨

Way 2 Eternal Bot is a modern, *Enterprise/Cloud-Ready* Discord bot that blends **Artificial Intelligence (Gemini 2.5 Flash)**, a **Sultan-tier RPG & Economy System (Market 3.0)**, and **dynamic image generation with Pillow**, all stored safely in a relational **SQLite** database.

The bot uses a **Modular Cogs (discord.py)** architecture for maximum scalability, managing dozens of commands in a structured way (RPG, AI, Utils) with high performance thanks to asynchronous query optimization via `aiosqlite`.

---

## 🌟 Project Overview

This project was built for Discord communities that want a complete feature set in a single bot without having to invite many different bots. Highlights include:
1. **AI Chat & Persona**: Chat like a human with custom language styles (Gen-Z, weeb, etc.). Chat memory is stored permanently.
2. **RPG & Economy**: A stock-market simulation (Market), crypto mining (Mining Rigs), Boss Raids, casino gambling, and inventory management.
3. **Social & Visual**: Virtual marriage, child adoption, plus dynamically generated Family Trees and profile cards rendered with Pillow.
4. **Hybrid Command System**: Supports native Discord **Slash Commands** (`/`) and, magically, also **Prefix Commands** (`w!`) thanks to an internal `FakeInteraction` system that translates plain text messages into Slash Command execution.

---

## 🛠️ Setup & Installation Steps

### Prerequisites
* **Python 3.10** or higher
* **FFmpeg** (for the voice listener/music) installed on your OS PATH
* A Discord Bot Token & a Gemini API Key

### Local Installation
1. **Clone the repository & install dependencies**:
   ```bash
   git clone https://github.com/overhaulpxl/w2ebot.git
   cd w2ebot
   pip install -r requirements.txt
   ```

2. **Environment configuration (`.env`)**:
   Create a `.env` file in the project root:
   ```env
   DISCORD_TOKEN=YOUR_DISCORD_BOT_TOKEN
   GEMINI_API_KEY=YOUR_GEMINI_AI_KEY
   ALLOWED_SERVER_ID=887968847842402355
   BOT_PREFIX=w!

   # Optional — Web Dashboard / API
   DASHBOARD_TOKEN=          # Auth token for state-changing API endpoints. Empty = those endpoints are disabled (fail closed).
   ALLOWED_ORIGINS=          # Comma-separated CORS whitelist (e.g. https://way2eternal.com). Empty = allow all (dev only).
   ```

3. **Run the bot**:
   On Windows: double-click `run_all.bat`, or run:
   ```bash
   python main.py
   ```

### Docker Installation (Production)
The bot is configured to run directly in Docker using `docker-compose.yml`.
```bash
# Create an empty database file first
touch w2ebot.db

# Run the container in the background
docker compose up -d --build
```

---

## 🌐 Web Dashboard & API

On startup the bot launches a small HTTP server (aiohttp) on port **`8081`** as a background task in `on_ready`. It serves:
* A **control dashboard** at `http://localhost:8081` for configuring announcement channels.
* A **REST API** that the external **way2eternal main website** can consume to read live server state and update settings.

State-changing endpoints (`POST /api/config`, `POST /api/announce-config`, `POST /api/broadcast`) require the header `X-Auth-Token: <DASHBOARD_TOKEN>`. If `DASHBOARD_TOKEN` is empty, those endpoints fail closed (always `401`). When hosting the website on a different domain, set `ALLOWED_ORIGINS` to that origin and put the bot behind an HTTPS reverse proxy.

👉 Full endpoint contract, request/response shapes, integration pattern, and `curl` examples live in **[`API.md`](API.md)**.

### Announcement Channels

The bot posts several kinds of announcements; each can be routed to its own channel via the dashboard or the API. The 6 categories are:

| Category | What it announces |
|---|---|
| `market` | Crypto market pump/dump events |
| `levelup` | Level-ups earned from voice activity |
| `birthday` | Birthday celebrations |
| `boss` | Boss raid spawns |
| `booster` | Server boosters joining a voice channel |
| `binomo` | Binomo gambling results |

Resolution order for each category: the per-category channel → the `default` channel → the legacy `booster_channel_id` (booster only) → an automatic search for a writable `general`/`chat` channel. Leaving a category empty simply falls back, so the bot works out of the box with no configuration.

---

## 🏗️ How Each Function / Core Component Works

The W2E Bot architecture is split into several main components to separate logic and ease maintenance:

1. **`main.py` (Entry Point)**:
   The main launcher. Loads the base configuration module, imports `core.py`, and registers all sub-modules (Cogs) from the `cogs/` folder (such as `rpg`, `ai`, and `utils`).
2. **`core.py` (Core Library & Database)**:
   The heart of the bot. It manages the `aiosqlite` database connection, JSON/dictionary helpers (`load_json`, `save_json` with the in-memory `_json_cache` for O(1) reads), Intent configuration (including `message_content`), the web API, and the main event listeners such as `on_ready` and `on_message`.
3. **`FakeInteraction` (Prefix Wrapper)**:
   Located in `core.py`, this class intercepts incoming `on_message` messages that start with `BOT_PREFIX`. It "pretends" to be a `discord.Interaction` to satisfy slash command arguments, so members can call Slash Command functions using plain text.
4. **`cogs/rpg.py`**:
   Handles all games, math, gambling, the shop, boss raids, and crypto mining.
5. **`cogs/ai.py`**:
   Handles API requests to Google Gemini 2.5 Flash, conversation history (memory), persona commands, and sentiment analysis (*roasting*, *rate*, *shipper*).
6. **`cogs/utils.py`**:
   Daily utilities such as latency check (`ping`), voting (`poll`), giveaways, reminders (`remindme`), plus bot/player radar (`find`, `checkbots`).

---

## 📘 List of All Features / Commands

Below is the full list of all 54 available commands. Every command can be invoked using a **Prefix** (e.g. `w!help`) or a **Slash** (e.g. `/help`).

### Category A: RPG & Economy
* **`daily`** - Claim your daily coins and XP.
* **`weekly`** - Claim your weekly coin allowance.
* **`work`** - Work to mine coins.
* **`profile`** - Show a full profile card image with level and assets.
* **`shop`** - Open the W2E shop UI.
* **`buy <item>`** / **`sell <item>`** - Item transactions.
* **`inventory`** - Check your bag and active buffs.
* **`rob @user`** - Steal coins from another member.
* **`transfer @user <amount>`** - Send coins safely.
* **`top`** - Show the leaderboard (richest & highest level).
* **`buyrig <tier>`** - Buy a mining machine for passive income.
* **`miner`** - Check your mining machine efficiency.
* **`market`** - Check the rise and fall of the fictional crypto currencies.
* **`portfolio`** - Check your total crypto investment assets.
* **`quest`** - View your daily/weekly mission progress.
* **`attack`** - Attack the raid boss together.
* **`buypet <pet>`** - Buy a pet to increase your attack power.

### Category B: Gambling & Casino
* **`cf <choice> <bet>`** - Coin flip, guess heads/tails.
* **`flip`** - Flip a regular coin.
* **`slot`** - Spin the fruit slot machine.
* **`blackjack <bet>`** - Classic card gambling against an AI dealer.
* **`tebak <number>`** - Number-guessing gamble (1-10).
* **`crash <bet>`** - Bet on a rising graph before it crashes!
* **`gacha`** - Open a paid waifu-item gacha roll.
* **`box`** - Open a Mystery Loot Box.
* **`rps`** - Play rock-paper-scissors.

### Category C: AI & Social
* **`ai <message>`** - Smart chat with Gemini.
* **`chat <message>`** - Casual chat without the AI framing.
* **`setpersona <trait>`** - Change the AI reply personality (fierce, weeb, wise, etc.).
* **`listen`** - The AI records and replies to your Voice Channel conversation.
* **`roast @user`** - The AI roasts the target sarcastically and humorously.
* **`rate @user`** - The AI rates how attractive someone is from 1-10.
* **`image`** - The AI generates an image from text (*prompt*).
* **`shipper @user1 @user2`** - Predict relationship compatibility (Love Card image).
* **`marry @user`** / **`divorce`** - Virtual server marriage.
* **`adopt @user`** / **`family`** - Adopted-child relationships and family-tree visualization.

### Category D: Utilities
* **`help`** - Open this interactive help menu.
* **`ping`** - Check the bot's ping (latency).
* **`poll <question>;<options>`** - Create a voting/polling system for the community.
* **`giveaway`** - Run a time-limited giveaway (Admin only).
* **`find @user`** - Find out which Voice Channel a target is hanging out in.
* **`checkbots`** - Check all music bots currently playing in the server.
* **`remindme <minutes> <message>`** - A reminder alarm from the bot.
* **`birthday <date>`** - Set your birthday for a surprise.
* **`bg <url>`** - Change the background (banner) image of your RPG profile card.
* **`kas`** - Check the admin server treasury (tax vault) balance.
* **`valo`** - Ping fellow server members to play Valorant together.

---

## 🎮 Example Usage

Here are some fun scenarios you can try with the W2E Bot:

**Scenario 1: Getting Rich off Fictional Crypto**
> **Player:** `w!buyrig 2` *(Buys a Tier 2 Mining Rig for an expensive amount of coins)*
> **Player:** `w!miner` *(Checks the machine's hashing speed, then waits for payday)*
> **Player:** `w!market` *(Waits for the ETHR price to dip red, then buys it in bulk)*
> **Player:** `w!portfolio` *(Enjoys the green chart as the ETHR price spikes and sells it!)*

**Scenario 2: Emotional Interaction with the AI**
> **User:** `w!setpersona A grumpy housemaid named Inem`
> *(The AI changes its character in the database memory)*
> **User:** `w!chat make me some coffee, Nem`
> **Bot:** *(Replies angrily)* "Make it yourself! You think I'm a free robot servant? Coffee's in the drawer, hot water's in the dispenser, why wait for me, you lazy boss!"
> **User:** `w!roast @Joko`
> **Bot:** "Joko? Your face looks like a construction worker who got lost. You'd be better off as a dock laborer lol."

**Scenario 3: Surviving Through Dangerous Gambling**
> **Player:** `w!crash 10000` *(Wagers 10 thousand coins)*
> *(The graph starts climbing: 1.2x... 1.5x... 1.8x)*
> *(Player clicks the Stop button)*
> *(The graph crashes at 1.9x)*
> **Bot:** "Congratulations! You escaped at 1.8x and won 18,000 coins!"

---

*Copyright © Way 2 Eternal Community. Developed with ♥ by the W2E Dev Team.*
