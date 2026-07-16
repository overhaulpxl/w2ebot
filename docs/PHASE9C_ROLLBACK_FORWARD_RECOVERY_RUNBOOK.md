# Phase 9C Rollback And Forward-Recovery Runbook

## Immediate Containment

1. Stop new operations by pausing the affected feature or disabling its flag.
2. Do not delete, rewrite, or replace pending operation identities.
3. Revoke dashboard sessions or signing keys when authentication or authorization is involved.
4. Preserve database, logs, source-event markers, receipts, and sanitized evidence.
5. Run integrity, foreign-key, ledger, supply, liability, outbox, and review reconciliation.

## Rollback

- Roll back the dashboard deployment independently when no database contract changed.
- Restore a database backup only when it is conclusively before all accepted post-migration writes
  and the restore has explicit approval.
- Never restore over ambiguous committed financial, asset, winner, delivery, or audit state.
- After restore, verify every migration marker, checksum, capability, integrity result, and foreign
  key before enabling any feature.

## Forward Recovery

- Reuse original operation, request, transaction, outcome, source-event, delivery, receipt, and audit
  identities.
- Retry only operations whose existing recovery service proves retry safety.
- Preserve `REVIEW_REQUIRED` when financial or Discord-send acceptance is uncertain.
- Conclusive notification failures retry the same delivery identity; uncertain sends are never
  automatically resent.
- Do not substitute prices, winners, recipients, quantities, routes, or product outcomes.
- Complete with direct and dashboard reconciliation and an immutable compensating receipt where the
  approved service explicitly supports compensation.

## Emergency Controls

Emergency pause, operator-session revocation, key rotation, notification review, and reviewed
recovery require their existing Phase 9A/9B permissions and append-only audits. Administrator or bot
owner identity alone does not bypass those controls.
