"""Phase 9B reviewed-recovery reservations without replacement identities."""

from __future__ import annotations

import hashlib
import json
import uuid

from .dashboard_auth import has_permission
from .dashboard_security import DashboardSecurityError, canonical_json, iso, payload_hash, utc_now
from .phase9b_schema import phase9b_capability


async def recover_phase9b(db, *, now=None):
    if not await phase9b_capability(db):
        return {"capable": False, "expiredLeases": 0, "reviewRequired": 0}
    moment = iso(now or utc_now())
    async with db.execute(
        "SELECT COUNT(*) FROM DashboardNotificationDelivery WHERE status='LEASED' AND leaseExpiresAt<?",
        (moment,),
    ) as cursor:
        expired = int((await cursor.fetchone())[0])
    async with db.execute(
        "SELECT COUNT(*) FROM DashboardNotificationDelivery WHERE status='REVIEW_REQUIRED'",
    ) as cursor:
        review = int((await cursor.fetchone())[0])
    return {"capable": True, "expiredLeases": expired, "reviewRequired": review}


RECOVERY_TARGETS = {
    "RPG_OPERATION": ("RpgOperation", "operationId", {"RETRY", "VOID"}),
    "MARKETPLACE_SALE": ("MarketplaceSale", "saleId", {"RETRY"}),
    "MARKETPLACE_RETURN": ("MarketplaceReturn", "returnId", {"RETRY"}),
    "CASINO_SESSION": ("CasinoSession", "sessionId", {"RETRY", "REFUND"}),
    "MINING_OPERATION": ("MiningOperation", "operationId", {"RETRY"}),
    "ETERNAL_OPTION_POSITION": ("EternalOptionPosition", "positionId", {"RETRY"}),
}


async def reserve_reviewed_recovery(db, *, guild_id, actor_id, request_id, target_type,
                                    target_id, resolution, expected_version, reason, now=None):
    if not await phase9b_capability(db):
        raise DashboardSecurityError("capability_unavailable", 503)
    if not await has_permission(db, guild_id, actor_id, "REVIEWED_RECOVERY_CONTROL"):
        raise DashboardSecurityError("forbidden", 403)
    target_type = str(target_type).upper(); resolution = str(resolution).upper()
    target = RECOVERY_TARGETS.get(target_type)
    if not target or resolution not in target[2] or not str(reason).strip():
        raise DashboardSecurityError("invalid_request", 400)
    table, key_column, _ = target
    async with db.execute(
        f"SELECT guildId,status FROM {table} WHERE {key_column}=?", (str(target_id),),
    ) as cursor:
        source = await cursor.fetchone()
    if not source or source[0] != str(guild_id) or source[1] != "REVIEW_REQUIRED":
        raise DashboardSecurityError("review_required", 409)
    payload = {"targetType": target_type, "targetId": str(target_id), "resolution": resolution,
               "expectedVersion": int(expected_version), "reason": str(reason).strip()}
    digest = payload_hash(payload)
    async with db.execute(
        "SELECT operationId,guildId,actorId,payloadHash,status,receiptJson FROM DashboardControlledOperation "
        "WHERE requestId=?", (str(request_id),),
    ) as cursor:
        existing = await cursor.fetchone()
    if existing:
        if existing[1] != str(guild_id) or existing[2] != str(actor_id) or existing[3] != digest:
            raise DashboardSecurityError("request_identity_conflict", 409)
        return {"operationId": existing[0], "status": existing[4],
                "receipt": json.loads(existing[5]) if existing[5] else None, "replayed": True}
    operation_id = str(uuid.uuid4()); moment = iso(now or utc_now())
    try:
        await db.execute(
            "INSERT INTO DashboardControlledOperation (operationId,requestId,guildId,actorId,permissionClass,"
            "operationType,targetType,targetId,payloadHash,expectedVersion,status,createdAt) "
            "VALUES (?,?,?,?,'REVIEWED_RECOVERY_CONTROL','REVIEW_RESOLVE',?,?,?,?,'PENDING',?)",
            (operation_id, str(request_id), str(guild_id), str(actor_id), target_type,
             str(target_id), digest, int(expected_version), moment),
        )
    except Exception as exc:
        raise DashboardSecurityError("request_identity_conflict", 409) from exc
    source_hash = hashlib.sha256(canonical_json({"status": source[1], "target": str(target_id)}).encode()).hexdigest()
    await db.execute(
        "INSERT INTO DashboardRecoveryControl (controlId,guildId,domain,entityType,entityId,sourceStateHash,"
        "status,version,lastOperationId,createdAt,updatedAt) VALUES (?,?,?,?,?,?,'OPEN',0,?,?,?) "
        "ON CONFLICT(guildId,domain,entityType,entityId) DO UPDATE SET lastOperationId=excluded.lastOperationId,"
        "updatedAt=excluded.updatedAt",
        (str(uuid.uuid4()), str(guild_id), target_type.split('_')[0], target_type, str(target_id),
         source_hash, operation_id, moment, moment),
    )
    return {"operationId": operation_id, "status": "PENDING", "receipt": None, "replayed": False}


async def finalize_reviewed_recovery(db, *, operation_id, success, result_code, now=None):
    moment = iso(now or utc_now())
    async with db.execute(
        "SELECT requestId,guildId,actorId,targetType,targetId,expectedVersion,payloadHash,status "
        "FROM DashboardControlledOperation WHERE operationId=?", (str(operation_id),),
    ) as cursor:
        row = await cursor.fetchone()
    if not row or row[7] not in {"PENDING", "REVIEW_REQUIRED"}:
        raise DashboardSecurityError("version_conflict", 409)
    if not success:
        await db.execute(
            "UPDATE DashboardControlledOperation SET status='REVIEW_REQUIRED',errorCode=?,settledAt=? "
            "WHERE operationId=? AND status='PENDING'", (str(result_code), moment, str(operation_id)),
        )
        await db.execute(
            "UPDATE DashboardRecoveryControl SET status='REVIEW_REQUIRED',updatedAt=?,version=version+1 "
            "WHERE guildId=? AND entityType=? AND entityId=? AND lastOperationId=?",
            (moment, row[1], row[3], row[4], str(operation_id)),
        )
        return {"requestId": row[0], "status": "REVIEW_REQUIRED", "code": str(result_code)}
    receipt = {"requestId": row[0], "targetType": row[3], "targetId": row[4],
               "status": "COMMITTED", "resultCode": str(result_code)}
    receipt_json = canonical_json(receipt); receipt_hash = hashlib.sha256(receipt_json.encode()).hexdigest()
    await db.execute(
        "UPDATE DashboardControlledOperation SET status='COMMITTED',resultingVersion=?,receiptJson=?,receiptHash=?,"
        "settledAt=? WHERE operationId=? AND status IN ('PENDING','REVIEW_REQUIRED')",
        (int(row[5]) + 1, receipt_json, receipt_hash, moment, str(operation_id)),
    )
    await db.execute(
        "UPDATE DashboardRecoveryControl SET status='RESOLVED',updatedAt=?,version=version+1 "
        "WHERE guildId=? AND entityType=? AND entityId=? AND lastOperationId=?",
        (moment, row[1], row[3], row[4], str(operation_id)),
    )
    await db.execute(
        "INSERT INTO DashboardOperatorAudit (auditId,guildId,executorUserId,permissionClass,operationType,targetType,"
        "targetId,requestId,previousVersion,resultingVersion,resultStatus,payloadHash,receiptHash,metadataJson,"
        "sourceRoute,createdAt) VALUES (?,?,?,'REVIEWED_RECOVERY_CONTROL','REVIEW_RESOLVE',?,?,?,?,?,'COMMITTED',"
        "?,?, '{}','/api/economy/recovery/resolve',?)",
        (str(uuid.uuid4()), row[1], row[2], row[3], row[4], row[0], int(row[5]), int(row[5]) + 1,
         row[6], receipt_hash, moment),
    )
    return receipt
