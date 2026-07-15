THIS FILE IS GENERATED.
DO NOT EDIT IT MANUALLY.
Update docs/project_state.json and run:
python scripts/update_ai_handoff.py

# W2E Bot — AI Coder Handoff

## Purpose

Permanent machine-readable project handoff. Code and committed constraints outrank this state.

## Source-Of-Truth Precedence

- Committed migrations and database constraints
- Committed automated tests and integrity checks
- Committed service-layer implementation
- Committed runtime configuration and command registration
- docs/project_state.json
- Generated docs/AI_CODER_HANDOFF.md
- Historical implementation reports
- Previous chat history

## Repository Snapshot

- **lastKnownBranch:** codex/economy-v1-phase9a
- **observedBranch:** codex/economy-v1-phase9a
- **observedHead:** a5490ac1f2a914f1c0a81f2c80e4172f5fb37ef1
- **remotePushAfterPhase4:** false
- **workingTreeAtSeed:** clean before Phase 9B implementation

## Project Progress

| id | name | status |
| --- | --- | --- |
| phase1 | Economy Foundation | complete |
| phase2 | Economy Progression | complete |
| phase3 | RPG | complete_and_committed |
| phase4 | Eternal Marketplace | complete_and_committed |
| phase5 | Casino | implemented_staging_ready |
| phase6 | Crypto | implemented_staging_ready |
| phase7 | Mining | implemented_staging_ready |
| phase8 | Giveaway and Eternal Options | implemented_staging_ready |
| phase9a | Backend Safety Foundation | implemented_local_verification |
| phase9b | Economy Dashboard And Notification Routing | implemented_local_verification |

## Capabilities By Phase

- **phase1:**
  - wallet
  - ledger
  - treasury
  - admin controls
  - migration framework
- **phase2:**
  - profile
  - Daily
  - Weekly
  - Work
  - Transfer
  - Exchange
  - activity events
- **phase3:**
  - catalog
  - equipment
  - pets
  - Hunt
  - Dungeon
  - Boss
  - Quest
  - recovery
- **phase4:**
  - listing
  - escrow
  - purchase
  - return
  - watch
  - report
  - moderation
  - recovery
- **phase5:**
  - ECY Casino games
  - bankroll exposure reservations
  - atomic settlement
  - Blackjack persisted actions
  - authorization classes
  - restart recovery
  - migration 500
  - D18 simulation passed; ready for connected Discord staging
- **phase6:**
  - global Crypto prices and ticks
  - guild holdings and Market Reserve
  - atomic ECY buy/sell
  - cost basis and profit
  - market news outbox
  - restart recovery
  - migration 600
  - deterministic market simulation passed
- **phase7:**
  - ECY rig purchases and maintenance
  - profile-level slots
  - seven-day price accrual
  - overflow-safe fractional carry
  - asset-only claims
  - legacy rig quarantine
  - restart recovery
  - migration 700
  - deterministic Mining simulation passed
- **phase8:**
  - Giveaway ECY ticket escrow
  - capped Activity Score eligibility
  - non-overlapping voice blocks
  - secure draws and structured redraw evidence
  - Eternal Options
  - shared Casino exposure
  - restart recovery
  - restart-safe notification outbox replay
  - migration 800
  - deterministic simulations passed
- **phase9a:**
  - Discord OAuth2 PKCE
  - bounded server sessions
  - one-time CSRF
  - signed internal requests
  - explicit dashboard permissions
  - append-only operator audit
  - legacy route tombstones
  - migration 900
- **phase9b:**
  - authoritative Economy reporting
  - versioned notification routes
  - durable delivery reservation and marker adoption
  - controlled pause and reviewed recovery
  - protected operational dashboard
  - migration 910

## Protected Systems

- Deal
- Middleman
- Trusted Vouch
- payment configuration
- reports
- reviews
- archive
- casino
- crypto
- mining
- giveaway
- legacy recovery
- unrelated dashboard systems

## Feature Flags

- **ECONOMY PHASE2 ENABLED:** false
- **ECONOMY PHASE3 ENABLED:** false
- **ECONOMY PHASE4 ENABLED:** false
- **ECONOMY PHASE5 ENABLED:** false
- **ECONOMY PHASE6 ENABLED:** false
- **ECONOMY PHASE7 ENABLED:** false
- **ECONOMY PHASE8 ENABLED:** false
- **ECONOMY V1 ENABLED:** false

## Command Ownership

- **/leaderboard:** RPG
- **/rank:** Trusted Vouch
- **/vouchleaderboard:** Trusted Vouch
- **w!deal leaderboard:** Trusted Vouch
- **w!deal rank:** Trusted Vouch
- **w!leaderboard:** RPG
- **w!rank:** RPG

## Forbidden Aliases

- w!vouch
- w!vouches
- w!rep
- w!trustlb
- w!trank
- w!vouchleaderboard
- w!vouchremove
- w!vouchreport

## Legacy Commands

- /sell
- /shop
- /buy
- /buypet
- /rob
- /pray
- /curse
- /flip
- /top
- /attack
- /bounty hunt

## Important Commits

| commit | subject |
| --- | --- |
| 9b07585 | feat(economy): complete phase 3 RPG and staging hardening |
| 02fcac317fb6d6856fc8a1f6ee27d6cba3661f0d | feat(economy): complete phase 4 eternal marketplace |
| 7ca5e70 | feat(docs): add living PRD and AI coder handoff automation |
| 8e924d4 | feat(docs): add phase 5 casino PRD and guarded planning state |
| 25ea3bb318e292044fa4b230ccbd08bf728efb0e | feat(economy): implement phase 5 casino |
| a7da7f1f243a045c88f1d304c2b6be4e865c23cf | feat(economy): implement phase 6 crypto |
| 381d99a249dd9d009fc582947635c1aabffbd9c3 | feat(economy): implement phase 7 mining |
| 2931a47b0b7db2626f124d744391a788bcd79051 | feat(economy): implement phase 8 giveaway and eternal options |
| a5490ac1f2a914f1c0a81f2c80e4172f5fb37ef1 | feat(dashboard): implement phase 9a backend safety foundation |

## Migrations And Checksums

-
  - **checksum:** -
  - **name:** economy foundation
  - **verificationStatus:** last_known_requires_verification
  - **version:** 100
-
  - **checksum:** -
  - **name:** phase2 progression
  - **verificationStatus:** last_known_requires_verification
  - **version:** 200
-
  - **checksum:** ba8c15135f68a8d78f3eccb550721e86f99d06b3a37b77906eb9ad9f4fcc729b
  - **evidencePaths:**
    - economy/phase3_migrations.py
    - economy/catalog.py
  - **name:** phase3-rpg
  - **verificationStatus:** verified
  - **version:** 300
-
  - **checksum:** d594bff8aa86bc75706d322b655e9ed41def36fca45cbf65908374b7b564159c
  - **evidencePaths:**
    - economy/phase3_schema.py
  - **name:** phase3-hardening
  - **verificationStatus:** verified
  - **version:** 301
-
  - **checksum:** 9d8e6f4b8688f8990bed8810bb5dbcd1593d70ee80df4e9d27c219d4207bab0e
  - **evidencePaths:**
    - economy/phase4_schema.py
  - **name:** phase4-marketplace
  - **verificationStatus:** verified
  - **version:** 400
-
  - **checksum:** 05441b86aa7cbab27eb2cf01d94ee1f998077b68498cad52d03a79c33b1e2650
  - **evidencePaths:**
    - economy/phase5_schema.py
  - **name:** phase5-casino
  - **verificationStatus:** verified
  - **version:** 500
-
  - **checksum:** 33d17df45ef14e4140ce58b3c5718ddea39894a21e176bcb3617e2c4b2f14d3b
  - **evidencePaths:**
    - economy/phase6_schema.py
  - **name:** phase6-crypto
  - **verificationStatus:** verified
  - **version:** 600
-
  - **checksum:** 5ab02d518818b7f3449d8008ed2712d9ccd6ba684bf237df6d080870563742e3
  - **evidencePaths:**
    - economy/phase7_schema.py
  - **name:** phase7-mining
  - **verificationStatus:** verified
  - **version:** 700
-
  - **checksum:** 33c88d9b49b31b0b029c641f7fecaadeacd57db2f5f2e8c6dacfb8cd958d40a9
  - **evidencePaths:**
    - economy/phase8_schema.py
  - **name:** phase8-giveaway-options
  - **verificationStatus:** verified
  - **version:** 800
-
  - **checksum:** ba692b4677207d848799439d708e0367ef766d56dec852db78546bdd74916aa2
  - **evidencePaths:**
    - economy/phase9a_schema.py
  - **name:** phase9a-backend-safety
  - **verificationStatus:** verified
  - **version:** 900
-
  - **checksum:** 90c50b1d6a1a0515086bf14cdec82573ee83baf66e06524ee1bda963a2de4934
  - **evidencePaths:**
    - economy/phase9b_schema.py
  - **name:** phase9b-dashboard-notification-routing
  - **verificationStatus:** verified
  - **version:** 910

## Catalog Versions And Checksums

-
  - **checksum:** ba8c15135f68a8d78f3eccb550721e86f99d06b3a37b77906eb9ad9f4fcc729b
  - **evidencePaths:**
    - economy/catalog.py
  - **verificationStatus:** verified
  - **version:** rpg-v1.0.0

## Deal, Middleman, And Trusted Vouch

- **deal:** Private staged middleman flow: forms, payment instruction, proof, funds confirmation, payout, dispute, completion, archive.
- **middleman:** Middleman cannot be buyer or seller; actor-aware permissions remain required.
- **trustedVouch:** Verified deal and approved manual vouch data remain isolated from RPG and Marketplace.

## Interaction Safety And Persistent Recovery

- **interactionSafety:** Deferred interactions use bounded finalization and actor/stage validation.
- **persistentViews:** Tracked staged views recover from persisted message identity without duplicating active controls.

## Payment Configuration

- **behavior:** Per-user payment profiles and private proof/payout data remain restricted to the Deal flow.
- **privacy:** Never expose payment destinations, proof URLs, credentials, or private notes in this handoff.

## Economy Design

- **feeAllocation:** 80% treasury, 10% reserve, remainder burn
- **integerOnly:** true
- **ledgerRule:** Each committed transaction is zero-sum per currency.
- **maxAmount:** 9000000000000000
- **systemAccounts:**
  - ETM_GENERAL
  - ETM_BOSS_DUNGEON
  - ETM_EVENT
  - ETM_RESERVE
  - ETM_BURN
  - ETM_ISSUANCE
  - ECY_GENERAL
  - ECY_GIVEAWAY
  - ECY_CASINO
  - ECY_MARKET
  - ECY_MINING
  - ECY_RESERVE
  - ECY_BURN
  - ECY_ISSUANCE

## System Accounts And Constants

- **feeBps:** 500
- **maxAmount:** 9000000000000000
- **systemAccounts:**
  - ETM_GENERAL
  - ETM_BOSS_DUNGEON
  - ETM_EVENT
  - ETM_RESERVE
  - ETM_BURN
  - ETM_ISSUANCE
  - ECY_GENERAL
  - ECY_GIVEAWAY
  - ECY_CASINO
  - ECY_MARKET
  - ECY_MINING
  - ECY_RESERVE
  - ECY_BURN
  - ECY_ISSUANCE

## Phase 1

- wallets
- system accounts
- PENDING/COMMITTED/REVERSED transaction headers
- zero-sum ledger
- mint whitelist
- idempotent mutation
- integer-only balances

## Phase 2

- **daily:** 50000 ETM and 5000 ECY, 24-hour cooldown
- **exchange:** 10 ETM = 1 ECY, 5% fee, multiple of 200, level-gated daily limits
- **profile:** base HP 1000, ATK 50, DEF 25, Crit 500 bps, Energy 100
- **transfer:** ETM minimum 10000, 5% fee, daily submitted limit 2000000
- **weekly:** 350000 ETM and 35000 ECY, seven-day cooldown
- **work:** 10000-18000 ETM, two-hour cooldown, four Jakarta-day successes

## Phase 3 RPG

- starter package
- versioned catalog
- inventory/equipment/pets
- enhancement
- crafting
- open attempts
- Hunt
- Dungeon
- Boss
- Quest
- persisted random outcomes
- restart recovery

## Complete RPG Balance Tables

- **assetPolicy:** Common-Epic eggs tradeable; Legendary/Eternal eggs and hatched pets non-tradeable; Epic chest and Dungeon Ticket non-tradeable; blueprints tradeable; LEGACY_BOUND and STARTER_BOUND assets are not marketplace eligible.
- **boss:**
  - **ELITE:** Lv50 HP750000 DEF300 pool8000000 valid1500 petXP300; Astral Fragment40%, Beast Core30%, Legendary0.5%, Epic5%, Epic egg0.75%
  - **NORMAL:** Lv20 HP100000 DEF100 pool2000000 valid100 petXP100; Shadow Crystal35%, Beast Core20%, Epic0.5%, Rare4%
  - **WORLD:** Lv80 HP5000000 DEF700 pool25000000 valid12500 petXP800; Dragon Core50%, Eternal Fragment1%, Legendary3%, Eternal egg0.05%, Legendary egg0.5%, random blueprint0.25%
  - **distribution:** 20% equal, 65% proportional, 15% top ten; contribution rank then user ID remainder; cooldown 30s.
- **crafting:**
  - **EPIC:** 5000000 ETM +45 Astral Fragments +5 Beast Cores
  - **ETERNAL:** 75000000 ETM +50 Eternal Fragments +20 Dragon Cores + matching blueprint
  - **LEGENDARY:** 20000000 ETM +30 Dragon Cores +10 Beast Cores
  - **RARE:** 1200000 ETM +35 Shadow Crystals +3 Beast Cores
  - **UNCOMMON:** 300000 ETM +20 Iron Shards
- **dungeon:**
  - **eternal abyss:** Lv45 entry 500000; ETM 1200000-2000000; XP 1800-2500; Epic25%, Legendary5%, Eternal Blueprint0.25%, Dragon Core45%, Eternal Fragment2%, Legendary egg0.3%
  - **forgotten crypt:** Lv10 entry 50000 ETM or ticket; ETM 120000-220000; XP 250-400; Uncommon35%, Rare12%, Shadow Crystal60%, Rare egg1%
  - **funding:** ETM_BOSS_DUNGEON insufficient means AWAITING_FUNDS without entry debit or reroll.
  - **shadow fortress:** Lv25 entry 150000; ETM 350000-650000; XP 700-1000; Rare30%, Epic10%, Legendary0.5%, Astral Fragment55%, Epic egg1%
- **enhancement:**
  - **bonusBps:**
    - 0
    - 500
    - 1000
    - 1600
    - 2300
    - 3100
    - 4000
    - 5000
    - 6100
    - 7300
    - 8600
    - 10000
    - 11500
    - 13100
    - 14800
    - 16600
  - **costBps:**
    - 0
    - 800
    - 1200
    - 1800
    - 2500
    - 3500
    - 5000
    - 7000
    - 9500
    - 12500
    - 16000
    - 21000
    - 27000
    - 35000
    - 45000
    - 60000
  - **failure:** ETM consumed, half materials returned, no destroy/downgrade, pity +500 bps capped 2000.
  - **max:** 15
  - **successBps:**
    - 0
    - 10000
    - 10000
    - 10000
    - 10000
    - 10000
    - 8500
    - 8000
    - 7500
    - 6500
    - 5500
    - 4500
    - 4000
    - 3500
    - 3000
    - 2500
- **enhancementMaterials:**
  - **10:** 12 Astral Fragments
  - **11:** 18 Astral Fragments
  - **12:** 10 Dragon Cores
  - **13:** 15 Dragon Cores
  - **14:** 5 Eternal Fragments
  - **15:** 10 Eternal Fragments
  - **6:** 10 Iron Shards
  - **7:** 15 Iron Shards
  - **8:** 10 Shadow Crystals
  - **9:** 15 Shadow Crystals
- **equipment:**
  | id | level | rarity | slot | stats | value |
  | --- | --- | --- | --- | --- | --- |
  | eq_wanderer_blade | 1 | COMMON | WEAPON | +20 ATK | 100000 |
  | eq_traveler_vest | 1 | COMMON | ARMOR | +120 HP +10 DEF | 120000 |
  | eq_copper_charm | 1 | COMMON | ACCESSORY | +100 Crit bps | 80000 |
  | eq_ironfang_sword | 10 | UNCOMMON | WEAPON | +55 ATK | 300000 |
  | eq_ironbark_guard | 10 | UNCOMMON | ARMOR | +250 HP +30 DEF | 350000 |
  | eq_gale_sigil | 10 | UNCOMMON | ACCESSORY | +200 Crit bps | 250000 |
  | eq_nightfang_blade | 25 | RARE | WEAPON | +120 ATK | 1200000 |
  | eq_shadowmail_armor | 25 | RARE | ARMOR | +500 HP +65 DEF | 1400000 |
  | eq_oracles_eye | 25 | RARE | ACCESSORY | +300 Crit bps +300 Boss Damage bps | 1000000 |
  | eq_astral_edge | 45 | EPIC | WEAPON | +250 ATK +200 Crit bps | 5000000 |
  | eq_starforged_plate | 45 | EPIC | ARMOR | +1000 HP +140 DEF | 5800000 |
  | eq_eclipse_pendant | 45 | EPIC | ACCESSORY | +400 Crit bps +400 Boss Damage bps | 4500000 |
  | eq_void_reaver | 70 | LEGENDARY | WEAPON | +500 ATK +400 Crit bps | 18000000 |
  | eq_dragonbone_aegis | 70 | LEGENDARY | ARMOR | +2200 HP +300 DEF | 22000000 |
  | eq_crown_lunniera | 70 | LEGENDARY | ACCESSORY | +600 Crit bps +800 Boss Damage bps | 16000000 |
  | eq_first_eternal_blade | 90 | ETERNAL | WEAPON | +900 ATK +600 Crit bps | 60000000 |
  | eq_endless_dawn_aegis | 90 | ETERNAL | ARMOR | +4000 HP +550 DEF | 70000000 |
  | eq_heart_eternium | 90 | ETERNAL | ACCESSORY | +800 Crit bps +1000 Boss Damage bps | 55000000 |
- **hunt:**
  - **abyss realm:** Lv45 Energy20 ETM 90000-150000 XP180-280; Astral Fragment15%, Dragon Core3%, Beast Core12%, Epic equipment2%, Legendary0.2%, Epic egg0.5%
  - **dark cave:** Lv10 Energy12 ETM 20000-35000 XP45-70; Iron Shard35%, Shadow Crystal12%, Beast Core8%, Uncommon equipment4%, Rare0.3%, Uncommon egg1.2%
  - **eternal ruins:** Lv25 Energy15 ETM 45000-75000 XP90-140; Shadow Crystal22%, Astral Fragment6%, Beast Core10%, Rare equipment3%, Epic0.4%, Rare egg0.8%
  - **green forest:** Lv1 Energy10 ETM 8000-15000 XP20-35; Iron Shard45%, Beast Core5%, Common equipment3%, Common egg1%
  - **maximum:** One equipment and one egg per Hunt.
- **pets:**
  - **definitions:**
    | id | level | name | passive | rarity |
    | --- | --- | --- | --- | --- |
    | pet_moss_slime | 1 | Moss Slime | +400 HP bps | COMMON |
    | pet_ember_chick | 1 | Ember Chick | +400 Attack bps | COMMON |
    | pet_stonehorn_cub | 10 | Stonehorn Cub | +600 Defense bps | UNCOMMON |
    | pet_gale_fox | 10 | Gale Fox | +300 Crit bps | UNCOMMON |
    | pet_shadow_wolf | 25 | Shadow Wolf | +800 Attack bps | RARE |
    | pet_moonlight_owl | 25 | Moonlight Owl | +800 Defense bps | RARE |
    | pet_abyss_panther | 45 | Abyss Panther | +1000 Attack bps +200 Crit bps | EPIC |
    | pet_celestial_stag | 45 | Celestial Stag | +1200 HP bps | EPIC |
    | pet_dawn_phoenix | 70 | Dawn Phoenix | +1800 HP bps | LEGENDARY |
    | pet_void_wyrm | 70 | Void Wyrm | +1600 Attack bps | LEGENDARY |
    | pet_eternion_dragon | 90 | Eternion Dragon | +2200 Attack bps | ETERNAL |
    | pet_lunniera_seraph | 90 | Lunniera Seraph | +1200 HP bps +1000 Defense bps | ETERNAL |
  - **duplicateEssence:**
    - **COMMON:** 10
    - **EPIC:** 80
    - **ETERNAL:** 320
    - **LEGENDARY:** 160
    - **RARE:** 40
    - **UNCOMMON:** 20
  - **maxLevel:** 50
  - **petXp:** Hunt max(1, player XP//2); Dungeon player XP//2; Boss NORMAL/ELITE/WORLD 100/300/800.
- **profileFormula:** Power = attack*4 + defense*3 + maxHp//5 + critBps//100; maximum level 100; maximum crit 5000 bps.
- **quests:**
  - **daily:** 3 Hunt, 2 Work, 3 Boss attack; 80000 ETM, 150 XP, 1 ticket
  - **periods:** Jakarta daily midnight and Monday weekly; daily Boss COUNT attack, weekly SUM committed damage.
  - **weekly:** 25 Hunt, 5 Dungeon, assignment-level Boss damage; 600000 ETM, 1000 XP, 1 Epic Chest
  - **weeklyTargets:** Lv1-24:3000; 25-44:10000; 45-69:30000; 70-89:75000; 90-100:150000
- **setBonuses:**
  - **Astral:** 2:+8% ATK, 3:+6% Dungeon Damage
  - **First Eternal:** 2:+12% ATK, 3:+10% all damage and context DEF
  - **Ironclad:** 2:+4% DEF, 3:+5% HP
  - **Nightfall:** 2:+5% ATK, 3:+2% Crit
  - **Void:** 2:+10% ATK, 3:+10% Boss Damage
  - **Wanderer:** 2:+2% ATK, 3:+3% HP
- **starter:**
  - **attack:** 71
  - **critBps:** 600
  - **defense:** 35
  - **effectiveHp:** 1198
  - **equipment:**
    - eq_wanderer_blade
    - eq_traveler_vest
    - eq_copper_charm
  - **pet:** pet_moss_slime
  - **power:** 634

## Phase 4 Marketplace

- **commands:**
  - /rpg-market browse
  - /rpg-market search
  - /rpg-market details
  - /rpg-market sell
  - /rpg-market buy
  - /rpg-market cancel
  - /rpg-market my-listings
  - /rpg-market history
  - /rpg-market price-check
  - /rpg-market watch
  - /rpg-market watchlist
  - /rpg-market unwatch
  - /rpg-market claim-returns
  - /rpg-market report
  - /rpg-market status
- **currency:** ETM only
- **feeBps:** 500
- **listingDuration:** indefinite
- **maxUnresolvedListings:** 10
- **minimumStackQuantity:** 1
- **missingUserState:** ACTIVE
- **reportCooldownSeconds:** 3600
- **staffCommands:**
  - inspect
  - pause
  - resume
  - pause-listing
  - review
  - cancel
  - return
  - freeze-user
  - unfreeze-user
  - reports
  - resolve-report
  - reconcile
- **states:**
  - ACTIVE
  - PARTIALLY_FILLED
  - PAUSED
  - REVIEW_REQUIRED
  - CANCELLED
  - EXPIRED
  - SOLD
  - RETURNED
- **unitPriceEtm:** 10000-2000000000
- **watchLimit:** 50

## Marketplace Recovery And Hardening

- **escrow:** Listing and escrow are mutually deferred foreign keys; unresolved escrow blocks equipment mutations.
- **historicalCatalog:** Listing/escrow/sale/return use each asset persisted catalog version.
- **outbox:** Notification delivery has stable deduplicated identities.
- **purchase:** PENDING EconomyTransaction and MarketplaceSale form an atomic reservation pair.
- **quantityAuthority:** Exact stack binding and expected versions govern debit, transfer, and return.
- **recovery:** PENDING complete pairs resume/replay; missing or ambiguous pairs enter REVIEW_REQUIRED without replacement identity.
- **returns:** Seller can atomically return own ACTIVE or PARTIALLY_FILLED remainder even while globally paused.
- **stackIdentity:** Migrated stack identity is guildId,userId,itemId,catalogVersion,bindingStatus.

## Marketplace Lifecycle Definitions

- **listingLifecycle:** ACTIVE/PARTIALLY_FILLED to SOLD or atomic RETURNED; PAUSED/REVIEW_REQUIRED/CANCELLED/EXPIRED retain escrow until resolution.
- **pause:** Pause blocks listings, purchases, watches, reports; read-only, eligible cancellation, returns, recovery, and receipt replay remain allowed.
- **returnLifecycle:** Authoritative seller remainder returns atomically with MarketplaceReturn receipt.
- **saleLifecycle:** PENDING, COMMITTED, REVIEW_REQUIRED, VOID; only committed sales have immutable buyer/seller receipts.
- **userStates:** Missing is ACTIVE; RESTRICTED limits new marketplace mutation; FROZEN requires staff-audited return.

## Phase 5 Casino

- **approvedFutureFeatureFlagDefault:** false
- **approvedFutureFeatureFlagName:** ECONOMY_PHASE5_ENABLED
- **approvedGames:**
  - Blackjack
  - Coinflip
  - Rock-paper-scissors
  - Slots
  - Number guessing
  - Gacha
  - Loot boxes
- **approvedMigration:**
  - **name:** phase5-casino
  - **version:** 500
- **approvedTargets:**
  - **Blackjack:** 97.5% target RTP verified by complete D02 simulation
  - **Coinflip:** 97% RTP
  - **Gacha:** financial RTP not applicable
  - **Loot box:** 95% RTP
  - **Number guessing:** 95% RTP
  - **Rock-paper-scissors:** 96.7% RTP
  - **Slots:** 95% RTP
- **authorizationClasses:**
  - **CASINO CONTROL:**
    - pause
    - resume
    - status
  - **CASINO FINANCIAL:**
    - initial_seed
    - bankroll_adjustment
    - excess_distribution
  - **CASINO RECOVERY:**
    - reviewed_refund
    - review_resolution
    - compensating_settlement
- **bankroll:**
  - **activeMemberDefinition:** Current non-bot guild member with at least one committed approved non-Casino activity event in the rolling previous 30 UTC days.
  - **burnMechanism:** Use the existing ECY_BURN system account; do not create another burn account.
  - **distributionMode:** manual only while Casino is paused
  - **excessDistribution:** 60% ECY_GENERAL, 20% ECY_RESERVE, remainder ECY_BURN
  - **exposureCapBasis:** total maximum reserved gross liability
  - **exposureCapBps:** 200
  - **lossDestination:** ECY_CASINO
  - **safeRequirement:** max(25000000 ECY, 100000 ECY * approved active-member count)
  - **silentMinting:** false
- **betRangeEcy:**
  - **maximumRequestCeiling:** 500000
  - **minimum:** 1000
- **currency:** ECY
- **effectiveMaximumStake:**
  - **blackjackExposure:** Initial acceptance reserves the highest liability still possible through either Double or the permitted Split path.
  - **capBasis:** total maximum reserved gross liability
  - **definition:** min(500000 ECY, maximum 1000-ECY-step stake whose complete worst-case gross liability fits the current 2% exposure cap and available unreserved bankroll)
  - **displayWhenReduced:** true
- **eternalOptionsPhase:** Phase 8
- **existingCasinoObservations:**
  -
    - **evidencePaths:**
      - cogs/rpg.py
      - w2e_views.py
    - **game:** Blackjack
    - **observation:** Slash /blackjack bet and prefix w!blackjack <bet> use legacy coins, pseudo-scores, and a replay view.
    - **verificationStatus:** repository_observed
  -
    - **evidencePaths:**
      - cogs/rpg.py
      - w2e_views.py
    - **game:** Slots
    - **observation:** Slash /slot bet and prefix w!slot <bet> use legacy coins, three reels, and a legacy payout table.
    - **verificationStatus:** repository_observed
  -
    - **evidencePaths:**
      - cogs/rpg.py
    - **game:** Coinflip
    - **observation:** Slash /cf tebakan bet and prefix w!cf use legacy coins and a two-times gross payout.
    - **verificationStatus:** repository_observed
  -
    - **evidencePaths:**
      - cogs/rpg.py
    - **game:** Rock-paper-scissors
    - **observation:** Slash /rps pilihan bet and prefix w!rps use legacy coins, refund draws, and pay two-times gross on wins.
    - **verificationStatus:** repository_observed
  -
    - **evidencePaths:**
      - cogs/rpg.py
    - **game:** Number guessing
    - **observation:** Slash /tebak tebakan and prefix w!tebak have no stake and pay a fixed legacy reward.
    - **verificationStatus:** repository_observed
  -
    - **evidencePaths:**
      - cogs/rpg.py
      - w2e_views.py
    - **game:** Gacha
    - **observation:** Slash /gacha and prefix w!gacha charge a fixed legacy cost and return a cosmetic result.
    - **verificationStatus:** repository_observed
  -
    - **evidencePaths:**
      - cogs/rpg.py
      - w2e_views.py
    - **game:** Loot box
    - **observation:** Slash /box and prefix w!box charge a fixed legacy cost and return legacy coin rewards.
    - **verificationStatus:** repository_observed
  -
    - **evidencePaths:**
      - cogs/rpg.py
      - core.py
      - w2e_views.py
      - economy/database.py
    - **game:** Shared legacy behavior
    - **observation:** Current games use legacy wallet helpers, users.json statistics, general-purpose random, and non-persistent replay views; no Casino-specific durable session, ledger, or recovery schema is present.
    - **verificationStatus:** repository_observed
  -
    - **evidencePaths:**
      - economy/constants.py
      - economy/treasury.py
    - **game:** ECY burn
    - **observation:** ECY_BURN already exists as the authoritative ECY BURN system account and is included in supply reporting.
    - **verificationStatus:** repository_observed
- **fixedPricesEcy:**
  - **gacha:** 1000
  - **lootBox:** 1000
- **gameRules:**
  - **Blackjack:**
    - **dealerNaturalCheck:** before player actions
    - **dealerSoft17:** hit
    - **decks:** 6
    - **double:** hard 11 only
    - **doubleAfterSplit:** false
    - **insurance:** false
    - **naturalPayout:** 5:4 profit / 2.25x gross
    - **naturalPush:** true
    - **resplitAces:** false
    - **split:** one split maximum, Aces and 8s only
    - **splitAcesCards:** 1
    - **status:** D02 simulation passed
    - **surrender:** false
    - **timeout:** auto-stand after 10 minutes
  - **Coinflip:**
    - **grossPayout:** floor(stake * 19400 / 10000)
    - **outcomes:** fair 50/50
    - **rtp:** 97%
  - **Gacha:**
    - **duplicates:** true
    - **financialPayout:** false
    - **fixedPriceEcy:** 1000
    - **inventoryGrant:** false
    - **liabilityReservation:** false
    - **lossDestination:** ECY_CASINO
    - **outcomes:**
      - Ampas (Zonk)
      - Nasi Bungkus
      - Panci Bolong
      - Kunci Jawaban UN
      - Waifu Wangi
      - Pedang Excalibur
      - Gundam Bekas
      - Sertifikat Rumah
    - **pity:** false
    - **probability:** equal
  - **Loot box:**
    - **fixedPriceEcy:** 1000
    - **maximumGrossLiability:** 15x
    - **outcomes:**
      | grossEcy | probability |
      | --- | --- |
      | 0 | 50% |
      | 1000 | 30% |
      | 2000 | 15% |
      | 5000 | 4% |
      | 15000 | 1% |
    - **rtp:** 95%
  - **Number guessing:**
    - **attempts:** 1
    - **grossPayout:** 19x
    - **phase5Command:** adds a wager while preserving the disabled legacy free path
    - **range:** 1-20
    - **rtp:** 95%
  - **Rock-paper-scissors:**
    - **choices:** uniform independent
    - **draw:** 1x refund
    - **rtp:** 96.7%
    - **winGrossPayout:** floor(stake * 19010 / 10000)
  - **Slots:**
    - **exactPairGrossMultiplier:** 2x
    - **paylines:** 1
    - **reels:** 3
    - **rtp:** 95%
    - **symbols:** 6
    - **tripleGrossMultipliers:**
      - **7:** 8x
      - **bell:** 3x
      - **cherry:** 3x
      - **diamond:** 5x
      - **lemon:** 2.2x
      - **star:** 4x
    - **weights:** equal
- **implementationStatus:** implemented
- **implementedTables:**
  - CasinoSession
  - CasinoSessionAction
  - CasinoSettlement
  - CasinoBankrollReservation
  - CasinoBankrollDistribution
  - CasinoNotificationOutbox
  - CasinoRecoveryReview
  - CasinoLegacyStatistic
  - CasinoAuthorization
  - CasinoAuthorizationAudit
- **legacyCasinoPolicy:**
  - **highRoller:** Preserve gambler_king as legacy history; no Phase 5 award until a separate ECY threshold is approved.
  - **luckyCharm:** Legacy-only and ignored by Phase 5; it never changes odds.
  - **statistics:** Preserve users.json.games byte-for-byte and create only an idempotent read-only source-hashed compatibility snapshot; derive new statistics from committed Phase 5 settlements and display them separately.
- **migrationChecksum:** 05441b86aa7cbab27eb2cf01d94ee1f998077b68498cad52d03a79c33b1e2650
- **migrationExists:** true
- **ownerDecisionRecords:**
  | condition | decision | id | simulationGateStatus | status |
  | --- | --- | --- | --- | --- |
  | - | The 2% cap applies to total maximum reserved gross liability; effective maximum stake is exposure- and bankroll-limited and includes Blackjack Double or Split worst-case liability. | D01 | - | approved_with_revision |
  | The complete deterministic rerun measured RTP 0.9748809836156533 and passed the approved tolerance, confidence, seed, and invariant gates. | The approved rules keep six decks and H17, restrict Double to hard 11 and Split to Aces/8s, and pay a winning natural at 5:4 profit / 2.25x gross. | D02 | passed | approved_recommended |
  | - | Approve the exact equal-weight one-payline Slots table at 95% RTP with 1000-ECY wager increments. | D03 | - | approved_with_revision |
  | - | Approve fair Coinflip with floor(stake*19400/10000) gross payout and 1000-ECY wager increments. | D04 | - | approved_with_revision |
  | - | Approve uniform RPS, draw refund, floor(stake*19010/10000) win payout, and 1000-ECY wager increments. | D05 | - | approved_with_revision |
  | - | Approve one-attempt 1-20 Number Guessing at 19x gross and 1000-ECY wager increments. | D06 | - | approved_with_revision |
  | - | Approve cosmetic-only Gacha at fixed 1000 ECY with equal eight-label outcomes, no payout or inventory grant, and no liability reservation. | D07 | - | approved_with_revision |
  | - | Approve the fixed 1000-ECY Loot Box table at 95% RTP and 15x maximum gross liability. | D08 | - | approved_recommended |
  | - | Approve one unresolved session per user, one active Blackjack session per user, 100 unresolved sessions per guild, ten-minute Blackjack abandonment, 90-second replay controls, and approved per-game cooldowns. | D09 | - | approved_with_revision |
  | - | Approve mixed public/ephemeral result visibility with private errors, staff actions, and recovery details. | D10 | - | approved_recommended |
  | - | Preserve legacy users.json statistics byte-for-byte and snapshot them idempotently as read-only compatibility history; derive new statistics from committed settlements. | D11 | - | approved_recommended |
  | - | Preserve High Roller as legacy history and treat Lucky Charm as legacy-only with no Phase 5 odds effect. | D12 | - | approved_recommended |
  | - | Use the approved rolling-30-day committed non-Casino activity definition for active-member bankroll sizing. | D13 | - | approved_recommended |
  | - | Approve max(25,000,000 ECY, 100,000 ECY times active members) as the exact seed formula; production amount remains a cutover approval. | D14 | - | approved_recommended |
  | - | Use separately represented and audited CASINO_CONTROL, CASINO_FINANCIAL, and CASINO_RECOVERY authorization classes without Administrator or implicit owner financial bypass. | D15 | - | approved_with_revision |
  | - | Approve manual excess distribution only while paused, retaining safe bankroll plus unresolved/review liabilities and allocating 60/20/remainder to general/reserve/burn. | D16 | - | approved_recommended |
  | - | Approve persisted-state recovery, timeout auto-stand, immutable identity replay, and audited recovery-class compensation for reviewed ambiguity. | D17 | - | approved_recommended |
  | - | Approve the deterministic simulation matrix and additional boundary/exposure cases with separate theoretical, simulated, rounded RTP, rejection, exposure, and drawdown reporting. | D18 | - | approved_with_revision |
  | - | Migration identity 500 named phase5-casino is implemented for explicit non-production staging use only. | D19 | - | approved_recommended |
  | - | ECONOMY_PHASE5_ENABLED exists with default false; enabled missing prerequisites fail closed without legacy fallback. | D20 | - | approved_recommended |
- **ownerDecisionStatus:** approved_with_conditions
- **planningDocument:** docs/PHASE5_CASINO_PRD.md
- **productionEnabled:** false
- **productionMigrated:** false
- **productionStatus:** not_approved
- **recoveryPolicy:**
  - **ambiguousState:** REVIEW_REQUIRED without replacement identity
  - **blackjackRestart:** resume; abandonment timeout auto-stands
  - **departedUser:** receives persisted settlement
  - **missingDiscordMessage:** does not reverse financial truth
  - **provableDebitedOperation:** settle using persisted original identities
  - **reviewResolution:** requires CASINO_RECOVERY and an audited compensating action
  - **unacceptedConfirmation:** expires without debit
  - **validPersistedOperation:** resume or settle using original IDs
- **resultVisibilityPolicy:**
  - **ephemeralSlash:**
    - Gacha
    - Loot box
  - **prefix:** public because prefix has no ephemeral response
  - **private:**
    - validation errors
    - staff actions
    - recovery details
    - unresolved hidden outcomes
  - **publicSanitized:**
    - Blackjack
    - Slots
    - Coinflip
    - Rock-paper-scissors
    - Number guessing
- **roadmapPhase:** Phase 5
- **runtimeFeatureFlagExists:** true
- **scope:** Casino
- **sessionPolicy:**
  - **blackjackAbandonmentSeconds:** 600
  - **cooldownRule:** Cooldowns are secondary UX controls and never replace database idempotency, uniqueness, or locking.
  - **cooldownsAfterCommittedTerminalSeconds:**
    - **Blackjack:** 5
    - **Coinflip:** 3
    - **Gacha:** 5
    - **Loot box:** 5
    - **Number guessing:** 3
    - **Rock-paper-scissors:** 3
    - **Slots:** 3
  - **maxActiveBlackjackPerUser:** 1
  - **maxUnresolvedPerGuild:** 100
  - **maxUnresolvedPerUser:** 1
  - **replayControlSeconds:** 90
- **simulationAcceptanceGates:**
  | decisionId | gate | status |
  | --- | --- | --- |
  | D02 | The complete deterministic Blackjack simulation satisfied the approved 97.5% target tolerance, confidence, seed, and invariant thresholds without probability manipulation. | passed |
- **simulationPolicy:**
  - **acceptance:** Zero invariant failures and at most one seed outside the approved 99% interval.
  - **confidence:** 99%
  - **deterministicSeeds:** 20
  - **requiredMetrics:**
    - theoretical RTP
    - simulated RTP
    - RTP after integer rounding
    - rejected-bet count
    - maximum reserved exposure
    - maximum observed drawdown
  - **requiredWagers:**
    - minimum stake
    - effective maximum stake
    - one 1000-ECY step below effective maximum
    - global 500000-ECY request
    - insufficient exposure
    - bankroll with active reservations
    - integer-floor boundaries
  - **roundsPerSeed:**
    - **Blackjack:** 500000
    - **Coinflip:** 1000000
    - **Loot box:** 1000000
    - **Number guessing:** 1000000
    - **Rock-paper-scissors:** 1000000
    - **Slots:** 1000000
  - **tolerancePercentagePoints:**
    - **Blackjack:** 0.2
    - **Coinflip:** 0.1
    - **Loot box:** 0.2
    - **Number guessing:** 0.3
    - **Rock-paper-scissors:** 0.1
    - **Slots:** 0.2
- **simulationResult:**
  - **artifactSha256:** b24dc703728749a6ee32d637f8b62fd676833627dd9498e06c7dba13f0dea285
  - **blackjack:**
    - **absoluteDeviation:** 0.0001190163843467
    - **confidenceInterval99:**
      - 0.9740564018985632
      - 0.9757051127387927
    - **maximumObservedDrawdownEcy:** 176000
    - **maximumReservedExposureEcy:** 500000
    - **rejectedBetCount:** 3
    - **rtpAfterIntegerRounding:** 0.9748809836156533
    - **seedsOutsideAcceptance:** 1
    - **simulatedRtp:** 0.9748809836156533
    - **theoreticalRtp:** 0.975
    - **tolerance:** 0.002
  - **blockingDecision:** -
  - **candidate:** Double hard 11 only; Split Aces/8s only; natural 5:4 profit / 2.25x gross
  - **completed:** true
  - **configuration:**
    - **blackjackSessionsPerSeed:** 500000
    - **roundsPerSeedFixedGames:** 1000000
    - **seeds:** 20
  - **evidencePath:** docs/PHASE5_CASINO_PRD.md
  - **fixedGameResultsReused:** false
  - **invariantFailures:** 0
  - **otherGamesPassed:** true
  - **passed:** true
  - **priorArtifactSha256:** 1ae042eae52b4f45078b7308da2b0637c6f8b94be3cf6d67a801d4de4ef6b643
  - **stagingReady:** true
- **status:** implemented_staging_ready
- **unresolvedOwnerDecisions:**
  - -
- **wagerIncrementEcy:** 1000
- **winnerTax:** none

## Phase 6 Crypto

- **accounting:**
  - **checkedIntegerOnly:** true
  - **costBasisIncludesBuyFee:** true
  - **realizedAndUnrealizedProfit:** true
  - **reserveAccount:** ECY_MARKET
- **assets:**
  - **ECLP:**
    - **basePriceEcy:** 10000
    - **documentedMismatch:** Source PRD spells Eclipscoin; repository display spelling is preserved.
    - **maximumNormalChangeBps:** 50
    - **name:** Eclipsoin
  - **ETHR:**
    - **basePriceEcy:** 10000
    - **maximumNormalChangeBps:** 15
    - **name:** ETHERnal
  - **LUNA:**
    - **basePriceEcy:** 13000
    - **maximumNormalChangeBps:** 120
    - **name:** Lunniera
  - **MTR:**
    - **basePriceEcy:** 10000
    - **maximumNormalChangeBps:** 35
    - **name:** Meteorite
  - **ORBT:**
    - **basePriceEcy:** 20000
    - **maximumNormalChangeBps:** 70
    - **name:** Orbitcoin
  - **ORCL:**
    - **basePriceEcy:** 10000
    - **maximumNormalChangeBps:** 25
    - **name:** Cosmic Oracle
  - **TRST:**
    - **basePriceEcy:** 14000
    - **maximumNormalChangeBps:** 90
    - **name:** TrustCoin
- **commands:**
  - /market
  - w!market
  - /portfolio
  - w!portfolio
  - /buycoin
  - w!buycoin
  - /sellcoin
  - w!sellcoin
- **featureFlag:**
  - **default:** false
  - **name:** ECONOMY_PHASE6_ENABLED
- **fee:**
  - **basisPoints:** 200
  - **burnRemainderPercent:** 20
  - **marketReservePercent:** 50
  - **treasuryPercent:** 30
- **implementationStatus:** implemented
- **legacyMigration:**
  - **ambiguousPolicy:** REVIEW_REQUIRED and non-tradeable
  - **duplicateAcrossGuilds:** false
  - **sourceFilesMutated:** false
  - **targetGuildSource:** exactly one completed Phase 1 migration target guild
- **marketScope:**
  - **financialState:** guild-scoped
  - **offlineBackfill:** false
  - **prices:** one global authoritative series
  - **tickIntervalSeconds:** 60
- **migration:**
  - **checksum:** 33d17df45ef14e4140ce58b3c5718ddea39894a21e176bcb3617e2c4b2f14d3b
  - **name:** phase6-crypto
  - **startupAutomatic:** false
  - **version:** 600
- **minimumGrossEcy:** 50
- **moduleOwnership:**
  - **cogs/economy.py:** staff controls and minute worker
  - **cogs/rpg.py:** member command adapters
  - **economy/crypto.py:** atomic trades, holdings, authorization, and portfolio
  - **economy/crypto market.py:** global tick and news engine
  - **economy/crypto simulation.py:** deterministic acceptance simulation
  - **economy/phase6 migrations.py:** staging migration and reconciliation
  - **economy/phase6 recovery.py:** restart recovery and outbox
  - **economy/phase6 schema.py:** migration 600 schema and checksum
- **news:**
  - **alertThresholdBps:** 1000
  - **comparisonMinutes:** 30
  - **globalCooldownMinutesPerAsset:** 30
  - **surgeCrashThresholdBps:** 2500
- **pricing:**
  - **eventReplacesNormalMovement:** true
  - **majorEventPerMinute:** 0.005%
  - **maximumBasePercent:** 500
  - **meanReversionPercentOfDistance:** 2
  - **minimumBasePercent:** 20
  - **normalEventPerMinute:** 0.05%
- **productionEnabled:** false
- **productionMigrated:** false
- **productionSeeded:** false
- **productionStatus:** not_approved
- **rolloutBlocker:** Production cutover awaits separate approval and Phase 7 integration for ongoing legacy Mining output.
- **scope:** Crypto prices and trading migrated to ECY
- **simulation:**
  - **artifactSha256:** 66cb9ecb7e85c0eec3a9a744ae20323fb423b39c2354db7ce755ba2cf564767a
  - **completed:** true
  - **invariantFailures:** 0
  - **majorEvents:** 38
  - **normalEvents:** 444
  - **passed:** true
  - **seeds:** 20
  - **ticksPerSeed:** 43200
  - **totalTicks:** 864000
- **status:** implemented_staging_ready
- **unitScale:** 100000000
- **verificationResults:**
  - **commandOwnership:** passed through static verifier
  - **forbiddenAliases:** absent through static verifier
  - **foreignKeyErrors:** 0
  - **integrityCheck:** ok
  - **livingPrdToolingTests:** 14 passed
  - **marketplaceRegressionTests:** 64 passed
  - **migration600SecondRun:** idempotent replay
  - **phase1To6EconomyTests:** 146 passed
  - **pyCompile:** passed
  - **temporaryMainImport:** passed

## Phase 7 Mining

- **accounting:**
  - **claimAuthority:**
    - MiningClaim
    - MiningClaimAsset
    - MiningAssetLedger
  - **claimUsesEconomyTransaction:** false
  - **holdingCostBasisChangedByClaim:** false
  - **purchaseAndMaintenanceAllocation:**
    - **burnRemainderPercent:** 10
    - **miningPercent:** 80
    - **reservePercent:** 10
- **accrual:**
  - **assetUnitScale:** 100000000
  - **durabilityBps:** 10000
  - **fractionalCarryScale:** 1000000000
  - **maximumOfflineSeconds:** 86400
  - **priceWindowDays:** 7
  - **pythonBigIntegerArithmetic:** true
  - **sqliteIntermediateMultiplication:** false
- **authorizationClasses:**
  - MINING_CONTROL
  - MINING_RECOVERY
- **commands:**
  - /mining
  - w!mining
  - /buyrig
  - w!buyrig
  - /miner
  - w!miner
  - /moverig
  - w!moverig
- **connectedDiscordStaging:** pending
- **dependencies:**
  - **economyV1:** true
  - **existingProfileRequired:** true
  - **phase2:** true
  - **phase3ProfileCapability:** true
  - **phase3RuntimeFlagRequired:** false
  - **phase6Capability:** true
- **featureFlag:**
  - **default:** false
  - **name:** ECONOMY_PHASE7_ENABLED
- **implementationStatus:** implemented
- **legacyMigration:**
  - **cryptoBalancesRecredited:** false
  - **mappedTiers:**
    - **1:** rig_basic
    - **2:** rig_advanced
    - **3:** rig_elite
  - **sourceFilesMutated:** false
  - **tier4Policy:** REVIEW_REQUIRED
  - **unknownTierPolicy:** REVIEW_REQUIRED
- **migration:**
  - **checksum:** 5ab02d518818b7f3449d8008ed2712d9ccd6ba684bf237df6d080870563742e3
  - **name:** phase7-mining
  - **startupAutomatic:** false
  - **version:** 700
- **moduleOwnership:**
  - **cogs/economy.py:** staff authorization and recovery
  - **cogs/mining.py:** member command group
  - **cogs/rpg.py:** legacy compatibility adapters
  - **economy/mining.py:** atomic Mining services and overflow-safe accrual
  - **economy/mining simulation.py:** deterministic acceptance simulation
  - **economy/phase7 migrations.py:** staging migration and legacy quarantine
  - **economy/phase7 recovery.py:** restart recovery
  - **economy/phase7 schema.py:** migration 700 schema and capability
- **productionEnabled:** false
- **productionMigrated:** false
- **productionSeeded:** false
- **productionStatus:** not_approved
- **profileSlots:**
  - **10:** 1
  - **25:** 2
  - **45:** 3
  - **70:** 4
- **rigs:**
  - **rig advanced:**
    - **grossEquivalentPerDay:** 60000
    - **maintenanceEcy:** 15000
    - **purchaseEcy:** 3000000
  - **rig basic:**
    - **grossEquivalentPerDay:** 10000
    - **maintenanceEcy:** 2500
    - **purchaseEcy:** 500000
  - **rig elite:**
    - **grossEquivalentPerDay:** 300000
    - **maintenanceEcy:** 75000
    - **purchaseEcy:** 15000000
  - **rig eternal:**
    - **grossEquivalentPerDay:** 1500000
    - **maintenanceEcy:** 375000
    - **purchaseEcy:** 75000000
- **scope:** Crypto asset Mining migrated to ECY-funded rigs with asset-only claims
- **simulation:**
  - **artifactSha256:** e7599dbf34beca0fffa777cbe3fab9c0d6b7fb77d0546e6f48646b464224b187
  - **completed:** true
  - **days:** 90
  - **duplicateOutput:** 0
  - **durabilityViolations:** 0
  - **invariantFailures:** 0
  - **maximumRoiDays:** 66.66666666666667
  - **minimumRoiDays:** 66.66666666666667
  - **overflowAttempts:** 0
  - **passed:** true
  - **scenarioCount:** 2240
  - **seeds:** 20
- **status:** implemented_staging_ready
- **verificationResults:**
  - **commandOwnership:** passed through static verifier
  - **forbiddenAliases:** absent through static verifier
  - **foreignKeyErrors:** 0
  - **integrityCheck:** ok
  - **livingPrdToolingTests:** 15 passed
  - **marketplaceRegressionTests:** 64 passed
  - **migration700SecondRun:** idempotent replay
  - **migrationRestore:** passed
  - **miningFocusedTests:** 25 passed
  - **phase1To7EconomyTests:** 171 passed
  - **pyCompile:** passed
  - **temporaryMainImport:** passed

## Phase 8 Giveaway And Eternal Options

- **connectedDiscordStaging:** pending
- **dependencies:**
  - **economyV1:** true
  - **phase2Activity:** true
  - **phase5CasinoCapability:** true
  - **phase6CryptoCapability:** true
  - **phase7Required:** false
- **featureFlag:**
  - **default:** false
  - **name:** ECONOMY_PHASE8_ENABLED
- **giveaway:**
  - **accountAgeDays:** 30
  - **activePerChannel:** 1
  - **activePerGuild:** 3
  - **claimHours:** 24
  - **completionAllocation:**
    - **burnPercent:** 10
    - **reservePercent:** 10
    - **retainedPercent:** 80
  - **guildMembershipDays:** 14
  - **manualWinnerSelection:** false
  - **minimumActivityScore:** 80
  - **secureRandom:** secrets.randbelow
  - **ticketEcy:** 10000
  - **winnerCount:** 1
- **implementationStatus:** implemented
- **legacyFencing:**
  - **binomo:** true
  - **crash:** true
  - **disabledFlagPreservesLegacy:** true
  - **giveaway:** true
  - **legacySnapshotsReadOnly:** true
- **migration:**
  - **checksum:** 33c88d9b49b31b0b029c641f7fecaadeacd57db2f5f2e8c6dacfb8cd958d40a9
  - **name:** phase8-giveaway-options
  - **startupAutomatic:** false
  - **version:** 800
- **moduleOwnership:**
  - **cogs/phase8.py:** member/admin command adapters and deduplicated notification delivery
  - **economy/eternal options.py:** Options opening, shared exposure, and settlement
  - **economy/giveaways.py:** Giveaway eligibility, ticket escrow, draw, claim, and redraw
  - **economy/phase8 migrations.py:** staging migration and legacy snapshots
  - **economy/phase8 recovery.py:** restart recovery and notification outbox leasing
  - **economy/phase8 schema.py:** migration 800 schema and checksum
  - **economy/phase8 simulation.py:** deterministic acceptance simulations
  - **economy/phase8 voice.py:** durable qualified voice blocks
- **options:**
  - **activePositionLimit:** 3
  - **cancellable:** false
  - **combinedStakeLimitEcy:** 500000
  - **durationsMinutes:**
    - 5
    - 10
    - 30
  - **grossPayoutBps:** 19000
  - **lossUsesSecondCurrencyTransaction:** false
  - **stakeMaximumEcy:** 500000
  - **stakeMinimumEcy:** 1000
  - **stakeStepEcy:** 1000
  - **tieRefund:** true
- **productionEnabled:** false
- **productionMigrated:** false
- **productionSeeded:** false
- **productionStatus:** not_approved
- **redraw:**
  - **oneTimeEvidence:** true
  - **reasonCodes:**
    - CLAIM_EXPIRED
    - WINNER_DEPARTED
    - WINNER_INVALID
    - RULE_VIOLATION
  - **ruleViolationEvidence:** verified guild-local Discord message reference and content hash
- **scope:** Giveaway V1 and Eternal Options with shared Casino exposure
- **sharedExposure:**
  - **account:** ECY_CASINO
  - **exposureBps:** 200
  - **includesCasinoReservations:** true
  - **includesOptionReservations:** true
- **simulation:**
  - **artifactSha256:** ce50819010645c8cabcc5a2398837b77f0911f8dd863a8c85f6408d3a4a38ec4
  - **completed:** true
  - **giveawayDraws:** 10000
  - **giveawayPValue:** 0.6212634449446391
  - **giveawayUsers:** 1000
  - **optionsConfidence95:**
    - 0.9491074010171691
    - 0.9517406664479008
  - **optionsPositions:** 2000000
  - **optionsPositionsPerSeed:** 100000
  - **optionsRtp:** 0.9504240337325349
  - **optionsSeeds:** 20
  - **passed:** true
- **status:** implemented_staging_ready
- **verificationResults:**
  - **casinoRegressionTests:** 33 passed
  - **commandOwnership:** passed through static verifier
  - **cryptoRegressionTests:** 26 passed
  - **forbiddenAliases:** absent through static verifier
  - **foreignKeyErrors:** 0
  - **integrityCheck:** ok
  - **livingPrdToolingTests:** 15 passed
  - **marketplaceRegressionTests:** 64 passed
  - **migration800FirstApply:** passed
  - **migration800Reconciliation:** passed
  - **migration800RollbackInjection:** passed
  - **migration800SecondRun:** idempotent replay
  - **miningRegressionTests:** 25 passed
  - **outboxReplay:** passed
  - **phase1To8EconomyTests:** 191 passed
  - **phase8FocusedTests:** 20 passed
  - **pyCompile:** passed
  - **temporaryMainImport:** passed
- **voiceActivity:**
  - **deterministicBlockIdentity:** true
  - **eventType:** VOICE_ACTIVITY_30M
  - **nonOverlapping:** true
  - **offlineBackfill:** false
  - **segmentMinutes:** 30

## Phase 9A Backend Safety Foundation

- **audit:**
  - **authorizationAuditAppendOnly:** true
  - **legacyAuditAuthoritative:** false
  - **operatorAuditAppendOnly:** true
  - **securityEventsSanitized:** true
- **authentication:**
  - **absoluteHours:** 8
  - **cookie:** __Host-w2e_admin_session
  - **csrfMinutes:** 10
  - **flow:** Discord OAuth2 authorization code with PKCE
  - **idleMinutes:** 30
  - **oauthAttemptMinutes:** 10
  - **scope:** identify
- **connectedDiscordOauthStaging:** pending
- **controlledOperations:**
  - **ambiguousState:** REVIEW_REQUIRED
  - **auditAtomicWithMutation:** true
  - **beginImmediate:** true
  - **expectedVersions:** true
  - **idempotentReceipts:** true
- **dashboardProductionBuild:** passed locally
- **exclusions:**
  - Phase 9B
  - Phase 9C
  - Economy analytics
  - pause and resume operations
  - reviewed recovery operations
  - notification routing mutations
  - product-value editing
  - second backend
- **featureFlagAdded:** false
- **implementationStatus:** implemented
- **migration:**
  - **checksum:** ba692b4677207d848799439d708e0367ef766d56dec852db78546bdd74916aa2
  - **name:** phase9a-backend-safety
  - **startupAutomatic:** false
  - **version:** 900
- **moduleOwnership:**
  - **core.py:** public tombstones and signed internal aiohttp routes
  - **dashboard-example:** authenticated Next.js pages, OAuth, signed reads, and security administration
  - **economy/dashboard auth.py:** OAuth attempts, sessions, permissions, and CSRF
  - **economy/dashboard operations.py:** controlled security operations and append-only audit
  - **economy/dashboard security.py:** canonical signing, nonce, rate limit, and safe security events
  - **economy/phase9a migrations.py:** manual migration, reconciliation, restore, bootstrap, and key registration
  - **economy/phase9a schema.py:** migration 900 schema and capability
- **permissionClasses:**
  - DASHBOARD_VIEW
  - DASHBOARD_CONFIGURATION
  - ECONOMY_PAUSE_CONTROL
  - REVIEWED_RECOVERY_CONTROL
  - NOTIFICATION_ROUTING_CONTROL
  - OPERATOR_AUDIT_READ
  - DASHBOARD_SECURITY_ADMIN
- **productionEnabled:** false
- **productionMigrated:** false
- **productionStatus:** not_approved
- **publicSurface:**
  - **healthBody:**
    - **status:** ok
  - **healthPath:** /healthz
  - **otherPublicDataRoutes:** 0
- **routeIsolation:**
  - **browserDirectAiohttp:** false
  - **legacyReads:** 410 legacy_dashboard_read_disabled
  - **legacyWrites:** 410 legacy_dashboard_write_disabled
  - **rawConfigReplacement:** false
  - **sensitiveReadsSignedInternalOnly:** true
- **scope:** Authenticated dashboard backend safety foundation
- **securityHeaders:**
  - **csp:** true
  - **explicitCorsAllowlist:** true
  - **frameDenied:** true
  - **mimeSniffingDenied:** true
  - **noStore:** true
  - **strictReferrer:** true
- **signedInternalRequests:**
  - **algorithm:** HMAC-SHA256
  - **backendRevalidatesSessionMembershipAndPermission:** true
  - **clockSkewSeconds:** 5
  - **expirySeconds:** 30
  - **nonceSingleUse:** true
- **status:** implemented_local_verification
- **verificationResults:**
  - **dashboardDependencyAudit:** 0 vulnerabilities
  - **dashboardProductionBuild:** passed on Next.js 16.2.10
  - **dashboardTypecheck:** passed
  - **dashboardVitest:** 8 passed
  - **foreignKeyErrors:** 0
  - **integrityCheck:** ok
  - **livingPrdToolingTests:** 16 passed
  - **marketplaceRegressionTests:** 64 passed
  - **migration900BackupRestore:** passed
  - **migration900FirstApply:** passed
  - **migration900Reconciliation:** passed
  - **migration900RollbackInjection:** all six stages passed
  - **migration900SecondRun:** idempotent replay
  - **phase1To8EconomyTests:** 191 passed
  - **phase9aFocusedTests:** 20 passed
  - **pyCompile:** passed
  - **temporaryMainImportMigrationAbsent:** passed
  - **temporaryMainImportMigrationPresent:** passed

## Phase 9B Economy Dashboard And Notification Routing

- **connectedDiscordOauthStaging:** pending
- **controlledOperations:**
  - **appendOnlyAudit:** true
  - **csrf:** true
  - **expectedVersion:** true
  - **idempotentReceipt:** true
  - **pausePermission:** ECONOMY_PAUSE_CONTROL
  - **recoveryPermission:** REVIEWED_RECOVERY_CONTROL
  - **routePermission:** NOTIFICATION_ROUTING_CONTROL
- **dashboardProductionBuild:** passed on Next.js 16.2.10
- **delivery:**
  - **automaticReviewRetry:** false
  - **centralWorkerOnly:** true
  - **markerAdoption:** true
  - **oneIdentityPerSource:** true
  - **routeSnapshotImmutable:** true
  - **testHistorySeparate:** true
  - **uncertainSendState:** REVIEW_REQUIRED
- **dependencies:**
  - **phase9aCapability:** true
  - **sessionRequired:** true
  - **signedInternalRequestRequired:** true
- **featureFlagAdded:** false
- **implementationStatus:** implemented
- **migration:**
  - **checksum:** 90c50b1d6a1a0515086bf14cdec82573ee83baf66e06524ee1bda963a2de4934
  - **name:** phase9b-dashboard-notification-routing
  - **startupAutomatic:** false
  - **version:** 910
- **notificationCategories:**
  - GENERAL
  - MARKET_CRYPTO
  - MARKETPLACE
  - GIVEAWAY
  - CASINO
  - ETERNAL_OPTIONS
  - MINING
  - BOSS
  - LEVEL_UP
  - BIRTHDAY
  - BOOSTER
  - RECOVERY
  - SECURITY
  - OPERATOR_AUDIT
- **productionEnabled:** false
- **productionMigrated:** false
- **productionStatus:** not_approved
- **reporting:**
  - **freshnessStates:**
    - FRESH
    - STALE
    - UNAVAILABLE
  - **healthStates:**
    - UNBALANCED
    - NEEDS_ATTENTION
    - HEALTHY
  - **integerTransport:** decimal strings
  - **windowsDays:**
    - 7
    - 30
- **scope:** Authenticated Economy dashboard, notification routing, durable delivery, pause control, and reviewed recovery
- **status:** implemented_local_verification
- **verificationResults:**
  - **dashboardProductionBuild:** passed
  - **dashboardTypecheck:** passed
  - **dashboardVitest:** 14 passed
  - **foreignKeyErrors:** 0
  - **integrityCheck:** ok
  - **migration910BackupRestore:** passed
  - **migration910ChecksumMismatch:** rejected
  - **migration910FirstApply:** passed
  - **migration910Reconciliation:** passed
  - **migration910RollbackInjection:** all six stages passed
  - **migration910SecondRun:** idempotent replay
  - **phase9aRegressionTests:** 20 passed
  - **phase9bFocusedTests:** 19 passed

## Module Ownership

- **cogs:**
  - **cogs/deal.py:** Deal, Middleman, payment, dispute, archive
  - **cogs/economy.py:** Economy staff adapters
  - **cogs/marketplace.py:** Marketplace commands
  - **cogs/mining.py:** Phase 7 member commands
  - **cogs/phase8.py:** Phase 8 Giveaway and Options commands
  - **cogs/rpg.py:** legacy RPG and flag-gated compatibility routing
  - **cogs/rpg phase3.py:** Phase 3 interactions
- **dashboard:**
  - **dashboard-example/lib/dashboardAuth.ts:** server session validation
  - **dashboard-example/lib/dashboardReads.ts:** strict read resource allowlist
  - **dashboard-example/lib/internalRequest.ts:** signed internal client
  - **dashboard-example/middleware.ts:** unauthenticated page and API boundary
- **economy:**
  - **economy/dashboard auth.py:** bounded sessions, OAuth attempts, permissions, and CSRF
  - **economy/dashboard operations.py:** idempotent security operations and append-only audit
  - **economy/dashboard security.py:** HMAC envelopes, replay protection, rate limits, and safe events
  - **economy/ledger.py:** atomic currency transactions and ledger
  - **economy/phase9a migrations.py:** manual migration and security bootstrap tooling
  - **economy/phase9a schema.py:** canonical migration 900 schema and checksum
- **livingPrd:**
  - **docs/AI CODER HANDOFF.md:** generated onboarding document
  - **docs/PHASE9A BACKEND SAFETY PRD.md:** Phase 9A specification and implementation status
  - **docs/project state.json:** authoritative structured state
  - **scripts/generate ai handoff.py:** pure renderer and generator
  - **scripts/update ai handoff.py:** generator/verifier wrapper
  - **scripts/verify ai handoff.py:** static verifier
- **runtime:**
  - **core.py:** shared persistence, FakeInteraction, events, public tombstones, and signed internal web API
  - **main.py:** entry point and cog setup
  - **runtime config.py:** database path, staging guards, feature flags, and Phase 9A server configuration
- **tests:**
  - **dashboard-example/tests:** Next.js middleware, auth, route, and signature contracts
  - **tests/test ai handoff tools.py:** Living PRD deterministic/static tooling
  - **tests/test economy *.py:** Phase 1-8 economy/RPG/Casino/Crypto/Mining/Giveaway/Options
  - **tests/test marketplace*.py:** Phase 4 Marketplace
  - **tests/test phase9a *.py:** Phase 9A authentication, security, operations, migration, routes, and dashboard contract

## Verification History

- **casinoTests:** 33 passed
- **commandOwnership:** passed through static verifier
- **cryptoTests:** 26 passed
- **dashboardDependencyAudit:** 0 vulnerabilities (historical Phase 9A)
- **dashboardProductionBuild:** passed on Next.js 16.2.10
- **dashboardTypecheck:** passed
- **dashboardVitest:** 14 passed
- **forbiddenAliases:** absent through static verifier
- **gitDiffCheck:** passed
- **historicalBaseline:**
  - **marketplaceTests:** 64 passed
  - **phase1To3Tests:** 87 passed
  - **total:** 151 passed
- **livingPrdToolingTests:** 17 passed
- **mainImportTemporaryDatabaseMigrationAbsent:** passed
- **mainImportTemporaryDatabaseMigrationPresent:** passed
- **marketplaceTests:** 64 passed
- **migration900BackupRestore:** passed
- **migration900FirstApply:** passed
- **migration900Reconciliation:** passed
- **migration900RollbackInjection:** all six stages passed
- **migration900SecondRun:** idempotent replay
- **migration910BackupRestore:** passed
- **migration910ChecksumMismatch:** rejected
- **migration910FirstApply:** passed
- **migration910Reconciliation:** passed
- **migration910RollbackInjection:** all six stages passed
- **migration910SecondRun:** idempotent replay
- **miningTests:** 25 passed
- **phase1To8EconomyTests:** 191 passed
- **phase8FocusedTests:** 20 passed
- **phase8Simulation:** 10000 Giveaway draws and 20 x 100000 Options positions; both gates passed
- **phase9aFocusedTests:** 20 passed
- **phase9bFocusedTests:** 19 passed
- **pyCompile:** passed
- **sqliteForeignKeyErrors:** 0
- **sqliteIntegrityCheck:** ok

## Staging

- **liveDiscord:** pending
- **phase5Readiness:** ready_for_connected_discord_staging
- **phase6Readiness:** ready_for_connected_discord_staging
- **phase7Readiness:** ready_for_connected_discord_staging
- **phase8Readiness:** ready_for_connected_discord_staging
- **requirements:**
  - dedicated staging bot
  - non-production SQLite copy
  - dedicated staging guild
  - required flags enabled only for staging
  - manual command and restart smoke test
- **scripts:**
  - scripts/migrate_economy_phase8.py
  - scripts/setup_phase8_staging.py
  - scripts/run_phase8_staging.py
  - scripts/run_phase8_staging.ps1
  - scripts/simulate_phase8.py

## Dashboard

- **apiProtection:** all non-auth Next routes validate the server session and use explicit signed internal routes
- **authentication:** Phase 9A Discord OAuth2 PKCE and bounded server session
- **botReads:** signed internal allowlist only
- **connectedOauthStaging:** pending
- **dependencyAudit:** 0 vulnerabilities (historical Phase 9A)
- **economyReporting:** Phase 9B integer-safe independently loading panels
- **legacyWrites:** removed and backend tombstoned
- **localProductionBuild:** passed on Next.js 16.2.10
- **localTest:** 14 passed
- **localTypecheck:** passed
- **notificationRouting:** versioned routes with immutable delivery reservations
- **pageProtection:** all pages except login redirect without a valid session

## Production

- **approvedProductionRecord:** -
- **cutoverApproved:** false
- **databaseAccessedByThisTask:** false
- **enabled:** false
- **migrated:** false
- **restrictions:**
  - No automatic startup migration
  - No production catalog seed
  - No production economy enablement
  - No production cutover

## Known Limitations

- Connected Discord staging remains pending for Phase 5 through Phase 8.
- Phase 9A connected Discord OAuth staging remains pending.
- Phase 9B connected notification-routing staging remains pending.
- Phase 9C is not implemented.
- Deal runtime claims are retained as last-known until a separately scoped audit verifies them.

## Blockers

- Production cutover requires separate explicit approval.
- Production migrations 500, 600, 700, 800, 900, and 910 have not occurred and all Economy production flags must remain disabled.
- Connected Discord and OAuth staging has not been executed.

## Pending Work

- Phase 5 connected Discord staging validation
- Phase 6 connected Discord staging validation
- Phase 7 connected Discord staging validation
- Phase 8 connected Discord staging validation
- Phase 9A connected Discord OAuth staging validation
- Phase 9B connected Discord notification-routing staging validation
- Production rollout approval

## AI Coder Onboarding

- Read docs/AI_CODER_HANDOFF.md.
- Inspect Git status, branch, and relevant baseline.
- Stop and report repository/doc mismatch before changing behavior.
- Keep production migration and flag enablement separately approved.

## Mandatory Update Workflow

- **status:** IMPLEMENTED
- **steps:**
  - Read generated handoff
  - Inspect baseline
  - Implement requested change
  - Run required verification
  - Update project_state.json
  - Run python scripts/update_ai_handoff.py
  - Review generated handoff
  - Include JSON and generated Markdown in the same change set
  - Mention Living PRD update in final report

## Task Completion Template

- Task title
- Date
- Phase
- Status
- Summary
- Files changed
- Behavior/schema/migration/command/flag changes
- Tests and static checks
- Database integrity
- Commit hash
- Manual staging status
- Known limitations
- Remaining work
- Next recommended task

## Definition Of Done

- Implementation and relevant tests pass
- Migration/integrity/recovery/concurrency checked when applicable
- Command ownership and aliases preserved
- No secrets or runtime data staged
- Living PRD updated
- Manual staging and production status recorded

## Update History

| commit | date | title |
| --- | --- | --- |
| 9b07585 | 2026-07-13 | Phase 3 RPG Completed |
| 02fcac317fb6d6856fc8a1f6ee27d6cba3661f0d | 2026-07-13 | Phase 4 Eternal Marketplace Completed |
| 7ca5e70 | 2026-07-14 | Living PRD Automation Implemented |
| 25ea3bb318e292044fa4b230ccbd08bf728efb0e | 2026-07-14 | Phase 5 Casino Implemented |
| a7da7f1f243a045c88f1d304c2b6be4e865c23cf | 2026-07-14 | Phase 6 Crypto Implemented |
| 381d99a249dd9d009fc582947635c1aabffbd9c3 | 2026-07-14 | Phase 7 Mining Implemented |
| 2931a47b0b7db2626f124d744391a788bcd79051 | 2026-07-14 | Phase 8 Giveaway And Eternal Options Implemented |
| a5490ac1f2a914f1c0a81f2c80e4172f5fb37ef1 | 2026-07-15 | Phase 9A Backend Safety Foundation Implemented |
| PENDING | 2026-07-15 | Phase 9B Economy Dashboard And Notification Routing Implemented |

## Current Handoff Summary

- **completed:**
  - Deal/Middleman interaction hardening
  - Phase 1 Economy Foundation
  - Phase 2 Economy Progression
  - Phase 3 RPG
  - Phase 4 Eternal Marketplace
  - Living PRD automation
  - Phase 5 Casino and D02 simulation
  - Phase 6 Crypto
  - Phase 7 Mining
  - Phase 8 Giveaway and Eternal Options
  - Phase 9A backend safety foundation runtime, migration, authenticated dashboard boundary, and local tests
  - Phase 9B Economy dashboard, durable notification routing, controlled operations, migration, dashboard build, and local tests
- **current:** Phase 9B is implemented locally without a feature flag. Migration 910 is manual and depends on Phase 9A. Reporting and notification delivery are protected by authenticated signed routes; connected Discord/OAuth notification staging and production approval remain pending.
