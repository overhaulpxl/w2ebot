from datetime import datetime, timezone

import aiosqlite

from .constants import EMERGENCY_FEATURES, configured_whitelist_ids
from .database import configure_connection


def _now():
    return datetime.now(timezone.utc).isoformat()


def normalize_control_reason(reason):
    text = str(reason or "").strip()
    if not 1 <= len(text) <= 300 or "\n" in text or "\r" in text:
        raise ValueError("Alasan wajib 1-300 karakter dalam satu baris.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise ValueError("Alasan mengandung karakter yang tidak diizinkan.")
    return text


async def _write_existing_audit(db, *, action, target_id, detail):
    async with db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='AuditLog'"
    ) as cursor:
        if not await cursor.fetchone():
            return
    await db.execute(
        "INSERT INTO AuditLog (ts,action,target_id,detail,source) VALUES (?,?,?,?,?)",
        (_now(), action, str(target_id) if target_id is not None else None, detail, "economy_v1"),
    )


async def is_whitelisted(db_path, guild_id, user_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT enabled FROM EconomyMintWhitelist WHERE guildId=? AND userId=?",
            (str(guild_id), str(user_id)),
        ) as cursor:
            row = await cursor.fetchone()
    return bool(row and int(row[0]) == 1)


async def set_whitelist(db_path, *, guild_id, user_id, enabled, actor_id, reason):
    reason = normalize_control_reason(reason)
    now = _now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute(
            "INSERT INTO EconomyMintWhitelist (guildId,userId,enabled,addedById,reasonCode,createdAt,updatedAt) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(guildId,userId) DO UPDATE SET "
            "enabled=excluded.enabled,addedById=excluded.addedById,reasonCode=excluded.reasonCode,updatedAt=excluded.updatedAt",
            (str(guild_id), str(user_id), 1 if enabled else 0, str(actor_id), reason, now, now),
        )
        await _write_existing_audit(
            db,
            action="economy-whitelist-enable" if enabled else "economy-whitelist-disable",
            target_id=user_id,
            detail="Whitelist ekonomi diperbarui.",
        )
        await db.commit()


async def list_whitelist(db_path, guild_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT userId,enabled,addedById,updatedAt FROM EconomyMintWhitelist WHERE guildId=? ORDER BY userId",
            (str(guild_id),),
        ) as cursor:
            return await cursor.fetchall()


async def bootstrap_whitelist(db_path, guild_id):
    now = _now()
    ids = configured_whitelist_ids()
    if not ids:
        return 0
    inserted = 0
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        for user_id in ids:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO EconomyMintWhitelist "
                "(guildId,userId,enabled,addedById,reasonCode,createdAt,updatedAt) VALUES (?,?,1,?,'environment_bootstrap',?,?)",
                (str(guild_id), user_id, user_id, now, now),
            )
            inserted += max(0, cursor.rowcount)
        if inserted:
            await _write_existing_audit(
                db, action="economy-whitelist-bootstrap", target_id=None,
                detail=f"Bootstrap whitelist selesai: {inserted} ID.",
            )
        await db.commit()
    return inserted


async def set_feature_paused(db_path, *, guild_id, feature, paused, actor_id, reason):
    feature = str(feature).lower()
    if feature not in EMERGENCY_FEATURES:
        raise ValueError("Feature ekonomi tidak valid.")
    reason = normalize_control_reason(reason)
    now = _now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            "INSERT INTO EconomyFeatureState (guildId,feature,paused,reasonCode,changedById,changedAt,version) "
            "VALUES (?,?,?,?,?,?,0) ON CONFLICT(guildId,feature) DO UPDATE SET "
            "paused=excluded.paused,reasonCode=excluded.reasonCode,changedById=excluded.changedById,"
            "changedAt=excluded.changedAt,version=EconomyFeatureState.version+1",
            (str(guild_id), feature, 1 if paused else 0, reason, str(actor_id), now),
        )
        await _write_existing_audit(
            db,
            action="economy-feature-pause" if paused else "economy-feature-resume",
            target_id=feature,
            detail="Emergency control ekonomi diperbarui.",
        )
        await db.commit()


async def feature_states(db_path, guild_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT feature,paused,reasonCode,changedById,changedAt FROM EconomyFeatureState WHERE guildId=?",
            (str(guild_id),),
        ) as cursor:
            rows = await cursor.fetchall()
    mapped = {row[0]: row for row in rows}
    return [mapped.get(feature, (feature, 0, None, None, None)) for feature in EMERGENCY_FEATURES]
