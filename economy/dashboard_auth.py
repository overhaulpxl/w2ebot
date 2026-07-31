"""Dashboard identities, sessions, OAuth attempts, permissions, and CSRF."""

from __future__ import annotations

from datetime import timedelta
import secrets
import uuid

from .dashboard_security import (
    DashboardSecurityError, iso, keyed_hash, parse_iso, sha256_text, utc_now, validate_snowflake,
)
from .phase9a_schema import PERMISSION_CLASSES, phase9a_capability


SESSION_IDLE_MINUTES = 30
SESSION_ABSOLUTE_HOURS = 8
OAUTH_ATTEMPT_MINUTES = 10
CSRF_MINUTES = 10


async def has_permission(db, guild_id, user_id, permission_class):
    if permission_class not in PERMISSION_CLASSES:
        return False
    async with db.execute(
        "SELECT 1 FROM DashboardOperatorPermission WHERE guildId=? AND userId=? "
        "AND permissionClass=? AND status='ACTIVE'",
        (str(guild_id), str(user_id), permission_class),
    ) as cursor:
        return await cursor.fetchone() is not None


async def list_permissions(db, guild_id, user_id):
    async with db.execute(
        "SELECT permissionClass FROM DashboardOperatorPermission WHERE guildId=? AND userId=? "
        "AND status='ACTIVE' ORDER BY permissionClass", (str(guild_id), str(user_id)),
    ) as cursor:
        return [row[0] for row in await cursor.fetchall()]


async def create_oauth_attempt(db, *, state_hash, pkce_challenge, ip_hash, return_path="/", now=None):
    if not await phase9a_capability(db):
        raise DashboardSecurityError("capability_unavailable", 503)
    if return_path != "/" or len(state_hash) != 64 or not pkce_challenge:
        raise DashboardSecurityError("invalid_request", 400)
    moment = now or utc_now()
    attempt_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO DashboardOAuthAttempt "
        "(attemptId,stateHash,pkceChallenge,returnPath,ipHash,status,createdAt,expiresAt) "
        "VALUES (?,?,?,?,?,'PENDING',?,?)",
        (attempt_id, state_hash, pkce_challenge, return_path, ip_hash, iso(moment),
         iso(moment + timedelta(minutes=OAUTH_ATTEMPT_MINUTES))),
    )
    return attempt_id


async def consume_oauth_attempt(db, *, state_hash, pkce_challenge, now=None):
    moment = now or utc_now()
    async with db.execute(
        "SELECT attemptId,pkceChallenge,returnPath,expiresAt,status,ipHash "
        "FROM DashboardOAuthAttempt WHERE stateHash=?",
        (state_hash,),
    ) as cursor:
        row = await cursor.fetchone()
    if not row or row[4] != "PENDING" or row[1] != pkce_challenge:
        raise DashboardSecurityError("unauthenticated", 401)
    if parse_iso(row[3]) <= moment:
        await db.execute(
            "UPDATE DashboardOAuthAttempt SET status='EXPIRED',consumedAt=? WHERE attemptId=? AND status='PENDING'",
            (iso(moment), row[0]),
        )
        raise DashboardSecurityError("expired", 401)
    cursor = await db.execute(
        "UPDATE DashboardOAuthAttempt SET status='CONSUMED',consumedAt=? WHERE attemptId=? AND status='PENDING'",
        (iso(moment), row[0]),
    )
    if cursor.rowcount != 1:
        raise DashboardSecurityError("unauthenticated", 401)
    return {"attemptId": row[0], "returnPath": row[2], "ipHash": row[5]}


async def establish_session(db, *, guild_id, user_id, token_hash, session_key_id,
                            discord_administrator=False, now=None):
    guild_id = validate_snowflake(guild_id, "guildId")
    user_id = validate_snowflake(user_id, "userId")
    if len(token_hash) != 64:
        raise DashboardSecurityError("invalid_request", 400)
    if not await phase9a_capability(db):
        raise DashboardSecurityError("capability_unavailable", 503)
    explicit_view = await has_permission(db, guild_id, user_id, "DASHBOARD_VIEW")
    if not discord_administrator and not explicit_view:
        raise DashboardSecurityError("forbidden", 403)
    moment = now or utc_now()
    await db.execute(
        "INSERT INTO DashboardIdentity (guildId,userId,status,createdAt,updatedAt) VALUES (?,?,'ACTIVE',?,?) "
        "ON CONFLICT(guildId,userId) DO UPDATE SET status='ACTIVE',updatedAt=excluded.updatedAt,version=version+1",
        (guild_id, user_id, iso(moment), iso(moment)),
    )
    session_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO DashboardSession "
        "(sessionId,tokenHash,guildId,userId,signingKeyId,status,createdAt,lastSeenAt,idleExpiresAt,absoluteExpiresAt) "
        "VALUES (?,?,?,?,?,'ACTIVE',?,?,?,?)",
        (session_id, token_hash, guild_id, user_id, session_key_id, iso(moment), iso(moment),
         iso(moment + timedelta(minutes=SESSION_IDLE_MINUTES)),
         iso(moment + timedelta(hours=SESSION_ABSOLUTE_HOURS))),
    )
    return session_id


async def validate_session(db, *, token_hash, required_permission="DASHBOARD_VIEW",
                           discord_member=True, discord_administrator=False, now=None, touch=True,
                           expected_version=None):
    if not await phase9a_capability(db):
        raise DashboardSecurityError("capability_unavailable", 503)
    moment = now or utc_now()
    async with db.execute(
        "SELECT sessionId,guildId,userId,status,idleExpiresAt,absoluteExpiresAt,version,signingKeyId "
        "FROM DashboardSession WHERE tokenHash=?", (token_hash,),
    ) as cursor:
        row = await cursor.fetchone()
    if not row or row[3] != "ACTIVE":
        raise DashboardSecurityError("unauthenticated", 401)
    if expected_version is not None and row[6] != int(expected_version):
        raise DashboardSecurityError("unauthenticated", 401)
    if parse_iso(row[4]) <= moment or parse_iso(row[5]) <= moment:
        await db.execute(
            "UPDATE DashboardSession SET status='EXPIRED',revokedAt=?,revokeReasonCode='SESSION_EXPIRED',version=version+1 "
            "WHERE sessionId=? AND status='ACTIVE'", (iso(moment), row[0]),
        )
        raise DashboardSecurityError("expired", 401)
    if not discord_member:
        raise DashboardSecurityError("forbidden", 403)
    permissions = await list_permissions(db, row[1], row[2])
    view_allowed = discord_administrator or "DASHBOARD_VIEW" in permissions
    if not view_allowed:
        raise DashboardSecurityError("forbidden", 403)
    if required_permission != "DASHBOARD_VIEW" and required_permission not in permissions:
        raise DashboardSecurityError("forbidden", 403)
    if touch:
        idle_expiry = min(moment + timedelta(minutes=SESSION_IDLE_MINUTES), parse_iso(row[5]))
        cursor = await db.execute(
            "UPDATE DashboardSession SET lastSeenAt=?,idleExpiresAt=? "
            "WHERE sessionId=? AND status='ACTIVE' AND version=?",
            (iso(moment), iso(idle_expiry), row[0], row[6]),
        )
        if cursor.rowcount != 1:
            raise DashboardSecurityError("unauthenticated", 401)
        version = row[6]
    else:
        version = row[6]
    return {"sessionId": row[0], "guildId": row[1], "userId": row[2], "permissions": permissions,
            "version": version, "idleExpiresAt": iso(min(moment + timedelta(minutes=SESSION_IDLE_MINUTES), parse_iso(row[5]))),
            "absoluteExpiresAt": row[5], "signingKeyId": row[7]}


async def revoke_session(db, *, session_id, reason_code, now=None, expected_version=None):
    moment = now or utc_now()
    sql = ("UPDATE DashboardSession SET status='REVOKED',revokedAt=?,revokeReasonCode=?,version=version+1 "
           "WHERE sessionId=? AND status='ACTIVE'")
    params = [iso(moment), str(reason_code)[:64], str(session_id)]
    if expected_version is not None:
        sql += " AND version=?"
        params.append(int(expected_version))
    cursor = await db.execute(sql, tuple(params))
    if cursor.rowcount != 1:
        raise DashboardSecurityError("version_conflict", 409)
    await db.execute(
        "UPDATE DashboardCsrfToken SET status='REVOKED' WHERE sessionId=? AND status='ACTIVE'",
        (str(session_id),),
    )


async def rotate_session(db, *, session_id, new_token_hash, expected_version, now=None):
    if len(str(new_token_hash)) != 64:
        raise DashboardSecurityError("invalid_request", 400)
    moment = now or utc_now()
    async with db.execute(
        "SELECT absoluteExpiresAt FROM DashboardSession WHERE sessionId=? AND status='ACTIVE' AND version=?",
        (str(session_id), int(expected_version)),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise DashboardSecurityError("version_conflict", 409)
    idle_expiry = min(moment + timedelta(minutes=SESSION_IDLE_MINUTES), parse_iso(row[0]))
    cursor = await db.execute(
        "UPDATE DashboardSession SET tokenHash=?,lastSeenAt=?,idleExpiresAt=?,version=version+1 "
        "WHERE sessionId=? AND status='ACTIVE' AND version=?",
        (str(new_token_hash), iso(moment), iso(idle_expiry),
         str(session_id), int(expected_version)),
    )
    if cursor.rowcount != 1:
        raise DashboardSecurityError("version_conflict", 409)
    await db.execute(
        "UPDATE DashboardCsrfToken SET status='REVOKED' WHERE sessionId=? AND status='ACTIVE'",
        (str(session_id),),
    )
    return int(expected_version) + 1


async def issue_csrf(db, *, session_id, method, canonical_route, request_id, session_hash_key, now=None):
    if method.upper() not in {"POST", "PUT", "PATCH", "DELETE"} or not canonical_route.startswith("/"):
        raise DashboardSecurityError("invalid_request", 400)
    moment = now or utc_now()
    raw = secrets.token_urlsafe(32)
    token_hash = keyed_hash(session_hash_key, raw)
    csrf_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO DashboardCsrfToken "
        "(csrfId,tokenHash,sessionId,method,canonicalRoute,requestId,status,createdAt,expiresAt) "
        "VALUES (?,?,?,?,?,?,'ACTIVE',?,?)",
        (csrf_id, token_hash, session_id, method.upper(), canonical_route, request_id,
         iso(moment), iso(moment + timedelta(minutes=CSRF_MINUTES))),
    )
    return {"token": raw, "expiresAt": iso(moment + timedelta(minutes=CSRF_MINUTES))}


async def consume_csrf(db, *, raw_token, session_id, method, canonical_route, request_id,
                       session_hash_key, now=None):
    moment = now or utc_now()
    token_hash = keyed_hash(session_hash_key, raw_token)
    async with db.execute(
        "SELECT csrfId,status,expiresAt,sessionId,method,canonicalRoute,requestId FROM DashboardCsrfToken WHERE tokenHash=?",
        (token_hash,),
    ) as cursor:
        row = await cursor.fetchone()
    if (not row or row[1] != "ACTIVE" or row[3] != session_id or row[4] != method.upper()
            or row[5] != canonical_route or row[6] != request_id):
        raise DashboardSecurityError("forbidden", 403)
    if parse_iso(row[2]) <= moment:
        await db.execute("UPDATE DashboardCsrfToken SET status='EXPIRED' WHERE csrfId=?", (row[0],))
        raise DashboardSecurityError("expired", 403)
    cursor = await db.execute(
        "UPDATE DashboardCsrfToken SET status='CONSUMED',consumedAt=? WHERE csrfId=? AND status='ACTIVE'",
        (iso(moment), row[0]),
    )
    if cursor.rowcount != 1:
        raise DashboardSecurityError("forbidden", 403)
