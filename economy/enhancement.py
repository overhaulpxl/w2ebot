"""Reservasi dan settlement enhancement atomic."""

import secrets

import aiosqlite

from .catalog import (
    ENHANCEMENT_COST_BPS, ENHANCEMENT_MATERIALS, ENHANCEMENT_SUCCESS_BPS, EQUIPMENT,
)
from .constants import RPG_PHASE3_CATALOG_VERSION
from .database import configure_connection
from .inventory import adjust_stack, inventory_quantity
from .ledger import AccountDelta, EconomyMutationError, EconomyResult, execute_transaction
from .operations import reserve_operation


async def reserve_enhancement(db_path, *, guild_id, user_id, equipment_instance_id, now=None):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT itemId,enhancementLevel,pityBps,status FROM RpgEquipmentInstance "
            "WHERE equipmentInstanceId=? AND guildId=? AND ownerId=?",
            (str(equipment_instance_id), str(guild_id), str(user_id)),
        ) as cursor:
            item = await cursor.fetchone()
        if not item or item[3] != "OWNED" or item[0] not in EQUIPMENT:
            return EconomyResult(False, "not_found", "Equipment tidak ditemukan.")
        target = int(item[1]) + 1
        if target > 15:
            return EconomyResult(False, "max_enhancement", "Equipment sudah mencapai +15.")
        cost = EQUIPMENT[item[0]]["base_value"] * ENHANCEMENT_COST_BPS[target] // 10_000
        material = ENHANCEMENT_MATERIALS.get(target)
        async with db.execute(
            "SELECT etmBalance FROM EconomyWallet WHERE guildId=? AND userId=?",
            (str(guild_id), str(user_id)),
        ) as cursor:
            wallet = await cursor.fetchone()
        if not wallet or int(wallet[0]) < cost:
            return EconomyResult(False, "insufficient_balance", "Saldo ETM tidak mencukupi.")
        if material and await inventory_quantity(db, guild_id, user_id, material[0]) < material[1]:
            return EconomyResult(False, "insufficient_material", "Material enhancement tidak mencukupi.")
    roll = secrets.randbelow(10_000)
    outcome = {"target_level": target, "roll": roll, "cost": cost, "material": material,
               "catalog_version": RPG_PHASE3_CATALOG_VERSION}
    operation_id, status, saved, replayed = await reserve_operation(
        db_path, guild_id=guild_id, user_id=user_id, operation_type="ENHANCEMENT",
        reservation_key=f"enhance:{guild_id}:{equipment_instance_id}",
        source_resource_id=equipment_instance_id, outcome=outcome, now=now,
    )
    if not replayed:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute(
                "INSERT INTO RpgEnhancementAttempt (operationId,equipmentInstanceId,targetLevel,successRoll) VALUES (?,?,?,?)",
                (operation_id, str(equipment_instance_id), target, roll),
            )
            await db.commit()
    return operation_id, saved, replayed


async def settle_enhancement(db_path, *, guild_id, user_id, operation_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT sourceResourceId,outcomeJson,status FROM RpgOperation WHERE operationId=? AND guildId=? AND userId=?",
            (str(operation_id), str(guild_id), str(user_id)),
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return EconomyResult(False, "not_found", "Attempt enhancement tidak ditemukan.")
    import json
    outcome = json.loads(row[1])
    cost = int(outcome["cost"])
    general = cost * 80 // 100
    reserve = cost * 10 // 100
    burn = cost - general - reserve

    async def extension(db, context):
        async with db.execute(
            "SELECT status,sourceResourceId,outcomeJson FROM RpgOperation WHERE operationId=?",
            (str(operation_id),),
        ) as cursor:
            operation = await cursor.fetchone()
        if not operation or operation[0] != "RESERVED":
            raise EconomyMutationError("stale", "Attempt enhancement sudah diproses.")
        async with db.execute(
            "SELECT itemId,enhancementLevel,pityBps,status FROM RpgEquipmentInstance "
            "WHERE equipmentInstanceId=? AND guildId=? AND ownerId=?",
            (operation[1], str(guild_id), str(user_id)),
        ) as cursor:
            item = await cursor.fetchone()
        if not item or item[3] != "OWNED" or int(item[1]) + 1 != int(outcome["target_level"]):
            raise EconomyMutationError("stale", "Status equipment sudah berubah.")
        success = int(outcome["roll"]) < min(10_000, ENHANCEMENT_SUCCESS_BPS[int(outcome["target_level"])] + int(item[2]))
        material = outcome.get("material")
        if material:
            required = int(material[1])
            consumed = required if success else required - required // 2
            try:
                await adjust_stack(db, guild_id, user_id, material[0], -consumed, context.now)
            except ValueError as exc:
                raise EconomyMutationError("insufficient_material", str(exc)) from exc
        next_level = int(outcome["target_level"]) if success else int(item[1])
        next_pity = 0 if success else min(2000, int(item[2]) + 500)
        await db.execute(
            "UPDATE RpgEquipmentInstance SET enhancementLevel=?,pityBps=?,updatedAt=? WHERE equipmentInstanceId=?",
            (next_level, next_pity, context.now, operation[1]),
        )
        result = {"success": success, "enhancement_level": next_level, "pity_bps": next_pity}
        await db.execute(
            "UPDATE RpgOperation SET status='COMMITTED',reservationKey=NULL,resultJson=?,transactionId=?,updatedAt=?,settledAt=? "
            "WHERE operationId=? AND status='RESERVED'",
            (json.dumps(result, sort_keys=True), context.transaction_id, context.now, context.now, str(operation_id)),
        )
        return result

    return await execute_transaction(
        db_path, guild_id=guild_id, idempotency_key=f"enhancement:{operation_id}",
        operation="RPG_ENHANCEMENT", source="RPG_ENHANCEMENT", actor_id=user_id,
        reason="equipment enhancement", reason_code="rpg_enhancement", reference_id=operation_id,
        deltas=(
            AccountDelta("USER", str(user_id), "ETM", -cost, str(user_id)),
            AccountDelta("SYSTEM", "ETM_GENERAL", "ETM", general),
            AccountDelta("SYSTEM", "ETM_RESERVE", "ETM", reserve),
            AccountDelta("SYSTEM", "ETM_BURN", "ETM", burn),
        ), before_commit=extension, feature="rpg", success_code="enhancement_settled",
        success_message="Enhancement berhasil diproses.",
    )
