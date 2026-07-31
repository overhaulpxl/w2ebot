# PRD — Way 2 Eternal Economy, RPG, Crypto, Marketplace & Community System V1

**Product:** Way 2 Eternal Discord Bot
**Repository:** `E:/w2ebot`
**Document status:** Source of truth
**Version:** V1

---

# 1. Product Goal

Build a connected economy containing two currencies:

* **Eternium (ETM):** RPG progression currency.
* **Eterncy (ECY):** casino, crypto, mining, giveaway, and high-risk economy currency.

Core gameplay loop:

```text
Server activity and RPG gameplay
→ Earn ETM
→ Buy and upgrade equipment and pets
→ Progress through hunts, dungeons, quests, and boss raids
→ Trade RPG items with other players
→ Convert ETM into ECY
→ Use ECY for casino, crypto, mining, giveaways, and Eternal Options
```

The system must:

* provide long-term progression;
* reward meaningful server activity;
* keep RPG and casino economies separated;
* prevent excessive inflation;
* prevent duplicated balances, items, and payouts;
* remain safe across bot restarts;
* provide complete transaction and staff audit trails;
* preserve unrelated existing bot functionality.

---

# 2. Currency System

## 2.1 Eternium — ETM

ETM is the primary RPG currency.

ETM is earned from:

* daily rewards;
* weekly rewards;
* work;
* hunt;
* quests;
* dungeons;
* boss raids;
* achievements;
* RPG events;
* limited voice activity rewards;
* selling items through the RPG marketplace.

ETM is used for:

* RPG shop purchases;
* equipment;
* pets;
* crafting;
* equipment enhancement;
* repairs;
* consumables;
* dungeon entry;
* RPG marketplace purchases;
* player-to-player ETM transfers;
* conversion into ECY.

---

## 2.2 Eterncy — ECY

ECY is the casino, market, mining, and community-event currency.

ECY is earned from:

* daily rewards;
* weekly rewards;
* ETM conversion;
* casino winnings;
* crypto sales;
* mining assets sold through the market;
* Eternal Options winnings;
* ECY events;
* whitelisted admin minting.

ECY is used for:

* blackjack;
* slots;
* coinflip;
* rock-paper-scissors;
* number guessing;
* gacha and loot boxes;
* crypto trading;
* mining rigs;
* mining maintenance;
* Eternal Options;
* giveaway tickets;
* ECY events.

---

## 2.3 Currency Direction

Conversion is one-way only:

```text
ETM → ECY: Allowed
ECY → ETM: Forbidden
```

Transfer rules:

```text
ETM player transfer: Allowed
ECY player transfer: Forbidden
```

---

# 3. Economy Scaling and Legacy Migration

All legacy economy values must be scaled by `1,000`.

Examples:

```text
10 legacy coins → 10,000 new units
500 legacy coins → 500,000 new units
```

Legacy balance migration:

```text
Legacy coin balance × 1,000 → ETM
Initial ECY balance → 0
```

Legacy crypto prices:

```text
10 legacy coins → 10,000 ECY
20 legacy coins → 20,000 ECY
```

Migration requirements:

* run only once;
* use a database migration version;
* be idempotent;
* create a backup before mutation;
* support dry-run mode;
* report totals before and after migration;
* never multiply balances again after restart;
* preserve existing user IDs and profiles;
* produce an audit report for migrated users, assets, pets, inventory, and rigs.

---

# 4. Number Formatting and Input Parsing

Display values using Indonesian thousands separators:

```text
1.000 ETM
500.000 ECY
1.250.000 ETM
```

Accepted input formats:

```text
10000
10.000
10k
500k
1m
half
all
```

Rejected input:

```text
negative numbers
zero where a positive value is required
scientific notation such as 1e18
NaN
Infinity
unsupported decimal values
```

All balances, prices, rewards, fees, and transaction amounts must use integers.

Do not use floating-point values for wallet balances.

---

# 5. Base Rewards

## 5.1 Daily

```text
+50,000 ETM
+5,000 ECY
```

## 5.2 Weekly

```text
+350,000 ETM
+35,000 ECY
```

Daily and weekly claims must atomically update:

* ETM balance;
* ECY balance;
* cooldown;
* transaction ledger;
* activity tracking.

Partial completion is forbidden.

---

## 5.3 Work

```text
Reward: 10,000–18,000 ETM
Cooldown: 2 hours
Maximum: 4 successful work actions per day
```

Work does not directly reward ECY.

---

# 6. Eternal Exchange

The Eternal Exchange converts ETM into ECY.

```text
Rate: 10 ETM = 1 ECY
Exchange fee: 5%
```

Example:

```text
Submitted: 100,000 ETM
Fee: 5,000 ETM
Convertible amount: 95,000 ETM
Received: 9,500 ECY
```

The effective ETM conversion amount leaves the active ETM economy.

The 5% fee is distributed as:

```text
80% → ETM Treasury
10% → ETM Locked Reserve
10% → Burn
```

Daily limits:

| RPG Level | Daily ETM Limit |
| --------: | --------------: |
|       1–9 |  Feature locked |
|     10–19 |         250,000 |
|     20–39 |         500,000 |
|       40+ |       1,000,000 |

Commands:

```text
/exchange
/exchange amount:<ETM>
```

ECY-to-ETM conversion must not exist.

---

# 7. ETM Player Transfers

Only ETM may be transferred.

```text
Minimum transfer: 10,000 ETM
Transfer fee: 5%
Daily transfer limit: 2,000,000 ETM
```

Example:

```text
Sender pays: 100,000 ETM
Fee: 5,000 ETM
Receiver receives: 95,000 ETM
```

Rules:

* no self-transfer;
* no bot recipients;
* ECY transfer is forbidden;
* debit and credit must occur atomically;
* fees must be recorded and distributed;
* transfer activity does not increase giveaway Activity Score;
* transaction replay must not duplicate payment.

---

# 8. RPG Player Profile

Each RPG player has:

```text
Level
XP
HP
Attack
Defense
Critical Chance
Energy
Power Score
ETM Balance
ECY Balance
Active Equipment
Active Pet
Inventory
Materials
Achievements
```

Baseline limits:

```text
Maximum RPG level: 100
Critical damage multiplier: 1.50×
Maximum critical chance: 50%
Maximum damage reduction: 60%
Maximum energy: 100
Energy regeneration: 1 every 10 minutes
```

---

# 9. Starter Package

A new RPG profile automatically receives one starter package.

## Starter Equipment

* Wanderer’s Blade
* Traveler’s Vest
* Copper Eternium Charm

## Starter Pet

* Moss Slime

Starter package rules:

* granted once;
* automatically equipped;
* free;
* does not debit the treasury;
* cannot be sold;
* cannot be transferred;
* cannot enter the marketplace;
* cannot be granted again after restart;
* remains in inventory when replaced.

Required marker:

```text
starter_pack_claimed = true
```

Starter binding type:

```text
STARTER_BOUND
```

---

# 10. RPG Combat Formula

## 10.1 Raw Damage

```text
Raw Damage =
Attack × Skill Multiplier × Random Variance
```

Baseline values:

```text
Normal skill multiplier: 1.00
Random variance: 0.90–1.10
Critical multiplier: 1.50
```

## 10.2 Damage Reduction

```text
Damage Reduction =
Defense / (Defense + 500 + 20 × Attacker Level)
```

Damage reduction must be capped at 60%.

## 10.3 Final Damage

```text
Final Damage =
max(1, Raw Damage × (1 - Damage Reduction))
```

Critical damage is applied after reduction.

## 10.4 Power Score

```text
Power Score =
Attack × 4
+ Defense × 3
+ HP × 0.20
+ Critical Chance × 100
```

Equipment, pet, enhancement, and set bonuses must be included in the final Power Score.

---

# 11. RPG Level and XP

Maximum level:

```text
100
```

XP requirement:

```text
XP Required =
round(100 × Level^1.60)
```

Approximate progression:

| Level | XP Required for Next Level |
| ----: | -------------------------: |
|     1 |                        100 |
|     5 |                      1,313 |
|    10 |                      3,981 |
|    20 |                     12,068 |
|    40 |                     36,594 |
|    70 |                     89,900 |
|    99 |      Approximately 156,000 |

Levels unlock:

* hunt areas;
* dungeons;
* equipment tiers;
* pet tiers;
* ETM exchange limits;
* mining slots.

---

# 12. Equipment System

Equipment slots:

```text
Weapon
Armor
Accessory
```

Rarities:

```text
Common
Uncommon
Rare
Epic
Legendary
Eternal
```

Binding states:

```text
UNBOUND
BOUND_ON_EQUIP
ACCOUNT_BOUND
STARTER_BOUND
```

Rules:

* Common through Legendary equipment uses `BOUND_ON_EQUIP`;
* once equipped, it becomes permanently bound;
* Eternal equipment is always `ACCOUNT_BOUND`;
* starter equipment is always `STARTER_BOUND`;
* bound equipment cannot be sold or transferred.

Each equipment instance must store:

```text
instance_id
item_id
owner_id
enhancement_level
binding_status
acquired_source
created_at
```

---

# 13. Equipment Catalog V1

## 13.1 Common — Wanderer Set

| Internal ID         | Item                  | Slot      | Level | Base Stats       |  Base Value |
| ------------------- | --------------------- | --------- | ----: | ---------------- | ----------: |
| `eq_wanderer_blade` | Wanderer’s Blade      | Weapon    |     1 | +20 ATK          | 100,000 ETM |
| `eq_traveler_vest`  | Traveler’s Vest       | Armor     |     1 | +120 HP, +10 DEF | 120,000 ETM |
| `eq_copper_charm`   | Copper Eternium Charm | Accessory |     1 | +1% Crit         |  80,000 ETM |

Set bonus:

```text
2 pieces: +2% Attack
3 pieces: +3% HP
```

---

## 13.2 Uncommon — Ironclad Set

| Internal ID         | Item           | Slot      | Level | Base Stats       |  Base Value |
| ------------------- | -------------- | --------- | ----: | ---------------- | ----------: |
| `eq_ironfang_sword` | Ironfang Sword | Weapon    |    10 | +55 ATK          | 300,000 ETM |
| `eq_ironbark_guard` | Ironbark Guard | Armor     |    10 | +250 HP, +30 DEF | 350,000 ETM |
| `eq_gale_sigil`     | Gale Sigil     | Accessory |    10 | +2% Crit         | 250,000 ETM |

Set bonus:

```text
2 pieces: +4% Defense
3 pieces: +5% HP
```

---

## 13.3 Rare — Nightfall Set

| Internal ID           | Item             | Slot      | Level | Base Stats                |    Base Value |
| --------------------- | ---------------- | --------- | ----: | ------------------------- | ------------: |
| `eq_nightfang_blade`  | Nightfang Blade  | Weapon    |    25 | +120 ATK                  | 1,200,000 ETM |
| `eq_shadowmail_armor` | Shadowmail Armor | Armor     |    25 | +500 HP, +65 DEF          | 1,400,000 ETM |
| `eq_oracles_eye`      | Oracle’s Eye     | Accessory |    25 | +3% Crit, +3% Boss Damage | 1,000,000 ETM |

Set bonus:

```text
2 pieces: +5% Attack
3 pieces: +2% Critical Chance
```

---

## 13.4 Epic — Astral Set

| Internal ID           | Item             | Slot      | Level | Base Stats                |    Base Value |
| --------------------- | ---------------- | --------- | ----: | ------------------------- | ------------: |
| `eq_astral_edge`      | Astral Edge      | Weapon    |    45 | +250 ATK, +2% Crit        | 5,000,000 ETM |
| `eq_starforged_plate` | Starforged Plate | Armor     |    45 | +1,000 HP, +140 DEF       | 5,800,000 ETM |
| `eq_eclipse_pendant`  | Eclipse Pendant  | Accessory |    45 | +4% Crit, +4% Boss Damage | 4,500,000 ETM |

Set bonus:

```text
2 pieces: +8% Attack
3 pieces: +6% Dungeon Damage
```

---

## 13.5 Legendary — Void Sovereign Set

| Internal ID           | Item              | Slot      | Level | Base Stats                |     Base Value |
| --------------------- | ----------------- | --------- | ----: | ------------------------- | -------------: |
| `eq_void_reaver`      | Void Reaver       | Weapon    |    70 | +500 ATK, +4% Crit        | 18,000,000 ETM |
| `eq_dragonbone_aegis` | Dragonbone Aegis  | Armor     |    70 | +2,200 HP, +300 DEF       | 22,000,000 ETM |
| `eq_crown_lunniera`   | Crown of Lunniera | Accessory |    70 | +6% Crit, +8% Boss Damage | 16,000,000 ETM |

Set bonus:

```text
2 pieces: +10% Attack
3 pieces: +10% Boss Damage
```

---

## 13.6 Eternal — First Eternal Set

| Internal ID              | Item                       | Slot      | Level | Base Stats                 |     Base Value |
| ------------------------ | -------------------------- | --------- | ----: | -------------------------- | -------------: |
| `eq_first_eternal_blade` | Blade of the First Eternal | Weapon    |    90 | +900 ATK, +6% Crit         | 60,000,000 ETM |
| `eq_endless_dawn_aegis`  | Aegis of Endless Dawn      | Armor     |    90 | +4,000 HP, +550 DEF        | 70,000,000 ETM |
| `eq_heart_eternium`      | Heart of Eternium          | Accessory |    90 | +8% Crit, +10% Boss Damage | 55,000,000 ETM |

Set bonus:

```text
2 pieces: +12% Attack

3 pieces — Eternal Resonance:
+10% Damage
+10% Defense
inside Boss and Dungeon content
```

Eternal equipment cannot be sold or transferred.

---

# 14. Equipment Enhancement

Enhancement levels:

```text
+0 through +15
```

| Level | Total Stat Bonus | Success Rate |
| ----: | ---------------: | -----------: |
|    +1 |               5% |         100% |
|    +2 |              10% |         100% |
|    +3 |              16% |         100% |
|    +4 |              23% |         100% |
|    +5 |              31% |         100% |
|    +6 |              40% |          85% |
|    +7 |              50% |          80% |
|    +8 |              61% |          75% |
|    +9 |              73% |          65% |
|   +10 |              86% |          55% |
|   +11 |             100% |          45% |
|   +12 |             115% |          40% |
|   +13 |             131% |          35% |
|   +14 |             148% |          30% |
|   +15 |             166% |          25% |

Upgrade costs are based on the equipment base value:

| Target Level | Cost |
| -----------: | ---: |
|           +1 |   8% |
|           +2 |  12% |
|           +3 |  18% |
|           +4 |  25% |
|           +5 |  35% |
|           +6 |  50% |
|           +7 |  70% |
|           +8 |  95% |
|           +9 | 125% |
|          +10 | 160% |
|          +11 | 210% |
|          +12 | 270% |
|          +13 | 350% |
|          +14 | 450% |
|          +15 | 600% |

Failure behavior:

* item is never destroyed;
* enhancement level does not decrease;
* ETM cost is consumed;
* 50% of required materials are returned;
* pity success increases by 5%;
* pity bonus is capped at 20%;
* pity resets after a successful enhancement.

---

# 15. Pet System

Players may own multiple pets.

Only one pet may be active at a time.

Each pet stores:

```text
pet_instance_id
pet_id
owner_id
rarity
level
xp
passive
skill
evolution_state
active_status
created_at
```

Rules:

* hatched pets cannot be traded;
* unopened tradeable Pet Eggs may be sold;
* duplicate pets convert into Pet Essence;
* buying a new pet must never overwrite existing pets.

---

# 16. Pet Catalog V1

| Rarity    | Internal ID           | Pet             | Required Level | Passive            | Skill                                      |
| --------- | --------------------- | --------------- | -------------: | ------------------ | ------------------------------------------ |
| Common    | `pet_moss_slime`      | Moss Slime      |              1 | +4% HP             | 8% chance to reduce incoming damage by 10% |
| Common    | `pet_ember_chick`     | Ember Chick     |              1 | +4% Attack         | 8% chance to deal 25% bonus damage         |
| Uncommon  | `pet_stonehorn_cub`   | Stonehorn Cub   |             10 | +6% Defense        | First incoming attack is reduced by 15%    |
| Uncommon  | `pet_gale_fox`        | Gale Fox        |             10 | +3% Crit           | 10% chance to counter for 30% damage       |
| Rare      | `pet_shadow_wolf`     | Shadow Wolf     |             25 | +8% Attack         | 10% chance to deal 150% damage             |
| Rare      | `pet_moonlight_owl`   | Moonlight Owl   |             25 | +8% Defense        | 8% chance to dodge                         |
| Epic      | `pet_abyss_panther`   | Abyss Panther   |             45 | +10% ATK, +2% Crit | 10% chance to ignore 20% DEF               |
| Epic      | `pet_celestial_stag`  | Celestial Stag  |             45 | +12% HP            | Restores 5% HP once per battle             |
| Legendary | `pet_dawn_phoenix`    | Dawn Phoenix    |             70 | +18% HP            | Revives once with 20% HP                   |
| Legendary | `pet_void_wyrm`       | Void Wyrm       |             70 | +16% Attack        | 8% chance to strike twice                  |
| Eternal   | `pet_eternion_dragon` | Eternion Dragon |             90 | +22% Attack        | 10% chance to ignore 35% DEF               |
| Eternal   | `pet_lunniera_seraph` | Lunniera Seraph |             90 | +12% HP, +10% DEF  | Grants a 15% HP shield once per battle     |

Pet maximum level:

```text
50
```

Pet XP formula:

```text
Pet XP Required =
round(50 × Pet Level^1.50)
```

Every five pet levels increases the passive toward a maximum of 120% of its base value at level 50.

Skill trigger chance does not scale with pet level.

---

# 17. RPG Materials

| Internal ID            | Material         | Purpose                      | Tradeable |
| ---------------------- | ---------------- | ---------------------------- | --------- |
| `mat_iron_shard`       | Iron Shard       | Common and Uncommon crafting | Yes       |
| `mat_shadow_crystal`   | Shadow Crystal   | Rare crafting                | Yes       |
| `mat_astral_fragment`  | Astral Fragment  | Epic crafting                | Yes       |
| `mat_dragon_core`      | Dragon Core      | Legendary crafting           | Yes       |
| `mat_eternal_fragment` | Eternal Fragment | Eternal crafting             | No        |
| `mat_beast_core`       | Beast Core       | Pet upgrades and evolution   | Yes       |
| `mat_pet_essence`      | Pet Essence      | Pet duplicates and evolution | No        |
| `mat_protection_stone` | Protection Stone | Enhancement protection       | Yes       |

---

# 18. Crafting

| Target Rarity |   ETM Cost | Materials                                          | Required Base Item           |
| ------------- | ---------: | -------------------------------------------------- | ---------------------------- |
| Uncommon      |    300,000 | 20 Iron Shards                                     | Common item of the same slot |
| Rare          |  1,200,000 | 35 Shadow Crystals + 3 Beast Cores                 | Uncommon item                |
| Epic          |  5,000,000 | 45 Astral Fragments + 5 Beast Cores                | Rare item                    |
| Legendary     | 20,000,000 | 30 Dragon Cores + 10 Beast Cores                   | Epic item                    |
| Eternal       | 75,000,000 | 50 Eternal Fragments + 20 Dragon Cores + Blueprint | Legendary item               |

The required base item is consumed only when crafting succeeds.

Crafting must be atomic.

---

# 19. Hunt System

| Area          | Required Level | Energy Cost |     ETM Reward | XP Reward |
| ------------- | -------------: | ----------: | -------------: | --------: |
| Green Forest  |              1 |          10 |   8,000–15,000 |     20–35 |
| Dark Cave     |             10 |          12 |  20,000–35,000 |     45–70 |
| Eternal Ruins |             25 |          15 |  45,000–75,000 |    90–140 |
| Abyss Realm   |             45 |          20 | 90,000–150,000 |   180–280 |

## Green Forest Drops

```text
Iron Shard: 45%
Beast Core: 5%
Common Equipment: 3%
Common Pet Egg: 1%
```

## Dark Cave Drops

```text
Iron Shard: 35%
Shadow Crystal: 12%
Beast Core: 8%
Uncommon Equipment: 4%
Rare Equipment: 0.30%
Uncommon Pet Egg: 1.20%
```

## Eternal Ruins Drops

```text
Shadow Crystal: 22%
Astral Fragment: 6%
Beast Core: 10%
Rare Equipment: 3%
Epic Equipment: 0.40%
Rare Pet Egg: 0.80%
```

## Abyss Realm Drops

```text
Astral Fragment: 15%
Dragon Core: 3%
Beast Core: 12%
Epic Equipment: 2%
Legendary Equipment: 0.20%
Epic Pet Egg: 0.50%
```

Material, equipment, and pet egg rolls are separate.

A hunt may grant at most one equipment item and one pet egg.

---

# 20. Dungeon System

| Dungeon         |            Entry Cost |          ETM Reward |
| --------------- | --------------------: | ------------------: |
| Forgotten Crypt |  50,000 ETM or Ticket |     120,000–220,000 |
| Shadow Fortress | 150,000 ETM or Ticket |     350,000–650,000 |
| Eternal Abyss   | 500,000 ETM or Ticket | 1,200,000–2,000,000 |

Dungeon ETM rewards are paid from the ETM treasury.

## Forgotten Crypt Drops

```text
Uncommon Equipment: 35%
Rare Equipment: 12%
Shadow Crystal: 60%
Rare Pet Egg: 1%
```

## Shadow Fortress Drops

```text
Rare Equipment: 30%
Epic Equipment: 10%
Legendary Equipment: 0.50%
Astral Fragment: 55%
Epic Pet Egg: 1%
```

## Eternal Abyss Drops

```text
Epic Equipment: 25%
Legendary Equipment: 5%
Eternal Blueprint: 0.25%
Dragon Core: 45%
Eternal Fragment: 2%
Legendary Pet Egg: 0.30%
```

Only one equipment drop may be granted per dungeon completion.

---

# 21. Boss Raid System

Reward pools:

```text
Normal Boss: 2,000,000 ETM
Elite Boss: 8,000,000 ETM
World Boss: 25,000,000 ETM
```

Reward distribution:

```text
20% → equally divided among valid participants
65% → proportional to damage contribution
15% → Top 10 contribution bonus
```

Last hit does not grant a large ETM bonus.

Last-hit rewards should be cosmetic, such as:

* title;
* badge;
* visual achievement.

Boss rewards are paid from the ETM Boss and Dungeon Fund.

## Normal Boss Drops

```text
Shadow Crystal: 35%
Beast Core: 20%
Rare Equipment: 4%
Epic Equipment: 0.50%
```

## Elite Boss Drops

```text
Astral Fragment: 40%
Beast Core: 30%
Epic Equipment: 5%
Legendary Equipment: 0.50%
Epic Pet Egg: 0.75%
```

## World Boss Drops

```text
Dragon Core: 50%
Eternal Fragment: 1%
Legendary Equipment: 3%
Eternal Blueprint: 0.25%
Legendary Pet Egg: 0.50%
Eternal Pet Egg: 0.05%
```

A valid participant must meet the boss-specific minimum damage requirement.

---

# 22. Quest System

Quest types:

* daily quests;
* weekly quests;
* story quests;
* seasonal quests in a later phase.

Daily Quest baseline:

```text
Complete 3 Hunts
Complete 2 Work actions
Attack a Boss 3 times

Reward:
80,000 ETM
150 XP
1 Dungeon Ticket
```

Weekly Quest baseline:

```text
Complete 25 Hunts
Complete 5 Dungeons
Reach the required Boss Damage target

Reward:
600,000 ETM
1,000 XP
1 Epic Chest
```

Quest progress must be driven by actual game events, not manually editable counters.

---

# 23. Eternal Marketplace

The Eternal Marketplace is the only V1 player-to-player RPG item trading system.

Currency:

```text
ETM only
```

V1 excludes:

* direct `/trade`;
* auctions;
* bidding;
* offers;
* barter;
* ECY item payments.

Marketplace listings have no expiration duration.

A listing remains active until:

* sold;
* cancelled by the seller;
* cancelled by staff;
* cancelled by the system.

Listing statuses:

```text
ACTIVE
SOLD
CANCELLED
SYSTEM_CANCELLED
```

---

# 24. Marketplace Member Commands

```text
/rpg-market browse
/rpg-market search
/rpg-market details
/rpg-market buy
/rpg-market sell
/rpg-market my-listings
/rpg-market cancel
/rpg-market history
/rpg-market price-check
/rpg-market watch
/rpg-market watchlist
/rpg-market unwatch
/rpg-market claim-returns
/rpg-market report
```

Prefix support:

```text
w!rpg-market browse
w!rpg-market search
w!rpg-market buy
w!rpg-market my-listings
w!rpg-market cancel
w!rpg-market history
w!rpg-market price-check
w!rpg-market watchlist
w!rpg-market claim-returns
```

For safe item instance selection, prefix selling should direct the user to:

```text
Use /rpg-market sell to select an item from your inventory.
```

---

# 25. Marketplace Staff Commands

```text
/rpg-market-admin inspect
/rpg-market-admin cancel
/rpg-market-admin freeze-user
/rpg-market-admin unfreeze-user
/rpg-market-admin reports
```

Staff cannot:

* take an escrowed item;
* change the seller;
* edit the listing price;
* force-buy an item without payment;
* move an item into their own account.

All staff actions must enter the audit log.

---

# 26. Marketplace Rules

```text
Minimum listing price: 10,000 ETM
Maximum listing price: 2,000,000,000 ETM
Maximum active listings: 10 per user
Minimum seller level: 10
Minimum server membership: 7 days
```

Seller fee:

```text
5%
```

Example:

```text
Buyer pays: 1,000,000 ETM
Seller receives: 950,000 ETM
Marketplace fee: 50,000 ETM
```

Marketplace fee distribution:

```text
80% → ETM Treasury
10% → ETM Locked Reserve
10% → Burn
```

There is no fee for:

* creating a listing;
* cancelling a listing;
* keeping a listing active.

The fee only applies after a successful sale.

---

# 27. Marketplace Tradeable Items

Tradeable:

* unbound Common–Legendary equipment;
* enhanced equipment that has never been equipped;
* tradeable materials;
* consumables;
* dungeon tickets;
* Common–Epic Pet Eggs;
* tradeable recipes and blueprints.

Not tradeable:

* starter equipment;
* bound equipment;
* Eternal equipment;
* hatched pets;
* Eternal Fragments;
* Pet Essence;
* quest items;
* bound seasonal rewards;
* equipped items;
* items already inside marketplace escrow.

Stackable items support partial purchases.

---

# 28. Marketplace Features

The marketplace must support:

* browse;
* pagination;
* search;
* category filters;
* rarity filters;
* equipment-slot filters;
* minimum and maximum price filters;
* enhancement filters;
* newest, cheapest, highest-price, rarity, and enhancement sorting;
* item details;
* equipment comparison;
* fixed-price purchases;
* partial stack purchases;
* personal listing management;
* seller cancellation;
* purchase history;
* sales history;
* 30-day price checks;
* watchlists;
* listing reports;
* transaction receipts;
* item escrow;
* return storage;
* suspicious trade alerts.

Price-check data:

```text
Lowest sale price
Median sale price
Highest sale price
Number of sales
30-day window
```

Suspicious alert thresholds:

```text
More than 300% of the 30-day median
or
Less than 20% of the 30-day median
```

Suspicious trades are flagged, not automatically cancelled.

Marketplace transactions:

* do not add Activity Score;
* do not count as newly minted farming rewards;
* do not trigger coin-earned achievements;
* preserve the equipment instance ID and enhancement level.

---

# 29. Marketplace Purchase Flow

```text
Buyer selects a listing
→ listing is revalidated
→ buyer is confirmed not to be the seller
→ buyer balance is checked
→ confirmation UI is shown
→ buyer confirms
→ buyer ETM is debited
→ seller receives 95%
→ 5% fee is distributed
→ item moves from escrow to buyer
→ receipts and ledgers are created
→ transaction commits
```

The entire flow must use one database transaction.

If two buyers attempt to purchase the same item:

```text
The first committed transaction receives the item.

The second transaction:
- does not debit the buyer;
- receives an “already sold” response.
```

---

# 30. Marketplace Partial Stack Purchases

Example listing:

```text
Iron Shard ×100
Price: 10,000 ETM per unit
```

Buyer purchases 25:

```text
Buyer receives: 25 Iron Shards
Buyer pays: 250,000 ETM
Remaining listing quantity: 75
```

Seller is paid only for the quantity sold.

Unique equipment and Pet Eggs always use quantity `1`.

---

# 31. Marketplace Binding Confirmation

When unbound equipment is equipped for the first time:

```text
This equipment will become permanently bound.

After binding:
- it cannot be sold;
- it cannot be transferred;
- it may still be enhanced.

[Equip and Bind]
[Cancel]
```

The binding state update and equipment action must be atomic.

---

# 32. Casino System

All casino games use ECY.

Games:

* blackjack;
* slots;
* coinflip;
* rock-paper-scissors;
* number guessing;
* gacha;
* loot boxes.

Bet limits:

```text
Minimum bet: 1,000 ECY
Maximum bet: 500,000 ECY
```

Target RTP:

| Game                |        Target RTP |
| ------------------- | ----------------: |
| Blackjack           |             97.5% |
| Coinflip            |               97% |
| Rock-paper-scissors |             96.7% |
| Slots               |               95% |
| Number guessing     |               95% |
| Eternal Options     | Approximately 95% |

Casino odds must never depend on:

* user identity;
* balance;
* bet size;
* previous wins;
* previous losses;
* treasury balance.

Casino winnings have no additional winner tax.

---

# 33. Casino Bankroll

When a user loses:

```text
User ECY → Casino Bankroll
```

When a user wins:

```text
Casino Bankroll → User ECY
```

Maximum potential payout per bet:

```text
2% of the current Casino Bankroll
```

Recommended initial bankroll:

```text
max(
25,000,000 ECY,
100,000 ECY × active members in the last 30 days
)
```

Only excess bankroll above the safe requirement may be distributed.

Excess profit distribution:

```text
60% → ECY Treasury
20% → ECY Locked Reserve
20% → Burn
```

Casino loss money must not be split after every round.

---

# 34. Legacy Crash/Binomo Replacement

The existing `/crash` or legacy Binomo multiplier game is retired.

It must be replaced by:

```text
Eternal Options
```

Do not create a second multiplier-based Crash game.

Legacy `/crash` may temporarily respond with a deprecation message directing users to Eternal Options.

---

# 35. Eternal Options

Flow:

```text
Select crypto asset
→ Select UP or DOWN
→ Enter ECY stake
→ Select duration
→ Store entry price
→ Compare entry and expiry price
→ Settle position
```

Rules:

```text
Durations: 5, 10, or 30 minutes
Minimum stake: 1,000 ECY
Maximum stake: 500,000 ECY
Correct prediction gross payout: 1.90×
Equal price: Full refund
Maximum active positions: 3
Maximum combined active stake: 500,000 ECY
```

Eternal Options uses the same price source as the crypto market.

Positions must:

* survive restarts;
* store immutable entry price;
* store immutable expiry time;
* settle once only;
* be non-cancellable after opening;
* use idempotent settlement.

---

# 36. Crypto Assets

Existing asset names remain unchanged.

| Symbol | Name          | Initial Price |
| ------ | ------------- | ------------: |
| ETHR   | ETHERnal      |    10,000 ECY |
| ORCL   | Cosmic Oracle |    10,000 ECY |
| MTR    | Meteorite     |    10,000 ECY |
| ECLP   | Eclipscoin    |    10,000 ECY |
| ORBT   | Orbitcoin     |    20,000 ECY |
| TRST   | TrustCoin     |    14,000 ECY |
| LUNA   | Lunniera      |    13,000 ECY |

Existing commands should be preserved and upgraded:

```text
/market
/portfolio
/buycoin
/sellcoin
```

---

# 37. Crypto Market Pricing

Market tick interval:

```text
1 minute
```

Maximum normal movement per tick:

| Asset | Maximum Normal Change |
| ----- | --------------------: |
| ETHR  |                ±0.15% |
| ORCL  |                ±0.25% |
| MTR   |                ±0.35% |
| ECLP  |                ±0.50% |
| ORBT  |                ±0.70% |
| TRST  |                ±0.90% |
| LUNA  |                ±1.20% |

Pricing must include:

* mean reversion;
* minimum price of 20% of base price;
* maximum price of 500% of base price;
* persistent price history;
* rare market events;
* integer price storage.

Normal market events:

```text
8%–20%
```

Major special events may reach approximately 30%.

Extreme values such as `-77%` must not occur from a normal tick.

---

# 38. Crypto Trading

Trading fees:

```text
Buy fee: 2%
Sell fee: 2%
```

Portfolio must display:

* asset quantity;
* average buy price;
* current price;
* total portfolio value;
* realized profit;
* unrealized profit;
* transaction history.

Crypto quantities use fixed integer units:

```text
1 crypto = 100,000,000 asset units
```

The trade principal must use the Market Reserve.

Fee distribution:

```text
50% → Market Reserve
30% → ECY Treasury
20% → Burn
```

Buying and selling must be atomic.

A failed buy or sell must not partially mutate wallet or holdings.

---

# 39. Market News

The existing market-news system must be retained and upgraded, not replaced.

News messages display:

* asset name;
* asset symbol;
* previous price;
* current price;
* percentage change;
* volatility level.

News movement is calculated over a 30-minute window:

```text
Below 10%:
No news

10%–24.99%:
Market Alert

25% or more:
Market Surge or Market Crash
```

Anti-spam:

```text
Maximum one news message per asset every 30 minutes
```

Normal market ticks must not create extreme news events.

---

# 40. Mining System

Mining uses ECY for rig purchases and maintenance.

Flow:

```text
Purchase rig using ECY
→ Select crypto target
→ Rig generates crypto asset units
→ Rewards accumulate as pending
→ User claims rewards
→ Assets enter portfolio
→ User may sell assets for ECY
```

Mining must not directly generate ECY.

---

# 41. Mining Rig Catalog

| Internal ID    | Rig          |          Price | Gross ECY Equivalent per Day | Maintenance | Net Equivalent |
| -------------- | ------------ | -------------: | ---------------------------: | ----------: | -------------: |
| `rig_basic`    | Basic Rig    |    500,000 ECY |                       10,000 |       2,500 |          7,500 |
| `rig_advanced` | Advanced Rig |  3,000,000 ECY |                       60,000 |      15,000 |         45,000 |
| `rig_elite`    | Elite Rig    | 15,000,000 ECY |                      300,000 |      75,000 |        225,000 |
| `rig_eternal`  | Eternal Rig  | 75,000,000 ECY |                    1,500,000 |     375,000 |      1,125,000 |

Target net ROI:

```text
Approximately 67 days
```

Crypto yield formula:

```text
Crypto Units =
Gross ECY Equivalent / 7-Day Average Crypto Price
```

Offline mining cap:

```text
24 hours
```

Mining slots:

| RPG Level | Active Rig Slots |
| --------: | ---------------: |
|        10 |                1 |
|        25 |                2 |
|        45 |                3 |
|        70 |                4 |

Rig data must include:

```text
rig_instance_id
owner_id
rig_type
target_asset
hashrate
efficiency
durability
pending_asset_units
last_calculated_at
created_at
```

---

# 42. Giveaway System

Giveaway is a new ECY-based community feature.

Only Discord Administrators may:

```text
/giveaway create
/giveaway end
/giveaway cancel
/giveaway redraw
/giveaway history
```

Members may:

```text
/giveaway list
/giveaway info
/giveaway enter
/giveaway status
```

Baseline:

```text
Default ticket price: 10,000 ECY
Maximum tickets: 1 per user
Maximum active giveaways per channel: 1
Maximum active giveaways per server: 3
```

Administrators create giveaways, but cannot choose winners.

---

# 43. Giveaway Eligibility and Activity Score

Baseline requirements:

```text
Discord account age: Minimum 30 days
Server membership: Minimum 14 days
30-day Activity Score: Minimum 80
Must not be a bot
Must not be blacklisted
Must still be in the server
```

Activity Score:

| Activity                        | Score | 30-Day Cap |
| ------------------------------- | ----: | ---------: |
| Daily claim                     |    +2 |         40 |
| Daily quest completed           |    +4 |         80 |
| Valid 30-minute voice activity  |    +2 |         40 |
| Valid boss participation        |    +5 |         30 |
| Dungeon completed               |    +3 |         30 |
| Active day with 3 valid actions |    +3 |         60 |

The following do not count:

* casino profit;
* crypto profit;
* Eternal Options profit;
* admin mint;
* refund;
* admin adjustment;
* marketplace sales volume.

Activity Score must be derived from activity records, not from wallet balance.

---

# 44. Giveaway Escrow

When a ticket is purchased:

```text
User ECY → Giveaway Escrow
```

If cancelled:

```text
100% refund to ticket holders
```

If completed:

```text
80% → Giveaway Fund
10% → ECY Locked Reserve
10% → Burn
```

Ticket purchase, escrow movement, and ledger creation must be atomic.

---

# 45. Giveaway Random Draw

Winners must be selected randomly by the bot.

Eligible draw pool:

* valid ticket purchased;
* ECY payment completed;
* eligibility requirements met;
* still in the server;
* not blacklisted;
* not a bot;
* not refunded or disqualified.

Use cryptographically secure randomness.

One user cannot win twice in the same giveaway.

The draw result must be stored permanently before announcement.

Admin cannot manually select or replace a winner.

Claim period:

```text
24 hours
```

Redraw is allowed only when:

* winner did not claim;
* winner left the server;
* winner became invalid;
* verified rule violation occurred.

Redraw must randomly select from the remaining valid participants.

---

# 46. Server Treasury

The treasury belongs to the guild system, not to an admin account.

## ETM Treasury Accounts

```text
ETM_GENERAL
ETM_BOSS_DUNGEON
ETM_EVENT
ETM_RESERVE
```

## ECY Treasury Accounts

```text
ECY_GENERAL
ECY_GIVEAWAY
ECY_CASINO
ECY_MARKET
ECY_MINING
ECY_RESERVE
```

Standard purchase allocation:

```text
80% → Related Operational Fund
10% → Locked Reserve
10% → Burn
```

This applies to:

* RPG shop purchases;
* equipment purchases;
* pet purchases;
* crafting;
* equipment enhancement;
* repairs;
* mining rig purchases;
* mining maintenance;
* completed giveaway ticket funds.

Exceptions:

* casino uses Casino Bankroll;
* crypto principal uses Market Reserve;
* exchange uses its specific fee flow;
* admin mint creates new supply;
* marketplace only splits the 5% seller fee.

---

# 47. Admin Minting

Whitelisted user IDs may mint ETM or ECY.

Command:

```text
/economy mint
target:
currency:
amount:
reason:
```

Whitelisting is based on executor user ID.

Discord Administrator permission alone is not enough.

Admin mint behavior:

* creates new currency;
* does not debit treasury;
* has no tax;
* does not enter reserve;
* does not increase Activity Score;
* does not trigger quests;
* does not trigger economic achievements;
* does not count as farming;
* requires a non-empty reason;
* requires confirmation;
* requires permanent ledger and audit log;
* must be idempotent.

Ledger source:

```text
ADMIN_MINT
```

Separate actions:

```text
ADMIN_MINT
TREASURY_GRANT
ADMIN_REMOVE
SYSTEM_SEED
```

`ADMIN_REMOVE` must be a separate command.

Negative mint values are forbidden.

Large mint amounts require an additional confirmation step.

---

# 48. System Seed

Casino Bankroll and Market Reserve may receive a one-time seed.

Ledger source:

```text
SYSTEM_SEED
```

The seed must:

* use a migration or configuration marker;
* run only once;
* never repeat after restart;
* appear in the audit ledger.

---

# 49. Economy Ledger

Every wallet mutation must produce a ledger record.

Required fields:

```text
transaction_id
guild_id
user_id
currency
transaction_type
amount
balance_before
balance_after
reference_id
source
created_at
```

Supported sources include:

```text
MINTED
TREASURY_PAID
CASINO_PAYOUT
MARKET_SETTLEMENT
REFUND
ADMIN_MINT
ADMIN_REMOVE
ADMIN_ADJUSTMENT
SYSTEM_SEED
```

Transaction types should cover:

* daily;
* weekly;
* work;
* hunt;
* quest;
* dungeon;
* boss;
* shop;
* equipment enhancement;
* crafting;
* transfer;
* exchange;
* marketplace sale;
* marketplace purchase;
* casino bet;
* casino payout;
* crypto buy;
* crypto sell;
* crypto fee;
* mining rig purchase;
* mining maintenance;
* mining claim;
* giveaway ticket;
* giveaway refund;
* Eternal Options stake;
* Eternal Options payout;
* admin mint;
* treasury grant;
* admin remove.

---

# 50. Atomic Transactions

The following must be atomic:

* daily;
* weekly;
* transfer;
* exchange;
* shop purchase;
* crafting;
* enhancement;
* equipment binding;
* marketplace listing creation;
* marketplace purchase;
* marketplace cancellation;
* casino bet and payout;
* crypto buy and sell;
* mining claim;
* giveaway entry;
* giveaway refund;
* Eternal Options settlement;
* admin mint;
* treasury grant.

General pattern:

```text
Validate
→ Debit
→ Credit destination
→ Grant item or asset
→ Write ledger
→ Commit
```

If any step fails, roll back everything.

---

# 51. Restart Safety and Idempotency

After a bot restart:

* active giveaways remain active;
* giveaway buttons remain usable;
* Eternal Options positions settle correctly;
* pending mining rewards remain intact;
* market prices remain persisted;
* marketplace listings remain active;
* escrow items remain intact;
* starter packages are not duplicated;
* payouts are not duplicated;
* admin mint actions are not replayed;
* completed migrations do not rerun;
* persistent views are re-registered;
* transaction settlement uses idempotency keys.

---

# 52. Emergency Controls

Whitelisted staff commands:

```text
/economy pause casino
/economy pause crypto
/economy pause exchange
/economy pause giveaway
/economy pause mining
/economy pause marketplace
/economy status
```

Pause behavior:

* blocks new transactions;
* does not silently delete active sessions;
* active settlements must finish safely;
* impossible settlements must be refunded;
* pause and resume actions must enter the audit log.

---

# 53. Economy Dashboard

Admin dashboard must display:

* total ETM supply;
* total ECY supply;
* circulating balances;
* treasury balances;
* locked reserves;
* total burned;
* seven-day minted amount;
* seven-day burned amount;
* median user balances;
* active users;
* Casino Bankroll;
* Market Reserve;
* Giveaway Fund;
* marketplace volume;
* treasury income;
* treasury expenses;
* economy health status.

Health indicators:

```text
Healthy
Needs Attention
Unbalanced
```

The dashboard should report recommendations but must not silently change tax, reward, or exchange settings.

---

# 54. Immutable Command Ownership

These command ownership rules must not change:

```text
/leaderboard = RPG
w!leaderboard = RPG

/vouchleaderboard = Trusted Vouch
w!deal leaderboard = Trusted Vouch

w!rank = RPG
w!deal rank = Trust/Vouch
```

Forbidden top-level prefix aliases:

```text
w!vouch
w!vouches
w!rep
w!trustlb
w!trank
w!vouchleaderboard
w!vouchremove
w!vouchreport
```

Do not modify unrelated middleman, deal, vouch, or trusted-reputation ownership.

---

# 55. Out of Scope for V1

Do not implement the following in V1:

* direct item trading;
* auctions;
* bidding;
* price offers;
* item barter;
* ECY transfers;
* ECY-to-ETM conversion;
* trading hatched pets;
* trading Eternal equipment;
* real-money cryptocurrency;
* withdrawable currency;
* automatic dynamic tax changes;
* duplicate Crash-style multiplier game.

---

# 56. Implementation Phases

## Phase 1 — Economy Foundation

* ETM and ECY wallets;
* legacy migration;
* integer balances;
* economy ledger;
* atomic wallet helpers;
* treasury accounts;
* reserves;
* burns;
* admin mint whitelist;
* system seed;
* emergency controls.

## Phase 2 — Core Economy

* daily;
* weekly;
* work;
* ETM transfer;
* Eternal Exchange;
* upgraded profile.

## Phase 3 — RPG

* starter package;
* equipment;
* binding;
* enhancement;
* pets;
* materials;
* crafting;
* hunt;
* quests;
* dungeons;
* boss raids.

## Phase 4 — Eternal Marketplace

* listing escrow;
* browse;
* search;
* details;
* comparison;
* fixed-price purchase;
* partial stack purchase;
* listing cancellation;
* history;
* price checks;
* watchlists;
* reports;
* moderation.

## Phase 5 — Casino

* migrate all casino games to ECY;
* validate bets;
* enforce limits;
* add Casino Bankroll;
* atomic settlement;
* RTP simulation and verification.

## Phase 6 — Crypto

* migrate prices to ECY;
* upgraded market;
* buy and sell;
* Market Reserve;
* portfolio;
* profit tracking;
* fee allocation;
* market history;
* upgraded market news.

## Phase 7 — Mining

* rig purchases;
* target asset selection;
* durability;
* maintenance;
* pending rewards;
* claims;
* offline cap;
* slot progression.

## Phase 8 — Giveaway and Eternal Options

* admin-only giveaway creation;
* eligibility;
* Activity Score;
* escrow;
* secure random draw;
* claim and redraw;
* replace legacy Crash/Binomo;
* restart-safe Options settlement.

## Phase 9 — Dashboard and QA

* economy dashboard;
* treasury reporting;
* audit reports;
* migration validation;
* simulation;
* concurrency testing;
* restart recovery;
* live Discord testing.

---

# 57. Acceptance Criteria

The V1 system is accepted only when:

1. Legacy balances migrate into ETM exactly once.
2. ETM and ECY are fully separated.
3. ECY cannot be transferred or converted back.
4. Critical transactions are atomic.
5. Marketplace purchases cannot duplicate items or balances.
6. Two buyers cannot purchase the same unique item.
7. Marketplace listings have no expiration.
8. Casino bets above 500,000 ECY are rejected.
9. Casino payouts use the Casino Bankroll.
10. Casino RTP is validated through simulation.
11. Crypto settlement uses the Market Reserve.
12. Mining produces crypto assets, not direct ECY.
13. Giveaway creation is Administrator-only.
14. Giveaway winners are random valid ticket holders.
15. Admin mint requires a whitelisted executor ID.
16. Admin mint does not count as user activity.
17. All staff actions are audited.
18. Restarting does not duplicate rewards or payouts.
19. Wallet and asset values do not use floating point.
20. Persistent interactions do not produce avoidable interaction failures.
21. Existing immutable command ownership remains unchanged.
22. Unrelated deal and middleman systems remain functional.

---

# 58. Required Testing

Before production, simulate:

```text
1,000 virtual users
30–90 simulated days
```

Player profiles:

* casual;
* active;
* RPG-focused;
* marketplace buyer;
* marketplace seller;
* casino-focused;
* crypto trader;
* miner;
* whale;
* alt account.

Testing must evaluate:

* ETM supply growth;
* ECY supply growth;
* treasury income and spending;
* burn rate;
* equipment progression speed;
* pet progression speed;
* Basic Rig purchase time;
* mining ROI;
* Casino Bankroll stability;
* Market Reserve liquidity;
* marketplace pricing;
* concurrent purchases;
* Activity Score eligibility;
* giveaway fairness;
* duplicate interaction handling;
* migration idempotency;
* restart recovery;
* settlement idempotency.

---

This PRD is the authoritative source of truth for the Way 2 Eternal V1 economy, RPG, equipment, pet, marketplace, casino, crypto, mining, giveaway, treasury, Eternal Options, and admin economy-control systems.
