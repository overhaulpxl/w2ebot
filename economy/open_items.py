"""Satu jalur authoritative untuk membuka Egg dan Epic Chest."""

import json
import secrets
import uuid


from .catalog import EQUIPMENT, PETS, PET_DUPLICATE_ESSENCE, RPG_PHASE3_CATALOG_VERSION
from .database import configure_connection
from .inventory import adjust_stack, inventory_quantity
from .operations import reserve_operation
from .time_policy import utc_iso


EGG_RARITY = {
    "egg_pet_common": "COMMON", "egg_pet_uncommon": "UNCOMMON",
    "egg_pet_rare": "RARE", "egg_pet_epic": "EPIC",
    "egg_pet_legendary": "LEGENDARY", "egg_pet_eternal": "ETERNAL",
}


async def reserve_open_item(db_path, *, guild_id, user_id, item_id, now=None):
    if item_id not in EGG_RARITY and item_id != "item_epic_chest":
        raise ValueError("Item ini tidak dapat dibuka.")
    async with _pool.acquire() as db:
        
        if await inventory_quantity(
            db, guild_id, user_id, item_id, catalog_version=RPG_PHASE3_CATALOG_VERSION,
        ) < 1:
            raise ValueError("Item tidak tersedia di inventory.")
        pending = await db.fetchrow(
            "SELECT operationId,status,outcomeJson FROM RpgOperation WHERE guildId=$1 AND userId=$2 "
            "AND operationType='OPEN_ITEM' AND sourceResourceId=? "
            "AND status IN ('RESERVED','AWAITING_FUNDS','REVIEW_REQUIRED')",
            (str(guild_id), str(user_id), str(item_id)),
        )
    if pending:
        return pending[0], json.loads(pending[2]), True
    if item_id == "item_epic_chest":
        choices = sorted(key for key, value in EQUIPMENT.items() if value["rarity"] == "EPIC")
        result_id = choices[secrets.randbelow(len(choices))]
        outcome = {"kind": "EQUIPMENT", "definition_id": result_id,
                   "catalog_version": RPG_PHASE3_CATALOG_VERSION,
                   "result_instance_id": str(uuid.uuid4())}
    else:
        rarity = EGG_RARITY[item_id]
        choices = sorted(key for key, value in PETS.items() if value[1] == rarity)
        result_id = choices[secrets.randbelow(len(choices))]
        outcome = {"kind": "PET", "definition_id": result_id, "rarity": rarity,
                   "catalog_version": RPG_PHASE3_CATALOG_VERSION,
                   "result_instance_id": str(uuid.uuid4())}
    operation_id, _, saved, replayed = await reserve_operation(
        db_path, guild_id=guild_id, user_id=user_id, operation_type="OPEN_ITEM",
        reservation_key=f"open:{guild_id}:{user_id}:{item_id}", source_resource_id=item_id,
        outcome=outcome, now=now,
    )
    if not replayed:
        async with _pool.acquire() as db:
            
            await db.execute(
                "INSERT INTO RpgOpenAttempt (operationId,itemId,resultDefinitionId) VALUES ($1,$2,$3)",
                (operation_id, str(item_id), result_id),
            )
            await db.commit()
    return operation_id, saved, replayed


async def settle_open_item(db_path, *, guild_id, user_id, operation_id, now=None):
    timestamp = utc_iso(now)
    async with _pool.acquire() as db:
        
        async with db.transaction():
        try:
            row = await db.fetchrow(
                "SELECT status,sourceResourceId,outcomeJson,resultJson FROM RpgOperation "
                "WHERE operationId=$1 AND guildId=$2 AND userId=$3 AND operationType='OPEN_ITEM'",
                (str(operation_id), str(guild_id), str(user_id)),
            )
            if not row:
                raise ValueError("Attempt open tidak ditemukan.")
            if row[0] == "COMMITTED":
                await db.rollback()
                return json.loads(row[3]), True
            if row[0] != "RESERVED":
                raise ValueError("Attempt open tidak dapat diselesaikan.")
            outcome = json.loads(row[2])
            await adjust_stack(
                db, guild_id, user_id, row[1], -1, timestamp,
                catalog_version=outcome["catalog_version"],
            )
            result = dict(outcome)
            if outcome["kind"] == "PET":
                duplicate = await db.fetchrow(
                    "SELECT petInstanceId FROM RpgPetInstance WHERE guildId=$1 AND ownerId=$2 AND petId=$3 AND status='OWNED' LIMIT 1",
                    (str(guild_id), str(user_id), outcome["definition_id"]),
                )
                if duplicate:
                    essence = PET_DUPLICATE_ESSENCE[outcome["rarity"]]
                    await adjust_stack(
                        db, guild_id, user_id, "mat_pet_essence", essence, timestamp,
                        catalog_version=outcome["catalog_version"],
                    )
                    result = {**result, "duplicate": True, "pet_essence": essence}
                else:
                    instance_id = str(outcome["result_instance_id"])
                    await db.execute(
                        "INSERT INTO RpgPetInstance "
                        "(petInstanceId,guildId,ownerId,petId,catalogVersion,rarity,level,xp,evolutionState,status,acquiredSource,createdAt,updatedAt) "
                        "VALUES ($1,$2,$3,$4,$5,$6,1,0,'BASE','OWNED','OPEN_ITEM',$1,$2)",
                        (instance_id, str(guild_id), str(user_id), outcome["definition_id"],
                         outcome["catalog_version"], outcome["rarity"], timestamp, timestamp),
                    )
                    result["pet_instance_id"] = instance_id
            else:
                definition = EQUIPMENT[outcome["definition_id"]]
                instance_id = str(outcome["result_instance_id"])
                await db.execute(
                    "INSERT INTO RpgEquipmentInstance "
                    "(equipmentInstanceId,guildId,ownerId,itemId,catalogVersion,slot,enhancementLevel,pityBps,bindingStatus,status,acquiredSource,createdAt,updatedAt) "
                    "VALUES ($3,$4,$5,$6,$7,$8,0,0,'BOUND_ON_EQUIP','OWNED','EPIC_CHEST',$1,$2)",
                    (instance_id, str(guild_id), str(user_id), definition["item_id"],
                     outcome["catalog_version"], definition["slot"], timestamp, timestamp),
                )
                result["equipment_instance_id"] = instance_id
            cursor = await db.execute(
                "UPDATE RpgOperation SET status='COMMITTED',reservationKey=NULL,resultJson=$1,updatedAt=$2,settledAt=$3 "
                "WHERE operationId=? AND status='RESERVED'",
                (json.dumps(result, sort_keys=True), timestamp, timestamp, str(operation_id)),
            )
            if cursor.rowcount != 1:
                raise ValueError("Attempt open sudah berubah.")
            await db.commit()
            return result, False
        except Exception:
            await db.rollback()
            raise
