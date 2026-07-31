# Phase 6 Crypto V1

## Status And Guardrails

Phase 6 is implemented for temporary-database verification and connected staging.
`ECONOMY_PHASE6_ENABLED` defaults to `false`. Production is not migrated, seeded,
enabled, or approved. Migration `600 / phase6-crypto` is explicit and never runs at
startup. Mining, Giveaway, Eternal Options, Casino rules, Deal, Middleman, Trusted
Vouch, and Marketplace behavior are outside this phase.

## Market Scope

One global immutable V1 series owns asset definitions, current prices, ticks,
events, history, and news. Guilds separately own wallets, holdings, trades,
Market Reserve balances, seed markers, authorizations, and ledgers.

| Symbol | Name | Base ECY | Normal max/tick |
| --- | --- | ---: | ---: |
| ETHR | ETHERnal | 10,000 | 0.15% |
| ORCL | Cosmic Oracle | 10,000 | 0.25% |
| MTR | Meteorite | 10,000 | 0.35% |
| ECLP | Eclipsoin | 10,000 | 0.50% |
| ORBT | Orbitcoin | 20,000 | 0.70% |
| TRST | TrustCoin | 14,000 | 0.90% |
| LUNA | Lunniera | 13,000 | 1.20% |

The source PRD spells ECLP as `Eclipscoin`; repository command data uses
`Eclipsoin`, so current repository behavior is preserved without changing ECLP.
Prices are clamped to 20%-500% of base. Normal ticks combine sampled movement
with a 2% pull of the distance to base, then clamp the complete movement to the
asset limit. Every UTC minute has one persisted outcome and no offline backfill.

One mutually exclusive event draw is made per tick. A normal event occurs at
0.05% per minute and moves one selected asset 8%-20%. A major event occurs at
0.005% per minute and moves one selected asset 25%-30%. Direction is equiprobable.
The event replaces normal movement for that asset; all others use normal mean
reversion.

## Trading And Accounting

One asset equals 100,000,000 integer units. `/market`, `/portfolio`, `/buycoin`,
and `/sellcoin`, plus compatible prefix commands, retain ownership in the RPG cog.
Amounts accept up to eight decimal places or `all`; gross value is
`floor(units * committedPrice / 100000000)` and must be at least 50 ECY.

Both buys and sells charge `floor(gross * 2%)`. Fee allocation is 50% to
`ECY_MARKET`, 30% to `ECY_GENERAL`, and the integer remainder to `ECY_BURN`.
Buys include fees in cost basis. Partial sales allocate basis proportionally with
integer floor; full sales consume all remaining basis. Portfolio output reports
average buy price, cumulative realized profit, and estimated net unrealized profit.

Buy `all` is the largest whole asset-unit quantity affordable after fee at the
locked price. Sell `all` is the complete active holding. Both are recalculated only
when the original request is first settled; retries return its immutable receipt.
One `BEGIN IMMEDIATE` transaction owns the transaction header, trade, wallet,
Market Reserve, holding, fee accounts, zero-sum ledger, history, and receipt.

## Migration And Recovery

Migration 600 creates global market tables and guild-scoped holding, trade,
authorization, recovery, and outbox tables. It preserves `users.json` and
`market.json`. Legacy holdings use exactly one completed Phase 1 target guild;
ambiguous mappings, malformed values, unknown symbols, and over-precision values
remain non-tradeable in migration review. Valid values use the initial V1 price as
baseline cost basis. Migration does not seed `ECY_MARKET`.

Startup recovery commits persisted reserved ticks, adopts proven committed trade
receipts, retains ambiguous operations as `REVIEW_REQUIRED`, and reclaims expired
news leases. It never rerolls prices, replaces request IDs, duplicates fees, or
silently funds Market Reserve. News compares with the latest committed price at or
before 30 minutes earlier; changes below 10% are silent, 10%-24.99% are alerts,
and at least 25% are surge/crash news, limited globally to one per asset per 30
minutes before guild outbox fan-out.

## Rollout

Staging uses a dedicated database, explicit backup/apply/verify/reconcile flow,
an explicit positive Market Reserve seed through `SYSTEM_SEED`, and all integrity
and foreign-key checks. Production cutover remains blocked pending separate
approval and Phase 7 integration for continuing legacy Mining output.
