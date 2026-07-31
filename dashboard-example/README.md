# W2E Dashboard

Next.js App Router dashboard protected by the Phase 9A administrator session.

## Security Boundary

- Discord OAuth2 authorization-code flow with PKCE and `identify`.
- Secure `__Host-w2e_admin_session` cookie; no token is exposed to browser code.
- Middleware protects all pages except `/login` and all APIs except login/callback.
- Server layouts and route handlers repeat backend session validation.
- All bot reads use signed, short-lived internal requests from the Next server.
- State-changing security operations require one-time CSRF and immutable request IDs.
- Legacy write proxies and direct browser-to-bot reads are removed.

## Required Server Environment

```dotenv
BOT_API_URL=https://bot-api.example.com
DASHBOARD_PUBLIC_URL=https://dashboard.example.com
DASHBOARD_DISCORD_CLIENT_ID=
DASHBOARD_DISCORD_CLIENT_SECRET=
DASHBOARD_INTERNAL_KEY_ID=
DASHBOARD_INTERNAL_SIGNING_KEY=
DASHBOARD_SESSION_HASH_KEY=
ALLOWED_SERVER_ID=
```

Do not use `NEXT_PUBLIC_` for bot URLs, OAuth credentials, session keys, or signing
keys. Run behind HTTPS; insecure public dashboard URLs fail closed.

## Local Verification

```text
npm test
npm run typecheck
npm run build
```

Connected OAuth/Discord staging requires a dedicated OAuth application, staging
guild, temporary database with migration 900, registered key fingerprints, and a
bootstrapped operator.
