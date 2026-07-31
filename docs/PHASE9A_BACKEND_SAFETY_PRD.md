# Phase 9A Backend Safety Foundation

## Status

Phase 9A is implemented for local verification. Connected Discord OAuth staging and
production rollout remain pending. Migration `900 / phase9a-backend-safety` is
manual and must never run at application startup.

Phase 9A adds no Economy feature flag and does not implement Phase 9B or 9C.

## Objective

Replace the legacy token-based dashboard boundary with a fail-closed administrator
session, signed server-to-server requests, explicit permission classes, replay
protection, and authoritative append-only audit records. The only public aiohttp
data endpoint is `GET /healthz`, which returns only `{\"status\":\"ok\"}`.

## Browser Authentication

- Next.js owns Discord OAuth2 authorization-code flow with PKCE and `identify`.
- The browser receives only `__Host-w2e_admin_session`, with `Secure`, `HttpOnly`,
  `SameSite=Lax`, `Path=/`, and no `Domain` attribute.
- Sessions expire after 30 minutes idle or eight hours absolute.
- Raw session tokens, OAuth tokens, PKCE verifiers, and signing keys are not stored
  in SQLite or returned in JSON.
- Next middleware rejects unauthenticated API calls and redirects unauthenticated
  page requests to `/login`. Server pages and route handlers repeat full backend
  validation so stale, revoked, or expired cookies fail closed.
- State-changing browser requests require a one-time CSRF token bound to the
  session, method, route, and request ID.

## Authorization

The supported permission classes are:

- `DASHBOARD_VIEW`
- `DASHBOARD_CONFIGURATION`
- `ECONOMY_PAUSE_CONTROL`
- `REVIEWED_RECOVERY_CONTROL`
- `NOTIFICATION_ROUTING_CONTROL`
- `OPERATOR_AUDIT_READ`
- `DASHBOARD_SECURITY_ADMIN`

Discord Administrator permits login and viewing only. It does not grant security
administration or future Economy operational controls. Phase 9A exposes only
security administration; pause, recovery, notification routing, and product-value
operations remain unavailable.

## Internal Requests

Next.js sends HMAC-SHA256 signed envelopes to aiohttp. The canonical envelope binds
the key ID, method, route, guild, actor, permission class, request ID, issue/expiry
times, nonce, canonical payload hash, session token hash, and session version.
Envelopes expire after 30 seconds and nonces are consumed exactly once.

aiohttp independently validates the signature, nonce, route, method, payload,
session, current guild membership, and permission. Browser-origin requests to
internal routes are rejected.

## Route Isolation

- `GET /healthz` is the only intentionally public data route.
- `GET /` redirects only to the configured HTTPS dashboard `/login` URL.
- Every legacy `/api/*` read returns `410 legacy_dashboard_read_disabled`.
- Every legacy dashboard write returns `410 legacy_dashboard_write_disabled`.
- Sensitive reads are available only through the allowlisted signed internal read
  dispatcher after a current `DASHBOARD_VIEW` session is validated.
- Raw configuration has no replacement read route.
- The browser never calls aiohttp directly.

The read allowlist covers server summary, radar/voice presence, channels,
sanitized announcement configuration, leaderboard, user/profile, market,
treasury, Boss, Economy summaries, Phase 4-8 status, marriages, and bot summary.
It does not permit arbitrary paths or arbitrary query fields.

## Migration 900

Migration 900 creates:

1. `DashboardIdentity`
2. `DashboardOperatorPermission`
3. `DashboardAuthorizationAudit`
4. `DashboardSession`
5. `DashboardSigningKeyVersion`
6. `DashboardOAuthAttempt`
7. `DashboardCsrfToken`
8. `DashboardInternalNonce`
9. `DashboardControlledOperation`
10. `DashboardOperatorAudit`
11. `DashboardSecurityEvent`
12. `DashboardRateLimitBucket`
13. `DashboardLegacyRouteSnapshot`

The migration uses `EconomySchemaMigration`, canonical SHA-256 verification,
backup-first application, idempotent replay, reconciliation, restore, production
path refusal, failure injection, `integrity_check`, and `foreign_key_check`.
SQLite stores key identifiers and fingerprints only.

## Controlled Operations And Audit

Security-administration mutations use `BEGIN IMMEDIATE`, expected versions,
affected-row checks, stable request identities, immutable receipts, and one atomic
commit with `DashboardOperatorAudit` and `DashboardAuthorizationAudit` records.
Committed retries return the stored receipt. Conflicting request reuse fails.
Append-only triggers reject audit updates and deletes.

Rejected authentication, authorization, signature, CSRF, replay, and rate-limit
checks create sanitized `DashboardSecurityEvent` evidence without secrets,
cookies, headers, configuration values, paths, SQL, or exception traces.

## Security Controls

- Explicit CORS allowlist; an empty allowlist never becomes wildcard.
- CSP, frame denial, MIME sniffing protection, strict referrer policy, and
  `no-store` caching.
- Bounded request bodies, strict JSON content type, known-field validation, and
  safe error codes.
- Separate environment keys for session hashing, internal request signing, and
  privacy-preserving IP hashes.
- Key rotation revokes sessions, CSRF tokens, and outstanding nonces associated
  with retired key material.
- Rate limits cover login, callback, session/CSRF reads, security writes, and
  signed internal calls.

## Compatibility And Exclusions

Phase 1-8 Economy product behavior and commands are unchanged. Deal, Middleman,
Trusted Vouch, `cogs/deal.py`, and their data are unchanged. Phase 9A does not add
Economy analytics, pause/resume, reviewed recovery, notification routing,
balance editing, product-value editing, a second backend, Phase 9B, or Phase 9C.

## Staging And Production

Staging requires a copied or temporary database, HTTPS dashboard URL, dedicated
Discord OAuth application, registered key fingerprints, and a bootstrap operator.
Connected Discord/OAuth staging has not been executed.

Production remains disabled, unmigrated, unseeded, and unapproved. No production
database or production credential is used by migration or verification tooling.
