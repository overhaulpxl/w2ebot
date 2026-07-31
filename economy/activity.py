from datetime import timedelta
import uuid

import aiosqlite

from .database import configure_connection
from .time_policy import utc_datetime, utc_iso


ACTIVITY_WINDOW_DAYS = 30


async def append_activity_event(
    db,
    *,
    guild_id,
    user_id,
    event_type,
    event_key,
    points,
    metric_value=0,
    occurred_at,
    transaction_id=None,
    reference_id=None,
):
    if isinstance(points, bool) or not isinstance(points, int) or points < 0:
        raise ValueError("points aktivitas tidak valid")
    if isinstance(metric_value, bool) or not isinstance(metric_value, int) or metric_value < 0:
        raise ValueError("metric aktivitas tidak valid")
    await db.execute(
        "INSERT INTO EconomyActivityEvent "
        "(eventId,guildId,userId,eventType,eventKey,points,metricValue,transactionId,referenceId,occurredAt,createdAt) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            str(uuid.uuid4()), str(guild_id), str(user_id), str(event_type), str(event_key),
            points, metric_value, str(transaction_id) if transaction_id else None,
            str(reference_id) if reference_id else None, utc_iso(occurred_at), utc_iso(),
        ),
    )


async def rolling_activity_score(db_path, guild_id, user_id, *, now=None):
    upper = utc_datetime(now)
    lower = upper - timedelta(days=ACTIVITY_WINDOW_DAYS)
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            async with db.execute(
                "SELECT COALESCE(SUM(points),0) FROM EconomyActivityEvent "
                "WHERE guildId=? AND userId=? AND occurredAt>=? AND occurredAt<=?",
                (str(guild_id), str(user_id), utc_iso(lower), utc_iso(upper)),
            ) as cursor:
                return int((await cursor.fetchone())[0])
    except aiosqlite.OperationalError:
        return 0


async def activity_metric(db, *, guild_id, user_id, event_type, start_utc, end_utc,
                          aggregate="sum"):
    expression = "COUNT(*)" if aggregate == "count" else "COALESCE(SUM(metricValue),0)"
    async with db.execute(
        f"SELECT {expression} FROM EconomyActivityEvent "
        "WHERE guildId=? AND userId=? AND eventType=? AND occurredAt>=? AND occurredAt<?",
        (str(guild_id), str(user_id), str(event_type), utc_iso(start_utc), utc_iso(end_utc)),
    ) as cursor:
        return int((await cursor.fetchone())[0])
