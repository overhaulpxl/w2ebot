"""Starter package, equipment, dan effective-stat Phase 3."""

import json
import uuid
from dataclasses import dataclass

import aiosqlite

from .catalog import ENHANCEMENT_BONUS_BPS, EQUIPMENT, PETS, SETS
from .constants import RPG_MAX_CRIT_BPS, RPG_PHASE3_CATALOG_VERSION
from .database import configure_connection
from .time_policy import utc_iso


STARTER_ITEMS = ("eq_wanderer_blade", "eq_traveler_vest", "eq_copper_charm")
STARTER_PET = "pet_moss_slime"


@dataclass(frozen=True)
class EffectiveStats:
    max_hp: int
    attack: int
    defense: int
    crit_bps: int
    power_score: int
    boss_damage_bps: int
    dungeon_damage_bps: int
    all_damage_bps: int


async def assert_equipment_not_in_marketplace_escrow(db, guild_id, equipment_instance_id):
    """Fail closed terhadap escrow aktif tanpa mewajibkan schema Phase 4 untuk Phase 3."""
    starter_equipment = await db.fetch(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='MarketplaceEscrow'"
        if not await cursor.fetchone():
            return
    profile = await db.fetchrow(
        "SELECT 1 FROM MarketplaceEscrow WHERE guildId=$1 AND equipmentInstanceId=$2 "
        "AND status IN ('HELD','PARTIAL','REVIEW_REQUIRED') LIMIT 1", str(guild_id), str(equipment_instance_id),
        if await cursor.fetchone():
            raise ValueError("Equipment sedang ditahan oleh marketplace.")


def enhanced_flat(value, enhancement_level):
    return int(value) * (10_000 + ENHANCEMENT_BONUS_BPS[int(enhancement_level)]) // 10_000


def _set_modifiers(equipped):
    counts = {}
    for row in equipped:
        set_id = row["definition"].get("set_id")
        if set_id:
            counts[set_id] = counts.get(set_id, 0) + 1
    totals = {}
    for set_id, count in counts.items():
        for required, modifiers in SETS[set_id].items():
            if count >= required:
                for key, value in modifiers.items():
                    totals[key] = totals.get(key, 0) + int(value)
    return totals


def calculate_effective_stats(*, base_hp, base_attack, base_defense, base_crit_bps,
                              equipped=(), active_pet_id=None, active_pet_level=1, context=None):
    flat = {"hp": 0, "attack": 0, "defense": 0, "crit_bps": 0, "boss_damage_bps": 0}
    for row in equipped:
        definition = row["definition"]
        level = int(row.get("enhancement_level", 0))
        for key in ("hp", "attack", "defense", "crit_bps", "boss_damage_bps"):
            flat[key] += enhanced_flat(definition.get(key, 0), level)
    modifiers = _set_modifiers(equipped)
    pet_modifiers = PETS.get(active_pet_id, None, None, None, {}, None)[3]
    pet_scale_bps = 10_000 + min(10, max(0, int(active_pet_level) // 5)) * 200
    for key, value in pet_modifiers.items():
        modifiers[key] = modifiers.get(key, 0) + int(value) * pet_scale_bps // 10_000
    hp = (int(base_hp) + flat["hp"]) * (10_000 + modifiers.get("hp_bps", 0)) // 10_000
    attack = (int(base_attack) + flat["attack"]) * (10_000 + modifiers.get("attack_bps", 0)) // 10_000
    defense_bps = modifiers.get("defense_bps", 0)
    if context in ("BOSS", "DUNGEON"):
        defense_bps += modifiers.get("context_defense_bps", 0)
    defense = (int(base_defense) + flat["defense"]) * (10_000 + defense_bps) // 10_000
    crit = min(RPG_MAX_CRIT_BPS, int(base_crit_bps) + flat["crit_bps"] + modifiers.get("crit_bps", 0))
    boss_damage = flat["boss_damage_bps"] + modifiers.get("boss_damage_bps", 0)
    dungeon_damage = modifiers.get("dungeon_damage_bps", 0)
    all_damage = modifiers.get("all_damage_bps", 0)
    power = attack * 4 + defense * 3 + hp // 5 + crit // 100
    return EffectiveStats(hp, attack, defense, crit, power, boss_damage, dungeon_damage, all_damage)


def starter_effective_stats():
    equipped = [
        {"definition": EQUIPMENT[item_id], "enhancement_level": 0}
        for item_id in STARTER_ITEMS
    ]
    return calculate_effective_stats(
        base_hp=1000, base_attack=50, base_defense=25, base_crit_bps=500,
        equipped=equipped, active_pet_id=STARTER_PET,
    )


async def initialize_phase3_profile(db_path, guild_id, user_id, *, now=None):
    timestamp = utc_iso(now)
    stats = starter_effective_stats()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        try:
            guild_key = str(guild_id)
            user_key = str(user_id)
            async with db.execute(
                "SELECT starterPackClaimed,starterPackClaimedAt FROM RpgProfile "
                "WHERE guildId=$1 AND userId=$2", guild_key, user_key),
            )
            grant = await db.fetchrow(
                "SELECT grantId,status,weaponInstanceId,armorInstanceId,accessoryInstanceId,"
                "petInstanceId FROM RpgStarterGrant WHERE guildId=$1 AND userId=$2", guild_key, user_key),
            )
            await db.execute(
                "INSERT OR IGNORE INTO RpgProfile "
                "(guildId,userId,level,xp,maxHp,currentHp,attack,defense,critBps,energy,energyUpdatedAt,version,createdAt,updatedAt) "
                "VALUES ($1,$2,1,0,1000,$3,50,25,500,100,$4,0,$5,$6)", guild_key, user_key, stats.max_hp, timestamp, timestamp, timestamp),
            )
            profile = await db.fetchrow(
                "SELECT equipmentInstanceId,itemId,slot FROM RpgEquipmentInstance "
                "WHERE guildId=$1 AND ownerId=$2 AND acquiredSource='STARTER' ORDER BY equipmentInstanceId",
                (guild_key, user_key),
            )
            starter_pets = await db.fetch(
                "SELECT petInstanceId,petId FROM RpgPetInstance "
                "WHERE guildId=$1 AND ownerId=$2 AND acquiredSource='STARTER' ORDER BY petInstanceId",
                (guild_key, user_key),
            )

            expected_items = set(STARTER_ITEMS)
            existing_items = {row[1] for row in starter_equipment}
            complete_children = (
                len(starter_equipment) == 3
                and existing_items == expected_items
                and len(starter_pets) == 1
                and starter_pets[0][1] == STARTER_PET
            has_children = bool(starter_equipment or starter_pets)
            existing_instance_ids = ({row[2]: row[0] for row in starter_equipment}
                                     if complete_children else {})
            expected_grant_ids = (
                existing_instance_ids.get("WEAPON"), existing_instance_ids.get("ARMOR"),
                existing_instance_ids.get("ACCESSORY"), starter_pets[0][0] if complete_children else None,
            )
            grant_conflict = bool(
                grant and complete_children
                and tuple(grant[2:6]) != expected_grant_ids
            marker_without_children = bool(profile and int(profile[0]) == 1 and not complete_children)
            grant_without_children = bool(grant and not complete_children)
            if (has_children and not complete_children) or grant_conflict or marker_without_children or grant_without_children:
                grant_id = grant[0] if grant else str(uuid.uuid4()
                review = json.dumps(
                    {"code": "starter_children_conflict"},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                await db.execute(
                    "INSERT INTO RpgStarterGrant "
                    "(grantId,guildId,userId,status,recoveryReviewJson,createdAt,updatedAt) "
                    "VALUES ($1,$2,$3,'REVIEW_REQUIRED',$4,$5,$6) "
                    "ON CONFLICT(guildId,userId) DO UPDATE SET status='REVIEW_REQUIRED',"
                    "recoveryReviewJson=excluded.recoveryReviewJson,updatedAt=excluded.updatedAt", grant_id, guild_key, user_key, review, timestamp, timestamp),
                )
                await db.execute(
                    "INSERT OR IGNORE INTO RpgRecoveryReview "
                    "(reviewId,grantId,guildId,userId,reviewCode,metadataJson,createdAt) "
                    "VALUES ($1,$2,$3,$4,$5,'{}',$6)",
                    (str(uuid.uuid4(), grant_id, guild_key, user_key,
                     "STARTER_CHILDREN_CONFLICT", timestamp),
                )
                await db.commit()
                return False

            if complete_children:
                instance_ids = existing_instance_ids
                pet_instance_id = starter_pets[0][0]
                if grant and grant[1] == "COMMITTED" and profile and int(profile[0]) == 1:
                    await db.rollback()
                    return False
            else:
                instance_ids = {}
                for item_id in STARTER_ITEMS:
                    instance_id = str(uuid.uuid4()
                    instance_ids[EQUIPMENT[item_id]["slot"]] = instance_id
                    await db.execute(
                        "INSERT INTO RpgEquipmentInstance "
                        "(equipmentInstanceId,guildId,ownerId,itemId,catalogVersion,slot,enhancementLevel,pityBps,bindingStatus,status,acquiredSource,createdAt,updatedAt) "
                        "VALUES ($1,$2,$3,$4,$5,$6,0,0,'STARTER_BOUND','OWNED','STARTER',$7,$8)", instance_id, guild_key, user_key, item_id,
                         RPG_PHASE3_CATALOG_VERSION, EQUIPMENT[item_id]["slot"], timestamp, timestamp),
                    )
                pet_instance_id = str(uuid.uuid4()
                await db.execute(
                    "INSERT INTO RpgPetInstance "
                    "(petInstanceId,guildId,ownerId,petId,catalogVersion,rarity,level,xp,evolutionState,status,acquiredSource,createdAt,updatedAt) "
                    "VALUES ($1,$2,$3,$4,$5,'COMMON',1,0,'BASE','OWNED','STARTER',$6,$7)", pet_instance_id, guild_key, user_key, STARTER_PET,
                     RPG_PHASE3_CATALOG_VERSION, timestamp, timestamp),
                )
            grant_id = grant[0] if grant else str(uuid.uuid4()
            await db.execute(
                "INSERT INTO RpgStarterGrant "
                "(grantId,guildId,userId,status,weaponInstanceId,armorInstanceId,accessoryInstanceId,"
                "petInstanceId,createdAt,updatedAt,committedAt) "
                "VALUES ($1,$2,$3,'COMMITTED',$4,$5,$6,$7,$8,$9,$10) "
                "ON CONFLICT(guildId,userId) DO UPDATE SET status='COMMITTED',"
                "weaponInstanceId=excluded.weaponInstanceId,armorInstanceId=excluded.armorInstanceId,"
                "accessoryInstanceId=excluded.accessoryInstanceId,petInstanceId=excluded.petInstanceId,"
                "updatedAt=excluded.updatedAt,committedAt=excluded.committedAt", grant_id, guild_key, user_key, instance_ids["WEAPON"], instance_ids["ARMOR"],
                 instance_ids["ACCESSORY"], pet_instance_id, timestamp, timestamp, timestamp),
            )
            await db.execute(
                "UPDATE RpgProfile SET currentHp=$1,activeWeaponInstanceId=$2,activeArmorInstanceId=$3,"
                "activeAccessoryInstanceId=$1,activePetInstanceId=$2,starterPackClaimed=1,"
                "starterPackClaimedAt=COALESCE(starterPackClaimedAt,$1),version=version+1,updatedAt=$2 "
                "WHERE guildId=$1 AND userId=$2",
                (stats.max_hp, instance_ids["WEAPON"], instance_ids["ARMOR"],
                 instance_ids["ACCESSORY"], pet_instance_id, timestamp, timestamp,
                 guild_key, user_key),
            )
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            raise


async def _effective_stats_in_db(db, guild_id, user_id, *, context=None):
    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT maxHp,attack,defense,critBps,activeWeaponInstanceId,activeArmorInstanceId,"
        "activeAccessoryInstanceId,activePetInstanceId,currentHp FROM RpgProfile WHERE guildId=$1 AND userId=$2",
        (str(guild_id), str(user_id),
    )
    if not profile:
        return None, None
    active_ids = [profile[4], profile[5], profile[6]]
    equipped = []
    for instance_id in active_ids:
        if not instance_id:
            continue
        row = await db.fetchrow(
            "SELECT itemId,enhancementLevel FROM RpgEquipmentInstance WHERE equipmentInstanceId=$1 AND guildId=$2 AND ownerId=$3 AND status='OWNED'", instance_id, str(guild_id), str(user_id),
        )
        if row and row["itemId"] in EQUIPMENT:
            equipped.append({"definition": EQUIPMENT[row["itemId"]], "enhancement_level": row["enhancementLevel"]})
    pet_id = None
    if profile[7]:
        pet = await db.fetchrow(
            "SELECT petId,level FROM RpgPetInstance WHERE petInstanceId=$1 AND guildId=$2 AND ownerId=$3 AND status='OWNED'", profile[7], str(guild_id), str(user_id),
        )
        pet_id = pet[0] if pet else None
        pet_level = int(pet[1]) if pet else 1
    else:
        pet_level = 1
    stats = calculate_effective_stats(
        base_hp=profile[0], base_attack=profile[1], base_defense=profile[2],
        base_crit_bps=profile[3], equipped=equipped, active_pet_id=pet_id,
        active_pet_level=pet_level, context=context,
    )
    return stats, profile


async def get_effective_stats(db_path, guild_id, user_id, *, context=None):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        stats, _ = await _effective_stats_in_db(db, guild_id, user_id, context=context)
        return stats


async def get_active_loadout(db_path, guild_id, user_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        profile = await db.fetchrow(
            "SELECT activeWeaponInstanceId,activeArmorInstanceId,activeAccessoryInstanceId,activePetInstanceId "
            "FROM RpgProfile WHERE guildId=$1 AND userId=$2", str(guild_id), str(user_id),
        )
        if not profile:
            return {}
        result = {}
        for slot, instance_id in zip(("weapon", "armor", "accessory"), profile[:3]):
            if not instance_id:
                result[slot] = None
                continue
            row = await db.fetchrow(
                "SELECT itemId,enhancementLevel FROM RpgEquipmentInstance WHERE equipmentInstanceId=$1", instance_id,),
            )
            definition = EQUIPMENT.get(row[0], {}) if row else {}
            result[slot] = {"instance_id": instance_id, "name": definition.get("name", row[0] if row else "Unknown"),
                            "enhancement_level": int(row[1]) if row else 0}
        if profile[3]:
            pet = await db.fetchrow(
                "SELECT petId FROM RpgPetInstance WHERE petInstanceId=$1", (profile[3],),
            )
            result["pet"] = {"instance_id": profile[3], "name": PETS.get(pet[0], (pet[0])[0]} if pet else None
        else:
            result["pet"] = None
        return result


async def equip_instance(db_path, guild_id, user_id, equipment_instance_id, *, now=None):
    timestamp = utc_iso(now)
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            await assert_equipment_not_in_marketplace_escrow(db, guild_id, equipment_instance_id)
            item = await db.fetchrow(
                "SELECT itemId,slot,bindingStatus,status FROM RpgEquipmentInstance "
                "WHERE equipmentInstanceId=$1 AND guildId=$2 AND ownerId=$3", str(equipment_instance_id), str(guild_id), str(user_id),
            )
            profile = await db.fetchrow(
                "SELECT level FROM RpgProfile WHERE guildId=$1 AND userId=$2",
                (str(guild_id), str(user_id),
            )
            if not item or item["status"] != "OWNED" or not profile:
                raise ValueError("Equipment tidak ditemukan.")
            definition = EQUIPMENT.get(item["itemId"])
            if not definition or int(profile[0]) < definition["required_level"]:
                raise ValueError("Level belum memenuhi syarat equipment.")
            column = {"WEAPON": "activeWeaponInstanceId", "ARMOR": "activeArmorInstanceId", "ACCESSORY": "activeAccessoryInstanceId"}[item["slot"]]
            await db.execute(
                f"UPDATE RpgProfile SET {column}=$1,version=version+1,updatedAt=$2 WHERE guildId=$3 AND userId=$4", str(equipment_instance_id), timestamp, str(guild_id), str(user_id),
            )
            if item["bindingStatus"] == "BOUND_ON_EQUIP":
                await db.execute(
                    "UPDATE RpgEquipmentInstance SET bindingStatus='ACCOUNT_BOUND',updatedAt=$1 "
                    "WHERE equipmentInstanceId=$1 AND status='OWNED'", timestamp, str(equipment_instance_id),
                )
            stats, latest = await _effective_stats_in_db(db, guild_id, user_id)
            if int(latest[8]) > stats.max_hp:
                await db.execute(
                    "UPDATE RpgProfile SET currentHp=$1,version=version+1,updatedAt=$2 WHERE guildId=$3 AND userId=$4", stats.max_hp, timestamp, str(guild_id), str(user_id),
                )
            await db.commit()
            return stats
        except Exception:
            await db.rollback()
            raise
