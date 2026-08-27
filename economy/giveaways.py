"""Layanan authoritative Giveaway V1 dan Activity Score Phase 8."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import asyncio
import hashlib
import json
import secrets
import uuid

import aiosqlite

from .constants import GIVEAWAY_ACTIVITY_MINIMUM, GIVEAWAY_CLAIM_SECONDS, GIVEAWAY_TICKET_ECY
from .database import configure_connection, ensure_system_accounts
from .ledger import AccountDelta, EconomyMutationError, apply_deltas_in_connection
from .phase8_schema import phase8_capability


ACTIVE_DAY_EVENTS = (
    "DAILY_CLAIM", "WEEKLY_CLAIM", "WORK_SUCCESS", "HUNT_COMPLETED",
    "DUNGEON_COMPLETED", "BOSS_ATTACK", "BOSS_PARTICIPATION",
    "DAILY_QUEST_COMPLETED", "WEEKLY_QUEST_COMPLETED", "VOICE_ACTIVITY_30M",
)


@dataclass(frozen=True)
class Phase8Result:
    ok: bool
    code: str
    message: str
    entity_id: str | None = None
    transaction_id: str | None = None
    replayed: bool = False
    receipt: dict | None = None


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


def _iso(value=None):
    return _dt(value).isoformat()


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _hash(value):
    raw = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def capped_activity_score(db, guild_id, user_id, *, as_of=None):
    upper = _dt(as_of)
    lower = upper - timedelta(days=30)
    params = (str(guild_id), str(user_id), lower.isoformat(), upper.isoformat())
    async with db.execute(
        "SELECT eventType,eventKey,occurredAt FROM EconomyActivityEvent WHERE guildId=? AND userId=? "
        "AND occurredAt>=? AND occurredAt<? ORDER BY occurredAt,eventId", params,
    ) as cursor:
        events = await cursor.fetchall()
    counts, active_day_counts = {}, {}
    for event_type, _, occurred_at in events:
        counts[event_type] = counts.get(event_type, 0) + 1
        if event_type in ACTIVE_DAY_EVENTS:
            day = str(occurred_at)[:10]
            active_day_counts[day] = active_day_counts.get(day, 0) + 1
    active_days = sum(1 for count in active_day_counts.values() if count >= 3)
    categories = {
        "dailyClaim": min(counts.get("DAILY_CLAIM", 0) * 2, 40),
        "dailyQuest": min(counts.get("DAILY_QUEST_COMPLETED", 0) * 4, 80),
        "qualifiedVoice": min(counts.get("VOICE_ACTIVITY_30M", 0) * 2, 40),
        "bossParticipation": min(counts.get("BOSS_PARTICIPATION", 0) * 5, 30),
        "dungeonCompletion": min(counts.get("DUNGEON_COMPLETED", 0) * 3, 30),
        "activeDays": min(active_days * 3, 60),
    }
    return {
        "score": sum(categories.values()), "categories": categories, "eventCounts": counts,
        "activeDays": active_days, "windowStart": lower.isoformat(), "windowEnd": upper.isoformat(),
        "sourceEventIdentities": [row[1] for row in events],
    }


async def build_eligibility_evidence(db, *, guild_id, user_id, account_created_at,
                                     guild_joined_at, present, is_bot, blacklisted, as_of=None):
    now = _dt(as_of)
    activity = await capped_activity_score(db, guild_id, user_id, as_of=now)
    created = _dt(account_created_at)
    joined = _dt(guild_joined_at)
    checks = {
        "accountAgeDays": (now - created).days,
        "guildMembershipDays": (now - joined).days,
        "present": bool(present), "isBot": bool(is_bot), "blacklisted": bool(blacklisted),
        "activityScore": activity["score"],
    }
    eligible = (checks["accountAgeDays"] >= 30 and checks["guildMembershipDays"] >= 14
                and checks["present"] and not checks["isBot"] and not checks["blacklisted"]
                and checks["activityScore"] >= GIVEAWAY_ACTIVITY_MINIMUM)
    evidence = {"guildId": str(guild_id), "userId": str(user_id), "asOf": now.isoformat(),
                "checks": checks, "activity": activity, "eligible": eligible}
    evidence["evidenceHash"] = _hash(evidence)
    return evidence


async def _feature_ready(db, guild_id):
    if not await phase8_capability(db):
        raise EconomyMutationError("schema_unavailable", "Schema Phase 8 belum siap.")
    async with db.execute(
        "SELECT paused FROM EconomyFeatureState WHERE guildId=? AND feature IN ('economy','giveaway') AND paused=1 LIMIT 1",
        (str(guild_id),),
    ) as cursor:
        if await cursor.fetchone():
            raise EconomyMutationError("paused", "Giveaway sedang dijeda.")


async def create_giveaway(db_path, *, guild_id, channel_id, host_id, request_id, prize,
                          duration_minutes, now=None):
    prize = " ".join(str(prize or "").split())
    if not 1 <= len(prize) <= 300:
        return Phase8Result(False, "invalid_prize", "Hadiah wajib 1-300 karakter.")
    if isinstance(duration_minutes, bool) or not 1 <= int(duration_minutes) <= 1440:
        return Phase8Result(False, "invalid_duration", "Durasi harus 1-1440 menit.")
    giveaway_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:giveaway:{guild_id}:{request_id}"))
    started = _dt(now)
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            await _feature_ready(db, guild_id)
            async with db.execute("SELECT giveawayId,status FROM GiveawayV1 WHERE guildId=? AND requestId=?",
                                  (str(guild_id), str(request_id))) as cursor:
                existing = await cursor.fetchone()
            if existing:
                await db.rollback()
                return Phase8Result(True, "already_created", "Giveaway ini sudah dibuat.", existing[0], replayed=True)
            async with db.execute(
                "SELECT COUNT(*) FROM GiveawayV1 WHERE guildId=? AND status IN ('ACTIVE','DRAW_PENDING','AWAITING_CLAIM','REVIEW_REQUIRED')",
                (str(guild_id),),
            ) as cursor:
                if int((await cursor.fetchone())[0]) >= 3:
                    raise EconomyMutationError("guild_limit", "Maksimum tiga Giveaway aktif per guild.")
            await db.execute(
                "INSERT INTO GiveawayV1 (giveawayId,requestId,guildId,channelId,hostId,prize,status,startsAt,endsAt,createdAt,updatedAt) "
                "VALUES (?,?,?,?,?,?,'ACTIVE',?,?,?,?)",
                (giveaway_id, str(request_id), str(guild_id), str(channel_id), str(host_id), prize,
                 started.isoformat(), (started + timedelta(minutes=int(duration_minutes))).isoformat(),
                 started.isoformat(), started.isoformat()),
            )
            await db.execute(
                "INSERT INTO GiveawayEscrow (giveawayId,guildId,paidTickets,amountEcy,status,updatedAt) VALUES (?,?,0,0,'OPEN',?)",
                (giveaway_id, str(guild_id), started.isoformat()),
            )
            await db.execute(
                "INSERT INTO Phase8Audit (auditId,guildId,actorId,actionType,entityType,entityId,receiptJson,createdAt) VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), str(guild_id), str(host_id), "CREATE", "GIVEAWAY", giveaway_id,
                 _json({"giveawayId": giveaway_id, "prize": prize}), started.isoformat()),
            )
            await db.commit()
        return Phase8Result(True, "created", "Giveaway V1 berhasil dibuat.", giveaway_id)
    except (EconomyMutationError, aiosqlite.Error) as exc:
        code = getattr(exc, "code", "database_error")
        return Phase8Result(False, code, getattr(exc, "message", "Giveaway gagal dibuat."))


async def set_giveaway_message(db_path, giveaway_id, message_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute(
            "UPDATE GiveawayV1 SET messageId=?,version=version+1,updatedAt=? WHERE giveawayId=? AND messageId IS NULL",
            (str(message_id), _iso(), str(giveaway_id)),
        )
        await db.commit()


async def enter_giveaway(db_path, *, guild_id, user_id, giveaway_id, request_id, evidence, now=None,
                         _lock_retry=0):
    if not evidence.get("eligible") or evidence.get("evidenceHash") != _hash({k: v for k, v in evidence.items() if k != "evidenceHash"}):
        return Phase8Result(False, "not_eligible", "Kamu belum memenuhi syarat Giveaway.")
    now_iso = _iso(now)
    transaction_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:giveaway-entry:{guild_id}:{request_id}"))
    ticket_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:giveaway-ticket:{giveaway_id}:{user_id}"))
    operation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:phase8-op:{guild_id}:{request_id}"))
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            await _feature_ready(db, guild_id)
            async with db.execute(
                "SELECT t.ticketId,t.entryTransactionId FROM GiveawayTicket t WHERE t.giveawayId=? AND t.userId=?",
                (str(giveaway_id), str(user_id)),
            ) as cursor:
                existing = await cursor.fetchone()
            if existing:
                await db.rollback()
                return Phase8Result(True, "already_entered", "Kamu sudah memiliki tiket Giveaway ini.",
                                    existing[0], existing[1], True)
            async with db.execute(
                "SELECT status,startsAt,endsAt FROM GiveawayV1 WHERE giveawayId=? AND guildId=?",
                (str(giveaway_id), str(guild_id)),
            ) as cursor:
                giveaway = await cursor.fetchone()
            if not giveaway or giveaway[0] != "ACTIVE" or not (_dt(giveaway[1]) <= _dt(now_iso) < _dt(giveaway[2])):
                raise EconomyMutationError("not_active", "Giveaway tidak aktif.")
            await db.execute(
                "INSERT INTO EconomyTransaction (transactionId,guildId,idempotencyKey,operation,source,referenceId,actorId,reasonCode,reasonText,metadataJson,status,createdAt) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,'PENDING',?)",
                (transaction_id, str(guild_id), f"phase8:giveaway-entry:{request_id}", "GIVEAWAY_ENTRY",
                 "phase8", str(giveaway_id), str(user_id), "TICKET", "Tiket Giveaway V1", "{}", now_iso),
            )
            await ensure_system_accounts(db, guild_id, now_iso)
            balances = await apply_deltas_in_connection(
                db, transaction_id=transaction_id, guild_id=guild_id, operation="GIVEAWAY_ENTRY",
                source="phase8", reference_id=giveaway_id, now=now_iso,
                deltas=(AccountDelta("USER", str(user_id), "ECY", -GIVEAWAY_TICKET_ECY, str(user_id)),
                        AccountDelta("SYSTEM", "ECY_GIVEAWAY", "ECY", GIVEAWAY_TICKET_ECY)),
            )
            receipt = {"ticketId": ticket_id, "giveawayId": str(giveaway_id), "amountEcy": GIVEAWAY_TICKET_ECY,
                       "transactionId": transaction_id, "balances": balances}
            await db.execute(
                "INSERT INTO GiveawayTicket (ticketId,giveawayId,guildId,userId,amountEcy,eligibilityEvidenceJson,evidenceHash,status,entryTransactionId,createdAt,updatedAt) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (ticket_id, str(giveaway_id), str(guild_id), str(user_id), GIVEAWAY_TICKET_ECY,
                 _json(evidence), evidence["evidenceHash"], "PAID", transaction_id, now_iso, now_iso),
            )
            await db.execute(
                "INSERT INTO GiveawayEligibilityEvidence (evidenceId,giveawayId,userId,stage,drawSequence,eligible,evidenceJson,evidenceHash,observedAt) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:giveaway-evidence:{giveaway_id}:{user_id}:ENTRY:0")),
                 str(giveaway_id), str(user_id), "ENTRY", 0, int(bool(evidence.get("eligible"))),
                 _json(evidence), evidence["evidenceHash"], now_iso),
            )
            cursor = await db.execute(
                "UPDATE GiveawayEscrow SET paidTickets=paidTickets+1,amountEcy=amountEcy+10000,version=version+1,updatedAt=? "
                "WHERE giveawayId=? AND status='OPEN'", (now_iso, str(giveaway_id)),
            )
            if cursor.rowcount != 1:
                raise EconomyMutationError("stale", "Escrow Giveaway berubah.")
            await db.execute(
                "INSERT INTO Phase8Operation (operationId,requestId,guildId,userId,operationType,entityId,reservationKey,outcomeJson,resultJson,transactionId,status,createdAt,settledAt) "
                "VALUES (?,?,?,?,?,?,NULL,?,?,?,?,?,?)",
                (operation_id, str(request_id), str(guild_id), str(user_id), "GIVEAWAY_ENTER", str(giveaway_id),
                 _json({"evidenceHash": evidence["evidenceHash"], "amountEcy": GIVEAWAY_TICKET_ECY}),
                 _json(receipt), transaction_id, "COMMITTED", now_iso, now_iso),
            )
            await db.execute(
                "UPDATE EconomyTransaction SET metadataJson=?,status='COMMITTED',committedAt=? WHERE transactionId=?",
                (_json({"result_code": "entered", "result_message": "Tiket Giveaway berhasil dibeli.",
                        "receipt": receipt, "balances": balances}), now_iso, transaction_id),
            )
            await db.commit()
        return Phase8Result(True, "entered", "Tiket Giveaway berhasil dibeli.", ticket_id,
                            transaction_id, receipt=receipt)
    except EconomyMutationError as exc:
        return Phase8Result(False, getattr(exc, "code", "database_error"),
                            getattr(exc, "message", "Pembelian tiket gagal."))
    except aiosqlite.Error as exc:
        if "locked" in str(exc).lower() and _lock_retry < 5:
            await asyncio.sleep(0.05 * (_lock_retry + 1))
            return await enter_giveaway(
                db_path, guild_id=guild_id, user_id=user_id, giveaway_id=giveaway_id,
                request_id=request_id, evidence=evidence, now=now, _lock_retry=_lock_retry + 1,
            )
        return Phase8Result(False, "database_error", "Pembelian tiket gagal.")


async def _allocation(db, giveaway_id, guild_id, now_iso):
    async with db.execute("SELECT amountEcy,status FROM GiveawayEscrow WHERE giveawayId=?", (str(giveaway_id),)) as cursor:
        escrow = await cursor.fetchone()
    if not escrow or escrow[1] == "ALLOCATED":
        async with db.execute("SELECT receiptJson,transactionId FROM GiveawayFundAllocation WHERE giveawayId=?",
                              (str(giveaway_id),)) as cursor:
            existing = await cursor.fetchone()
        return json.loads(existing[0]) if existing else {"totalEcy": 0}, existing[1] if existing else None
    total = int(escrow[0])
    reserve, burn = total // 10, total // 10
    retained = total - reserve - burn
    transaction_id = None
    if reserve or burn:
        transaction_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:giveaway-allocation:{giveaway_id}"))
        await db.execute(
            "INSERT INTO EconomyTransaction (transactionId,guildId,idempotencyKey,operation,source,referenceId,reasonCode,reasonText,metadataJson,status,createdAt) "
            "VALUES (?,?,?,?,?,?,?,?,?,'PENDING',?)",
            (transaction_id, str(guild_id), f"phase8:giveaway-allocation:{giveaway_id}", "GIVEAWAY_ALLOCATION",
             "phase8", str(giveaway_id), "COMPLETION", "Alokasi dana Giveaway", "{}", now_iso),
        )
        await apply_deltas_in_connection(
            db, transaction_id=transaction_id, guild_id=guild_id, operation="GIVEAWAY_ALLOCATION",
            source="phase8", reference_id=giveaway_id, now=now_iso,
            deltas=(AccountDelta("SYSTEM", "ECY_GIVEAWAY", "ECY", -(reserve + burn)),
                    AccountDelta("SYSTEM", "ECY_RESERVE", "ECY", reserve),
                    AccountDelta("SYSTEM", "ECY_BURN", "ECY", burn)),
        )
    receipt = {"giveawayId": str(giveaway_id), "totalEcy": total, "retainedEcy": retained,
               "reserveEcy": reserve, "burnEcy": burn, "transactionId": transaction_id}
    await db.execute(
        "INSERT INTO GiveawayFundAllocation (allocationId,giveawayId,totalEcy,retainedEcy,reserveEcy,burnEcy,transactionId,receiptJson,createdAt) VALUES (?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), str(giveaway_id), total, retained, reserve, burn, transaction_id, _json(receipt), now_iso),
    )
    await db.execute("UPDATE GiveawayTicket SET status='ALLOCATED',updatedAt=? WHERE giveawayId=? AND status='PAID'",
                     (now_iso, str(giveaway_id)))
    await db.execute("UPDATE GiveawayEscrow SET status='ALLOCATED',version=version+1,updatedAt=? WHERE giveawayId=?",
                     (now_iso, str(giveaway_id)))
    if transaction_id:
        await db.execute("UPDATE EconomyTransaction SET metadataJson=?,status='COMMITTED',committedAt=? WHERE transactionId=?",
                         (_json({"result_code": "allocated", "receipt": receipt}), now_iso, transaction_id))
    return receipt, transaction_id


async def draw_giveaway(db_path, *, guild_id, giveaway_id, request_id, eligible_user_ids,
                        participant_evidence, random_source=None, now=None):
    random_source = random_source or secrets
    now_dt, now_iso = _dt(now), _iso(now)
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            if not await phase8_capability(db):
                raise EconomyMutationError("schema_unavailable", "Schema Phase 8 belum siap.")
            async with db.execute(
                "SELECT status,drawSequence FROM GiveawayV1 WHERE giveawayId=? AND guildId=?",
                (str(giveaway_id), str(guild_id)),
            ) as cursor:
                giveaway = await cursor.fetchone()
            if not giveaway:
                raise EconomyMutationError("not_found", "Giveaway tidak ditemukan.")
            async with db.execute("SELECT drawId,winnerId,receiptJson FROM GiveawayDraw WHERE requestId=?",
                                  (str(request_id),)) as cursor:
                replay = await cursor.fetchone()
            if replay:
                await db.rollback()
                return Phase8Result(True, "draw_replayed", "Hasil draw sudah tersedia.", replay[0],
                                    replayed=True, receipt=json.loads(replay[2]))
            if giveaway[0] not in {"ACTIVE", "DRAW_PENDING"}:
                raise EconomyMutationError("invalid_status", "Giveaway sudah memiliki hasil authoritative.")
            paid = {row[0] for row in await (await db.execute(
                "SELECT userId FROM GiveawayTicket WHERE giveawayId=? AND status='PAID'", (str(giveaway_id),)
            )).fetchall()}
            excluded = {row[0] for row in await (await db.execute(
                "SELECT userId FROM GiveawayWinner WHERE giveawayId=?", (str(giveaway_id),)
            )).fetchall()}
            candidates = sorted(paid - excluded, key=lambda value: int(value))
            evidence = {user_id: participant_evidence.get(user_id, {"eligible": False}) for user_id in candidates}
            pool = [user_id for user_id in candidates
                    if user_id in {str(value) for value in eligible_user_ids}
                    and evidence.get(user_id, {}).get("eligible")]
            index = random_source.randbelow(len(pool)) if pool else None
            winner_user_id = pool[index] if index is not None else None
            sequence = int(giveaway[1]) + 1
            draw_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:giveaway-draw:{giveaway_id}:{sequence}"))
            claim_deadline = (now_dt + timedelta(seconds=GIVEAWAY_CLAIM_SECONDS)).isoformat() if winner_user_id else None
            allocation, transaction_id = await _allocation(db, giveaway_id, guild_id, now_iso)
            receipt = {"drawId": draw_id, "giveawayId": str(giveaway_id), "sequence": sequence,
                       "poolHash": _hash(pool), "winnerId": winner_user_id,
                       "claimDeadline": claim_deadline, "allocation": allocation}
            await db.execute(
                "INSERT INTO GiveawayDraw (drawId,giveawayId,sequence,requestId,participantEvidenceJson,poolJson,poolHash,randomIndex,winnerId,noEligibleParticipants,receiptJson,createdAt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (draw_id, str(giveaway_id), sequence, str(request_id), _json(evidence), _json(pool),
                 receipt["poolHash"], index, winner_user_id, int(not pool), _json(receipt), now_iso),
            )
            for participant_id, snapshot in evidence.items():
                evidence_hash = snapshot.get("evidenceHash") or _hash(snapshot)
                await db.execute(
                    "INSERT INTO GiveawayEligibilityEvidence (evidenceId,giveawayId,userId,stage,drawSequence,eligible,evidenceJson,evidenceHash,observedAt) VALUES (?,?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:giveaway-evidence:{giveaway_id}:{participant_id}:DRAW:{sequence}")),
                     str(giveaway_id), participant_id, "DRAW", sequence,
                     int(bool(snapshot.get("eligible"))), _json(snapshot), evidence_hash, now_iso),
                )
            status = "AWAITING_CLAIM" if winner_user_id else "COMPLETED"
            if winner_user_id:
                winner_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:giveaway-winner:{giveaway_id}:{sequence}"))
                await db.execute(
                    "INSERT INTO GiveawayWinner (winnerId,giveawayId,drawId,userId,sequence,status,eligibilityEvidenceJson,claimDeadline,createdAt,updatedAt) VALUES (?,?,?,?,?,'AWAITING_CLAIM',?,?,?,?)",
                    (winner_id, str(giveaway_id), draw_id, winner_user_id, sequence,
                     _json(evidence[winner_user_id]), claim_deadline, now_iso, now_iso),
                )
            await db.execute(
                "UPDATE GiveawayV1 SET status=?,currentWinnerId=?,claimDeadline=?,drawSequence=?,version=version+1,updatedAt=? WHERE giveawayId=?",
                (status, winner_user_id, claim_deadline, sequence, now_iso, str(giveaway_id)),
            )
            await db.execute(
                "INSERT INTO Phase8NotificationOutbox (outboxId,eventKey,guildId,entityType,entityId,payloadJson,status,createdAt) VALUES (?,?,?,?,?,?,'PENDING',?)",
                (str(uuid.uuid4()), f"giveaway-draw:{draw_id}", str(guild_id), "GIVEAWAY_DRAW", draw_id,
                 _json(receipt), now_iso),
            )
            await db.commit()
        return Phase8Result(True, "drawn" if winner_user_id else "no_eligible", "Draw Giveaway selesai.",
                            draw_id, transaction_id, receipt=receipt)
    except (EconomyMutationError, aiosqlite.Error) as exc:
        return Phase8Result(False, getattr(exc, "code", "database_error"),
                            getattr(exc, "message", "Draw Giveaway gagal."))


async def claim_giveaway(db_path, *, giveaway_id, user_id, now=None):
    now_iso = _iso(now)
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT winnerId,status,claimDeadline FROM GiveawayWinner WHERE giveawayId=? AND userId=? ORDER BY sequence DESC LIMIT 1",
                (str(giveaway_id), str(user_id)),
            ) as cursor:
                winner = await cursor.fetchone()
            if not winner:
                raise EconomyMutationError("not_winner", "Kamu bukan pemenang Giveaway ini.")
            async with db.execute("SELECT receiptJson FROM GiveawayClaim WHERE winnerId=?", (winner[0],)) as cursor:
                existing = await cursor.fetchone()
            if existing:
                await db.rollback()
                return Phase8Result(True, "already_claimed", "Kemenangan sudah diakui.", winner[0],
                                    replayed=True, receipt=json.loads(existing[0]))
            if winner[1] != "AWAITING_CLAIM" or _dt(now_iso) >= _dt(winner[2]):
                raise EconomyMutationError("claim_expired", "Batas klaim sudah berakhir.")
            receipt = {"giveawayId": str(giveaway_id), "winnerId": winner[0], "userId": str(user_id),
                       "acknowledgedAt": now_iso}
            await db.execute(
                "INSERT INTO GiveawayClaim (claimId,giveawayId,winnerId,userId,status,receiptJson,claimedAt) VALUES (?,?,?,?, 'ACKNOWLEDGED',?,?)",
                (str(uuid.uuid4()), str(giveaway_id), winner[0], str(user_id), _json(receipt), now_iso),
            )
            await db.execute("UPDATE GiveawayWinner SET status='CLAIMED',updatedAt=? WHERE winnerId=?",
                             (now_iso, winner[0]))
            await db.execute("UPDATE GiveawayV1 SET status='COMPLETED',version=version+1,updatedAt=? WHERE giveawayId=?",
                             (now_iso, str(giveaway_id)))
            await db.commit()
        return Phase8Result(True, "claimed", "Kemenangan Giveaway berhasil diakui.", winner[0], receipt=receipt)
    except (EconomyMutationError, aiosqlite.Error) as exc:
        return Phase8Result(False, getattr(exc, "code", "database_error"),
                            getattr(exc, "message", "Klaim Giveaway gagal."))


async def cancel_giveaway(db_path, *, guild_id, giveaway_id, actor_id, request_id, reason, now=None):
    reason = " ".join(str(reason or "").split())
    if not 1 <= len(reason) <= 300:
        return Phase8Result(False, "invalid_reason", "Alasan pembatalan wajib 1-300 karakter.")
    now_iso = _iso(now)
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            if not await phase8_capability(db):
                raise EconomyMutationError("schema_unavailable", "Schema Phase 8 belum siap.")
            async with db.execute("SELECT status FROM GiveawayV1 WHERE giveawayId=? AND guildId=?",
                                  (str(giveaway_id), str(guild_id))) as cursor:
                row = await cursor.fetchone()
            if not row:
                raise EconomyMutationError("not_found", "Giveaway tidak ditemukan.")
            if row[0] == "CANCELLED":
                await db.rollback()
                return Phase8Result(True, "already_cancelled", "Giveaway sudah dibatalkan.", str(giveaway_id), replayed=True)
            if row[0] not in {"ACTIVE", "DRAW_PENDING"}:
                raise EconomyMutationError("invalid_status", "Giveaway tidak dapat dibatalkan pada status ini.")
            tickets = await (await db.execute(
                "SELECT ticketId,userId,amountEcy FROM GiveawayTicket WHERE giveawayId=? AND status='PAID' ORDER BY userId",
                (str(giveaway_id),),
            )).fetchall()
            for ticket_id, user_id, amount in tickets:
                transaction_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:giveaway-refund:{ticket_id}"))
                await db.execute(
                    "INSERT INTO EconomyTransaction (transactionId,guildId,idempotencyKey,operation,source,referenceId,actorId,reasonCode,reasonText,metadataJson,status,createdAt) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,'PENDING',?)",
                    (transaction_id, str(guild_id), f"phase8:giveaway-refund:{ticket_id}", "GIVEAWAY_REFUND",
                     "phase8", ticket_id, str(actor_id), "CANCELLED", reason, "{}", now_iso),
                )
                balances = await apply_deltas_in_connection(
                    db, transaction_id=transaction_id, guild_id=guild_id, operation="GIVEAWAY_REFUND",
                    source="phase8", reference_id=ticket_id, now=now_iso,
                    deltas=(AccountDelta("SYSTEM", "ECY_GIVEAWAY", "ECY", -int(amount)),
                            AccountDelta("USER", str(user_id), "ECY", int(amount), str(user_id))),
                )
                receipt = {"ticketId": ticket_id, "userId": user_id, "amountEcy": int(amount),
                           "transactionId": transaction_id, "balances": balances}
                await db.execute(
                    "INSERT INTO GiveawayRefund (refundId,giveawayId,ticketId,userId,amountEcy,transactionId,receiptJson,createdAt) VALUES (?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), str(giveaway_id), ticket_id, user_id, int(amount), transaction_id,
                     _json(receipt), now_iso),
                )
                await db.execute("UPDATE GiveawayTicket SET status='REFUNDED',refundTransactionId=?,updatedAt=? WHERE ticketId=?",
                                 (transaction_id, now_iso, ticket_id))
                await db.execute("UPDATE EconomyTransaction SET metadataJson=?,status='COMMITTED',committedAt=? WHERE transactionId=?",
                                 (_json({"result_code": "refunded", "receipt": receipt, "balances": balances}),
                                  now_iso, transaction_id))
            await db.execute("UPDATE GiveawayEscrow SET status='REFUNDED',version=version+1,updatedAt=? WHERE giveawayId=?",
                             (now_iso, str(giveaway_id)))
            await db.execute("UPDATE GiveawayV1 SET status='CANCELLED',version=version+1,updatedAt=? WHERE giveawayId=?",
                             (now_iso, str(giveaway_id)))
            audit = {"giveawayId": str(giveaway_id), "refundCount": len(tickets), "reason": reason,
                     "requestId": str(request_id)}
            await db.execute(
                "INSERT INTO Phase8Audit (auditId,guildId,actorId,actionType,entityType,entityId,receiptJson,createdAt) VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), str(guild_id), str(actor_id), "CANCEL", "GIVEAWAY", str(giveaway_id),
                 _json(audit), now_iso),
            )
            await db.commit()
        return Phase8Result(True, "cancelled", f"Giveaway dibatalkan; {len(tickets)} tiket dikembalikan.",
                            str(giveaway_id), receipt=audit)
    except (EconomyMutationError, aiosqlite.Error) as exc:
        return Phase8Result(False, getattr(exc, "code", "database_error"),
                            getattr(exc, "message", "Pembatalan Giveaway gagal."))


async def record_winner_review(db_path, *, guild_id, giveaway_id, reviewer_id, reason_code,
                               evidence_reference, evidence_type, prior_winner_state,
                               metadata=None, now=None):
    reason_code = str(reason_code).upper()
    if reason_code not in {"CLAIM_EXPIRED", "WINNER_DEPARTED", "WINNER_INVALID", "RULE_VIOLATION"}:
        return Phase8Result(False, "invalid_reason", "Kode alasan redraw tidak valid.")
    if reason_code == "RULE_VIOLATION" and evidence_type != "DISCORD_MESSAGE":
        return Phase8Result(False, "evidence_required", "Pelanggaran aturan memerlukan bukti pesan Discord terverifikasi.")
    metadata = metadata or {}
    if reason_code == "RULE_VIOLATION" and not all(
        str(metadata.get(key, "")).strip() for key in ("channelId", "messageId", "authorId", "contentHash")
    ):
        return Phase8Result(False, "evidence_required", "Bukti pesan Discord belum lengkap.")
    if reason_code == "WINNER_DEPARTED" and metadata.get("memberLookupFound") is not False:
        return Phase8Result(False, "evidence_required", "Winner departed wajib dibuktikan oleh lookup member.")
    if reason_code == "WINNER_INVALID" and metadata.get("eligible") is not False:
        return Phase8Result(False, "evidence_required", "Winner invalid wajib dibuktikan oleh eligibility terkini.")
    if not str(evidence_reference or "").strip():
        return Phase8Result(False, "evidence_required", "Referensi bukti wajib diisi.")
    now_iso = _iso(now)
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            "SELECT w.winnerId FROM GiveawayV1 g JOIN GiveawayWinner w "
            "ON w.giveawayId=g.giveawayId AND w.userId=g.currentWinnerId AND w.status='AWAITING_CLAIM' "
            "WHERE g.giveawayId=? AND g.guildId=?",
            (str(giveaway_id), str(guild_id)),
        ) as cursor:
            row = await cursor.fetchone()
        if not row or not row[0]:
            await db.rollback()
            return Phase8Result(False, "no_winner", "Giveaway tidak memiliki pemenang aktif.")
        canonical = {"reasonCode": reason_code, "evidenceType": evidence_type,
                     "evidenceReference": str(evidence_reference), "metadata": metadata}
        evidence_hash = _hash(canonical)
        review_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                                   f"w2e:giveaway-review:{giveaway_id}:{row[0]}:{reason_code}:{evidence_hash}"))
        receipt = {"reviewId": review_id, "giveawayId": str(giveaway_id), "winnerId": row[0],
                   "reasonCode": reason_code, "evidenceHash": evidence_hash, "reviewerId": str(reviewer_id)}
        await db.execute(
            "INSERT INTO GiveawayWinnerReview (reviewId,giveawayId,winnerId,reasonCode,evidenceType,evidenceReference,evidenceHash,reviewerId,reviewedAt,priorWinnerStateJson,sanitizedMetadataJson,auditReceiptJson) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (review_id, str(giveaway_id), row[0], reason_code, evidence_type, str(evidence_reference),
             evidence_hash, str(reviewer_id), now_iso, _json(prior_winner_state), _json(metadata), _json(receipt)),
        )
        await db.commit()
    return Phase8Result(True, "review_recorded", "Bukti redraw berhasil direkam.", review_id, receipt=receipt)


async def redraw_giveaway(db_path, *, guild_id, giveaway_id, reviewer_id, review_id,
                          request_id, eligible_user_ids, participant_evidence,
                          random_source=None, now=None):
    random_source = random_source or secrets
    now_iso = _iso(now)
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT r.winnerId,r.reasonCode,r.consumed,w.userId,g.drawSequence,g.status "
                "FROM GiveawayWinnerReview r JOIN GiveawayWinner w ON w.winnerId=r.winnerId "
                "JOIN GiveawayV1 g ON g.giveawayId=r.giveawayId "
                "WHERE r.reviewId=? AND r.giveawayId=? AND g.guildId=? "
                "AND g.currentWinnerId=w.userId AND w.status='AWAITING_CLAIM'",
                (str(review_id), str(giveaway_id), str(guild_id)),
            ) as cursor:
                review = await cursor.fetchone()
            if not review or int(review[2]):
                raise EconomyMutationError("invalid_review", "Bukti redraw tidak valid atau sudah dipakai.")
            if review[5] != "AWAITING_CLAIM":
                raise EconomyMutationError("invalid_status", "Giveaway tidak menunggu klaim.")
            if review[1] == "CLAIM_EXPIRED":
                async with db.execute("SELECT claimDeadline FROM GiveawayWinner WHERE winnerId=?", (review[0],)) as cursor:
                    deadline = await cursor.fetchone()
                if not deadline or _dt(now_iso) < _dt(deadline[0]):
                    raise EconomyMutationError("claim_not_expired", "Deadline klaim belum berakhir.")
            paid = {row[0] for row in await (await db.execute(
                "SELECT userId FROM GiveawayTicket WHERE giveawayId=? AND status='ALLOCATED'", (str(giveaway_id),)
            )).fetchall()}
            excluded = {row[0] for row in await (await db.execute(
                "SELECT userId FROM GiveawayWinner WHERE giveawayId=?", (str(giveaway_id),)
            )).fetchall()}
            candidates = sorted(paid - excluded, key=lambda value: int(value))
            evidence = {uid: participant_evidence.get(uid, {"eligible": False}) for uid in candidates}
            pool = [uid for uid in candidates if uid in {str(value) for value in eligible_user_ids}
                    and evidence.get(uid, {}).get("eligible")]
            index = random_source.randbelow(len(pool)) if pool else None
            new_user = pool[index] if index is not None else None
            sequence = int(review[4]) + 1
            draw_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:giveaway-draw:{giveaway_id}:{sequence}"))
            claim_deadline = (_dt(now_iso) + timedelta(seconds=GIVEAWAY_CLAIM_SECONDS)).isoformat() if new_user else None
            receipt = {"drawId": draw_id, "giveawayId": str(giveaway_id), "sequence": sequence,
                       "redrawReviewId": str(review_id), "poolHash": _hash(pool), "winnerId": new_user,
                       "claimDeadline": claim_deadline}
            await db.execute("UPDATE GiveawayWinnerReview SET consumed=1,consumedAt=? WHERE reviewId=? AND consumed=0",
                             (now_iso, str(review_id)))
            await db.execute("UPDATE GiveawayWinner SET status='INVALIDATED',updatedAt=? WHERE winnerId=?",
                             (now_iso, review[0]))
            await db.execute(
                "INSERT INTO GiveawayDraw (drawId,giveawayId,sequence,requestId,participantEvidenceJson,poolJson,poolHash,randomIndex,winnerId,noEligibleParticipants,receiptJson,createdAt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (draw_id, str(giveaway_id), sequence, str(request_id), _json(evidence), _json(pool),
                 receipt["poolHash"], index, new_user, int(not pool), _json(receipt), now_iso),
            )
            for participant_id, snapshot in evidence.items():
                evidence_hash = snapshot.get("evidenceHash") or _hash(snapshot)
                await db.execute(
                    "INSERT INTO GiveawayEligibilityEvidence (evidenceId,giveawayId,userId,stage,drawSequence,eligible,evidenceJson,evidenceHash,observedAt) VALUES (?,?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:giveaway-evidence:{giveaway_id}:{participant_id}:REDRAW:{sequence}")),
                     str(giveaway_id), participant_id, "REDRAW", sequence,
                     int(bool(snapshot.get("eligible"))), _json(snapshot), evidence_hash, now_iso),
                )
            status = "AWAITING_CLAIM" if new_user else "COMPLETED"
            if new_user:
                winner_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:giveaway-winner:{giveaway_id}:{sequence}"))
                await db.execute(
                    "INSERT INTO GiveawayWinner (winnerId,giveawayId,drawId,userId,sequence,status,eligibilityEvidenceJson,claimDeadline,createdAt,updatedAt) VALUES (?,?,?,?,?,'AWAITING_CLAIM',?,?,?,?)",
                    (winner_id, str(giveaway_id), draw_id, new_user, sequence, _json(evidence[new_user]),
                     claim_deadline, now_iso, now_iso),
                )
            await db.execute(
                "UPDATE GiveawayV1 SET status=?,currentWinnerId=?,claimDeadline=?,drawSequence=?,version=version+1,updatedAt=? WHERE giveawayId=?",
                (status, new_user, claim_deadline, sequence, now_iso, str(giveaway_id)),
            )
            await db.execute(
                "INSERT INTO Phase8Audit (auditId,guildId,actorId,actionType,entityType,entityId,receiptJson,createdAt) VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), str(guild_id), str(reviewer_id), "REDRAW", "GIVEAWAY", str(giveaway_id),
                 _json(receipt), now_iso),
            )
            await db.commit()
        return Phase8Result(True, "redrawn" if new_user else "no_eligible", "Redraw selesai.",
                            draw_id, receipt=receipt)
    except (EconomyMutationError, aiosqlite.Error) as exc:
        return Phase8Result(False, getattr(exc, "code", "database_error"),
                            getattr(exc, "message", "Redraw gagal."))


async def list_giveaways(db_path, guild_id, *, limit=25):
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            if not await phase8_capability(db):
                return []
            async with db.execute(
                "SELECT giveawayId,prize,status,endsAt,currentWinnerId FROM GiveawayV1 WHERE guildId=? ORDER BY createdAt DESC LIMIT ?",
                (str(guild_id), max(1, min(int(limit), 100))),
            ) as cursor:
                return await cursor.fetchall()
    except aiosqlite.Error:
        return []
