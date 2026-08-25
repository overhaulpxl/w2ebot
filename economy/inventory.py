"""Helper inventory stack dan instance RPG."""


from .database import configure_connection
from .constants import RPG_PHASE3_CATALOG_VERSION


async def stack_schema_is_phase4(db):
    row = await db.fetchrow("PRAGMA table_info(RpgInventoryStack)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}
    return {"catalogVersion", "bindingStatus", "status"}.issubset(columns)


async def list_inventory(db_path, guild_id, user_id, *, category="all", limit=20, offset=0):
    category = str(category or "all").lower()
    if category not in ("all", "equipment", "materials", "consumables"):
        raise ValueError("Kategori inventory tidak valid.")
    limit = max(1, min(int(limit), 25))
    offset = max(0, int(offset))
    async with _pool.acquire() as db:
        
        db.row_factory = aiosqlite.Row
        equipment = []
        stacks = []
        if category in ("all", "equipment"):
            async with db.execute(
                "SELECT equipmentInstanceId,itemId,slot,enhancementLevel,bindingStatus,status,catalogVersion "
                "FROM RpgEquipmentInstance WHERE guildId=$1 AND ownerId=$2 ORDER BY createdAt,equipmentInstanceId LIMIT $3 OFFSET $4",
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
            if await stack_schema_is_phase4(db):
                select = "SELECT itemId,catalogVersion,bindingStatus,status,quantity FROM RpgInventoryStack"
            else:
                select = "SELECT itemId,quantity FROM RpgInventoryStack"
            async with db.execute(
                select + " WHERE guildId=$1 AND userId=$2 AND quantity>0" + predicate +
                " ORDER BY itemId LIMIT $3 OFFSET $4", (*params, limit, offset),
            ) as cursor:
                stacks = [dict(row) for row in await cursor.fetchall()]
    return {"equipment": equipment, "stacks": stacks}


async def inventory_quantity(db, guild_id, user_id, item_id, *, catalog_version=None,
                             binding_status="UNBOUND"):
    if await stack_schema_is_phase4(db):
        catalog_version = str(catalog_version or RPG_PHASE3_CATALOG_VERSION)
        sql = ("SELECT quantity FROM RpgInventoryStack WHERE guildId=$1 AND userId=$2 AND itemId=$3 "
               "AND catalogVersion=$5 AND bindingStatus=$6 AND status='ACTIVE'")
        params = (str(guild_id), str(user_id), str(item_id), catalog_version, str(binding_status))
    else:
        sql = "SELECT quantity FROM RpgInventoryStack WHERE guildId=$1 AND userId=$2 AND itemId=$3"
        params = (str(guild_id), str(user_id), str(item_id))
    async with db.execute(sql, params)
    return int(row[0]) if row else 0


async def adjust_stack(db, guild_id, user_id, item_id, amount, now, *, catalog_version=None,
                       binding_status="UNBOUND", status="ACTIVE"):
    if isinstance(amount, bool) or not isinstance(amount, int) or amount == 0:
        raise ValueError("Mutasi stack tidak valid.")
    if await stack_schema_is_phase4(db):
        catalog_version = str(catalog_version or RPG_PHASE3_CATALOG_VERSION)
        await db.execute(
            "INSERT OR IGNORE INTO RpgInventoryStack "
            "(guildId,userId,itemId,catalogVersion,bindingStatus,status,quantity,version,createdAt,updatedAt) "
            "VALUES (?,?,?,?,?,?,0,0,?,?)",
            (str(guild_id), str(user_id), str(item_id), catalog_version,
             str(binding_status), str(status), now, now),
        )
        cursor = await db.execute(
            "UPDATE RpgInventoryStack SET quantity=quantity+$1,version=version+1,updatedAt=$2 "
            "WHERE guildId=? AND userId=? AND itemId=? AND catalogVersion=? AND bindingStatus=? "
            "AND status=? AND quantity+?>=0",
            (amount, now, str(guild_id), str(user_id), str(item_id), catalog_version,
             str(binding_status), str(status), amount),
        )
    else:
        await db.execute(
            "INSERT OR IGNORE INTO RpgInventoryStack "
            "(guildId,userId,itemId,quantity,version,createdAt,updatedAt) VALUES (?,?,?,0,0,?,?)",
            (str(guild_id), str(user_id), str(item_id), now, now),
        )
        cursor = await db.execute(
            "UPDATE RpgInventoryStack SET quantity=quantity+$1,version=version+1,updatedAt=$2 "
            "WHERE guildId=? AND userId=? AND itemId=? AND quantity+?>=0",
            (amount, now, str(guild_id), str(user_id), str(item_id), amount),
        )
    if cursor.rowcount != 1:
        raise ValueError("Jumlah item tidak mencukupi.")
