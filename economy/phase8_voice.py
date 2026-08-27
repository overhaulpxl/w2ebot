"""Pelacakan segmen Voice Activity Phase 8 yang tidak tumpang tindih."""

from datetime import datetime, timedelta, timezone
import uuid

import aiosqlite

from .database import configure_connection
from .phase8_schema import phase8_capability


BLOCK_SECONDS = 30 * 60


def _dt(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def voice_block_identity(guild_id, user_id, qualified_start, sequence, block_end):
    return (f"voice30:{guild_id}:{user_id}:{qualified_start.isoformat()}:"
            f"{int(sequence)}:{block_end.isoformat()}")


async def _checkpoint_locked(db, row, observed):
    guild_id, user_id, channel_id, start_raw, awarded_raw, _, sequence, status, version = row
    if status != "ACTIVE":
        return 0
    start, awarded = _dt(start_raw), _dt(awarded_raw)
    awarded_count = 0
    while (observed - awarded).total_seconds() >= BLOCK_SECONDS:
        block_end = awarded + timedelta(seconds=BLOCK_SECONDS)
        identity = voice_block_identity(guild_id, user_id, start, sequence, block_end)
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:{identity}"))
        await db.execute(
            "INSERT OR IGNORE INTO EconomyActivityEvent "
            "(eventId,guildId,userId,eventType,eventKey,points,metricValue,transactionId,referenceId,occurredAt,createdAt) "
            "VALUES (?,?,?,'VOICE_ACTIVITY_30M',?,2,1,NULL,?,?,?)",
            (event_id, guild_id, user_id, identity, identity, block_end.isoformat(), observed.isoformat()),
        )
        await db.execute(
            "INSERT OR IGNORE INTO GiveawayVoiceBlock "
            "(blockId,guildId,userId,channelId,qualifiedStartAt,blockSequence,blockEndAt,activityEventId,createdAt) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:block:{identity}")), guild_id, user_id,
             channel_id, start.isoformat(), sequence, block_end.isoformat(), event_id, observed.isoformat()),
        )
        awarded, sequence = block_end, int(sequence) + 1
        awarded_count += 1
    cursor = await db.execute(
        "UPDATE GiveawayVoiceQualification SET awardedThroughAt=?,lastObservedAt=?,nextBlockSequence=?,version=version+1 "
        "WHERE guildId=? AND userId=? AND version=? AND status='ACTIVE'",
        (awarded.isoformat(), observed.isoformat(), sequence, guild_id, user_id, version),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("Voice qualification berubah selama checkpoint.")
    return awarded_count


async def reconcile_voice_snapshot(db_path, guild_id, qualifying_channels, *, observed_at=None):
    """Rekonsiliasi {user_id: channel_id}; semua perubahan commit atomik."""
    observed = _dt(observed_at)
    current = {str(user): str(channel) for user, channel in qualifying_channels.items()}
    report = {"started": 0, "closed": 0, "awarded": 0}
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        if not await phase8_capability(db):
            return {**report, "ready": False}
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            "SELECT guildId,userId,channelId,qualifiedStartAt,awardedThroughAt,lastObservedAt,nextBlockSequence,status,version "
            "FROM GiveawayVoiceQualification WHERE guildId=? AND status='ACTIVE'", (str(guild_id),),
        ) as cursor:
            rows = await cursor.fetchall()
        active = {str(row[1]): row for row in rows}
        for user_id, row in active.items():
            report["awarded"] += await _checkpoint_locked(db, row, observed)
            if user_id not in current or current[user_id] != str(row[2]):
                await db.execute(
                    "UPDATE GiveawayVoiceQualification SET status='CLOSED',lastObservedAt=?,version=version+1 "
                    "WHERE guildId=? AND userId=? AND status='ACTIVE'",
                    (observed.isoformat(), str(guild_id), user_id),
                )
                report["closed"] += 1
        for user_id, channel_id in current.items():
            if user_id in active and channel_id == str(active[user_id][2]):
                continue
            await db.execute(
                "INSERT INTO GiveawayVoiceQualification "
                "(guildId,userId,channelId,qualifiedStartAt,awardedThroughAt,lastObservedAt,nextBlockSequence,status,version) "
                "VALUES (?,?,?,?,?,?,1,'ACTIVE',0) ON CONFLICT(guildId,userId) DO UPDATE SET "
                "channelId=excluded.channelId,qualifiedStartAt=excluded.qualifiedStartAt,"
                "awardedThroughAt=excluded.awardedThroughAt,lastObservedAt=excluded.lastObservedAt,"
                "nextBlockSequence=1,status='ACTIVE',version=GiveawayVoiceQualification.version+1",
                (str(guild_id), user_id, channel_id, observed.isoformat(), observed.isoformat(), observed.isoformat()),
            )
            report["started"] += 1
        await db.commit()
    return {**report, "ready": True}

async def close_voice_segments_on_restart(db_path):
    """Tutup segmen pada lastObservedAt tanpa memberi waktu offline."""
    report = {"closed": 0, "awarded": 0}
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        if not await phase8_capability(db):
            return {**report, "ready": False}
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            "SELECT guildId,userId,channelId,qualifiedStartAt,awardedThroughAt,lastObservedAt,nextBlockSequence,status,version "
            "FROM GiveawayVoiceQualification WHERE status='ACTIVE'"
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            report["awarded"] += await _checkpoint_locked(db, row, _dt(row[5]))
            await db.execute(
                "UPDATE GiveawayVoiceQualification SET status='CLOSED',version=version+1 "
                "WHERE guildId=? AND userId=? AND status='ACTIVE'", (row[0], row[1]),
            )
            report["closed"] += 1
        await db.commit()
    return {**report, "ready": True}
