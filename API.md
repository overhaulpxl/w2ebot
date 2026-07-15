# W2E Bot Web API

Phase 9A replaces the legacy public dashboard API with an authenticated Next.js
boundary and signed internal aiohttp requests. See
`docs/PHASE9A_BACKEND_SAFETY_PRD.md` for the complete security contract.

## Public Aiohttp Surface

| Method | Path | Result |
| --- | --- | --- |
| `GET` | `/healthz` | Exactly `{\"status\":\"ok\"}` |
| `GET` | `/` | Redirect to configured HTTPS dashboard `/login`, otherwise `503` |

No guild, user, configuration, path, database, version, migration, audit, or
operational information is public.

Every legacy `/api/*` read returns `410 legacy_dashboard_read_disabled`. Every
legacy dashboard write returns `410 legacy_dashboard_write_disabled`.
`DASHBOARD_TOKEN` is deprecated and cannot restore those routes.

## Browser-Facing Next.js Routes

Auth routes are the only unauthenticated routes:

- `GET /api/auth/login`
- `GET /api/auth/callback`

Session routes:

- `GET /api/auth/session`
- `GET /api/auth/csrf`
- `POST /api/auth/logout`

Security administration:

- `GET /api/admin/operators`
- `POST /api/admin/operators/grant`
- `POST /api/admin/operators/revoke`
- `POST /api/admin/sessions/revoke`
- `GET /api/admin/audit`
- `GET /api/admin/security-events`
- `GET /api/admin/phase9a/health`

Authenticated reads use:

- `GET /api/dashboard/read/[...resource]`

Every page and every non-auth route validates the server-side session. Browser
writes require one-time CSRF, request identity, and expected version when
applicable. Browser JavaScript never receives backend signing keys or raw session
tokens and never calls aiohttp directly.

## Signed Internal Aiohttp Routes

All internal routes are `POST`, reject browser origins, and require a short-lived
HMAC envelope:

- `/internal/phase9a/oauth/start`
- `/internal/phase9a/session/establish`
- `/internal/phase9a/session/validate`
- `/internal/phase9a/session/rotate`
- `/internal/phase9a/session/logout`
- `/internal/phase9a/session/revoke`
- `/internal/phase9a/csrf/issue`
- `/internal/phase9a/operators/list`
- `/internal/phase9a/operators/grant`
- `/internal/phase9a/operators/revoke`
- `/internal/phase9a/audit/list`
- `/internal/phase9a/security-events/list`
- `/internal/phase9a/health`
- `/internal/phase9a/read/{allowlistedResource}`

The backend independently validates the signature, nonce, route, method, payload,
session, current Discord membership, guild, and required permission.

## Read Allowlist

The strict resource allowlist includes server, radar, channels,
announce-configuration, leaderboard, user/profile, market, treasury, Boss,
Economy statistics and supply, Marketplace, Casino, Crypto, Mining, Phase 8,
marriages, summary, and bot statistics. Raw configuration has no replacement.

`/api/channels` and `/api/announce-config` are not public; the dashboard accesses
their signed replacements only after `DASHBOARD_VIEW` validation.

## Errors

Sanitized error codes are limited to:

- `invalid_request`
- `unauthenticated`
- `forbidden`
- `expired`
- `rate_limited`
- `version_conflict`
- `request_identity_conflict`
- `capability_unavailable`
- `internal_error`

Responses use `Cache-Control: no-store` and do not include secrets, paths, SQL,
configuration values, or exception traces.

## Phase 9B Economy Dashboard

Seluruh endpoint Phase 9B adalah signed internal `POST` dan memerlukan session Phase 9A aktif.
Read endpoint tersedia pada `/internal/phase9b/dashboard/{overview|supply|flows|liabilities|marketplace|casino-options|giveaway|crypto-mining|recovery}`.
Routing menggunakan `/internal/phase9b/notifications/routes/{list|details|update|test}`. Kontrol yang
diizinkan adalah `/internal/phase9b/features/{pause|resume}` dan `/internal/phase9b/recovery/resolve`.

Next.js mengekspos pasangan browser yang eksplisit di `/api/economy/*`; tidak ada catch-all proxy.
Mutation memerlukan CSRF satu kali, stable request ID, expected version, dan permission yang sesuai.
Amount dan count pada read model dikirim sebagai string desimal. Test notification terpisah dari
history real event. Timeout atau response loss pada Discord menjadi `review_required` dan tidak
dikirim ulang otomatis.
