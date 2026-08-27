"""Katalog RPG V1 yang deterministik dan tervalidasi."""

import hashlib
import json
import secrets

from .constants import RPG_PHASE3_CATALOG_VERSION
from .time_policy import utc_iso


RARITIES = ("COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY", "ETERNAL")
SLOTS = ("WEAPON", "ARMOR", "ACCESSORY")


class CatalogValidationError(ValueError):
    pass


def _equipment(item_id, name, rarity, slot, level, value, *, hp=0, attack=0, defense=0,
               crit_bps=0, boss_damage_bps=0, set_id=None):
    return {
        "item_id": item_id, "name": name, "type": "EQUIPMENT", "rarity": rarity,
        "slot": slot, "required_level": level, "base_value": value,
        "hp": hp, "attack": attack, "defense": defense, "crit_bps": crit_bps,
        "boss_damage_bps": boss_damage_bps, "set_id": set_id,
        "tradeable": rarity != "ETERNAL",
    }


EQUIPMENT = {
    row["item_id"]: row for row in (
        _equipment("eq_wanderer_blade", "Wanderer's Blade", "COMMON", "WEAPON", 1, 100_000, attack=20, set_id="set_wanderer"),
        _equipment("eq_traveler_vest", "Traveler's Vest", "COMMON", "ARMOR", 1, 120_000, hp=120, defense=10, set_id="set_wanderer"),
        _equipment("eq_copper_charm", "Copper Eternium Charm", "COMMON", "ACCESSORY", 1, 80_000, crit_bps=100, set_id="set_wanderer"),
        _equipment("eq_ironfang_sword", "Ironfang Sword", "UNCOMMON", "WEAPON", 10, 300_000, attack=55, set_id="set_ironclad"),
        _equipment("eq_ironbark_guard", "Ironbark Guard", "UNCOMMON", "ARMOR", 10, 350_000, hp=250, defense=30, set_id="set_ironclad"),
        _equipment("eq_gale_sigil", "Gale Sigil", "UNCOMMON", "ACCESSORY", 10, 250_000, crit_bps=200, set_id="set_ironclad"),
        _equipment("eq_nightfang_blade", "Nightfang Blade", "RARE", "WEAPON", 25, 1_200_000, attack=120, set_id="set_nightfall"),
        _equipment("eq_shadowmail_armor", "Shadowmail Armor", "RARE", "ARMOR", 25, 1_400_000, hp=500, defense=65, set_id="set_nightfall"),
        _equipment("eq_oracles_eye", "Oracle's Eye", "RARE", "ACCESSORY", 25, 1_000_000, crit_bps=300, boss_damage_bps=300, set_id="set_nightfall"),
        _equipment("eq_astral_edge", "Astral Edge", "EPIC", "WEAPON", 45, 5_000_000, attack=250, crit_bps=200, set_id="set_astral"),
        _equipment("eq_starforged_plate", "Starforged Plate", "EPIC", "ARMOR", 45, 5_800_000, hp=1000, defense=140, set_id="set_astral"),
        _equipment("eq_eclipse_pendant", "Eclipse Pendant", "EPIC", "ACCESSORY", 45, 4_500_000, crit_bps=400, boss_damage_bps=400, set_id="set_astral"),
        _equipment("eq_void_reaver", "Void Reaver", "LEGENDARY", "WEAPON", 70, 18_000_000, attack=500, crit_bps=400, set_id="set_void"),
        _equipment("eq_dragonbone_aegis", "Dragonbone Aegis", "LEGENDARY", "ARMOR", 70, 22_000_000, hp=2200, defense=300, set_id="set_void"),
        _equipment("eq_crown_lunniera", "Crown of Lunniera", "LEGENDARY", "ACCESSORY", 70, 16_000_000, crit_bps=600, boss_damage_bps=800, set_id="set_void"),
        _equipment("eq_first_eternal_blade", "Blade of the First Eternal", "ETERNAL", "WEAPON", 90, 60_000_000, attack=900, crit_bps=600, set_id="set_eternal"),
        _equipment("eq_endless_dawn_aegis", "Aegis of Endless Dawn", "ETERNAL", "ARMOR", 90, 70_000_000, hp=4000, defense=550, set_id="set_eternal"),
        _equipment("eq_heart_eternium", "Heart of Eternium", "ETERNAL", "ACCESSORY", 90, 55_000_000, crit_bps=800, boss_damage_bps=1000, set_id="set_eternal"),
    )
}

SETS = {
    "set_wanderer": {2: {"attack_bps": 200}, 3: {"hp_bps": 300}},
    "set_ironclad": {2: {"defense_bps": 400}, 3: {"hp_bps": 500}},
    "set_nightfall": {2: {"attack_bps": 500}, 3: {"crit_bps": 200}},
    "set_astral": {2: {"attack_bps": 800}, 3: {"dungeon_damage_bps": 600}},
    "set_void": {2: {"attack_bps": 1000}, 3: {"boss_damage_bps": 1000}},
    "set_eternal": {2: {"attack_bps": 1200}, 3: {"all_damage_bps": 1000, "context_defense_bps": 1000}},
}

PETS = {
    "pet_moss_slime": ("Moss Slime", "COMMON", 1, {"hp_bps": 400}, "8% reduksi damage masuk 10%"),
    "pet_ember_chick": ("Ember Chick", "COMMON", 1, {"attack_bps": 400}, "8% bonus damage 25%"),
    "pet_stonehorn_cub": ("Stonehorn Cub", "UNCOMMON", 10, {"defense_bps": 600}, "Serangan masuk pertama -15%"),
    "pet_gale_fox": ("Gale Fox", "UNCOMMON", 10, {"crit_bps": 300}, "10% counter 30%"),
    "pet_shadow_wolf": ("Shadow Wolf", "RARE", 25, {"attack_bps": 800}, "10% damage 150%"),
    "pet_moonlight_owl": ("Moonlight Owl", "RARE", 25, {"defense_bps": 800}, "8% dodge"),
    "pet_abyss_panther": ("Abyss Panther", "EPIC", 45, {"attack_bps": 1000, "crit_bps": 200}, "10% abaikan 20% DEF"),
    "pet_celestial_stag": ("Celestial Stag", "EPIC", 45, {"hp_bps": 1200}, "Pulihkan 5% HP sekali"),
    "pet_dawn_phoenix": ("Dawn Phoenix", "LEGENDARY", 70, {"hp_bps": 1800}, "Bangkit 20% HP"),
    "pet_void_wyrm": ("Void Wyrm", "LEGENDARY", 70, {"attack_bps": 1600}, "8% serang dua kali"),
    "pet_eternion_dragon": ("Eternion Dragon", "ETERNAL", 90, {"attack_bps": 2200}, "10% abaikan 35% DEF"),
    "pet_lunniera_seraph": ("Lunniera Seraph", "ETERNAL", 90, {"hp_bps": 1200, "defense_bps": 1000}, "Shield 15% HP"),
}

STACK_ITEMS = {
    "mat_iron_shard": ("Iron Shard", "MATERIAL", "COMMON", True),
    "mat_shadow_crystal": ("Shadow Crystal", "MATERIAL", "RARE", True),
    "mat_astral_fragment": ("Astral Fragment", "MATERIAL", "EPIC", True),
    "mat_dragon_core": ("Dragon Core", "MATERIAL", "LEGENDARY", True),
    "mat_eternal_fragment": ("Eternal Fragment", "MATERIAL", "ETERNAL", False),
    "mat_beast_core": ("Beast Core", "MATERIAL", "RARE", True),
    "mat_pet_essence": ("Pet Essence", "MATERIAL", "EPIC", False),
    "mat_protection_stone": ("Protection Stone", "MATERIAL", "EPIC", True),
    "item_dungeon_ticket": ("Dungeon Ticket", "CONSUMABLE", "RARE", False),
    "item_epic_chest": ("Epic Chest", "CONSUMABLE", "EPIC", False),
    "bp_eternal_weapon": ("Eternal Weapon Blueprint", "BLUEPRINT", "ETERNAL", True),
    "bp_eternal_armor": ("Eternal Armor Blueprint", "BLUEPRINT", "ETERNAL", True),
    "bp_eternal_accessory": ("Eternal Accessory Blueprint", "BLUEPRINT", "ETERNAL", True),
    "egg_pet_common": ("Common Pet Egg", "CONSUMABLE", "COMMON", True),
    "egg_pet_uncommon": ("Uncommon Pet Egg", "CONSUMABLE", "UNCOMMON", True),
    "egg_pet_rare": ("Rare Pet Egg", "CONSUMABLE", "RARE", True),
    "egg_pet_epic": ("Epic Pet Egg", "CONSUMABLE", "EPIC", True),
    "egg_pet_legendary": ("Legendary Pet Egg", "CONSUMABLE", "LEGENDARY", False),
    "egg_pet_eternal": ("Eternal Pet Egg", "CONSUMABLE", "ETERNAL", False),
}

ENHANCEMENT_BONUS_BPS = (0, 500, 1000, 1600, 2300, 3100, 4000, 5000, 6100, 7300, 8600, 10000, 11500, 13100, 14800, 16600)
ENHANCEMENT_SUCCESS_BPS = (0, 10000, 10000, 10000, 10000, 10000, 8500, 8000, 7500, 6500, 5500, 4500, 4000, 3500, 3000, 2500)
ENHANCEMENT_COST_BPS = (0, 800, 1200, 1800, 2500, 3500, 5000, 7000, 9500, 12500, 16000, 21000, 27000, 35000, 45000, 60000)
ENHANCEMENT_MATERIALS = {
    6: ("mat_iron_shard", 10), 7: ("mat_iron_shard", 15),
    8: ("mat_shadow_crystal", 10), 9: ("mat_shadow_crystal", 15),
    10: ("mat_astral_fragment", 12), 11: ("mat_astral_fragment", 18),
    12: ("mat_dragon_core", 10), 13: ("mat_dragon_core", 15),
    14: ("mat_eternal_fragment", 5), 15: ("mat_eternal_fragment", 10),
}
CRAFT_RECIPES = {
    "UNCOMMON": {"cost": 300_000, "materials": {"mat_iron_shard": 20}},
    "RARE": {"cost": 1_200_000, "materials": {"mat_shadow_crystal": 35, "mat_beast_core": 3}},
    "EPIC": {"cost": 5_000_000, "materials": {"mat_astral_fragment": 45, "mat_beast_core": 5}},
    "LEGENDARY": {"cost": 20_000_000, "materials": {"mat_dragon_core": 30, "mat_beast_core": 10}},
    "ETERNAL": {"cost": 75_000_000, "materials": {"mat_eternal_fragment": 50, "mat_dragon_core": 20}},
}
PET_DUPLICATE_ESSENCE = {
    "COMMON": 10, "UNCOMMON": 20, "RARE": 40,
    "EPIC": 80, "LEGENDARY": 160, "ETERNAL": 320,
}

HUNTS = {
    "green_forest": ("Green Forest", 1, 10, (8_000, 15_000), (20, 35)),
    "dark_cave": ("Dark Cave", 10, 12, (20_000, 35_000), (45, 70)),
    "eternal_ruins": ("Eternal Ruins", 25, 15, (45_000, 75_000), (90, 140)),
    "abyss_realm": ("Abyss Realm", 45, 20, (90_000, 150_000), (180, 280)),
}
DUNGEONS = {
    "forgotten_crypt": ("Forgotten Crypt", 10, 50_000, (120_000, 220_000), (250, 400)),
    "shadow_fortress": ("Shadow Fortress", 25, 150_000, (350_000, 650_000), (700, 1000)),
    "eternal_abyss": ("Eternal Abyss", 45, 500_000, (1_200_000, 2_000_000), (1800, 2500)),
}
BOSSES = {
    "NORMAL": {"level": 20, "max_hp": 100_000, "defense": 100, "pool": 2_000_000, "minimum_bps": 10, "pet_xp": 100},
    "ELITE": {"level": 50, "max_hp": 750_000, "defense": 300, "pool": 8_000_000, "minimum_bps": 20, "pet_xp": 300},
    "WORLD": {"level": 80, "max_hp": 5_000_000, "defense": 700, "pool": 25_000_000, "minimum_bps": 25, "pet_xp": 800},
}

HUNT_DROPS = {
    "green_forest": {"materials": [("mat_iron_shard", 4500), ("mat_beast_core", 500)], "equipment": [("COMMON", 300)], "eggs": [("egg_pet_common", 100)]},
    "dark_cave": {"materials": [("mat_iron_shard", 3500), ("mat_shadow_crystal", 1200), ("mat_beast_core", 800)], "equipment": [("RARE", 30), ("UNCOMMON", 400)], "eggs": [("egg_pet_uncommon", 120)]},
    "eternal_ruins": {"materials": [("mat_shadow_crystal", 2200), ("mat_astral_fragment", 600), ("mat_beast_core", 1000)], "equipment": [("EPIC", 40), ("RARE", 300)], "eggs": [("egg_pet_rare", 80)]},
    "abyss_realm": {"materials": [("mat_astral_fragment", 1500), ("mat_dragon_core", 300), ("mat_beast_core", 1200)], "equipment": [("LEGENDARY", 20), ("EPIC", 200)], "eggs": [("egg_pet_epic", 50)]},
}
DUNGEON_DROPS = {
    "forgotten_crypt": {"materials": [("mat_shadow_crystal", 6000)], "equipment": [("RARE", 1200), ("UNCOMMON", 3500)], "eggs": [("egg_pet_rare", 100)]},
    "shadow_fortress": {"materials": [("mat_astral_fragment", 5500)], "equipment": [("LEGENDARY", 50), ("EPIC", 1000), ("RARE", 3000)], "eggs": [("egg_pet_epic", 100)]},
    "eternal_abyss": {"materials": [("mat_dragon_core", 4500), ("mat_eternal_fragment", 200)], "equipment": [("LEGENDARY", 500), ("EPIC", 2500)], "eggs": [("egg_pet_legendary", 30)], "blueprints": [("RANDOM_ETERNAL", 25)]},
}
BOSS_DROPS = {
    "NORMAL": {"materials": [("mat_shadow_crystal", 3500), ("mat_beast_core", 2000)], "equipment": [("EPIC", 50), ("RARE", 400)]},
    "ELITE": {"materials": [("mat_astral_fragment", 4000), ("mat_beast_core", 3000)], "equipment": [("LEGENDARY", 50), ("EPIC", 500)], "eggs": [("egg_pet_epic", 75)]},
    "WORLD": {"materials": [("mat_dragon_core", 5000), ("mat_eternal_fragment", 100)], "equipment": [("LEGENDARY", 300)], "eggs": [("egg_pet_eternal", 5), ("egg_pet_legendary", 50)], "blueprints": [("RANDOM_ETERNAL", 25)]},
}


def roll_drops(table, *, randbelow=None):
    randbelow = randbelow or secrets.randbelow
    result = {"stacks": [], "equipment": None}
    for item_id, bps in table.get("materials", ()):  # material rolls independen
        if randbelow(10_000) < bps:
            result["stacks"].append(item_id)
    for rarity, bps in table.get("equipment", ()):  # urutan rarity tinggi, maksimum satu
        if randbelow(10_000) < bps:
            choices = sorted(key for key, row in EQUIPMENT.items() if row["rarity"] == rarity)
            result["equipment"] = choices[randbelow(len(choices))]
            break
    for item_id, bps in table.get("eggs", ()):  # maksimum satu egg
        if randbelow(10_000) < bps:
            result["stacks"].append(item_id)
            break
    for item_id, bps in table.get("blueprints", ()):
        if randbelow(10_000) < bps:
            if item_id == "RANDOM_ETERNAL":
                blueprints = ("bp_eternal_weapon", "bp_eternal_armor", "bp_eternal_accessory")
                item_id = blueprints[randbelow(len(blueprints))]
            result["stacks"].append(item_id)
            break
    return result


def catalog_payload():
    return {"equipment": EQUIPMENT, "sets": SETS, "pets": PETS, "items": STACK_ITEMS,
            "hunts": HUNTS, "dungeons": DUNGEONS, "bosses": BOSSES,
            "hunt_drops": HUNT_DROPS, "dungeon_drops": DUNGEON_DROPS,
            "boss_drops": BOSS_DROPS, "craft_recipes": CRAFT_RECIPES,
            "pet_duplicate_essence": PET_DUPLICATE_ESSENCE,
            "enhancement_materials": ENHANCEMENT_MATERIALS}


def catalog_hash():
    raw = json.dumps(catalog_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def validate_catalog():
    def require(condition, message):
        if not condition:
            raise CatalogValidationError(message)

    require(len(EQUIPMENT) == 18, "Jumlah equipment katalog tidak sesuai.")
    require(set(row["rarity"] for row in EQUIPMENT.values()) == set(RARITIES),
            "Cakupan rarity equipment tidak lengkap.")
    require(all(row["slot"] in SLOTS for row in EQUIPMENT.values()), "Slot equipment tidak valid.")
    require(all(row["item_id"] == item_id for item_id, row in EQUIPMENT.items()),
            "ID equipment tidak konsisten.")
    require(all(row["required_level"] in range(1, 101) for row in EQUIPMENT.values()),
            "Required level equipment tidak valid.")
    require(all(row.get("set_id") in SETS for row in EQUIPMENT.values()),
            "Referensi set equipment tidak valid.")
    require(all(item[1] in ("MATERIAL", "CONSUMABLE", "BLUEPRINT") for item in STACK_ITEMS.values()),
            "Tipe stack item tidak valid.")
    require(set(ENHANCEMENT_MATERIALS) == set(range(6, 16)),
            "Tabel material enhancement tidak lengkap.")
    require(all(item_id in STACK_ITEMS and amount > 0
                for item_id, amount in ENHANCEMENT_MATERIALS.values()),
            "Material enhancement tidak valid.")
    require(len(ENHANCEMENT_SUCCESS_BPS) == 16 and
            all(0 <= value <= 10_000 for value in ENHANCEMENT_SUCCESS_BPS),
            "Peluang enhancement tidak valid.")
    for table_name, tables in (("hunt", HUNT_DROPS), ("dungeon", DUNGEON_DROPS),
                               ("boss", BOSS_DROPS)):
        for table_id, table in tables.items():
            for item_id, bps in table.get("materials", ()):
                require(item_id in STACK_ITEMS and 0 <= bps <= 10_000,
                        f"Drop material {table_name}:{table_id} tidak valid.")
            for rarity, bps in table.get("equipment", ()):
                require(rarity in RARITIES and 0 <= bps <= 10_000,
                        f"Drop equipment {table_name}:{table_id} tidak valid.")
            for item_id, bps in table.get("eggs", ()):
                require(item_id in STACK_ITEMS and item_id.startswith("egg_pet_") and 0 <= bps <= 10_000,
                        f"Drop egg {table_name}:{table_id} tidak valid.")
    require(set(HUNT_DROPS) == set(HUNTS), "Referensi drop Hunt tidak lengkap.")
    require(set(DUNGEON_DROPS) == set(DUNGEONS), "Referensi drop Dungeon tidak lengkap.")
    require(set(BOSS_DROPS) == set(BOSSES), "Referensi drop Boss tidak lengkap.")
    require(set(PET_DUPLICATE_ESSENCE) == set(RARITIES), "Konversi Pet Essence tidak lengkap.")
    return catalog_hash()


async def seed_catalog(db, *, now=None):
    digest = validate_catalog()
    timestamp = utc_iso(now)
    async with db.execute(
        "SELECT catalogHash FROM RpgCatalogManifest WHERE catalogVersion=?",
        (RPG_PHASE3_CATALOG_VERSION,),
    ) as cursor:
        existing = await cursor.fetchone()
    if existing:
        if existing[0] != digest:
            raise ValueError("Hash katalog yang sudah tersimpan tidak cocok.")
        return digest
    rows = []
    for item in EQUIPMENT.values():
        rows.append((RPG_PHASE3_CATALOG_VERSION, item["item_id"], "EQUIPMENT", item["name"],
                     item["rarity"], item["slot"], item["required_level"], int(item["tradeable"]),
                     json.dumps(item, sort_keys=True, separators=(",", ":"))))
    for item_id, (name, item_type, rarity, tradeable) in STACK_ITEMS.items():
        rows.append((RPG_PHASE3_CATALOG_VERSION, item_id, item_type, name, rarity, None, 1,
                     int(tradeable), json.dumps({"item_id": item_id}, separators=(",", ":"))))
    for pet_id, (name, rarity, level, passive, skill) in PETS.items():
        definition = {"pet_id": pet_id, "passive": passive, "skill": skill}
        rows.append((RPG_PHASE3_CATALOG_VERSION, pet_id, "PET", name, rarity, None, level, 0,
                     json.dumps(definition, sort_keys=True, separators=(",", ":"))))
    await db.executemany(
        "INSERT INTO RpgCatalogItem (catalogVersion,itemId,itemType,name,rarity,slot,requiredLevel,tradeable,definitionJson) "
        "VALUES (?,?,?,?,?,?,?,?,?)", rows,
    )
    definition_rows = []
    for section, definitions in catalog_payload().items():
        if isinstance(definitions, dict):
            for definition_id, definition in definitions.items():
                definition_rows.append((
                    RPG_PHASE3_CATALOG_VERSION,
                    section,
                    str(definition_id),
                    json.dumps(definition, sort_keys=True, separators=(",", ":")),
                ))
        else:
            definition_rows.append((
                RPG_PHASE3_CATALOG_VERSION, section, section,
                json.dumps(definitions, sort_keys=True, separators=(",", ":")),
            ))
    await db.executemany(
        "INSERT INTO RpgCatalogDefinition "
        "(catalogVersion,definitionType,definitionId,definitionJson) VALUES (?,?,?,?)",
        definition_rows,
    )
    await db.execute(
        "INSERT INTO RpgCatalogManifest (catalogVersion,catalogHash,seededAt,detailsJson) VALUES (?,?,?,?)",
        (RPG_PHASE3_CATALOG_VERSION, digest, timestamp,
         json.dumps({"item_count": len(rows), "definition_count": len(definition_rows)})),
    )
    return digest
