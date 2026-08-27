"""Atomic controlled security-administration operations and receipts."""

from __future__ import annotations

import hashlib
import json
import uuid

from .dashboard_auth import has_permission, revoke_session
from .dashboard_security import DashboardSecurityError, canonical_json, iso, payload_hash, utc_now
from .phase9a_schema import PERMISSION_CLASSES


def _receipt_hash(receipt):
    return hashlib.sha256(canonical_json(receipt).encode("utf-8")).hexdigest()


async def _existing_operation(db, request_id, identity):
    row = await db.fetchrow(
        "SELECT guildId,actorId,permissionClass,operationType,targetType,targetId,payloadHash,expectedVersion,status,"
        "receiptJson,errorCode FROM DashboardControlledOperation WHERE requestId=$1", request_id,),
    )
    if not row:
        return None
    if tuple(row[:8]) != tuple(identity):
        raise DashboardSecurityError("request_identity_conflict", 409)
    if row[8] == "COMMITTED":
        return json.loads(row[9])
    if row[8] in {"PENDING", "REVIEW_REQUIRED"}:
        raise DashboardSecurityError("version_conflict", 409)
    raise DashboardSecurityError("request_identity_conflict", 409)


async def change_permission(db, *, action, guild_id, actor_id, target_user_id, permission_class,
                            request_id, expected_version, source_route, source_ip_hash=None, now=None):
    if action not in {"GRANT", "REVOKE"} or permission_class not in PERMISSION_CLASSES:
        raise DashboardSecurityError("invalid_request", 400)
    if not await has_permission(db, guild_id, actor_id, "DASHBOARD_SECURITY_ADMIN"):
        raise DashboardSecurityError("forbidden", 403)
    moment = now or utc_now()
    payload = {"action": action, "targetUserId": str(target_user_id),
               "permissionClass": permission_class, "expectedVersion": int(expected_version)}
    digest = payload_hash(payload)
    identity = (str(guild_id), str(actor_id), "DASHBOARD_SECURITY_ADMIN", f"PERMISSION_{action}",
                "DASHBOARD_OPERATOR", str(target_user_id), digest, int(expected_version)
    replay = await _existing_operation(db, request_id, identity)
    if replay is not None:
        return replay
    operation_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO DashboardControlledOperation "
        "(operationId,requestId,guildId,actorId,permissionClass,operationType,targetType,targetId,payloadHash,"
        "expectedVersion,status,createdAt) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'PENDING',$11)", operation_id, request_id, *identity[:7], identity[7], iso(moment),
    )
    await db.execute(
        "INSERT INTO DashboardIdentity (guildId,userId,status,createdAt,updatedAt) VALUES ($1,$2,'ACTIVE',$3,$4) "
        "ON CONFLICT(guildId,userId) DO NOTHING", str(guild_id), str(target_user_id), iso(moment), iso(moment),
    )
    if action == "GRANT":
        existing = await _active_assignment(db, guild_id, target_user_id, permission_class)
        if existing:
            assignment_id, current_version = existing
            if current_version != int(expected_version):
                raise DashboardSecurityError("version_conflict", 409)
            resulting_version = current_version
        else:
            if int(expected_version) != 0:
                raise DashboardSecurityError("version_conflict", 409)
            assignment_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO DashboardOperatorPermission "
                "(assignmentId,guildId,userId,permissionClass,status,grantedById,grantedAt) "
                "VALUES ($1,$2,$3,$4,'ACTIVE',$5,$6)", assignment_id, str(guild_id), str(target_user_id), permission_class, str(actor_id), iso(moment),
            )
            resulting_version = 0
    else:
        existing = await _active_assignment(db, guild_id, target_user_id, permission_class)
        if not existing or existing[1] != int(expected_version):
            raise DashboardSecurityError("version_conflict", 409)
        assignment_id, current_version = existing
        resulting_version = current_version + 1
        cursor = await db.execute(
            "UPDATE DashboardOperatorPermission SET status='REVOKED',revokedById=$1,revokedAt=$2,version=version+1 "
            "WHERE assignmentId=$1 AND status='ACTIVE' AND version=$2", str(actor_id), iso(moment), assignment_id, current_version),
        )
        if cursor.rowcount != 1:
            raise DashboardSecurityError("version_conflict", 409)
    await db.execute(
        "UPDATE DashboardSession SET status='REVOKED',revokedAt=$1,revokeReasonCode='PERMISSION_CHANGED',version=version+1 "
        "WHERE guildId=$1 AND userId=$2 AND status='ACTIVE'",
        (iso(moment), str(guild_id), str(target_user_id),
    )
    receipt = {"requestId": request_id, "action": action, "assignmentId": assignment_id,
               "targetUserId": str(target_user_id), "permissionClass": permission_class,
               "resultingVersion": resulting_version, "status": "COMMITTED"}
    receipt_json = canonical_json(receipt)
    receipt_digest = _receipt_hash(receipt)
    await db.execute(
        "UPDATE DashboardControlledOperation SET status='COMMITTED',resultingVersion=$1,receiptJson=$2,receiptHash=$3,settledAt=$4 "
        "WHERE operationId=$1 AND status='PENDING'", resulting_version, receipt_json, receipt_digest, iso(moment), operation_id),
    )
    await db.execute(
        "INSERT INTO DashboardOperatorAudit "
        "(auditId,guildId,executorUserId,permissionClass,operationType,targetType,targetId,requestId,previousVersion,"
        "resultingVersion,resultStatus,payloadHash,receiptHash,metadataJson,sourceRoute,sourceIpHash,createdAt) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10, 'COMMITTED',$11,$12,$13,$14,$15,$16)",
        (str(uuid.uuid4(), str(guild_id), str(actor_id), "DASHBOARD_SECURITY_ADMIN", f"PERMISSION_{action}",
         "DASHBOARD_OPERATOR", str(target_user_id), request_id, int(expected_version), resulting_version,
         digest, receipt_digest, "{}", source_route, source_ip_hash, iso(moment)),
    )
    await db.execute(
        "INSERT INTO DashboardAuthorizationAudit "
        "(auditId,guildId,targetUserId,permissionClass,action,executorUserId,requestId,assignmentId,previousVersion,"
        "resultingVersion,receiptHash,createdAt) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)", str(uuid.uuid4(), str(guild_id), str(target_user_id), permission_class, action, str(actor_id),
         request_id, assignment_id, int(expected_version), resulting_version, receipt_digest, iso(moment)),
    )
    return receipt


async def _active_assignment(db, guild_id, user_id, permission_class):
    target = await db.fetchrow(
        "SELECT assignmentId,version FROM DashboardOperatorPermission WHERE guildId=$1 AND userId=$2 "
        "AND permissionClass=$1 AND status='ACTIVE'", str(guild_id), str(user_id), permission_class),
        return await cursor.fetchone()


async def revoke_dashboard_session(db, *, guild_id, actor_id, target_session_id, request_id,
                                   expected_version, source_route, source_ip_hash=None, now=None):
    if not await has_permission(db, guild_id, actor_id, "DASHBOARD_SECURITY_ADMIN"):
        raise DashboardSecurityError("forbidden", 403)
    async with db.execute(
        "SELECT guildId FROM DashboardSession WHERE sessionId=$1", str(target_session_id),),
    )
    if not target or target[0] != str(guild_id):
        raise DashboardSecurityError("forbidden", 403)
    moment = now or utc_now()
    payload = {"sessionId": str(target_session_id), "expectedVersion": int(expected_version)}
    digest = payload_hash(payload)
    identity = (str(guild_id), str(actor_id), "DASHBOARD_SECURITY_ADMIN", "SESSION_REVOKE",
                "DASHBOARD_SESSION", str(target_session_id), digest, int(expected_version)
    replay = await _existing_operation(db, request_id, identity)
    if replay is not None:
        return replay
    operation_id = str(uuid.uuid4()
    await db.execute(
        "INSERT INTO DashboardControlledOperation "
        "(operationId,requestId,guildId,actorId,permissionClass,operationType,targetType,targetId,payloadHash,"
        "expectedVersion,status,createdAt) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'PENDING',$11)", operation_id, request_id, *identity[:7], identity[7], iso(moment),
    )
    await revoke_session(db, session_id=target_session_id, reason_code="ADMIN_REVOKED",
                         expected_version=expected_version, now=moment)
    resulting_version = int(expected_version) + 1
    receipt = {"requestId": request_id, "sessionId": str(target_session_id),
               "resultingVersion": resulting_version, "status": "COMMITTED"}
    receipt_json = canonical_json(receipt)
    receipt_digest = _receipt_hash(receipt)
    await db.execute(
        "UPDATE DashboardControlledOperation SET status='COMMITTED',resultingVersion=$1,receiptJson=$2,receiptHash=$3,settledAt=$4 "
        "WHERE operationId=$1 AND status='PENDING'", resulting_version, receipt_json, receipt_digest, iso(moment), operation_id),
    )
    await db.execute(
        "INSERT INTO DashboardOperatorAudit "
        "(auditId,guildId,executorUserId,permissionClass,operationType,targetType,targetId,requestId,previousVersion,"
        "resultingVersion,resultStatus,payloadHash,receiptHash,metadataJson,sourceRoute,sourceIpHash,createdAt) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'COMMITTED',$11,$12,$13,$14,$15,$16)",
        (str(uuid.uuid4(), str(guild_id), str(actor_id), "DASHBOARD_SECURITY_ADMIN", "SESSION_REVOKE",
         "DASHBOARD_SESSION", str(target_session_id), request_id, int(expected_version), resulting_version,
         digest, receipt_digest, "{}", source_route, source_ip_hash, iso(moment)),
    )
    return receipt
