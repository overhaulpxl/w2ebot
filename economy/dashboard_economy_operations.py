"""Audited Phase 9B dashboard controls built on Phase 9A operations."""

from __future__ import annotations

import hashlib
import uuid

from .constants import EMERGENCY_FEATURES
from .controls import normalize_control_reason
from .dashboard_auth import has_permission
from .dashboard_operations import _existing_operation
from .dashboard_security import DashboardSecurityError, canonical_json, iso, payload_hash, utc_now
from .notification_routing import update_notification_route
from .phase9b_schema import phase9b_capability


def _receipt_hash(receipt):
    return hashlib.sha256(canonical_json(receipt).encode("utf-8")).hexdigest()


async def _begin(db, *, guild_id, actor_id, permission, operation_type, target_type, target_id,
                 payload, request_id, expected_version, now):
    if not await phase9b_capability(db):
        raise DashboardSecurityError("capability_unavailable", 503)
    if not await has_permission(db, guild_id, actor_id, permission):
        raise DashboardSecurityError("forbidden", 403)
    digest = payload_hash(payload)
    identity = (str(guild_id), str(actor_id), permission, operation_type, target_type,
                str(target_id), digest, int(expected_version))
    replay = await _existing_operation(db, request_id, identity)
    if replay is not None:
        return None, replay, digest
    operation_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO DashboardControlledOperation (operationId,requestId,guildId,actorId,permissionClass,"
        "operationType,targetType,targetId,payloadHash,expectedVersion,status,createdAt) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,'PENDING',?)",
        (operation_id, request_id, *identity[:7], identity[7], iso(now)),
    )
    return operation_id, None, digest


async def _complete(db, *, operation_id, guild_id, actor_id, permission, operation_type,
                    target_type, target_id, request_id, expected_version, resulting_version,
                    digest, receipt, source_route, source_ip_hash, now):
    receipt_json = canonical_json(receipt); receipt_digest = _receipt_hash(receipt)
    cursor = await db.execute(
        "UPDATE DashboardControlledOperation SET status='COMMITTED',resultingVersion=?,receiptJson=?,"
        "receiptHash=?,settledAt=? WHERE operationId=? AND status='PENDING'",
        (int(resulting_version), receipt_json, receipt_digest, iso(now), operation_id),
    )
    if cursor.rowcount != 1:
        raise DashboardSecurityError("version_conflict", 409)
    await db.execute(
        "INSERT INTO DashboardOperatorAudit (auditId,guildId,executorUserId,permissionClass,operationType,"
        "targetType,targetId,requestId,previousVersion,resultingVersion,resultStatus,payloadHash,receiptHash,"
        "metadataJson,sourceRoute,sourceIpHash,createdAt) VALUES (?,?,?,?,?,?,?,?,?,?,'COMMITTED',?,?,?,?,?,?)",
        (str(uuid.uuid4()), str(guild_id), str(actor_id), permission, operation_type, target_type,
         str(target_id), request_id, int(expected_version), int(resulting_version), digest, receipt_digest,
         "{}", source_route, source_ip_hash, iso(now)),
    )
    return receipt


async def controlled_route_update(db, *, guild_id, actor_id, request_id, category, enabled,
                                  channel_id, role_mention_id, event_types, expected_version,
                                  source_route, source_ip_hash=None, now=None):
    moment = now or utc_now()
    payload = {"category": str(category).upper(), "enabled": bool(enabled),
               "channelId": str(channel_id) if channel_id is not None else None,
               "roleMentionId": str(role_mention_id) if role_mention_id is not None else None,
               "eventTypes": sorted(event_types or []), "expectedVersion": int(expected_version)}
    operation_id, replay, digest = await _begin(
        db, guild_id=guild_id, actor_id=actor_id, permission="NOTIFICATION_ROUTING_CONTROL",
        operation_type="NOTIFICATION_ROUTE_UPDATE", target_type="NOTIFICATION_ROUTE",
        target_id=str(category).upper(), payload=payload, request_id=request_id,
        expected_version=expected_version, now=moment,
    )
    if replay is not None:
        return replay
    result = await update_notification_route(
        db, guild_id=guild_id, actor_id=actor_id, category=category, enabled=enabled,
        channel_id=channel_id, role_mention_id=role_mention_id, event_types=event_types,
        expected_version=expected_version, now=moment,
    )
    receipt = {"requestId": request_id, "status": "COMMITTED", **result}
    return await _complete(db, operation_id=operation_id, guild_id=guild_id, actor_id=actor_id,
                           permission="NOTIFICATION_ROUTING_CONTROL", operation_type="NOTIFICATION_ROUTE_UPDATE",
                           target_type="NOTIFICATION_ROUTE", target_id=str(category).upper(), request_id=request_id,
                           expected_version=expected_version, resulting_version=result["version"], digest=digest,
                           receipt=receipt, source_route=source_route, source_ip_hash=source_ip_hash, now=moment)


async def controlled_feature_pause(db, *, guild_id, actor_id, request_id, feature, paused, reason,
                                   expected_version, source_route, source_ip_hash=None, now=None):
    feature = str(feature).lower()
    if feature not in EMERGENCY_FEATURES:
        raise DashboardSecurityError("invalid_request", 400)
    reason = normalize_control_reason(reason); moment = now or utc_now()
    payload = {"feature": feature, "paused": bool(paused), "reason": reason,
               "expectedVersion": int(expected_version)}
    operation_type = "FEATURE_PAUSE" if paused else "FEATURE_RESUME"
    operation_id, replay, digest = await _begin(
        db, guild_id=guild_id, actor_id=actor_id, permission="ECONOMY_PAUSE_CONTROL",
        operation_type=operation_type, target_type="ECONOMY_FEATURE", target_id=feature,
        payload=payload, request_id=request_id, expected_version=expected_version, now=moment,
    )
    if replay is not None:
        return replay
    async with db.execute("SELECT version FROM EconomyFeatureState WHERE guildId=? AND feature=?",
                          (str(guild_id), feature)) as cursor:
        current = await cursor.fetchone()
    expected = int(expected_version)
    if (current and int(current[0]) != expected) or (not current and expected != 0):
        raise DashboardSecurityError("version_conflict", 409)
    if current:
        cursor = await db.execute(
            "UPDATE EconomyFeatureState SET paused=?,reasonCode=?,changedById=?,changedAt=?,version=version+1 "
            "WHERE guildId=? AND feature=? AND version=?",
            (1 if paused else 0, reason, str(actor_id), iso(moment), str(guild_id), feature, expected),
        )
        if cursor.rowcount != 1:
            raise DashboardSecurityError("version_conflict", 409)
        resulting = expected + 1
    else:
        await db.execute(
            "INSERT INTO EconomyFeatureState (guildId,feature,paused,reasonCode,changedById,changedAt,version) "
            "VALUES (?,?,?,?,?,?,0)", (str(guild_id), feature, 1 if paused else 0, reason, str(actor_id), iso(moment)),
        )
        resulting = 0
    receipt = {"requestId": request_id, "status": "COMMITTED", "feature": feature,
               "paused": bool(paused), "resultingVersion": resulting}
    return await _complete(db, operation_id=operation_id, guild_id=guild_id, actor_id=actor_id,
                           permission="ECONOMY_PAUSE_CONTROL", operation_type=operation_type,
                           target_type="ECONOMY_FEATURE", target_id=feature, request_id=request_id,
                           expected_version=expected, resulting_version=resulting, digest=digest,
                           receipt=receipt, source_route=source_route, source_ip_hash=source_ip_hash, now=moment)
