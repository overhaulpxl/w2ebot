"""Kepemilikan, aktivasi, dan XP pet."""

import aiosqlite

from .catalog import PETS
from .database import configure_connection
from .equipment import _effective_stats_in_db
from .time_policy import utc_iso
from .xp import apply_pet_xp


async def list_pets(db_path, guild_id, user_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT activePetInstanceId FROM RpgProfile WHERE guildId=? AND userId=?",
            (str(guild_id), str(user_id)),
        ) as cursor:
            active = await cursor.fetchone()
        async with db.execute(
            "SELECT petInstanceId,petId,rarity,level,xp,evolutionState,status,catalogVersion "
            "FROM RpgPetInstance WHERE guildId=? AND ownerId=? ORDER BY rarity,createdAt",
            (str(guild_id), str(user_id)),
        ) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]
    active_id = active[0] if active else None
    for row in rows:
        definition = PETS.get(row["petId"])
        row["name"] = definition[0] if definition else row["petId"]
        row["passive"] = definition[3] if definition else {}
        row["skill"] = definition[4] if definition else "-"
        row["active"] = row["petInstanceId"] == active_id
    return rows


async def activate_pet(db_path, guild_id, user_id, pet_instance_id, *, now=None):
    timestamp = utc_iso(now)
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                "SELECT petId,status,catalogVersion FROM RpgPetInstance WHERE petInstanceId=? AND guildId=? AND ownerId=?",
                (str(pet_instance_id), str(guild_id), str(user_id)),
            ) as cursor:
                pet = await cursor.fetchone()
            async with db.execute(
                "SELECT level FROM RpgProfile WHERE guildId=? AND userId=?",
                (str(guild_id), str(user_id)),
            ) as cursor:
                profile = await cursor.fetchone()
            if not pet or pet["status"] != "OWNED" or not profile or pet["petId"] not in PETS:
                raise ValueError("Pet tidak ditemukan.")
            if int(profile[0]) < PETS[pet["petId"]][2]:
                raise ValueError("Level belum memenuhi syarat pet.")
            await db.execute(
                "UPDATE RpgProfile SET activePetInstanceId=?,version=version+1,updatedAt=? WHERE guildId=? AND userId=?",
                (str(pet_instance_id), timestamp, str(guild_id), str(user_id)),
            )
            stats, latest = await _effective_stats_in_db(db, guild_id, user_id)
            if int(latest[8]) > stats.max_hp:
                await db.execute(
                    "UPDATE RpgProfile SET currentHp=?,version=version+1,updatedAt=? WHERE guildId=? AND userId=?",
                    (stats.max_hp, timestamp, str(guild_id), str(user_id)),
                )
            await db.commit()
            return stats
        except Exception:
            await db.rollback()
            raise


async def grant_pet_xp_in_transaction(db, *, guild_id, user_id, pet_instance_id, amount, now):
    if not pet_instance_id or amount <= 0:
        return False
    async with db.execute(
        "SELECT level,xp,status FROM RpgPetInstance WHERE petInstanceId=? AND guildId=? AND ownerId=?",
        (str(pet_instance_id), str(guild_id), str(user_id)),
    ) as cursor:
        pet = await cursor.fetchone()
    if not pet or pet[2] != "OWNED":
        raise ValueError("Snapshot pet reward tidak lagi valid.")
    level, xp = apply_pet_xp(pet[0], pet[1], amount)
    cursor = await db.execute(
        "UPDATE RpgPetInstance SET level=?,xp=?,updatedAt=? WHERE petInstanceId=? AND guildId=? AND ownerId=? AND status='OWNED'",
        (level, xp, now, str(pet_instance_id), str(guild_id), str(user_id)),
    )
    if cursor.rowcount != 1:
        raise ValueError("Pet reward berubah saat settlement.")
    return True
