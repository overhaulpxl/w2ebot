# Phase 5 Casino Product Requirements Document

## 1. Document Status

- Phase: Phase 5 - Casino
- Status: Implemented and ready for connected Discord staging
- Implementation status: Implemented
- Production status: Not approved
- Production migrated: No
- Production enabled: No
- Document language: English
- Current task commit: `PENDING`

This document records the owner-approved D01-D20 product decisions and the resulting implementation. Migration 500 and the runtime flag now exist, but startup does not apply the migration and the flag defaults to false. No production database was migrated or seeded. The overall decision status remains `approved_with_conditions`; the complete natural-payout calibration passed D02 and Phase 5 is ready for connected Discord staging.

## 2. Source-of-Truth References

The source-of-truth order is:

1. Committed migrations and database constraints.
2. Committed automated tests and integrity checks.
3. Committed service-layer implementation.
4. Committed runtime configuration and command registration.
5. `docs/project_state.json`.
6. Generated `docs/AI_CODER_HANDOFF.md`.
7. This approved planning document and `docs/PRD_ECONOMY_RPG_V1.md`.
8. Historical reports and prior chat history.

Repository evidence used by this plan includes `cogs/rpg.py`, `core.py`, `w2e_views.py`, `economy/constants.py`, `economy/database.py`, `economy/ledger.py`, `economy/treasury.py`, `economy/controls.py`, and the existing economy tests.

## 3. Phase Objective

Move the seven approved Casino games from the legacy coin path to the Phase 1 ECY wallet and ledger. Phase 5 must provide validated bets, a funded Casino Bankroll, atomic and idempotent settlement, restart-safe sessions, and reproducible RTP verification without changing unrelated systems.

## 4. Approved Scope

Phase 5 includes:

- Blackjack, target RTP 97.5%, verified by the complete D02 simulation.
- Slots, target RTP 95%.
- Coinflip, target RTP 97%.
- Rock-paper-scissors, target RTP 96.7%.
- Number guessing, target RTP 95%.
- Cosmetic-only Gacha at a fixed 1,000 ECY cost, with equal probability across the eight approved labels and no financial payout or inventory grant.
- Loot boxes at a fixed 1,000 ECY cost using the approved 95% RTP payout table and 15x maximum gross liability.
- ECY-only Casino stakes and payouts.
- User-selected wagers from 1,000 ECY through the effective maximum, in exact 1,000 ECY increments. The 500,000 ECY global maximum is a request ceiling, not guaranteed acceptance.
- Casino Bankroll funding, exposure control, settlement, recovery, audit, emergency pause, and RTP simulation.

Casino winnings have no additional winner tax. Odds must never depend on user identity, wallet balance, stake size, prior results, treasury balance, staff status, roles, or Activity Score.

## 5. Explicit Non-Goals

Phase 5 does not include:

- Eternal Options, which remains Phase 8.
- UP/DOWN predictions, crypto price settlement, or timed Options positions.
- Replacing, deprecating, or changing legacy `/crash` or Binomo behavior.
- Crypto, mining, giveaways, or Marketplace changes.
- Changes to Deal, Middleman, Trusted Vouch, payment configuration, reports, reviews, or archive behavior.
- A second wallet, ledger, burn account, or independent currency system.
- Production migration, seed, cutover, or feature enablement.
- A claim of certified or independently audited cryptographic fairness.

## 6. Existing System Assessment

Every current-state observation below is tied to static repository evidence.

| Observation | verificationStatus | evidencePaths | Current behavior | Required Phase 5 behavior | Migration or compatibility risk |
| --- | --- | --- | --- | --- | --- |
| Blackjack command | repository_observed | `cogs/rpg.py`, `w2e_views.py` | `/blackjack bet` and generic `w!blackjack <bet>` use legacy coins, minimum 50, independently sampled pseudo-scores, and a 90-second replay button. | Preserve command identity; route enabled Phase 5 calls to persisted ECY settlement. | Current behavior is not standard Blackjack and cannot simply be relabeled. |
| Slots command | repository_observed | `cogs/rpg.py`, `w2e_views.py` | `/slot bet` and `w!slot <bet>` use legacy coins, minimum 50, three uniformly sampled symbols, and gross payouts of 10x, 5x, or 1.5x. | Preserve command identity; use an owner-approved 95% RTP table and integer payouts. | Existing static RTP is not the approved target. |
| Coinflip command | repository_observed | `cogs/rpg.py`, `core.py` | `/cf tebakan bet` and `w!cf ...` use legacy coins, minimum 10, equal outcomes, and 2x gross payout on a win. | Preserve `/cf`; use an owner-approved 97% RTP mechanism. | Current payout produces no approved house edge. |
| RPS command | repository_observed | `cogs/rpg.py`, `core.py` | `/rps pilihan bet` and `w!rps ...` use legacy coins, minimum 10, equal bot choices, draw refund, and 2x gross payout on a win. | Preserve command identity; use an owner-approved 96.7% RTP policy. | Current payout and draw policy do not implement the target RTP. |
| Number guessing command | repository_observed | `cogs/rpg.py` | `/tebak tebakan` and `w!tebak ...` have no stake and award 100 legacy coins for guessing 1-10. | Preserve the name; add only an owner-approved ECY stake and payout contract. | Current signature is not a Casino bet contract. |
| Gacha command | repository_observed | `cogs/rpg.py`, `w2e_views.py` | `/gacha` and `w!gacha` debit 500 legacy coins and return one uniformly selected display string; no owned asset is created. | Preserve the name; use an owner-approved ECY cost, reward catalog, probabilities, and ownership effects. | Existing strings have no approved economic value or RTP. |
| Loot-box command | repository_observed | `cogs/rpg.py`, `w2e_views.py` | `/box` and `w!box` debit 1,000 legacy coins and award 5,000, 2,000, 500, or 10 legacy coins from fixed probability bands. | Preserve the name; use an owner-approved ECY/reward contract. | Legacy expected value is not an approved Phase 5 value. |
| Prefix routing | repository_observed | `core.py` | Generic `FakeInteraction` resolves top-level slash callbacks for all seven commands. | Prefix and slash must call the same Casino service and use the same persisted request identity. | Decorator-only checks do not protect prefix execution. |
| Randomness | repository_observed | `cogs/rpg.py` | Games use Python's general `random` module and do not persist random outcomes before settlement. | Use a secure live RNG behind an injectable interface and persist immutable outcomes. | Retrying current commands can produce a different result. |
| Wallet and payout handling | repository_observed | `cogs/rpg.py`, `core.py` | Bets use `try_spend` and payouts use `add_coins` against legacy `DiscordStat.coins`. | Use `EconomyWallet.ecyBalance`, `EconomyTransaction`, and balanced `EconomyLedger` entries. | Mixed legacy/V1 writes would create two financial truths. |
| Statistics | repository_observed | `core.py` | `record_game` writes play/win/loss counters to `users.json`. | Decide whether legacy counters remain read-only history or migrate to a non-financial compatibility record. | Replaying history must not create ECY transactions. |
| Casino persistence | repository_observed | `economy/database.py`, `core.py` | No Casino session, settlement, receipt, recovery, or durable cooldown table exists. | Add explicit Phase 5 schema through an approved migration. | Enabled Phase 5 must fail closed before that migration exists. |
| Replay views | repository_observed | `w2e_views.py` | Blackjack, Slots, Gacha, and Box replay views are actor-bound, time out after 90 seconds, and are not registered for restart recovery. | Use persisted session IDs and stale-safe persistent interaction handling where applicable. | Old views cannot prove an ECY settlement after restart. |
| Emergency controls | repository_observed | `economy/constants.py`, `economy/controls.py`, `cogs/economy.py` | `casino` is an existing emergency feature; `/economy pause`, `/economy resume`, and `/economy status` use bot-owner or enabled-whitelist authorization. | Reuse the control state and re-check authorization inside callbacks and services. | Prefix or internal paths must not bypass service authorization. |
| Casino system account | repository_observed | `economy/constants.py`, `economy/database.py` | `ECY_CASINO` exists as a spendable ECY treasury account. | Use it as the authoritative Casino Bankroll. | A second bankroll account would fragment accounting. |
| ECY burn mechanism | repository_observed | `economy/constants.py`, `economy/database.py`, `economy/treasury.py` | `ECY_BURN` already exists as an ECY `BURN` system account and is included in burned-supply reporting. | Use the existing account only if the approved 20% burn distribution is executed. | Phase 5 must not create or approve another burn account. |
| Casino-specific automated tests | repository_observed | `tests`, `cogs/rpg.py` | No dedicated Phase 5 Casino test module exists. | Add isolated unit, transaction, concurrency, recovery, command, and simulation suites during implementation. | Legacy command behavior currently lacks regression coverage specific to Casino. |

No runtime or live-Discord claim is made from static source inspection.

## 7. User-Facing Game Flows

One-step games follow this logical flow:

1. User submits the existing slash or prefix command.
2. The adapter acknowledges safely and derives a stable request ID.
3. The service verifies flags, migration, pause state, actor, input, wallet balance, bankroll seed, and available exposure.
4. The service reserves one immutable outcome and one unresolved operation.
5. Stake, outcome, bankroll movement, payout or loss, ledger, receipt, and terminal state commit atomically.
6. Discord rendering reads the committed receipt; response failure never repeats settlement.

Blackjack requires a persisted interactive flow:

1. Validate the stake and maximum possible exposure.
2. Debit the accepted stake, reserve exposure, and persist the shuffled deck before showing controls.
3. Accept only actor-bound, version-checked actions for the stored session.
4. Append each action and derive state from the persisted deck without rerolling.
5. Settle or refund through one final atomic financial transition.
6. Disable stale controls and replay the immutable receipt on duplicate actions.

The D02-approved Blackjack rules support Hit and Stand, hard 11 Double only, and one Split limited to Aces or 8s, producing at most two hands. A winning natural pays 5:4 profit, or 2.25x gross, through checked integer arithmetic. The rules do not support Double on hard 10, Double after Split, resplitting Aces, surrender, or insurance. Split Aces receive one card each. The complete natural-payout calibration passed D02.

## 8. Slash Command Plan

Preserve the existing command names:

| Command | Existing parameters | Proposed Phase 5 contract |
| --- | --- | --- |
| `/blackjack` | `bet: int` | Preserve `bet`; accept 1,000-ECY steps subject to effective exposure, using the provisional versioned ruleset. |
| `/slot` | `bet: int` | Preserve `bet`; use the approved equal-weight one-payline 95% RTP table. |
| `/cf` | `tebakan: str`, `bet: int` | Preserve command and choices; use fair outcomes and `floor(bet * 19400 / 10000)` gross payout. |
| `/rps` | `pilihan: str`, `bet: int` | Preserve command and choices; refund draws and use `floor(bet * 19010 / 10000)` gross payout on wins. |
| `/tebak` | `tebakan: int` | Add a typed Phase 5 wager parameter; use one guess from 1-20 and 19x gross payout. |
| `/gacha` | none | Fixed 1,000 ECY cosmetic product; no user-selected stake or payout liability. |
| `/box` | none | Fixed 1,000 ECY product using the approved 95% RTP payout table. |

No `/casino` group or replacement command name is approved by this document.

## 9. Prefix Command Plan

Preserve:

- `w!blackjack <bet>`
- `w!slot <bet>`
- `w!cf <head|tail> <bet>`
- `w!rps <batu|gunting|kertas> <bet>`
- `w!tebak <guess> <bet>` when Phase 5 is enabled; the disabled legacy free path remains unchanged
- `w!gacha` at the fixed 1,000 ECY price when Phase 5 is enabled
- `w!box` at the fixed 1,000 ECY price when Phase 5 is enabled

Prefix parsing must use typed parameters and invoke the same service as slash and button paths. Prefix mode has no ephemeral responses and must perform all permission, flag, pause, migration, and stale-state validation inside the callback or service.

## 10. Command Ownership

Casino game commands remain owned by the RPG command surface in `cogs/rpg.py`. Phase 5 must not alter:

- `/leaderboard` and `w!leaderboard`: RPG.
- `/vouchleaderboard` and `w!deal leaderboard`: Trusted Vouch.
- `/rank`: Trusted Vouch.
- `w!rank`: RPG.
- `w!deal rank`: Trusted Vouch.

Forbidden Trusted Vouch prefix aliases remain absent.

## 11. Permissions And Authorization

- Member game commands require a valid guild actor, an eligible ECY wallet, enabled dependencies, an applied Phase 5 migration, an unpaused Casino, and a funded bankroll.
- No Discord Administrator permission is required to play.
- `CASINO_CONTROL` authorizes pause, resume, and status.
- `CASINO_FINANCIAL` authorizes initial seed, bankroll adjustment, and excess distribution.
- `CASINO_RECOVERY` authorizes reviewed refunds, review resolution, and compensating settlement.
- The three classes must be separately represented and audited. Existing whitelist infrastructure may be reused, but membership in one class does not imply another.
- Discord Administrator permission alone is insufficient. Bot-owner identity does not silently bypass financial approval. Emergency owner recovery requires an explicit audited override path.

## 12. Currency And Wallet Rules

- Casino stakes and payouts use integer ECY only.
- User-selected stakes are whole multiples of 1,000 ECY. Fixed products use their approved fixed price.
- The 500,000 ECY global maximum is a request ceiling. Actual acceptance uses the lower game-specific effective maximum.
- Boolean, signed, negative, zero, decimal, scientific notation, NaN, Infinity, malformed grouping, and overflow inputs are rejected before mutation.
- No floating-point value may enter wallet, bankroll, exposure, ledger, or receipt calculations.
- Every committed transaction remains zero-sum per currency.
- Casino winnings have no extra winner tax.
- Casino profit does not count as Activity Score or RPG progression unless separately approved.

## 13. Casino Bankroll Design

`ECY_CASINO` is the authoritative bankroll. Player losses credit it; gross payouts or approved refunds debit it.

The approved safe-bankroll recommendation is:

```text
max(25,000,000 ECY, 100,000 ECY * active members in the previous 30 days)
```

An active member is a current non-bot guild member with at least one committed approved non-Casino activity event in the rolling previous 30 UTC days. Casino, administrative, transfer, exchange, Marketplace, balance-only, departed-user, and bot activity does not count.

The 2% cap applies to total maximum reserved gross liability. Operational availability accounts for the current `ECY_CASINO` balance and all unresolved reservations. The effective maximum stake is:

```text
min(
    500,000 ECY,
    maximum 1,000-ECY-step stake whose complete worst-case gross liability
    fits the current 2% exposure cap and available unreserved bankroll
)
```

Every command and confirmation screen displays the effective maximum when below 500,000 ECY. Blackjack initial acceptance reserves the highest liability still possible through either Double or the permitted Split path. A new request is rejected before stake consumption when it cannot be supported.

The existing `EconomySeedMarker` and `system_seed` transaction model provide one-time, balanced issuance-to-bankroll seeding. All seed defaults remain zero until separately approved.

The exact seed is `max(25,000,000 ECY, 100,000 ECY * active members)`, with no multiplier. Production seed execution still requires a separate cutover approval and uses a one-time issuance-to-`ECY_CASINO` transaction and seed marker.

Excess distribution is manual only while Casino is paused. Retain the safe requirement plus unresolved and review liabilities, then distribute positive excess as 60% to `ECY_GENERAL`, 20% to `ECY_RESERVE`, and the integer remainder to the existing `ECY_BURN`. One confirmed, idempotent, audited `CASINO_FINANCIAL` transaction performs the distribution. Casino loss money is not distributed after each round.

## 14. Bet Validation

Validation occurs both before and after `BEGIN IMMEDIATE`:

- Required flags and schema capability.
- Guild and actor identity.
- Casino and global economy pause state.
- Canonical integer stake, exact 1,000 ECY step, request ceiling, checked payout arithmetic, and effective maximum.
- Game-specific choices and approved ruleset version.
- User ECY balance and wallet version.
- Bankroll seed, balance, version, and unresolved exposure.
- One unresolved session per user, one active Blackjack session per user, and no more than 100 unresolved sessions per guild.
- Approved cooldown: five seconds after committed terminal Blackjack, Gacha, or Loot Box; three seconds after committed Slots, Coinflip, RPS, or Number Guessing.
- Stable request identity and unresolved reservation lookup.

A failed read-only preflight creates no operation, outcome, transaction, cooldown, or balance change.

## 15. Atomic Settlement

For one-step games, one SQLite transaction performs:

1. `BEGIN IMMEDIATE`.
2. Idempotency and unresolved-operation lookup.
3. Post-lock validation.
4. `PENDING` transaction and Casino operation creation.
5. Immutable outcome creation through the approved game engine.
6. Player stake debit and Casino Bankroll credit.
7. Casino Bankroll debit and player gross payout credit when applicable.
8. Balanced ledger insertion and zero-sum verification.
9. Receipt first-write and operation terminalization.
10. Transaction header transition to `COMMITTED`.
11. Single commit.

Blackjack uses separate atomic acceptance/action/settlement transitions because a SQL transaction cannot remain open across Discord interactions. All related transactions reference the same immutable session.

## 16. Idempotency

- Slash, prefix, button, and recovery paths derive stable request IDs.
- Each economic transition has a unique `(guildId, idempotencyKey)` in `EconomyTransaction`.
- Each session has one unresolved reservation identity.
- Duplicate requests reuse the existing session and outcome.
- A committed retry returns the stored receipt.
- A pending retry resumes the original transaction/session identity.
- A review-required operation cannot be bypassed with a new request.
- A void operation is allowed only when no wallet, ledger, bankroll, exposure, or result mutation committed.

## 17. Concurrency Handling

- Use `BEGIN IMMEDIATE` for every financial or lifecycle mutation.
- Validate expected wallet, bankroll, session, and reservation versions.
- Require reliable affected-row counts.
- Include active exposure in bankroll availability checks.
- Partial unique indexes prevent duplicate unresolved reservation keys.
- Two simultaneous requests cannot both consume the same wallet balance or bankroll exposure.
- Duplicate button clicks cannot create a second action or settlement.
- No transaction may consume a cooldown unless its game operation commits.

## 18. Restart Recovery

Recovery scans unresolved sessions, settlements, exposures, and notification events only when dependencies and migration capability are valid.

- `RESERVED`: reuse the stored outcome or deck and resume the original operation.
- `ACTIVE`: restore the tracked Blackjack interaction where safe.
- `SETTLEMENT_PENDING`: reconcile ledger, wallet, bankroll, reservation, and receipt under the original IDs.
- `COMMITTED`: replay the immutable receipt without financial mutation.
- `REFUND_PENDING`: execute only the persisted approved refund plan.
- `REVIEW_REQUIRED`: retain reservations and require audited recovery.
- A valid persisted one-step result resumes or settles from its original IDs. A missing Discord message never reverses financial truth.
- Blackjack resumes after restart and auto-stands after ten minutes of abandonment.
- A debited operation with provable state settles using its original IDs. Ambiguous, conflicting, or impossible state enters `REVIEW_REQUIRED` without replacement identity.
- Departed users receive the persisted settlement. Reviewed refunds and compensating settlements require `CASINO_RECOVERY` authorization and audit.

Recovery never rerolls, silently mints, redirects a payout, or invents a replacement transaction.

## 19. Game-State Persistence

Persist before exposure is accepted or settlement begins:

- Ruleset version and checksum.
- Game type and canonical stake.
- Maximum potential payout or liability representation.
- Immutable random plan, selected symbols, choices, or shuffled Blackjack deck.
- Preallocated session, settlement, and receipt identities.
- Actor, guild, channel, and tracked message identity.
- Reservation and idempotency keys.
- Expiration and version metadata.

Do not reveal unresolved hidden outcomes. Mutable Blackjack state is derived from append-only actions and the persisted deck.

## 20. Ledger And Audit Requirements

Use stable source/reason/reference identities for:

- Casino bet acceptance.
- Casino loss.
- Casino payout.
- Casino refund.
- Bankroll seed.
- Authorized bankroll adjustment.
- Excess bankroll distribution.
- Recovery settlement.
- Casino pause and resume.

Financial truth resides in `EconomyTransaction` and `EconomyLedger`. Staff control changes also use the existing audit mechanism. Logs may include operation IDs, actor IDs, game types, result codes, and exception types, but must not contain private environment values, full wallet histories, hidden unresolved outcomes, credentials, or raw interaction payloads.

## 21. Feature Flags

Runtime flag: `ECONOMY_PHASE5_ENABLED=false`. It exists and remains false by default.

- Economy V1 disabled: preserve legacy routing and perform no Phase 5 schema access.
- Phase 2 disabled: Phase 5 cannot use ECY and must fail closed if its flag is inconsistently enabled.
- Phase 5 disabled: preserve existing legacy commands and behavior.
- Casino paused: block new bets and non-essential mutations; allow recovery, committed receipt replay, approved settlement, and approved refunds.
- Migration missing: fail closed without legacy fallback when Phase 5 is explicitly enabled.
- Bankroll not seeded: block new bets without consuming stakes.

Phase 3 and Phase 4 are not required dependencies for Casino and remain independently controlled.

## 22. Emergency Pause Behavior

`/economy pause casino` blocks new sessions immediately after service-level revalidation. Existing committed results remain valid. Recoverable pending sessions settle from persisted state when settlement remains valid. Refunds occur only under the approved refund policy; ambiguous states enter review.

Pause and resume create permanent audit records and survive restart through `EconomyFeatureState`. Service authorization requires `CASINO_CONTROL`; Discord Administrator or bot-owner identity alone does not bypass the approved class model.

## 23. Database Schema

Migration 500 defines the following schema only when explicitly applied to a non-production staging database. Disabled startup creates none of these tables.

### `CasinoSession`

Stores session identity, guild/user/game, ruleset version, stake, maximum exposure, reservation key, status, immutable outcome plan, mutable state version, tracked message identity, expiration, and timestamps.

### `CasinoSessionAction`

Append-only Blackjack actions with unique session sequence and request identity. Updates and deletes are rejected.

### `CasinoSettlement`

Stores one authoritative settlement envelope, immutable allocation plan, stake/payout/refund transaction references, status, result code, and first-write immutable receipt.

### `CasinoBankrollReservation`

Stores unresolved maximum liability by session. Active or review-required reservations count against available bankroll. Release occurs exactly once with committed settlement, approved refund, or conclusively mutation-free void.

### `CasinoBankrollDistribution`

Stores required-safe calculation inputs, active-member count, pre-distribution balance, reserved liabilities, approved excess, 60/20/20 allocations, actor, reason, transaction, receipt, and timestamp.

### `CasinoNotificationOutbox`

Stores deduplicated result-delivery events so Discord response failure does not repeat settlement.

### `CasinoRecoveryReview`

Stores sanitized ambiguity codes, affected operation identity, retry metadata, review status, and authorized resolution references.

### `CasinoLegacyStatistic`

Stores an idempotent read-only compatibility snapshot of legacy `users.json.games`, including the source hash. It never creates ECY transactions or alters the source JSON. Phase 5 statistics derive from committed Casino settlements and are displayed separately from legacy history.

Required indexes cover idempotency, unresolved reservation lookup, user/game sessions, expiry, settlement state, transaction references, notification delivery, and review status. Triggers enforce lifecycle transitions, outcome immutability, receipt first-write, reservation retention, terminal protection, and no-delete audit history.

`EconomySeedMarker` remains authoritative for the one-time bankroll seed; no duplicate Casino seed table is proposed.

## 24. Migration Strategy

The implemented migration identity is version `500`, name `phase5-casino`, checksum `05441b86aa7cbab27eb2cf01d94ee1f998077b68498cad52d03a79c33b1e2650`. The checksum is derived from canonical normalized schema, index, and trigger definitions in `economy/phase5_schema.py`.

The staging migration supports dry-run, backup, apply, verify, reconcile, recovery, and restore reporting against explicit non-production databases. It rejects the production path and resolved-equivalent paths, uses a dedicated connection with foreign keys enabled, validates checksums, runs `integrity_check` and `foreign_key_check`, and is idempotent. Startup does not apply it automatically.

## 25. Legacy Data Migration

- Legacy balances are not converted by Phase 5; ECY wallets already belong to Phase 1/2.
- Legacy `users.json.games` counters are non-financial history and must not generate ledger entries.
- Copy legacy game statistics only as an idempotent read-only compatibility snapshot with source hash; preserve `users.json.games` byte-for-byte.
- New Casino statistics are derived exclusively from committed Phase 5 settlements and remain separate from legacy history.
- Preserve the legacy `gambler_king` achievement as history; do not grant a new Phase 5 High Roller achievement until a separate ECY threshold is approved.
- Lucky Charm remains legacy-only and has no effect on Phase 5 odds.
- Existing replay views are ephemeral runtime objects and cannot be migrated as financial sessions.
- No legacy random outcome is treated as a pending ECY result.
- Legacy source JSON remains unchanged.

## 26. Legacy Command Compatibility

When Phase 5 is disabled, current Casino commands retain legacy behavior. When Phase 5 is enabled with all prerequisites, the same command names route to ECY services. An enabled-but-unmigrated environment fails closed instead of silently using legacy coins.

`/flip` remains a free coin-toss utility. `/crash` and legacy Binomo remain unchanged until Phase 8 approval. Existing RPG, Marketplace, Deal, and Trusted Vouch routes remain unchanged.

## 27. Game-Specific Product Rules

### Blackjack

The D02-approved rules use six decks, a securely shuffled persisted fresh shoe per session, dealer hit on soft 17, 5:4 natural profit payout (2.25x gross), and dealer-natural resolution before actions. Natural against natural is a push. Double is allowed only on hard 11. One Split is allowed only for Aces or 8s and creates at most two hands, with no Double after Split, no resplit Aces, one card for each split Ace, no surrender, and no insurance. Pushes refund 1x. Timeout after ten minutes auto-stands. One active Blackjack session is allowed per user. The complete D02 simulation verified the 97.5% target within the approved tolerance.

### Slots

Use six equally weighted symbols, three reels, and one payline. Any exact pair pays 2x gross. Triples pay: 7 at 8x, diamond at 5x, star at 4x, bell at 3x, cherry at 3x, and lemon at 2.2x. All other outcomes lose. The analytical RTP is 95%, hit rate is 44.444%, and maximum liability is 8x.

### Coinflip, RPS, And Number Guessing

- Coinflip uses fair 50/50 outcomes and gross payout `floor(stake * 19400 / 10000)` for 97% RTP.
- RPS uses uniform independent choices, refunds draws at 1x, and pays wins `floor(stake * 19010 / 10000)` gross for 96.7% RTP.
- Number Guessing uses one guess from 1-20 and 19x gross payout for 95% RTP. The Phase 5 command adds a wager; the disabled legacy free path remains unchanged.

### Gacha

Gacha costs exactly 1,000 ECY and selects with equal probability from: Ampas (Zonk), Nasi Bungkus, Panci Bolong, Kunci Jawaban UN, Waifu Wangi, Pedang Excalibur, Gundam Bekas, and Sertifikat Rumah. It grants no ECY payout, item, or inventory record; duplicates are allowed and there is no pity or guarantee. Financial RTP is not applicable. The cost is a completed Casino loss credited to `ECY_CASINO`, with no payout-liability reservation and no 2% cap application. Persist the random result and receipt exactly once.

### Loot Box

Loot Box costs exactly 1,000 ECY. Outcomes are 50% at 0 ECY, 30% at 1,000 ECY gross, 15% at 2,000 ECY gross, 4% at 5,000 ECY gross, and 1% at 15,000 ECY gross. Expected gross payout is 950 ECY for 95% RTP. The maximum 15x gross liability must fit the current exposure cap before acceptance.

No implementation may infer or alter payout tables from legacy behavior. Any Blackjack adjustment after failed simulation requires renewed owner approval and may not secretly manipulate probabilities.

## 28. RTP Requirements

The long-run gross payout divided by accepted stakes must converge to the approved target for each game with an approved RTP. Refunds are excluded from both accepted-stake and gross-payout totals for RTP reporting, while losses and wins are included. Any different accounting definition requires owner approval.

Gacha has no financial payout, so financial RTP is not applicable. Loot Box has approved theoretical RTP of 95%. Blackjack remains a target until the provisional D02 simulation gate passes.

## 29. RTP Simulation Methodology

The simulator:

- Use the same pure game engine as runtime settlement.
- Accept explicit deterministic seeds.
- Record code/ruleset checksum and configuration.
- Exercise minimum stake, effective maximum, one 1,000-ECY step below effective maximum, a global 500,000-ECY request, insufficient exposure, active reservations, and integer-floor boundaries.
- Use the frozen approved Blackjack strategy model.
- Report theoretical RTP, simulated RTP, RTP after integer rounding, rejected-bet count, maximum reserved exposure, maximum observed drawdown, accepted stakes, gross payouts, refunds, variance, confidence interval, and outcome frequencies.
- Fail on target/tolerance breach, invariant violation, integer overflow, impossible outcome, nondeterminism, or bankroll insolvency.
- Emit a deterministic JSON report suitable for review.

Use 20 deterministic seeds. Run 1,000,000 rounds per seed for Slots, Coinflip, RPS, Number Guessing, and Loot Box; run 500,000 Blackjack sessions per seed. Use 99% confidence, zero invariant failures, and at most one seed outside the approved 99% interval. Tolerances are +/-0.10 percentage points for Coinflip and RPS, +/-0.20 for Blackjack, Slots, and Loot Box, and +/-0.30 for Number Guessing. Emit deterministic JSON. The broader 1,000-user, 30-90-day economy simulation remains Phase 9 and does not replace Phase 5 per-game verification.

## 30. Abuse Prevention

- Canonical integer parsing and global limits.
- Service-level feature, pause, schema, and authorization checks.
- Stable idempotency and unresolved-session reservations.
- Actor-bound and message-bound interactions.
- Approved cooldowns and session limits are secondary UX/rate controls and never replace database idempotency, uniqueness, or locking.
- Maximum bankroll exposure and concurrent reservation accounting.
- No client-provided random outcome or payout.
- Monitoring for repeated invalid requests and unusual multi-account behavior without inventing account-age gates.
- Bounded recovery and notification retries.

## 31. Security And Privacy

- Reject overflow, signed or malformed values, decimals, scientific notation, NaN, Infinity, booleans, and zero/negative stakes.
- Use server-generated opaque IDs and validate custom IDs against persisted actor/session state.
- Do not expose hidden outcomes, RNG internals, private environment values, or credentials.
- Do not log full wallet history or unrelated private Discord data.
- Administrative balance operations require the appropriate separately represented and audited Casino authorization class.
- Secure live randomness must not use user, balance, role, prior-result, or treasury inputs.
- Enforce the approved per-user and per-guild unresolved-session limits before stake debit.

## 32. Interaction Safety

- Slash handlers acknowledge before slow database or Discord work.
- Prefix handlers use the same service and return one readable response.
- Buttons verify actor, guild, channel/message identity, session version, and lifecycle state.
- Finalization edits the deferred response first and uses follow-up only as fallback.
- A response failure after commit reports the stored result without retrying financial mutation.
- Persistent custom IDs carry only opaque session/action identifiers, never hidden outcomes or balances.
- Stale interactions return the committed receipt or a safe stale/review response.
- Sanitized Blackjack, Slots, Coinflip, RPS, and Number Guessing results may be public. Slash Gacha and Loot Box results are ephemeral; prefix results are necessarily public. Validation errors, staff actions, recovery details, and hidden outcomes remain private.

## 33. Compatibility With Phase 1-4

- Phase 1 wallet, system account, transaction, ledger, seed, whitelist, and pause infrastructure remain authoritative.
- Phase 2 ECY wallets remain the user balance source.
- Phase 3 RPG stats, Energy, inventory, equipment, pets, quests, and Activity Score remain unaffected.
- Phase 4 Marketplace continues using ETM and retains its own migration, escrow, and recovery lifecycle.
- Phase 5 neither requires nor modifies Phase 3 or Phase 4 state.
- Existing supply formulas continue treating the repository-observed ECY burn account as burned supply.

## 34. Compatibility With Protected Systems

Future Phase 5 implementation must leave `cogs/deal.py` unchanged and must not modify Deal, Middleman, Trusted Vouch, payment profiles, proof or payout privacy, reports, reviews, archive, RPG, Marketplace, Crypto, Mining, Giveaway, or Eternal Options behavior.

Casino receipts and logs must never contain Deal participants, payment destinations, proof URLs, payout accounts, credentials, or private moderation notes.

## 35. Testing Matrix

Implementation verification requires:

- Unit tests for canonical stake parsing, checked arithmetic, game engines, payout calculations, and lifecycle validation.
- Property tests for zero-sum ledger entries, payout bounds, deterministic replay, and impossible-state rejection.
- Transaction tests for every win, loss, draw, refund, and rollback path.
- Concurrency tests for duplicate slash/prefix/button requests, wallet races, bankroll races, and exposure overbooking.
- Restart tests for active Blackjack, pending settlement, committed receipt replay, notification delivery, refund, and review state.
- Interaction tests for defer-first behavior, actor binding, stale controls, exactly-once finalization, and prefix parity.
- Feature-flag, pause/resume, missing-migration, and unseeded-bankroll tests.
- Migration dry-run, apply, second-run, backup/restore, production refusal, integrity, and foreign-key tests.
- Overflow, malformed input, insufficient wallet, insufficient bankroll, and maximum-exposure tests.
- RTP simulations for Blackjack, Slots, Coinflip, RPS, Number Guessing, and Loot Box using all D18 seeds, boundary wagers, exposure conditions, integer-floor cases, metrics, tolerances, and invariant gates.
- Gacha tests proving equal label selection, exactly-once persisted result/receipt, completed loss accounting, and absence of payout reservation.
- Effective-maximum tests at minimum, one step below maximum, effective maximum, global 500,000 request, insufficient exposure, and active reservations for every financial game.
- Authorization tests proving the three Casino classes are independent, Administrator is insufficient, owner has no implicit financial bypass, and emergency override is explicitly audited.
- Legacy-routing tests while Phase 5 is disabled.
- Command ownership and forbidden-alias tests.
- Phase 1-4 regression tests.
- Connected Discord staging tests; these remain pending until actually performed.

## 36. Staging Plan

Use a dedicated staging bot token, staging guild, and temporary or copied staging database. Back up the staging database, record size and SHA-256, apply the explicit Phase 5 migration twice, verify idempotency, run integrity and foreign-key checks, seed only the staging Casino Bankroll, and enable flags only in the staging process.

Synchronize slash commands to the staging guild. Exercise every slash and prefix command, replay button, duplicate click, restart state, insufficient wallet/bankroll case, pause/resume case, result receipt, and refund/review path. Inspect ledgers, sessions, exposures, notifications, audit logs, and sensitive-data handling. Production credentials and databases are prohibited.

## 37. Rollback Strategy

Before production financial activity, rollback means disabling Phase 5, pausing Casino, restoring the verified backup if an approved migration rollback is required, and returning to legacy routing.

After committed production Casino transactions exist, rollback is forward-only: pause and disable new bets, preserve schema and immutable history, settle or review existing sessions, use compensating ledger transactions for approved corrections, and never delete committed transactions or restore an old database over newer financial history.

## 38. Production Rollout Plan

Separate approval gates are required for:

1. PRD and owner decisions.
2. Implementation.
3. Automated tests and simulations.
4. Independent quality check.
5. Hardening.
6. Rollback snapshot commit.
7. Staging migration.
8. Live Discord staging.
9. Simulation approval.
10. Production migration approval.
11. Production seed approval.
12. Production feature enablement.
13. Post-rollout monitoring.

Production migration, seed, and flag enablement are distinct approvals.

## 39. Implementation Order

1. Use the recorded D01-D20 decisions to freeze versioned rulesets and service contracts; retain D02 as a simulation acceptance gate.
2. Add pure game engines and deterministic simulation support, then run the D02 Blackjack acceptance gate before claiming verified 97.5% RTP.
3. Add schema, migration, capability guard, and staging tooling.
4. Add bankroll exposure, transaction, session, settlement, and recovery services.
5. Route existing commands and views through the shared service behind the disabled flag.
6. Add pause/status, audit, notification, and operator surfaces.
7. Add complete automated, simulation, migration, concurrency, and recovery tests.
8. Run independent quality and hardening passes.
9. Perform staging migration and connected Discord smoke tests.
10. Seek separate production approvals.

## 40. Definition Of Done

Phase 5 is complete only when:

- D01-D20 remain recorded as approved with conditions; D02 has passed its simulation gate or any adjusted rules received renewed owner approval.
- All seven games use ECY through one authoritative service when enabled.
- Approved RTPs and game rules are represented by versioned pure engines.
- Bankroll exposure, settlement, refund, and excess distribution are balanced and audited.
- Idempotency, concurrency, restart recovery, and persistent interactions pass tests.
- Migration, backup, restore, integrity, and production-path guards pass.
- Simulations meet approved statistical acceptance criteria.
- Command ownership, aliases, and disabled legacy routing remain correct.
- Phase 1-4 and protected-system regressions pass.
- Connected staging is completed and reported accurately.
- Living PRD and generated handoff are current.
- Production migration, seed, and enablement have separate explicit approval.

## 41. Owner Decision Record D01-D20

Overall status: `approved_with_conditions`. There are no unresolved owner decisions. D02 was a mandatory simulation acceptance gate and is now passed.

| ID | Status | Recorded decision |
| --- | --- | --- |
| D01 | `approved_with_revision` | The 2% cap applies to total maximum reserved gross liability. Effective maximum stake uses 1,000-ECY steps, available unreserved bankroll, and worst-case permitted Blackjack Double or Split exposure. |
| D02 | `approved_recommended` | The final six-deck rules restrict Double to hard 11, Split to Aces/8s, and pay a winning natural at 5:4 profit (2.25x gross). The complete simulation passed the 97.5% target tolerance and seed gate. |
| D03 | `approved_with_revision` | Approve the exact equal-weight one-payline Slots table at 95% RTP and 1,000-ECY wager steps. |
| D04 | `approved_with_revision` | Approve fair Coinflip with `floor(stake * 19400 / 10000)` gross payout and 1,000-ECY wager steps. |
| D05 | `approved_with_revision` | Approve uniform RPS with draw refund, `floor(stake * 19010 / 10000)` win payout, and 1,000-ECY wager steps. |
| D06 | `approved_with_revision` | Approve one-attempt 1-20 Number Guessing at 19x gross and 1,000-ECY wager steps. |
| D07 | `approved_with_revision` | Approve fixed 1,000-ECY cosmetic-only Gacha with equal eight-label outcomes, no payout or inventory grant, and no liability reservation. |
| D08 | `approved_recommended` | Approve fixed 1,000-ECY Loot Box at 95% RTP and 15x maximum gross liability. |
| D09 | `approved_with_revision` | Approve one unresolved session per user, one active Blackjack session per user, 100 unresolved sessions per guild, ten-minute Blackjack abandonment, 90-second replay controls, and committed-operation cooldowns. |
| D10 | `approved_recommended` | Approve mixed public/ephemeral visibility with private errors, staff actions, and recovery details. |
| D11 | `approved_recommended` | Preserve legacy statistics byte-for-byte and snapshot them only as idempotent read-only compatibility history; new statistics use committed settlements. |
| D12 | `approved_recommended` | Keep High Roller as legacy history and Lucky Charm legacy-only with no Phase 5 odds effect. |
| D13 | `approved_recommended` | Use the approved rolling-30-day committed non-Casino activity definition for active members. |
| D14 | `approved_recommended` | Approve the exact safe-seed formula; the production seed transaction remains a separate cutover approval. |
| D15 | `approved_with_revision` | Use independent `CASINO_CONTROL`, `CASINO_FINANCIAL`, and `CASINO_RECOVERY` classes with no Administrator or implicit owner financial bypass. |
| D16 | `approved_recommended` | Distribute excess manually only while paused, retaining safe bankroll and unresolved/review liabilities, in 60/20/remainder proportions. |
| D17 | `approved_recommended` | Recover from persisted state and original IDs; ambiguous state requires reviewed, authorized compensation. |
| D18 | `approved_with_revision` | Approve the deterministic simulation matrix plus boundary, exposure, rejection, rounding, and drawdown reporting. |
| D19 | `approved_recommended` | Migration identity `500` / `phase5-casino` is implemented for explicit non-production staging use only. |
| D20 | `approved_recommended` | `ECONOMY_PHASE5_ENABLED=false` exists; missing prerequisites fail closed and production remains disabled. |

## 42. Implementation And D18 Result

Casino V1 now includes integer-only game engines, cryptographically unique wager request identities, one unresolved session per guild/user, persisted hidden outcomes, exact bankroll exposure reservations, balanced ECY ledger settlement, Blackjack action persistence, least-privilege staff controls, restart recovery, notification outbox delivery, explicit migration 500 tooling, and read-only dashboard status. Legacy routes remain active while the flag is false. No Casino write API was added.

The first complete approved D18 run used 20 deterministic seeds, 1,000,000 rounds per seed for each fixed game, and 500,000 Blackjack sessions per seed. Its Blackjack result was `0.9796613279031707`, with 19 seeds outside acceptance.

The owner-approved revision then restricted Double to hard 10-11 and Split to Aces/8s. The complete D18 matrix was rerun at the same full volume without dynamic tuning. Fixed-game results remained unchanged and passed. Revised Blackjack produced simulated and integer-rounded RTP `0.977603947051104` against target `0.975` and tolerance `0.002`. Its 99% confidence interval was `[0.9767933401952931, 0.9784143256333722]`; 5 seeds were outside the approved interval. The deviation above target was `0.002603947051104`, exceeding tolerance by `0.000603947051104`. Maximum reserved exposure was `500,000 ECY`, maximum observed drawdown was `186,600 ECY`, rejected wager cases were `3`, and invariant failures were `0`.

The artifact for that hard-10-11 candidate had SHA-256 `d70cfaeedff671bed5c6e416ebce8e3a6dfb5e386267a9cf4c468da5426ab9f3`.

The final owner-approved revision removed hard-10 Double and retained every other rule. The full harness was rerun rather than reusing fixed-game output, preserving the shared per-seed RNG sequence. Final Blackjack simulated and integer-rounded RTP was `0.9727344988964964`; its 99% confidence interval was `[0.9719145251803206, 0.9735540213511035]`. The result was `0.0022655011035036` below target and exceeded tolerance by `0.0002655011035036`. Two seeds were outside acceptance, maximum reserved exposure was `500,000 ECY`, maximum observed drawdown was `165,000 ECY`, rejected wager cases were `3`, and invariant failures were `0`. Fixed games passed with unchanged measured values. The final artifact SHA-256 is `1ae042eae52b4f45078b7308da2b0637c6f8b94be3cf6d67a801d4de4ef6b643`.

At that point Phase 5 remained implemented but not staging-ready. The failed hard-11/6:5 result was preserved and no automatic adjustment was made before the separately approved natural-payout calibration.

The final natural-payout calibration retained hard-11-only Double and changed a winning natural from 6:5 to 5:4 profit, producing 2.25x gross through checked integer arithmetic. The full harness ran at unchanged volume and produced Blackjack RTP `0.9748809836156533` with 99% confidence interval `[0.9740564018985632, 0.9757051127387927]`. Absolute deviation from target was `0.0001190163843467`; one seed was outside acceptance, maximum exposure remained `500,000 ECY`, maximum drawdown was `176,000 ECY`, rejected wager cases were `3`, and invariant failures were `0`. The complete D18 result passed. Artifact SHA-256: `b24dc703728749a6ee32d637f8b62fd676833627dd9498e06c7dba13f0dea285`.

D02 is now passed and Phase 5 is **ready for connected Discord staging**. Dashboard production build and live staging remain pending. Production remains unapproved, unmigrated, unseeded, and disabled.
