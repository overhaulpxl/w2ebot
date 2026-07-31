# Phase 9C Production Readiness Runbook

Production activation is prohibited until a separate approved production change record exists.

## Preconditions

- Phase 9C local QA and deterministic simulation artifacts pass and match their recorded hashes.
- Connected Discord/OAuth staging has all 22 passed evidence records.
- A current production backup and tested restore procedure exist.
- Migration checksums 100-910 and all capability checks are independently verified.
- Production system-account seed requirements are approved and reconciled.
- OAuth callbacks, origins, session keys, internal signing keys, and IP-hash keys are provisioned
  through the approved secret manager. Only fingerprints enter SQLite or evidence.
- Dashboard production build, command-tree snapshot, monitoring, and on-call ownership are approved.

## Change Sequence

1. Freeze unrelated production changes and record the immutable source commit.
2. Validate environment names without printing values.
3. Pause affected Economy features and create a verified SQLite backup.
4. Run migration dry-runs, compare checksums, then apply each approved migration in order.
5. Verify capabilities, integrity, foreign keys, system accounts, seed markers, and supply.
6. Deploy the authenticated dashboard and verify `/healthz` exposes generic liveness only.
7. Register key fingerprints and bootstrap approved operators through audited tooling.
8. Synchronize commands and compare the resulting command tree to the approved manifest.
9. Enable flags individually in dependency order with smoke checks and reconciliation after each.
10. Monitor ledger balance, supply, liabilities, review queues, outboxes, notification delivery,
    sessions, security events, and dashboard freshness.

## Completion

Production is accepted only when smoke checks, direct reconciliation, dashboard reconciliation,
restart recovery, and notification delivery pass without duplicate outcomes. Preserve all evidence
and keep emergency pause, session revocation, and key rotation immediately available.
