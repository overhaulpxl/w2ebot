"""Helper inventory stack dan instance RPG."""

import aiosqlite

from .database import configure_connection


async def list_inventory(db_path, guild_id, user_id, *, category="all", limit=20, offset=0):
    category = str(category or "all").lower()
    if category not in ("all", "equipment", "materials", "consumables"):
        raise ValueError("Kategori inventory tidak valid.")
    limit = max(1, min(int(limit), 25))
    offset = max(0, int(offset))
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        equipment = []
        stacks = []
        if category in ("all", "equipment"):
            async with db.execute(
                "SELECT equipmentInstanceId,itemId,slot,enhancementLevel,bindingStatus,status,catalogVersion "
                "FROM RpgEquipmentInstance WHERE guildId=? AND ownerId=? ORDER BY createdAt,equipmentInstanceId LIMIT ? OFFSET ?",
                (str(guild_id), str(user_id), limit, offset),
            ) as cursor:
                equipment = [dict(row) for row in await cursor.fetchall()]
        if category in ("all", "materials", "consumables"):
            predicate = ""
            params = [str(guild_id), str(user_id)]
            if category == "materials":
                predicate = " AND (itemId LIKE 'mat_%' OR itemId LIKE 'bp_%')"
            elif category == "consumables":
                predicate = " AND (itemId LIKE 'item_%' OR itemId LIKE 'egg_%')"
            async with db.execute(
                "SELECT itemId,quantity FROM RpgInventoryStack WHERE guildId=? AND userId=? AND quantity>0" +
                predicate + " ORDER BY itemId LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ) as cursor:
                stacks = [dict(row) for row in await cursor.fetchall()]
    return {"equipment": equipment, "stacks": stacks}


async def inventory_quantity(db, guild_id, user_id, item_id):
    async with db.execute(
        "SELECT quantity FROM RpgInventoryStack WHERE guildId=? AND userId=? AND itemId=?",
        (str(guild_id), str(user_id), str(item_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def adjust_stack(db, guild_id, user_id, item_id, amount, now):
    if isinstance(amount, bool) or not isinstance(amount, int) or amount == 0:
        raise ValueError("Mutasi stack tidak valid.")
    await db.execute(
        "INSERT OR IGNORE INTO RpgInventoryStack "
        "(guildId,userId,itemId,quantity,version,createdAt,updatedAt) VALUES (?,?,?,0,0,?,?)",
        (str(guild_id), str(user_id), str(item_id), now, now),
    )
    cursor = await db.execute(
        "UPDATE RpgInventoryStack SET quantity=quantity+?,version=version+1,updatedAt=? "
        "WHERE guildId=? AND userId=? AND itemId=? AND quantity+?>=0",
        (amount, now, str(guild_id), str(user_id), str(item_id), amount),
    )
    if cursor.rowcount != 1:
        raise ValueError("Jumlah item tidak mencukupi.")
