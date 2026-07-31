# Phase 7 Mining V1

## Status And Guardrails

Phase 7 Mining is implemented for staging with migration `700 / phase7-mining`.
`ECONOMY_PHASE7_ENABLED` defaults to `false`. Startup does not migrate, seed,
or enable Mining. Production remains unmigrated, unseeded, disabled, and
unapproved. Phase 7 does not implement Giveaway or Eternal Options and does
not change Casino, Crypto pricing/trading, Deal, Middleman, or Trusted Vouch.

Runtime requires Economy V1, Phase 2, Crypto migration 600 capability, Mining
migration 700 capability, `ECY_MINING`, an unpaused Mining feature, and the
hardened Phase 3 profile schema. The Phase 3 runtime flag need not be enabled.
A user must already have one valid `RpgProfile`; Mining never creates one.

## Commands

Member commands are `/mining status|catalog|buy|rigs|target|maintenance|claim|details|history`
and equivalent `w!mining` actions. Existing `/buyrig`, `/miner`, `/moverig` and
their prefix routes remain compatibility adapters. When Phase 7 is disabled,
all legacy Mining behavior remains unchanged. Enabled but incomplete capability
fails closed without writing legacy output.

Staff commands are `/economy mining-auth add|remove|list`, `mining-status`,
`mining-config`, and `mining-recover`. Pause/resume requires `MINING_CONTROL`;
review recovery requires `MINING_RECOVERY`. Discord Administrator or bot-owner
identity alone is not operational authority. The API exposes read-only status
only and has no Mining mutation route.

## Profile Slots

Mining uses the authoritative Phase 3 profile level. Level 10, 25, 45, and 70
allow one, two, three, and four rigs respectively. `ACTIVE`,
`MAINTENANCE_DUE`, and `REVIEW_REQUIRED` rigs reserve slots. Profile validity,
level, slots, wallet, and expected versions are rechecked under
`BEGIN IMMEDIATE` before settlement.

## Rig Economics

| Rig | Purchase ECY | Gross/day | Maintenance/day ECY |
| --- | ---: | ---: | ---: |
| Basic | 500,000 | 10,000 | 2,500 |
| Advanced | 3,000,000 | 60,000 | 15,000 |
| Elite | 15,000,000 | 300,000 | 75,000 |
| Eternal | 75,000,000 | 1,500,000 | 375,000 |

Purchase and maintenance allocate 80% to `ECY_MINING`, 10% to `ECY_RESERVE`,
and the remainder to `ECY_BURN`. New and migrated rigs start
`MAINTENANCE_DUE`. Maintenance activates exactly 24 hours and cannot be
prepaid. Unpaid and expired time produces no output. Durability remains fixed
at 10,000 bps; V1 has no decay, repair, breakdown, destruction, or durability
yield modifier.

## Accrual And Price Evidence

The price reference is the integer-floor average of committed global Phase 6
prices in the half-open seven-day evidence window ending at observation time.
Each checkpoint stores bounds, sample count, price sum, average, latest history
identity, and a deterministic evidence hash. At least one sample is required.

Rewarded time is bounded by paid maintenance and a maximum 86,400 seconds per
observation. `accruedThrough` always advances to the committed observation,
discarding unpaid and excess offline time permanently.

```text
floor(grossEquivalentPerDay * rewardedSeconds * 100,000,000
      / (86,400 * sevenDayAveragePrice))
```

Python arbitrary-precision arithmetic, GCD factor cancellation, `divmod`, and
explicit signed-64-bit validation prevent SQLite intermediate overflow. Full
numerator and denominator are stored as decimal text with a calculation hash.
Fractional billionths of one asset unit carry into later checkpoints. Target
changes accrue the old target first; pending output is never converted.

## Asset-Only Claims

A claim transfers units from per-rig pending ownership to the guild-scoped
Phase 6 `CryptoHolding`. It does not create `EconomyTransaction`, ECY ledger
rows, Crypto trades, fees, Market Reserve mutations, or realized profit.
`totalCostBasisEcy` and `realizedProfitEcy` remain unchanged.

`MiningClaim`, `MiningClaimAsset`, and append-only `MiningAssetLedger` are the
authority. Every symbol records equal and opposite `RIG_PENDING` and
`USER_HOLDING` entries and verifies a zero unit sum before commit.

## Idempotency, Recovery, And Migration

Actor-bound confirmations expire after 90 seconds without creating state. Each
confirmed action reserves one cryptographically random request identity and an
immutable outcome. Partial unique indexes serialize one purchase per user and
one mutation per rig. Retries and recovery reuse IDs, timestamps, price
evidence, calculations, and receipts. Ambiguity remains `REVIEW_REQUIRED`.

Migration 700 is explicit, backup-first, checksummed, idempotent, staging-only,
and production-path rejecting. It supports dry-run, apply, verify, reconcile,
restore, rollback injection, integrity checks, and foreign-key checks. Legacy
tiers 1–3 map to Basic, Advanced, and Elite. Repository evidence does not prove
legacy tier 4 as Eternal, so tier 4 and unknown tiers are preserved in review
without operational rigs. `users.json` is not modified and legacy Crypto
balances already handled by migration 600 are not re-credited.

## Verification

The deterministic 20-seed, 90-day simulation covers four rigs, seven assets,
and daily, 72-hour casual, 15-minute, and maximum-offline/weekly-claim patterns.
Artifact SHA-256 is
`e7599dbf34beca0fffa777cbe3fab9c0d6b7fb77d0546e6f48646b464224b187`.
It reports 2,240 scenarios, zero overflow attempts, duplicate output,
durability violations, or invariant failures, and constant-price net ROI
`66.66666666666667` days.

Connected Discord staging and dashboard production build remain pending.
Production rollout requires separate approval.
