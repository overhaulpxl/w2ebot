# Phase 9C Connected Staging Acceptance Checklist

Use only an explicitly approved staging manifest and staging credentials. Record hashes or sanitized
booleans only; never record tokens, cookies, secrets, raw identifiers, database contents, or paths.

1. `S01` Verify staging database path and production refusal.
2. `S02` Create and verify a staging database backup.
3. `S03` Apply and verify migrations 100, 200, 300, 301, 400, 500, 600, 700, 800, 900, and 910.
4. `S04` Seed only approved staging system accounts and capability markers.
5. `S05` Register Phase 9A signing-key fingerprints without persisting key material.
6. `S06` Bootstrap one staging dashboard security administrator.
7. `S07` Configure the staging Discord OAuth callback and explicit dashboard origins.
8. `S08` Enable Economy flags one at a time in dependency order, staging only.
9. `S09` Synchronize the complete staging Discord command tree.
10. `S10` Verify stale slash commands were removed.
11. `S11` Start the dashboard production build against staging.
12. `S12` Complete authenticated Discord OAuth login.
13. `S13` Verify permission assignment, revocation, and session invalidation.
14. `S14` Verify session expiry, logout, CSRF, nonce, and signed-request rejection.
15. `S15` Configure validated notification routes.
16. `S16` Send clearly labeled test notifications with no real-event history mutation.
17. `S17` Prove route updates affect only future reservations.
18. `S18` Verify conclusive failure retry and uncertain-send review behavior.
19. `S19` Restart the bot during active domain and delivery operations.
20. `S20` Verify persistent controls, marker adoption, recovery, and no duplicate delivery.
21. `S21` Match every dashboard financial value to direct staging reconciliation.
22. `S22` Disable all Economy flags after acceptance.

Live interaction coverage includes slash/prefix ownership, permissions, autocomplete, modals,
persistent buttons, duplicate clicks, stale messages, response timing, Casino settlement, Crypto
trade/tick, Mining claim, Marketplace purchase/return, Giveaway lifecycle and structured redraw,
Eternal Options settlement, notification routing, pause/resume, reviewed recovery, and security
administration.

Every passed step requires a SHA-256 evidence hash. Any failed or incomplete step blocks production
readiness. Connected staging never uses production credentials, databases, guilds, OAuth
applications, channels, or origins.
