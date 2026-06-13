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

# Set announcement config (needs token)
curl -X POST http://localhost:8081/api/announce-config \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"market":"1332111384523309156","default":"","levelup":"","birthday":"","boss":"","booster":"","binomo":""}'

# Without token -> 401
curl -X POST http://localhost:8081/api/announce-config \
  -H "Content-Type: application/json" -d '{}'
# {"error": "unauthorized"}

# Broadcast a message (needs token)
curl -X POST http://localhost:8081/api/broadcast \
  -H "Content-Type: application/json" -H "X-Auth-Token: YOUR_TOKEN" \
  -d '{"channel":"1332113600894079131","message":"Halo!"}'
```
