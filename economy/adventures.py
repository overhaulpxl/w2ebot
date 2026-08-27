"""Hunt dan Dungeon dengan outcome persisted dan settlement atomic."""

import json
import secrets
import uuid

import aiosqlite

from .activity import append_activity_event
from .catalog import DUNGEON_DROPS, DUNGEONS, EQUIPMENT, HUNT_DROPS, HUNTS, RPG_PHASE3_CATALOG_VERSION, roll_drops
from .database import configure_connection
from .inventory import adjust_stack, inventory_quantity
from .ledger import AccountDelta, EconomyMutationError, EconomyResult, execute_transaction
from .operations import reserve_operation
from .pets import grant_pet_xp_in_transaction
from .profile import materialize_energy
from .time_policy import utc_iso
from .xp import apply_player_xp


def _random_between(bounds):
    return int(bounds[0]) + secrets.randbelow(int(bounds[1]) - int(bounds[0]) + 1)


async def _profile_preflight(db, guild_id, user_id):
    fund = await db.fetchrow(
        "SELECT level,energy,activePetInstanceId FROM RpgProfile WHERE guildId=$1 AND userId=$2", str(guild_id), str(user_id),
        return await cursor.fetchone()


async def reserve_hunt(db_path, *, guild_id, user_id, area_id, now=None):
    if area_id not in HUNTS:
        raise ValueError("Area Hunt tidak valid.")
    await materialize_energy(db_path, guild_id, user_id, now=now)
    definition = HUNTS[area_id]
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        profile = await _profile_preflight(db, guild_id, user_id)
        if not profile or int(profile[0]) < definition[1]:
            raise ValueError("Level belum memenuhi syarat Hunt.")
        if int(profile[1]) < definition[2]:
            raise ValueError("Energy tidak mencukupi.")
    xp = _random_between(definition[4])
    drops = roll_drops(HUNT_DROPS[area_id])
    outcome = {"catalog_version": RPG_PHASE3_CATALOG_VERSION,
               "area_id": area_id, "energy": definition[2], "etm": _random_between(definition[3]),
               "xp": xp, "pet_xp": max(1, xp // 2), "pet_instance_id": profile[2],
               "drops": drops,
               "equipment_instance_id": str(uuid.uuid4()) if drops.get("equipment") else None}
    operation_id, _, saved, replayed = await reserve_operation(
        db_path, guild_id=guild_id, user_id=user_id, operation_type="HUNT",
        reservation_key=f"hunt:{guild_id}:{user_id}", source_resource_id=area_id,
        outcome=outcome, now=now,
    )
    if not replayed:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute(
                "INSERT INTO RpgHuntRun (operationId,areaId,playerXp,activePetInstanceId) VALUES ($1,$2,$3,$4)", operation_id, area_id, xp, profile[2]),
            )
            await db.commit()
    return operation_id, saved, replayed


async def settle_hunt(db_path, *, guild_id, user_id, operation_id):
    return await _settle_adventure(db_path, guild_id=guild_id, user_id=user_id,
                                   operation_id=operation_id, kind="HUNT")


async def reserve_dungeon(db_path, *, guild_id, user_id, dungeon_id, use_ticket=False, now=None):
    if dungeon_id not in DUNGEONS:
        raise ValueError("Dungeon tidak valid.")
    definition = DUNGEONS[dungeon_id]
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        profile = await _profile_preflight(db, guild_id, user_id)
        if not profile or int(profile[0]) < definition[1]:
            raise ValueError("Level belum memenuhi syarat Dungeon.")
        async with db.execute(
            "SELECT balance FROM EconomySystemAccount WHERE guildId=$1 AND accountCode='ETM_BOSS_DUNGEON'",
            (str(guild_id),),
        )
        reward = _random_between(definition[3])
        if not fund or int(fund[0]) < reward:
            raise ValueError("Fund Boss dan Dungeon belum mencukupi.")
        if use_ticket:
            if await inventory_quantity(
                db, guild_id, user_id, "item_dungeon_ticket",
                catalog_version=RPG_PHASE3_CATALOG_VERSION,
            ) < 1:
                raise ValueError("Dungeon Ticket tidak tersedia.")
        else:
            wallet = await db.fetchrow(
                "SELECT etmBalance FROM EconomyWallet WHERE guildId=$1 AND userId=$2", str(guild_id), str(user_id),
            )
            if not wallet or int(wallet[0]) < definition[2]:
                raise ValueError("Saldo ETM tidak mencukupi.")
    xp = _random_between(definition[4])
    drops = roll_drops(DUNGEON_DROPS[dungeon_id])
    outcome = {"catalog_version": RPG_PHASE3_CATALOG_VERSION,
               "dungeon_id": dungeon_id, "entry_method": "TICKET" if use_ticket else "ETM",
               "entry_cost": 0 if use_ticket else definition[2], "etm": reward, "xp": xp,
               "pet_xp": xp // 2, "pet_instance_id": profile[2],
               "drops": drops,
               "equipment_instance_id": str(uuid.uuid4() if drops.get("equipment") else None}
    operation_id, _, saved, replayed = await reserve_operation(
        db_path, guild_id=guild_id, user_id=user_id, operation_type="DUNGEON",
        reservation_key=f"dungeon:{guild_id}:{user_id}", source_resource_id=dungeon_id,
        outcome=outcome, now=now,
    )
    if not replayed:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute(
                "INSERT INTO RpgDungeonRun (operationId,dungeonId,playerXp,activePetInstanceId,entryMethod) VALUES ($1,$2,$3,$4,$5)", operation_id, dungeon_id, xp, profile[2], outcome["entry_method"]),
            )
            await db.commit()
    return operation_id, saved, replayed


async def settle_dungeon(db_path, *, guild_id, user_id, operation_id):
    return await _settle_adventure(db_path, guild_id=guild_id, user_id=user_id,
                                   operation_id=operation_id, kind="DUNGEON")


async def _settle_adventure(db_path, *, guild_id, user_id, operation_id, kind):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        operation = await db.fetchrow(
            "SELECT outcomeJson,status FROM RpgOperation WHERE operationId=$1 AND guildId=$2 AND userId=$3 AND operationType=$4", str(operation_id), str(guild_id), str(user_id), kind),
        )
    if not operation:
        return EconomyResult(False, "not_found", "Operation tidak ditemukan.")
    outcome = json.loads(operation[0])
    reward = int(outcome["etm"])
    entry = int(outcome.get("entry_cost", 0)
    if kind == "HUNT":
        deltas = (AccountDelta("SYSTEM", "ETM_ISSUANCE", "ETM", -reward),
                  AccountDelta("USER", str(user_id), "ETM", reward, str(user_id))
    else:
        deltas = (AccountDelta("SYSTEM", "ETM_BOSS_DUNGEON", "ETM", entry - reward),
                  AccountDelta("USER", str(user_id), "ETM", reward - entry, str(user_id)))

    async def extension(db, context):
        latest = await db.fetchrow(
            "SELECT status,outcomeJson FROM RpgOperation WHERE operationId=$1", str(operation_id),),
        )
        if not latest or latest[0] != "RESERVED":
            raise EconomyMutationError("stale", "Operation sudah diproses.")
        profile = await db.fetchrow(
            "SELECT level,xp,energy FROM RpgProfile WHERE guildId=$1 AND userId=$2",
            (str(guild_id), str(user_id),
        )
        if not profile:
            raise EconomyMutationError("not_found", "Profile RPG tidak ditemukan.")
        energy_cost = int(outcome.get("energy", 0))
        if int(profile[2]) < energy_cost:
            raise EconomyMutationError("insufficient_energy", "Energy tidak mencukupi.")
        level, xp, discarded = apply_player_xp(profile[0], profile[1], int(outcome["xp"]))
        await db.execute(
            "UPDATE RpgProfile SET level=$1,xp=$2,energyUpdatedAt=CASE WHEN energy=100 THEN $3 ELSE energyUpdatedAt END,"
            "energy=energy-$1,version=version+1,updatedAt=$2 "
            "WHERE guildId=$1 AND userId=$2 AND energy>=$3", level, xp, context.now, energy_cost, context.now, str(guild_id), str(user_id), energy_cost),
        )
        if kind == "DUNGEON" and outcome["entry_method"] == "TICKET":
            try:
                await adjust_stack(
                    db, guild_id, user_id, "item_dungeon_ticket", -1, context.now,
                    catalog_version=outcome["catalog_version"],
                )
            except ValueError as exc:
                raise EconomyMutationError("missing_ticket", str(exc) from exc
        drops = outcome.get("drops", {})
        stack_drops = list(drops.get("stacks", ()))
        stack_drops.extend(item_id for item_id in (drops.get("material"), drops.get("egg")) if item_id)
        for item_id in stack_drops:
            if item_id:
                await adjust_stack(
                    db, guild_id, user_id, item_id, 1, context.now,
                    catalog_version=outcome["catalog_version"],
                )
        if drops.get("equipment"):
            definition = EQUIPMENT[drops["equipment"]]
            await db.execute(
                "INSERT INTO RpgEquipmentInstance "
                "(equipmentInstanceId,guildId,ownerId,itemId,catalogVersion,slot,enhancementLevel,pityBps,bindingStatus,status,acquiredSource,createdAt,updatedAt) "
                "VALUES ($1,$2,$3,$4,$5,$6,0,0,'BOUND_ON_EQUIP','OWNED',$7,$8,$9)", str(outcome["equipment_instance_id"]), str(guild_id), str(user_id), definition["item_id"],
                 outcome["catalog_version"], definition["slot"], kind, context.now, context.now),
            )
        try:
            await grant_pet_xp_in_transaction(
                db, guild_id=guild_id, user_id=user_id,
                pet_instance_id=outcome.get("pet_instance_id"), amount=int(outcome["pet_xp"]), now=context.now,
            )
        except ValueError as exc:
            raise EconomyMutationError("pet_snapshot_invalid", str(exc) from exc
        event_type = "HUNT_COMPLETED" if kind == "HUNT" else "DUNGEON_COMPLETED"
        await append_activity_event(
            db, guild_id=guild_id, user_id=user_id, event_type=event_type,
            event_key=f"{kind.lower()}:{operation_id}", points=0 if kind == "HUNT" else 3,
            metric_value=1, occurred_at=context.now, transaction_id=context.transaction_id,
            reference_id=operation_id,
        )
        result = {"etm": reward, "xp": outcome["xp"], "xp_discarded_at_cap": discarded,
                  "drops": drops}
        await db.execute(
            "UPDATE RpgOperation SET status='COMMITTED',reservationKey=NULL,resultJson=$1,transactionId=$2,updatedAt=$3,settledAt=$4 "
            "WHERE operationId=$1 AND status='RESERVED'", json.dumps(result, sort_keys=True), context.transaction_id, context.now, context.now, operation_id),
        )
        return result

    result = await execute_transaction(
        db_path, guild_id=guild_id, idempotency_key=f"rpg:{kind.lower()}:{operation_id}",
        operation=f"RPG_{kind}", source=f"RPG_{kind}", actor_id=user_id,
        reason=f"{kind.lower()} reward", reason_code=f"rpg_{kind.lower()}", reference_id=operation_id,
        deltas=deltas, before_commit=extension, feature="rpg",
        require_spendable_system_debits=kind == "DUNGEON",
        success_code=f"{kind.lower()}_settled", success_message=f"{kind.title()} berhasil diselesaikan.",
    )
    if result.code == "pet_snapshot_invalid":
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute(
                "UPDATE RpgOperation SET status='REVIEW_REQUIRED',lastErrorCode='pet_snapshot_invalid',"
                "recoveryReviewJson=$1,updatedAt=$2 "
                "WHERE operationId=$1 AND status='RESERVED'",
                (json.dumps({"code": "pet_snapshot_invalid"}), utc_iso(), str(operation_id),
            )
            await db.commit()
    return result
