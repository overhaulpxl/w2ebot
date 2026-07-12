"""Crafting equipment satu tingkat rarity secara atomic."""

import json
import uuid

import aiosqlite

from .catalog import CRAFT_RECIPES, EQUIPMENT, RARITIES, RPG_PHASE3_CATALOG_VERSION
from .database import configure_connection
from .inventory import adjust_stack, inventory_quantity
from .ledger import AccountDelta, EconomyMutationError, EconomyResult, execute_transaction
from .operations import reserve_operation


BLUEPRINTS = {"WEAPON": "bp_eternal_weapon", "ARMOR": "bp_eternal_armor", "ACCESSORY": "bp_eternal_accessory"}


async def reserve_craft(db_path, *, guild_id, user_id, base_equipment_instance_id, now=None):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT itemId,slot,status FROM RpgEquipmentInstance WHERE equipmentInstanceId=? AND guildId=? AND ownerId=?",
            (str(base_equipment_instance_id), str(guild_id), str(user_id)),
        ) as cursor:
            base = await cursor.fetchone()
        if not base or base[2] != "OWNED" or base[0] not in EQUIPMENT:
            raise ValueError("Base equipment tidak ditemukan.")
        source_rarity = EQUIPMENT[base[0]]["rarity"]
        index = RARITIES.index(source_rarity)
        if index >= len(RARITIES) - 1:
            raise ValueError("Eternal equipment tidak dapat di-craft lagi.")
        target_rarity = RARITIES[index + 1]
        candidates = sorted(key for key, row in EQUIPMENT.items() if row["rarity"] == target_rarity and row["slot"] == base[1])
        target_item_id = candidates[0]
        cost, materials = CRAFT_RECIPES[target_rarity]["cost"], CRAFT_RECIPES[target_rarity]["materials"]
        async with db.execute(
            "SELECT etmBalance FROM EconomyWallet WHERE guildId=? AND userId=?",
            (str(guild_id), str(user_id)),
        ) as cursor:
            wallet = await cursor.fetchone()
        if not wallet or int(wallet[0]) < cost:
            raise ValueError("Saldo ETM tidak mencukupi.")
        for item_id, amount in materials.items():
            if await inventory_quantity(db, guild_id, user_id, item_id) < amount:
                raise ValueError("Material crafting tidak mencukupi.")
        blueprint = BLUEPRINTS[base[1]] if target_rarity == "ETERNAL" else None
        if blueprint and await inventory_quantity(db, guild_id, user_id, blueprint) < 1:
            raise ValueError("Blueprint slot yang sesuai tidak tersedia.")
    outcome = {"target_item_id": target_item_id, "target_rarity": target_rarity,
               "cost": cost, "materials": materials, "blueprint": blueprint,
               "catalog_version": RPG_PHASE3_CATALOG_VERSION,
               "result_instance_id": str(uuid.uuid4())}
    operation_id, _, saved, replayed = await reserve_operation(
        db_path, guild_id=guild_id, user_id=user_id, operation_type="CRAFT",
        reservation_key=f"craft:{guild_id}:{base_equipment_instance_id}",
        source_resource_id=base_equipment_instance_id, outcome=outcome, now=now,
    )
    if not replayed:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute(
                "INSERT INTO RpgCraftAttempt (operationId,targetItemId,baseEquipmentInstanceId,blueprintItemId) VALUES (?,?,?,?)",
                (operation_id, target_item_id, str(base_equipment_instance_id), blueprint),
            )
            await db.commit()
    return operation_id, saved, replayed


async def settle_craft(db_path, *, guild_id, user_id, operation_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT sourceResourceId,outcomeJson FROM RpgOperation WHERE operationId=? AND guildId=? AND userId=?",
            (str(operation_id), str(guild_id), str(user_id)),
        ) as cursor:
            operation = await cursor.fetchone()
    if not operation:
        return EconomyResult(False, "not_found", "Attempt crafting tidak ditemukan.")
    outcome = json.loads(operation[1])
    cost = int(outcome["cost"])
    general, reserve = cost * 80 // 100, cost * 10 // 100
    burn = cost - general - reserve

    async def extension(db, context):
        async with db.execute(
            "SELECT status,sourceResourceId FROM RpgOperation WHERE operationId=?", (operation_id,),
        ) as cursor:
            latest = await cursor.fetchone()
        if not latest or latest[0] != "RESERVED":
            raise EconomyMutationError("stale", "Attempt crafting sudah diproses.")
        async with db.execute(
            "SELECT status FROM RpgEquipmentInstance WHERE equipmentInstanceId=? AND guildId=? AND ownerId=?",
            (latest[1], str(guild_id), str(user_id)),
        ) as cursor:
            base = await cursor.fetchone()
        if not base or base[0] != "OWNED":
            raise EconomyMutationError("stale", "Base equipment sudah berubah.")
        try:
            for item_id, amount in outcome["materials"].items():
                await adjust_stack(db, guild_id, user_id, item_id, -int(amount), context.now)
            if outcome.get("blueprint"):
                await adjust_stack(db, guild_id, user_id, outcome["blueprint"], -1, context.now)
        except ValueError as exc:
            raise EconomyMutationError("insufficient_material", str(exc)) from exc
        await db.execute(
            "UPDATE RpgEquipmentInstance SET status='CONSUMED',updatedAt=? WHERE equipmentInstanceId=? AND status='OWNED'",
            (context.now, latest[1]),
        )
        definition = EQUIPMENT[outcome["target_item_id"]]
        instance_id = str(outcome["result_instance_id"])
        binding = "ACCOUNT_BOUND" if definition["rarity"] == "ETERNAL" else "BOUND_ON_EQUIP"
        await db.execute(
            "INSERT INTO RpgEquipmentInstance "
            "(equipmentInstanceId,guildId,ownerId,itemId,catalogVersion,slot,enhancementLevel,pityBps,bindingStatus,status,acquiredSource,createdAt,updatedAt) "
            "VALUES (?,?,?,?,?,?,0,0,?,'OWNED','CRAFT',?,?)",
            (instance_id, str(guild_id), str(user_id), definition["item_id"],
             RPG_PHASE3_CATALOG_VERSION, definition["slot"], binding, context.now, context.now),
        )
        result = {"equipment_instance_id": instance_id, "item_id": definition["item_id"]}
        await db.execute(
            "UPDATE RpgOperation SET status='COMMITTED',reservationKey=NULL,resultJson=?,transactionId=?,updatedAt=?,settledAt=? "
            "WHERE operationId=? AND status='RESERVED'",
            (json.dumps(result, sort_keys=True), context.transaction_id, context.now, context.now, operation_id),
        )
        return result

    return await execute_transaction(
        db_path, guild_id=guild_id, idempotency_key=f"craft:{operation_id}",
        operation="RPG_CRAFT", source="RPG_CRAFT", actor_id=user_id,
        reason="equipment crafting", reason_code="rpg_craft", reference_id=operation_id,
        deltas=(AccountDelta("USER", str(user_id), "ETM", -cost, str(user_id)),
                AccountDelta("SYSTEM", "ETM_GENERAL", "ETM", general),
                AccountDelta("SYSTEM", "ETM_RESERVE", "ETM", reserve),
                AccountDelta("SYSTEM", "ETM_BURN", "ETM", burn)),
        before_commit=extension, feature="rpg", success_code="craft_settled",
        success_message="Crafting berhasil diselesaikan.",
    )
