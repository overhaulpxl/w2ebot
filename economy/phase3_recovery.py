"""Recovery Phase 3 yang memakai outcome persisted dan tidak membuat randomness baru."""

import aiosqlite

from .adventures import settle_dungeon, settle_hunt
from .bosses import commit_boss_attack, settle_boss
from .crafting import settle_craft
from .database import configure_connection
from .enhancement import settle_enhancement
from .equipment import initialize_phase3_profile
from .open_items import settle_open_item
from .operations import record_operation_retry
from .quests import claim_quest


async def inspect_phase3_recovery(db_path):
    counts = {"reserved": 0, "awaiting_funds": 0, "review_required": 0,
              "boss_awaiting_funds": 0}
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT status,COUNT(*) FROM RpgOperation "
            "WHERE status IN ('RESERVED','AWAITING_FUNDS','REVIEW_REQUIRED') GROUP BY status"
        ) as cursor:
            for status, count in await cursor.fetchall():
                counts[status.lower()] = int(count)
        async with db.execute(
            "SELECT COUNT(*) FROM RpgBossRaid WHERE status='AWAITING_FUNDS'"
        ) as cursor:
            counts["boss_awaiting_funds"] = int((await cursor.fetchone())[0])
    return counts


async def recover_phase3_operations(db_path):
    """Coba settlement ulang tanpa mengubah outcome atau mengganti reservation."""
    result = {"committed": 0, "review": 0, "failed": 0, "boss_settled": 0,
              "starter_repaired": 0}
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT operationId,guildId,userId,operationType,status FROM RpgOperation "
            "WHERE status IN ('RESERVED','AWAITING_FUNDS','REVIEW_REQUIRED') "
            "ORDER BY createdAt,operationId"
        ) as cursor:
            operations = await cursor.fetchall()
        async with db.execute(
            "SELECT guildId,userId FROM RpgStarterGrant WHERE status IN ('PENDING','REVIEW_REQUIRED')"
        ) as cursor:
            starter_rows = await cursor.fetchall()
        async with db.execute(
            "SELECT guildId,raidId FROM RpgBossRaid WHERE status='AWAITING_FUNDS'"
        ) as cursor:
            boss_rows = await cursor.fetchall()

    handlers = {
        "ENHANCEMENT": lambda row: settle_enhancement(
            db_path, guild_id=row[1], user_id=row[2], operation_id=row[0]),
        "CRAFT": lambda row: settle_craft(
            db_path, guild_id=row[1], user_id=row[2], operation_id=row[0]),
        "OPEN_ITEM": lambda row: settle_open_item(
            db_path, guild_id=row[1], user_id=row[2], operation_id=row[0]),
        "HUNT": lambda row: settle_hunt(
            db_path, guild_id=row[1], user_id=row[2], operation_id=row[0]),
        "DUNGEON": lambda row: settle_dungeon(
            db_path, guild_id=row[1], user_id=row[2], operation_id=row[0]),
        "BOSS_ATTACK": lambda row: commit_boss_attack(
            db_path, guild_id=row[1], user_id=row[2], operation_id=row[0]),
        "QUEST_CLAIM": lambda row: _recover_quest_claim(db_path, row),
    }
    for row in operations:
        if row[4] == "REVIEW_REQUIRED" or row[3] not in handlers:
            result["review"] += 1
            continue
        await record_operation_retry(db_path, row[0])
        try:
            settled = await handlers[row[3]](row)
            ok = getattr(settled, "ok", None)
            if ok is None and isinstance(settled, tuple):
                ok = True
            if ok:
                result["committed"] += 1
            else:
                result["failed"] += 1
                await record_operation_retry(
                    db_path, row[0], error_code=getattr(settled, "code", "recovery_failed"),
                )
        except Exception as exc:
            result["failed"] += 1
            await record_operation_retry(db_path, row[0], error_code=type(exc).__name__)

    for guild_id, raid_id in boss_rows:
        settled = await settle_boss(
            db_path, guild_id=guild_id, raid_id=raid_id, authorized=True,
        )
        if settled.ok:
            result["boss_settled"] += 1

    for guild_id, user_id in starter_rows:
        if await initialize_phase3_profile(db_path, guild_id, user_id):
            result["starter_repaired"] += 1
    return result


async def _recover_quest_claim(db_path, row):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT outcomeJson FROM RpgOperation WHERE operationId=?", (row[0],),
        ) as cursor:
            raw = await cursor.fetchone()
    if not raw:
        raise ValueError("Operation quest tidak ditemukan.")
    import json
    outcome = json.loads(raw[0])
    return await claim_quest(
        db_path, guild_id=row[1], user_id=row[2], quest_type=outcome["quest_type"],
    )
