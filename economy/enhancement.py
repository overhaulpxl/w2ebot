"""Reservasi dan settlement enhancement atomic."""

import secrets

import aiosqlite

from .catalog import (
    ENHANCEMENT_COST_BPS, ENHANCEMENT_MATERIALS, ENHANCEMENT_SUCCESS_BPS, EQUIPMENT,
)
from .constants import RPG_PHASE3_CATALOG_VERSION
from .database import configure_connection
from .equipment import assert_equipment_not_in_marketplace_escrow
from .inventory import adjust_stack, inventory_quantity
from .ledger import AccountDelta, EconomyMutationError, EconomyResult, execute_transaction
from .operations import reserve_operation


async def reserve_enhancement(db_path, *, guild_id, user_id, equipment_instance_id, now=None):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await assert_equipment_not_in_marketplace_escrow(db, guild_id, equipment_instance_id)
        item = await db.fetchrow(
            "SELECT itemId,enhancementLevel,pityBps,status FROM RpgEquipmentInstance "
            "WHERE equipmentInstanceId=$1 AND guildId=$2 AND ownerId=$3", str(equipment_instance_id), str(guild_id), str(user_id),
        )
        if not item or item[3] != "OWNED" or item[0] not in EQUIPMENT:
            return EconomyResult(False, "not_found", "Equipment tidak ditemukan.")
        target = int(item[1]) + 1
        if target > 15:
            return EconomyResult(False, "max_enhancement", "Equipment sudah mencapai +15.")
        cost = EQUIPMENT[item[0]]["base_value"] * ENHANCEMENT_COST_BPS[target] // 10_000
        material = ENHANCEMENT_MATERIALS.get(target)
        wallet = await db.fetchrow(
            "SELECT etmBalance FROM EconomyWallet WHERE guildId=$1 AND userId=$2", str(guild_id), str(user_id),
        )
        if not wallet or int(wallet[0]) < cost:
            return EconomyResult(False, "insufficient_balance", "Saldo ETM tidak mencukupi.")
        if material and await inventory_quantity(
            db, guild_id, user_id, material[0], catalog_version=RPG_PHASE3_CATALOG_VERSION,
        ) < material[1]:
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
                "INSERT INTO RpgEnhancementAttempt (operationId,equipmentInstanceId,targetLevel,successRoll) VALUES ($1,$2,$3,$4)", operation_id, str(equipment_instance_id), target, roll),
            )
            await db.commit()
    return operation_id, saved, replayed


async def settle_enhancement(db_path, *, guild_id, user_id, operation_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        row = await db.fetchrow(
            "SELECT sourceResourceId,outcomeJson,status FROM RpgOperation WHERE operationId=$1 AND guildId=$2 AND userId=$3", str(operation_id), str(guild_id), str(user_id),
        )
    if not row:
        return EconomyResult(False, "not_found", "Attempt enhancement tidak ditemukan.")
    import json
    outcome = json.loads(row[1])
    cost = int(outcome["cost"])
    general = cost * 80 // 100
    reserve = cost * 10 // 100
    burn = cost - general - reserve

    async def extension(db, context):
        await assert_equipment_not_in_marketplace_escrow(db, guild_id, row[0])
        operation = await db.fetchrow(
            "SELECT status,sourceResourceId,outcomeJson FROM RpgOperation WHERE operationId=$1",
            (str(operation_id),),
        )
        if not operation or operation[0] != "RESERVED":
            raise EconomyMutationError("stale", "Attempt enhancement sudah diproses.")
        item = await db.fetchrow(
            "SELECT itemId,enhancementLevel,pityBps,status FROM RpgEquipmentInstance "
            "WHERE equipmentInstanceId=$1 AND guildId=$2 AND ownerId=$3",
            (operation[1], str(guild_id), str(user_id),
        )
        if not item or item[3] != "OWNED" or int(item[1]) + 1 != int(outcome["target_level"]):
            raise EconomyMutationError("stale", "Status equipment sudah berubah.")
        success = int(outcome["roll"]) < min(10_000, ENHANCEMENT_SUCCESS_BPS[int(outcome["target_level"])] + int(item[2]))
        material = outcome.get("material")
        if material:
            required = int(material[1])
            consumed = required if success else required - required // 2
            try:
                await adjust_stack(
                    db, guild_id, user_id, material[0], -consumed, context.now,
                    catalog_version=outcome["catalog_version"],
                )
            except ValueError as exc:
                raise EconomyMutationError("insufficient_material", str(exc)) from exc
        next_level = int(outcome["target_level"]) if success else int(item[1])
        next_pity = 0 if success else min(2000, int(item[2]) + 500)
        cursor = await db.execute(
            "UPDATE RpgEquipmentInstance SET enhancementLevel=$1,pityBps=$2,updatedAt=$3 "
            "WHERE equipmentInstanceId=$1 AND guildId=$2 AND ownerId=$3 AND status='OWNED'", next_level, next_pity, context.now, operation[1], str(guild_id), str(user_id),
        )
        if cursor.rowcount != 1:
            raise EconomyMutationError("stale", "Equipment berubah saat enhancement diproses.")
        result = {"success": success, "enhancement_level": next_level, "pity_bps": next_pity}
        await db.execute(
            "UPDATE RpgOperation SET status='COMMITTED',reservationKey=NULL,resultJson=$1,transactionId=$2,updatedAt=$3,settledAt=$4 "
            "WHERE operationId=$1 AND status='RESERVED'", json.dumps(result, sort_keys=True), context.transaction_id, context.now, context.now, str(operation_id),
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
