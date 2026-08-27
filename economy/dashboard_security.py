"""Pure and database-backed security primitives for the dashboard boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import uuid

from .phase9a_schema import PERMISSION_CLASSES, phase9a_capability


SIGNATURE_PREFIX = "W2E-P9A"
SIGNATURE_TTL_SECONDS = 30
SIGNATURE_CLOCK_SKEW_SECONDS = 5
SAFE_ERROR_CODES = {
    "invalid_request", "unauthenticated", "forbidden", "expired", "rate_limited",
    "version_conflict", "request_identity_conflict", "capability_unavailable", "internal_error",
}
SAFE_METADATA_KEYS = {"reason", "routeGroup", "permissionClass", "operationType", "targetType"}
SNOWFLAKE_RE = re.compile(r"^[1-9][0-9]{5,24}$")


class DashboardSecurityError(RuntimeError):
    def __init__(self, code, status=400):
        if code not in SAFE_ERROR_CODES:
            code = "internal_error"
            status = 500
        super().__init__(code)
        self.code = code
        self.status = int(status)


def utc_now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat()


def parse_iso(value):
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_snowflake(value, field="id"):
    text = str(value or "")
    if not SNOWFLAKE_RE.fullmatch(text):
        raise DashboardSecurityError("invalid_request", 400)
    return text


def _validate_json_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise DashboardSecurityError("invalid_request", 400)
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise DashboardSecurityError("invalid_request", 400)
        for item in value.values():
            _validate_json_value(item)
        return
    raise DashboardSecurityError("invalid_request", 400)


def canonical_json(value):
    _validate_json_value(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def payload_hash(payload):
    return sha256_text(canonical_json(payload))


def keyed_hash(secret, value):
    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
    if len(secret_bytes) < 32:
        raise DashboardSecurityError("capability_unavailable", 503)
    return hmac.new(secret_bytes, str(value).encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class InternalEnvelope:
    key_id: str
    method: str
    canonical_route: str
    guild_id: str
    actor_id: str
    permission_class: str
    request_id: str
    issued_at: int
    expires_at: int
    nonce: str
    payload_hash: str
    session_token_hash: str
    session_version: int

    def signing_text(self):
        return "\n".join((
            SIGNATURE_PREFIX, self.key_id, self.method.upper(), self.canonical_route,
            self.guild_id, self.actor_id, self.permission_class, self.request_id,
            str(self.issued_at), str(self.expires_at), self.nonce, self.payload_hash,
            self.session_token_hash, str(self.session_version),
        ))

    def as_headers(self, secret):
        signature = hmac.new(
            secret.encode("utf-8") if isinstance(secret, str) else bytes(secret),
            self.signing_text().encode("utf-8"), hashlib.sha256,
        ).hexdigest()
        return {
            "X-W2E-Key-Id": self.key_id,
            "X-W2E-Method": self.method.upper(),
            "X-W2E-Route": self.canonical_route,
            "X-W2E-Guild-Id": self.guild_id,
            "X-W2E-Actor-Id": self.actor_id,
            "X-W2E-Permission": self.permission_class,
            "X-W2E-Request-Id": self.request_id,
            "X-W2E-Issued-At": str(self.issued_at),
            "X-W2E-Expires-At": str(self.expires_at),
            "X-W2E-Nonce": self.nonce,
            "X-W2E-Payload-Hash": self.payload_hash,
            "X-W2E-Session-Hash": self.session_token_hash,
            "X-W2E-Session-Version": str(self.session_version),
            "X-W2E-Signature": signature,
        }


HEADER_MAP = {
    "key_id": "X-W2E-Key-Id", "method": "X-W2E-Method", "canonical_route": "X-W2E-Route",
    "guild_id": "X-W2E-Guild-Id", "actor_id": "X-W2E-Actor-Id",
    "permission_class": "X-W2E-Permission", "request_id": "X-W2E-Request-Id",
    "issued_at": "X-W2E-Issued-At", "expires_at": "X-W2E-Expires-At", "nonce": "X-W2E-Nonce",
    "payload_hash": "X-W2E-Payload-Hash", "session_token_hash": "X-W2E-Session-Hash",
    "session_version": "X-W2E-Session-Version",
}


def envelope_from_headers(headers):
    try:
        values = {name: headers[header] for name, header in HEADER_MAP.items()}
        values["issued_at"] = int(values["issued_at"])
        values["expires_at"] = int(values["expires_at"])
        values["session_version"] = int(values["session_version"])
        envelope = InternalEnvelope(**values)
    except (KeyError, TypeError, ValueError):
        raise DashboardSecurityError("unauthenticated", 401)
    if envelope.permission_class not in PERMISSION_CLASSES:
        raise DashboardSecurityError("forbidden", 403)
    return envelope


def verify_envelope_signature(envelope, signature, secret, *, method, route, payload, now=None):
    now = int((now or utc_now()).timestamp())
    if envelope.method != method.upper() or envelope.canonical_route != route:
        raise DashboardSecurityError("unauthenticated", 401)
    if envelope.payload_hash != payload_hash(payload):
        raise DashboardSecurityError("unauthenticated", 401)
    if envelope.expires_at - envelope.issued_at > SIGNATURE_TTL_SECONDS:
        raise DashboardSecurityError("expired", 401)
    if envelope.issued_at > now + SIGNATURE_CLOCK_SKEW_SECONDS or envelope.expires_at < now - SIGNATURE_CLOCK_SKEW_SECONDS:
        raise DashboardSecurityError("expired", 401)
    expected = hmac.new(
        secret.encode("utf-8") if isinstance(secret, str) else bytes(secret),
        envelope.signing_text().encode("utf-8"), hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, str(signature or "")):
        raise DashboardSecurityError("unauthenticated", 401)


def sanitized_metadata(metadata=None):
    metadata = metadata or {}
    return {key: str(value)[:160] for key, value in metadata.items() if key in SAFE_METADATA_KEYS}


async def record_security_event(db, *, event_type, code, route, guild_id=None, actor_id=None,
                                request_id=None, source_ip_hash=None, metadata=None, now=None):
    if not await phase9a_capability(db):
        return
    await db.execute(
        "INSERT INTO DashboardSecurityEvent "
        "(eventId,guildId,actorId,eventType,safeErrorCode,requestId,route,sourceIpHash,metadataJson,createdAt) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), guild_id, actor_id, str(event_type)[:80], code if code in SAFE_ERROR_CODES else "internal_error",
         request_id, str(route)[:240], source_ip_hash,
         canonical_json(sanitized_metadata(metadata)), iso(now or utc_now())),
    )


async def consume_internal_nonce(db, envelope, *, now=None):
    moment = now or utc_now()
    nonce_hash = sha256_text(envelope.nonce)
    try:
        await db.execute(
            "INSERT INTO DashboardInternalNonce "
            "(keyId,nonceHash,requestId,canonicalRoute,createdAt,expiresAt,consumedAt) VALUES (?,?,?,?,?,?,?)",
            (envelope.key_id, nonce_hash, envelope.request_id, envelope.canonical_route,
             iso(moment), iso(datetime.fromtimestamp(envelope.expires_at, timezone.utc)), iso(moment)),
        )
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise DashboardSecurityError("unauthenticated", 401) from exc
        raise


async def enforce_rate_limit(db, *, scope_hash, route_group, limit, window_seconds, now=None):
    moment = now or utc_now()
    timestamp = int(moment.timestamp())
    start = timestamp - (timestamp % int(window_seconds))
    start_iso = iso(datetime.fromtimestamp(start, timezone.utc))
    expires = iso(datetime.fromtimestamp(start + int(window_seconds), timezone.utc))
    await db.execute(
        "INSERT INTO DashboardRateLimitBucket (scopeHash,routeGroup,windowStartedAt,requestCount,expiresAt) "
        "VALUES (?,?,?,1,?) ON CONFLICT(scopeHash,routeGroup,windowStartedAt) "
        "DO UPDATE SET requestCount=requestCount+1",
        (scope_hash, route_group, start_iso, expires),
    )
    async with db.execute(
        "SELECT requestCount FROM DashboardRateLimitBucket WHERE scopeHash=? AND routeGroup=? AND windowStartedAt=?",
        (scope_hash, route_group, start_iso),
    ) as cursor:
        count = (await cursor.fetchone())[0]
    if count > int(limit):
        raise DashboardSecurityError("rate_limited", 429)
