"""Durable notification reservation, leasing, and single finalization."""

from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import uuid

from .dashboard_security import DashboardSecurityError, canonical_json, iso, utc_now
from .notification_routing import get_notification_route
from .phase9b_schema import phase9b_capability


def delivery_marker(delivery_id):
    return f"w2e-delivery:{delivery_id}"


def deterministic_delivery_id(guild_id, delivery_kind, source_type, source_key):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
                          f"w2e:p9b:{guild_id}:{delivery_kind}:{source_type}:{source_key}"))


async def reserve_delivery(db, *, guild_id, delivery_kind, source_type, source_key, category,
                           event_type, payload, request_id=None, actor_id=None, now=None):
    if not await phase9b_capability(db):
        raise DashboardSecurityError("capability_unavailable", 503)
    kind = str(delivery_kind).upper()
    if kind not in {"EVENT", "TEST"}:
        raise DashboardSecurityError("invalid_request", 400)
    delivery_id = deterministic_delivery_id(guild_id, kind, source_type, source_key)
    async with db.execute(
        "SELECT deliveryId,guildId,deliveryKind,sourceType,sourceKey,category,eventType,payloadHash,status,"
        "channelId,roleMentionId,routeVersion,messageId,receiptJson FROM DashboardNotificationDelivery "
        "WHERE guildId=? AND deliveryKind=? AND sourceType=? AND sourceKey=?",
        (str(guild_id), kind, str(source_type), str(source_key)),
    ) as cursor:
        existing = await cursor.fetchone()
    payload_json = canonical_json(payload)
    digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    if existing:
        if existing[5] != str(category).upper() or existing[6] != str(event_type).upper() or existing[7] != digest:
            raise DashboardSecurityError("request_identity_conflict", 409)
        return _delivery_result(existing)
    route = await get_notification_route(db, guild_id, category, event_type=event_type)
    if route["status"] != "ENABLED":
        code = "not_configured" if route["status"] == "NOT_CONFIGURED" else "forbidden"
        raise DashboardSecurityError(code, 409 if code == "not_configured" else 403)
    moment = iso(now or utc_now())
    await db.execute(
        "INSERT INTO DashboardNotificationDelivery "
        "(deliveryId,guildId,deliveryKind,sourceType,sourceKey,category,routeVersion,channelId,roleMentionId,"
        "eventType,payloadJson,payloadHash,marker,status,requestId,actorId,createdAt) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'RESERVED',?,?,?)",
        (delivery_id, str(guild_id), kind, str(source_type), str(source_key), str(category).upper(),
         int(route["version"]), route["channelId"], route.get("roleMentionId"), str(event_type).upper(),
         payload_json, digest, delivery_marker(delivery_id), request_id, actor_id, moment),
    )
    return {"deliveryId": delivery_id, "status": "RESERVED", "channelId": route["channelId"],
            "roleMentionId": route.get("roleMentionId"), "routeVersion": route["version"],
            "marker": delivery_marker(delivery_id)}


async def reserve_crypto_news_outbox(db, *, limit=100, now=None):
    """Adopt Phase 6's authoritative outbox without creating a second source event."""
    if not await phase9b_capability(db):
        return []
    async with db.execute(
        "SELECT o.outboxId,o.newsId,o.guildId,n.eventKey,n.symbol,n.currentPriceEcy,n.changeBps,n.newsType "
        "FROM CryptoNewsOutbox o JOIN CryptoNewsEvent n ON n.newsId=o.newsId "
        "WHERE o.status IN ('PENDING','FAILED') ORDER BY o.createdAt,o.outboxId LIMIT ?",
        (max(1, min(int(limit), 100)),),
    ) as cursor:
        rows = await cursor.fetchall()
    reserved = []
    for outbox_id, _, guild_id, event_key, symbol, price, change_bps, news_type in rows:
        event_type = f"CRYPTO_MARKET_{news_type}"
        try:
            delivery = await reserve_delivery(
                db, guild_id=guild_id, delivery_kind="EVENT", source_type="CRYPTO_NEWS_OUTBOX",
                source_key=outbox_id, category="MARKET_CRYPTO", event_type=event_type,
                payload={"symbol": symbol, "currentPriceEcy": str(price),
                         "changeBps": str(change_bps), "newsType": news_type,
                         "sourceEventKey": event_key}, now=now,
            )
        except DashboardSecurityError as exc:
            if exc.code in {"not_configured", "forbidden"}:
                continue
            raise
        lease_owner = f"phase9b:{delivery['deliveryId']}"
        cursor = await db.execute(
            "UPDATE CryptoNewsOutbox SET status='CLAIMED',leaseOwner=?,leaseExpiresAt=NULL,"
            "attemptCount=attemptCount+1,lastErrorCode=NULL WHERE outboxId=? AND status IN ('PENDING','FAILED')",
            (lease_owner, outbox_id),
        )
        if cursor.rowcount == 1:
            reserved.append(delivery["deliveryId"])
    return reserved


def _delivery_result(row):
    return {"deliveryId": row[0], "status": row[8], "channelId": row[9],
            "roleMentionId": row[10], "routeVersion": row[11], "messageId": row[12],
            "receipt": json.loads(row[13]) if row[13] else None}


async def claim_deliveries(db, *, lease_owner, limit=50, lease_seconds=120, now=None):
    if not await phase9b_capability(db):
        return []
    moment = now or utc_now()
    expires = moment + timedelta(seconds=int(lease_seconds))
    async with db.execute(
        "SELECT deliveryId,status FROM DashboardNotificationDelivery "
        "WHERE status IN ('RESERVED','FAILED') OR (status='LEASED' AND leaseExpiresAt<?) "
        "ORDER BY createdAt LIMIT ?",
        (iso(moment), max(1, min(int(limit), 100))),
    ) as cursor:
        candidates = await cursor.fetchall()
    claimed = []
    for delivery_id, status in candidates:
        if status == "LEASED":
            cursor = await db.execute(
                "UPDATE DashboardNotificationDelivery SET leaseOwner=?,leaseExpiresAt=?,attemptCount=attemptCount+1,"
                "attemptedAt=? WHERE deliveryId=? AND status='LEASED' AND leaseExpiresAt<?",
                (str(lease_owner), iso(expires), iso(moment), delivery_id, iso(moment)),
            )
        else:
            cursor = await db.execute(
                "UPDATE DashboardNotificationDelivery SET status='LEASED',leaseOwner=?,leaseExpiresAt=?,"
                "attemptCount=attemptCount+1,attemptedAt=? WHERE deliveryId=? AND status=?",
                (str(lease_owner), iso(expires), iso(moment), delivery_id, status),
            )
        if cursor.rowcount == 1:
            claimed.append(delivery_id)
    if not claimed:
        return []
    marks = ",".join("?" for _ in claimed)
    async with db.execute(
        f"SELECT deliveryId,guildId,deliveryKind,sourceType,sourceKey,category,routeVersion,channelId,"
        f"roleMentionId,eventType,payloadJson,payloadHash,marker,attemptCount FROM DashboardNotificationDelivery "
        f"WHERE deliveryId IN ({marks}) AND leaseOwner=? ORDER BY createdAt",
        (*claimed, str(lease_owner)),
    ) as cursor:
        rows = await cursor.fetchall()
    keys = ("deliveryId", "guildId", "deliveryKind", "sourceType", "sourceKey", "category",
            "routeVersion", "channelId", "roleMentionId", "eventType", "payloadJson", "payloadHash",
            "marker", "attemptCount")
    return [dict(zip(keys, row)) for row in rows]


async def finalize_delivery(db, *, delivery_id, lease_owner, outcome, message_id=None,
                            failure_code=None, marker_inspected=False, now=None):
    outcome = str(outcome).upper()
    if outcome not in {"SENT", "FAILED", "REVIEW_REQUIRED"}:
        raise DashboardSecurityError("invalid_request", 400)
    if outcome == "SENT" and not message_id:
        raise DashboardSecurityError("invalid_request", 400)
    if outcome == "FAILED" and not marker_inspected:
        raise DashboardSecurityError("review_required", 409)
    async with db.execute(
        "SELECT guildId,category,status,leaseOwner,attemptCount,sourceType,sourceKey FROM DashboardNotificationDelivery WHERE deliveryId=?",
        (str(delivery_id),),
    ) as cursor:
        row = await cursor.fetchone()
    if not row or row[2] != "LEASED" or row[3] != str(lease_owner):
        raise DashboardSecurityError("version_conflict", 409)
    moment = iso(now or utc_now())
    receipt = {"deliveryId": str(delivery_id), "status": outcome, "messageId": str(message_id) if message_id else None,
               "failureCode": str(failure_code) if failure_code else None, "attemptCount": int(row[4]),
               "markerInspected": bool(marker_inspected)}
    receipt_json = canonical_json(receipt) if outcome != "FAILED" else None
    receipt_hash = hashlib.sha256(receipt_json.encode("utf-8")).hexdigest() if receipt_json else None
    cursor = await db.execute(
        "UPDATE DashboardNotificationDelivery SET status=?,leaseOwner=NULL,leaseExpiresAt=NULL,messageId=?,"
        "lastFailureCode=?,receiptJson=?,receiptHash=?,completedAt=? "
        "WHERE deliveryId=? AND status='LEASED' AND leaseOwner=?",
        (outcome, str(message_id) if message_id else None, failure_code, receipt_json, receipt_hash,
         moment if outcome != "FAILED" else None, str(delivery_id), str(lease_owner)),
    )
    if cursor.rowcount != 1:
        raise DashboardSecurityError("version_conflict", 409)
    if row[5] == "CRYPTO_NEWS_OUTBOX":
        source_status = outcome
        source_owner = f"phase9b:{delivery_id}"
        source = await db.execute(
            "UPDATE CryptoNewsOutbox SET status=?,messageId=COALESCE(?,messageId),lastErrorCode=?,sentAt=?,"
            "leaseOwner=NULL,leaseExpiresAt=NULL WHERE outboxId=? AND status='CLAIMED' AND leaseOwner=?",
            (source_status, str(message_id) if message_id else None,
             None if outcome == "SENT" else (failure_code or outcome.lower()),
             moment if outcome == "SENT" else None, row[6], source_owner),
        )
        if source.rowcount != 1:
            raise DashboardSecurityError("review_required", 409)
    if outcome == "SENT":
        await db.execute(
            "UPDATE DashboardNotificationRoute SET lastSuccessfulDeliveryAt=?,lastFailureCode=NULL "
            "WHERE guildId=? AND category=?", (moment, row[0], row[1]),
        )
    else:
        await db.execute(
            "UPDATE DashboardNotificationRoute SET lastFailedDeliveryAt=?,lastFailureCode=? "
            "WHERE guildId=? AND category=?", (moment, failure_code or outcome.lower(), row[0], row[1]),
        )
    return receipt
