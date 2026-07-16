# Phase 9C Final QA, Connected Staging, And Production Readiness

## Status

Phase 9C adds no runtime product feature, migration, or feature flag. It verifies the committed
Phase 1-9B implementation from immutable baseline
`1fbe1c52bff268e68794fd3006b7705a51f995b4` and produces sanitized local and connected-staging
evidence. Production activation remains a separate owner-approved task.

## Local Acceptance

The local QA runner executes the existing Economy, Marketplace, Phase 9A, Phase 9B, Living PRD,
Python, dashboard, main-import, ownership, alias, and diff checks. Existing domain suites remain
authoritative; Phase 9C adds only migration-chain, cross-domain reconciliation, restart delivery,
duplicate-prevention, and staging-contract tests.

The deterministic full-system simulation uses exactly 1,000 virtual users over 90 days with the
approved cohort distribution. All currency movement is integer-only and balanced. Existing accepted
Casino, Crypto, Mining, Giveaway, and Eternal Options simulation artifacts are immutable inputs and
are not retuned. Two simulation runs must produce byte-identical canonical JSON and the same SHA-256.

Acceptance requires zero ledger imbalance, zero supply mismatch, exact domain liabilities, exact
dashboard transport values, and zero duplicate money, assets, winners, messages, receipts, or audit
records. A failed gate preserves its evidence and blocks readiness without changing product rules.

## Verified Local Results

- Two 1,000-user, 90-day runs produced byte-identical canonical artifacts.
- Artifact identity: `3aa14ceb5dee96408d13337b3396ac2d576e102756475c39c671638cac4e8c8a`.
- File SHA-256: `f12012b7937699fc8b2fe3bca42740faee35067ecfb84d5b0eec25ba073be8b5`.
- The simulation applied 96,175 balanced transactions, 54 restart injections, and 990 durable
  notification source events for 1,000 users over 90 days.
- Ledger, supply, liabilities, and dashboard reconciliation passed exactly; duplicate outcome and
  unresolved review counts were zero.
- Local verification passed 322 Python tests and 14 dashboard tests, for 336 tests total.
- Python compilation, temporary-database main import, dashboard typecheck, production build,
  dependency audit, command ownership, forbidden aliases, integrity, foreign keys, and diff checks
  passed.

## Migration And Recovery

The verified migration chain is `100, 200, 300, 301, 400, 500, 600, 700, 800, 900, 910`.
Versions 100 and 200 retain source-manifest checksum contracts; later migrations retain their
committed catalog or canonical-schema checksums. Existing migration suites cover dry-run, backup,
apply, replay, verify, reconciliation, restore, rollback injection, capability validation,
production-path refusal, integrity, and foreign keys.

Cross-feature restart acceptance reuses original operation, transaction, source-event, delivery,
receipt, and audit identities. Conclusive delivery failures may retry the same delivery identity.
Uncertain sends remain `REVIEW_REQUIRED` and are never automatically resent.

## Connected Staging

Connected Discord/OAuth staging requires a separately approved staging manifest, dedicated staging
resources, and complete staging-only credentials. The evidence tooling stores hashes and sanitized
results only. It rejects production-equivalent database paths and secret-like fields.

The 22-step acceptance sequence is defined in `PHASE9C_STAGING_ACCEPTANCE_CHECKLIST.md`. All Economy
flags are disabled after staging acceptance. When approved resources are unavailable, the readiness
state is `ready_for_connected_staging` and no network staging is attempted.

## Production Decision

Passing local QA and deterministic simulation is insufficient for production activation. Passing
all connected staging checks may advance the project only to `ready_for_production_approval`.
Production migration, seed, command synchronization, deployment, and enablement require separate
explicit approval.

## Protected Boundaries

Phase 9C does not modify Economy Phase 1-8 values or commands, Phase 9A authentication, Phase 9B
dashboard architecture, Deal, Middleman, Trusted Vouch, or `cogs/deal.py`.
