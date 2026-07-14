# Phase 5 Casino Product Requirements Document

## 1. Document Status

- Phase: Phase 5 - Casino
- Status: Planning
- Implementation status: Not started
- Production status: Not approved
- Production migrated: No
- Production enabled: No
- Document language: English
- Current task commit: `PENDING`

This document is an implementation plan, not an authorization to create a migration, change runtime behavior, seed a bankroll, or enable production. All items marked **REQUIRES OWNER DECISION** must be resolved before Phase 5 implementation can be approved.

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

- Blackjack, target RTP 97.5%.
- Slots, target RTP 95%.
- Coinflip, target RTP 97%.
- Rock-paper-scissors, target RTP 96.7%.
- Number guessing, target RTP 95%.
- Gacha, with product values still requiring owner approval.
- Loot boxes, with product values still requiring owner approval.
- ECY-only Casino stakes and payouts.
- Global stake range from 1,000 ECY through 500,000 ECY.
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

Exact Blackjack actions remain an owner decision.

## 8. Slash Command Plan

Preserve the existing command names:

| Command | Existing parameters | Proposed Phase 5 contract |
| --- | --- | --- |
| `/blackjack` | `bet: int` | Preserve `bet`; interactive rules await owner approval. |
| `/slot` | `bet: int` | Preserve `bet`; payout table awaits owner approval. |
| `/cf` | `tebakan: str`, `bet: int` | Preserve command and choices; payout mechanism awaits owner approval. |
| `/rps` | `pilihan: str`, `bet: int` | Preserve command and choices; payout/draw mechanism awaits owner approval. |
| `/tebak` | `tebakan: int` | Final stake parameter and range require owner approval. |
| `/gacha` | none | Final fixed-cost or stake parameter requires owner approval. |
| `/box` | none | Final fixed-cost or stake parameter requires owner approval. |

No `/casino` group or replacement command name is approved by this document.

## 9. Prefix Command Plan

Preserve:

- `w!blackjack <bet>`
- `w!slot <bet>`
- `w!cf <head|tail> <bet>`
- `w!rps <batu|gunting|kertas> <bet>`
- `w!tebak <guess>` with its final stake syntax requiring owner approval
- `w!gacha` with its final cost/stake syntax requiring owner approval
- `w!box` with its final cost/stake syntax requiring owner approval

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
- `/economy pause casino`, `/economy resume casino`, and status inspection retain their existing bot-owner or enabled-economy-whitelist policy.
- Discord Administrator permission alone does not grant minting, bankroll adjustment, seed, or unrestricted balance mutation.
- Authorization for seed, bankroll adjustment, and excess distribution is a required owner decision and must be enforced in the service, not only through command decorators.

## 12. Currency And Wallet Rules

- Casino stakes and payouts use integer ECY only.
- The accepted stake is between 1,000 and 500,000 ECY inclusive.
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

The exact active-member definition requires owner approval. Until then, the formula cannot produce an approved production seed.

Operational availability must account for the current `ECY_CASINO` balance and unresolved reserved liabilities. A new request is rejected before stake consumption when it cannot be supported. The meaning of the 2% cap is unresolved: gross payout, net profit, or total maximum reserved liability must be selected by the owner.

The existing `EconomySeedMarker` and `system_seed` transaction model provide one-time, balanced issuance-to-bankroll seeding. All seed defaults remain zero until separately approved.

Excess is evaluated only after subtracting the approved safe requirement and unresolved liabilities. Distribution uses the approved 60/20/20 proportions and existing `ECY_GENERAL`, `ECY_RESERVE`, and `ECY_BURN` accounts. Authorization, schedule, and retained safety threshold require owner approval. Casino loss money is not distributed after each round.

## 14. Bet Validation

Validation occurs both before and after `BEGIN IMMEDIATE`:

- Required flags and schema capability.
- Guild and actor identity.
- Casino and global economy pause state.
- Canonical integer stake and global bounds.
- Game-specific choices and approved ruleset version.
- User ECY balance and wallet version.
- Bankroll seed, balance, version, and unresolved exposure.
- Session limit and cooldown when approved.
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
- Expired sessions follow the owner-approved timeout policy.

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

Proposed flag: `ECONOMY_PHASE5_ENABLED=false`. The exact name requires owner approval.

- Economy V1 disabled: preserve legacy routing and perform no Phase 5 schema access.
- Phase 2 disabled: Phase 5 cannot use ECY and must fail closed if its flag is inconsistently enabled.
- Phase 5 disabled: preserve existing legacy commands and behavior.
- Casino paused: block new bets and non-essential mutations; allow recovery, committed receipt replay, approved settlement, and approved refunds.
- Migration missing: fail closed without legacy fallback when Phase 5 is explicitly enabled.
- Bankroll not seeded: block new bets without consuming stakes.

Phase 3 and Phase 4 are not required dependencies for Casino and remain independently controlled.

## 22. Emergency Pause Behavior

`/economy pause casino` blocks new sessions immediately after service-level revalidation. Existing committed results remain valid. Recoverable pending sessions settle from persisted state when settlement remains valid. Refunds occur only under the approved refund policy; ambiguous states enter review.

Pause and resume create permanent audit records and survive restart through `EconomyFeatureState`. Authorization remains bot owner or enabled economy-whitelist member unless the owner approves a different policy.

## 23. Database Schema Proposal

This proposal creates no schema in the planning task.

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

Required indexes cover idempotency, unresolved reservation lookup, user/game sessions, expiry, settlement state, transaction references, notification delivery, and review status. Triggers enforce lifecycle transitions, outcome immutability, receipt first-write, reservation retention, terminal protection, and no-delete audit history.

`EconomySeedMarker` remains authoritative for the one-time bankroll seed; no duplicate Casino seed table is proposed.

## 24. Migration Strategy

The exact migration version is a required owner decision; `500` is proposed from the existing phase numbering convention. Its checksum is computed from the final approved canonical schema and must never be invented in planning.

The future migration must support dry-run, backup, apply, verify, reconcile, recovery, and rollback reporting against explicit non-production databases. It must reject the production path and resolved-equivalent paths, use a dedicated connection with foreign keys enabled, validate row counts and checksums, run `integrity_check` and `foreign_key_check`, and be idempotent. Startup must not apply it automatically.

## 25. Legacy Data Migration

- Legacy balances are not converted by Phase 5; ECY wallets already belong to Phase 1/2.
- Legacy `users.json.games` counters are non-financial history and must not generate ledger entries.
- Whether counters are copied into a compatibility table or remain read-only requires owner approval.
- Existing replay views are ephemeral runtime objects and cannot be migrated as financial sessions.
- No legacy random outcome is treated as a pending ECY result.
- Legacy source JSON remains unchanged.

## 26. Legacy Command Compatibility

When Phase 5 is disabled, current Casino commands retain legacy behavior. When Phase 5 is enabled with all prerequisites, the same command names route to ECY services. An enabled-but-unmigrated environment fails closed instead of silently using legacy coins.

`/flip` remains a free coin-toss utility. `/crash` and legacy Binomo remain unchanged until Phase 8 approval. Existing RPG, Marketplace, Deal, and Trusted Vouch routes remain unchanged.

## 27. Game-Specific Product Rules

Approved rules are limited to currency, global stake bounds, listed target RTPs, no winner tax, prohibited odds dependencies, and bankroll exposure. Exact Blackjack, Slots, Coinflip, RPS, Number Guessing, Gacha, and Loot Box rules listed in Section 41 require owner approval.

No implementation may infer payout tables from current legacy behavior merely to meet a target RTP.

## 28. RTP Requirements

The long-run gross payout divided by accepted stakes must converge to the approved target for each game with an approved RTP. Refunds are excluded from both accepted-stake and gross-payout totals for RTP reporting, while losses and wins are included. Any different accounting definition requires owner approval.

Gacha and Loot Box RTP or expected value remain undefined. No acceptance claim may be made for them.

## 29. RTP Simulation Methodology

The future simulator must:

- Use the same pure game engine as runtime settlement.
- Accept explicit deterministic seeds.
- Record code/ruleset checksum and configuration.
- Exercise minimum, maximum, fixed, and owner-approved wager distributions.
- Use an owner-approved Blackjack strategy model.
- Report accepted stakes, gross payouts, refunds, observed RTP, variance, confidence interval or equivalent statistical bound, drawdown, maximum exposure, and outcome frequencies.
- Fail on target/tolerance breach, invariant violation, integer overflow, impossible outcome, nondeterminism, or bankroll insolvency.
- Emit a deterministic JSON report suitable for review.

Casino-specific round counts, seeds, confidence level, tolerance, and maximum deviation require owner approval. The broader 1,000-user, 30-90-day economy simulation remains Phase 9 and does not replace Phase 5 per-game verification.

## 30. Abuse Prevention

- Canonical integer parsing and global limits.
- Service-level feature, pause, schema, and authorization checks.
- Stable idempotency and unresolved-session reservations.
- Actor-bound and message-bound interactions.
- Cooldowns and session limits only after owner approval.
- Maximum bankroll exposure and concurrent reservation accounting.
- No client-provided random outcome or payout.
- Monitoring for repeated invalid requests and unusual multi-account behavior without inventing account-age gates.
- Bounded recovery and notification retries.

## 31. Security And Privacy

- Reject overflow, signed or malformed values, decimals, scientific notation, NaN, Infinity, booleans, and zero/negative stakes.
- Use server-generated opaque IDs and validate custom IDs against persisted actor/session state.
- Do not expose hidden outcomes, RNG internals, private environment values, or credentials.
- Do not log full wallet history or unrelated private Discord data.
- Administrative balance operations require explicit audited authorization.
- Secure live randomness must not use user, balance, role, prior-result, or treasury inputs.
- Rate-limit abandoned-session creation after owner-approved limits are defined.

## 32. Interaction Safety

- Slash handlers acknowledge before slow database or Discord work.
- Prefix handlers use the same service and return one readable response.
- Buttons verify actor, guild, channel/message identity, session version, and lifecycle state.
- Finalization edits the deferred response first and uses follow-up only as fallback.
- A response failure after commit reports the stored result without retrying financial mutation.
- Persistent custom IDs carry only opaque session/action identifiers, never hidden outcomes or balances.
- Stale interactions return the committed receipt or a safe stale/review response.

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

Future implementation requires:

- Unit tests for canonical stake parsing, checked arithmetic, game engines, payout calculations, and lifecycle validation.
- Property tests for zero-sum ledger entries, payout bounds, deterministic replay, and impossible-state rejection.
- Transaction tests for every win, loss, draw, refund, and rollback path.
- Concurrency tests for duplicate slash/prefix/button requests, wallet races, bankroll races, and exposure overbooking.
- Restart tests for active Blackjack, pending settlement, committed receipt replay, notification delivery, refund, and review state.
- Interaction tests for defer-first behavior, actor binding, stale controls, exactly-once finalization, and prefix parity.
- Feature-flag, pause/resume, missing-migration, and unseeded-bankroll tests.
- Migration dry-run, apply, second-run, backup/restore, production refusal, integrity, and foreign-key tests.
- Overflow, malformed input, insufficient wallet, insufficient bankroll, and maximum-exposure tests.
- RTP simulations for all five games with approved targets.
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

1. Resolve all owner decisions and freeze a versioned ruleset.
2. Add pure game engines and deterministic simulation support.
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

- Every owner decision is approved and recorded.
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

## 41. REQUIRES OWNER DECISION

1. Whether the 2% Casino Bankroll cap applies to gross payout, net player profit, or total maximum reserved liability.
2. How the cap applies to Blackjack Double and Split.
3. Blackjack deck count, shuffle model, natural payout, dealer soft-17 rule, Split, Double, surrender, insurance, and timeout behavior.
4. Slots symbol weights, paylines, and complete payout table.
5. Coinflip payout or probability mechanism required to achieve 97% RTP.
6. RPS payout and draw policy required to achieve 96.7% RTP.
7. Number-guessing range, stake parameter, and payout table.
8. Gacha fixed or variable stake, reward catalog, probabilities, ownership effects, expected value, and RTP.
9. Loot Box fixed or variable stake, reward catalog, probabilities, ownership effects, expected value, and RTP.
10. Per-game cooldowns, unresolved-session limits, and abandoned-session timeout.
11. Public versus ephemeral result policy.
12. Legacy `users.json` statistic migration and compatibility reporting.
13. Legacy High Roller achievement and Lucky Charm behavior.
14. Definition and data source for active members during the previous 30 days.
15. Exact production Casino Bankroll seed.
16. Authorization for bankroll seed, adjustment, and excess distribution.
17. Excess-distribution schedule and minimum retained bankroll.
18. Refund versus manual-review policy for ambiguous or expired sessions.
19. Casino-specific simulation round counts, deterministic seeds, wager distributions, Blackjack strategy, confidence level, tolerance, and maximum deviation.
20. Exact migration version; `500` is proposed but not approved.
21. Exact feature-flag name; `ECONOMY_PHASE5_ENABLED` is proposed but not approved.
