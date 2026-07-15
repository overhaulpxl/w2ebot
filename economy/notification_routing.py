"""Authoritative Phase 9B notification route service."""

from __future__ import annotations

import json

from .dashboard_security import DashboardSecurityError, canonical_json, iso, utc_now
from .phase9b_schema import NOTIFICATION_CATEGORIES, phase9b_capability
from .reporting_taxonomy import normalize_event_filter


async def _require_capability(db):
    if not await phase9b_capability(db):
        raise DashboardSecurityError("capability_unavailable", 503)


async def list_notification_routes(db, guild_id):
    await _require_capability(db)
    async with db.execute(
        "SELECT category,enabled,channelId,roleMentionId,eventFilterJson,version,updatedById,updatedAt,"
        "lastSuccessfulDeliveryAt,lastFailedDeliveryAt,lastFailureCode "
        "FROM DashboardNotificationRoute WHERE guildId=? ORDER BY category",
        (str(guild_id),),
    ) as cursor:
        rows = {row[0]: row for row in await cursor.fetchall()}
    result = []
    for category in NOTIFICATION_CATEGORIES:
        row = rows.get(category)
        if not row:
            result.append({"category": category, "status": "NOT_CONFIGURED", "version": "0"})
            continue
        result.append({
            "category": category,
            "status": "ENABLED" if row[1] else "DISABLED",
            "channelId": row[2], "roleMentionId": row[3],
            "eventTypes": json.loads(row[4]).get("eventTypes", []),
            "version": str(row[5]), "updatedById": row[6], "updatedAt": row[7],
            "lastSuccessfulDeliveryAt": row[8], "lastFailedDeliveryAt": row[9],
            "lastFailureCode": row[10],
        })
    return result


async def get_notification_route(db, guild_id, category, *, event_type=None):
    await _require_capability(db)
    category = str(category).upper()
    if category not in NOTIFICATION_CATEGORIES:
        raise DashboardSecurityError("not_found", 404)
    async with db.execute(
        "SELECT enabled,channelId,roleMentionId,eventFilterJson,version,updatedAt "
        "FROM DashboardNotificationRoute WHERE guildId=? AND category=?",
        (str(guild_id), category),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return {"category": category, "status": "NOT_CONFIGURED"}
    filters = json.loads(row[3]).get("eventTypes", [])
    if not row[0]:
        status = "DISABLED"
    elif event_type and filters and str(event_type).upper() not in filters:
        status = "FILTERED"
    else:
        status = "ENABLED"
    return {"category": category, "status": status, "channelId": row[1],
            "roleMentionId": row[2], "eventTypes": filters, "version": int(row[4]),
            "updatedAt": row[5]}


async def update_notification_route(db, *, guild_id, actor_id, category, enabled, channel_id,
                                    role_mention_id, event_types, expected_version, now=None):
    await _require_capability(db)
    category = str(category).upper()
    if category not in NOTIFICATION_CATEGORIES:
        raise DashboardSecurityError("invalid_request", 400)
    if not isinstance(event_types, (list, tuple)):
        raise DashboardSecurityError("invalid_request", 400)
    try:
        filters = normalize_event_filter(category, event_types)
    except ValueError as exc:
        raise DashboardSecurityError("invalid_request", 400) from exc
    channel = str(channel_id) if channel_id is not None else None
    role = str(role_mention_id) if role_mention_id is not None else None
    if channel is not None and (not channel.isdigit() or len(channel) < 17):
        raise DashboardSecurityError("invalid_request", 400)
    if enabled and not channel:
        raise DashboardSecurityError("invalid_request", 400)
    if role is not None and (not role.isdigit() or len(role) < 17):
        raise DashboardSecurityError("invalid_request", 400)
    async with db.execute(
        "SELECT version FROM DashboardNotificationRoute WHERE guildId=? AND category=?",
        (str(guild_id), category),
    ) as cursor:
        current = await cursor.fetchone()
    expected = int(expected_version)
    if (current and int(current[0]) != expected) or (not current and expected != 0):
        raise DashboardSecurityError("version_conflict", 409)
    moment = iso(now or utc_now())
    filter_json = canonical_json({"eventTypes": filters})
    if current:
        cursor = await db.execute(
            "UPDATE DashboardNotificationRoute SET enabled=?,channelId=?,roleMentionId=?,eventFilterJson=?,"
            "version=version+1,updatedById=?,updatedAt=? WHERE guildId=? AND category=? AND version=?",
            (1 if enabled else 0, channel, role, filter_json, str(actor_id), moment,
             str(guild_id), category, expected),
        )
        if cursor.rowcount != 1:
            raise DashboardSecurityError("version_conflict", 409)
        version = expected + 1
    else:
        await db.execute(
            "INSERT INTO DashboardNotificationRoute "
            "(guildId,category,enabled,channelId,roleMentionId,eventFilterJson,version,updatedById,updatedAt) "
            "VALUES (?,?,?,?,?,?,0,?,?)",
            (str(guild_id), category, 1 if enabled else 0, channel, role, filter_json,
             str(actor_id), moment),
        )
        version = 0
    return {"category": category, "enabled": bool(enabled), "channelId": channel,
            "roleMentionId": role, "eventTypes": filters, "version": version}
