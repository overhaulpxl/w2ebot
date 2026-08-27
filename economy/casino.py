"""Service-layer Casino V1: reservasi, settlement, bankroll, dan otorisasi."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import uuid
from types import SimpleNamespace

import aiosqlite

from .casino_games import (
    SecureRng, apply_blackjack_action, blackjack_allowed_actions, blackjack_natural,
    liability_for, new_blackjack_plan, roll_box, roll_coinflip, roll_gacha,
    roll_number, roll_rps, roll_slot, settle_blackjack_plan,
)
from .constants import (
    CASINO_AUTH_CLASSES, CASINO_EXPOSURE_BPS, CASINO_MAX_UNRESOLVED_GUILD,
    CASINO_MAX_WAGER_ECY, CASINO_MIN_WAGER_ECY, CASINO_WAGER_STEP_ECY,
    ECONOMY_MAX_AMOUNT, SQLITE_MAX_INTEGER,
)
from .database import configure_connection, ensure_system_accounts
from .controls import normalize_control_reason, set_feature_paused
from .ledger import AccountDelta, EconomyMutationError, EconomyResult, execute_transaction
from .phase5_schema import phase5_capability
from .treasury import system_seed


UNRESOLVED_SESSION_STATES = ("RESERVED", "ACTIVE", "SETTLEMENT_PENDING", "REVIEW_REQUIRED")


@dataclass(frozen=True)
class CasinoResult:
    ok: bool
    code: str
    message: str
    session_id: str | None = None
    request_id: str | None = None
    receipt: dict | None = None
    replayed: bool = False


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def new_request_id():
    return uuid.uuid4().hex


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _blackjack_public_state(state):
    return {
        "playerHands": [list(hand.get("cards", ())) for hand in state.get("hands", ())],
        "dealerUpCard": (state.get("dealer") or [None])[0],
        "allowedActions": list(blackjack_allowed_actions(state)),
        "state": state.get("state"),
    }


def validate_stake(game, stake):
    game = str(game).upper()
    if isinstance(stake, bool) or not isinstance(stake, int):
        raise ValueError("Stake Casino wajib berupa integer.")
    if game in {"GACHA", "BOX"}:
        if stake != 1_000:
            raise ValueError("Harga produk Casino ini tetap 1.000 ECY.")
    elif stake < CASINO_MIN_WAGER_ECY or stake > CASINO_MAX_WAGER_ECY or stake % CASINO_WAGER_STEP_ECY:
        raise ValueError("Stake harus 1.000-500.000 ECY dalam kelipatan 1.000.")
    liability = liability_for(game, stake)
    if liability < 0 or liability > min(ECONOMY_MAX_AMOUNT, SQLITE_MAX_INTEGER):
        raise ValueError("Liability Casino melewati batas integer ekonomi.")
    return liability


def validate_game_payload(game, payload):
    game = str(game).upper()
    payload = dict(payload or {})
    if game == "COINFLIP" and str(payload.get("choice", "")).strip().lower() not in {"angka", "gambar"}:
        raise ValueError("Pilihan Coinflip harus angka atau gambar.")
    if game == "RPS" and str(payload.get("choice", "")).strip().lower() not in {"batu", "gunting", "kertas"}:
        raise ValueError("Pilihan RPS harus batu, gunting, atau kertas.")
    if game == "NUMBER":
        guess = payload.get("guess")
        if isinstance(guess, bool) or not isinstance(guess, int) or not 1 <= guess <= 20:
            raise ValueError("Tebakan harus integer 1 sampai 20.")
    if game not in {"BLACKJACK", "SLOT", "COINFLIP", "RPS", "NUMBER", "GACHA", "BOX"}:
        raise ValueError("Permainan Casino tidak dikenal.")
    return payload


def effective_maximum_stake(game, available_bankroll):
    game = str(game).upper()
    if game in {"GACHA", "BOX"}:
        return 1_000
    available = max(0, int(available_bankroll))
    cap = available * CASINO_EXPOSURE_BPS // 10_000
    accepted = 0
    for stake in range(CASINO_MIN_WAGER_ECY, CASINO_MAX_WAGER_ECY + 1, CASINO_WAGER_STEP_ECY):
        liability = liability_for(game, stake)
        if liability <= cap and liability <= available:
            accepted = stake
        else:
            break
    return accepted


async def _bankroll_state(db, guild_id):
    rows = await db.fetch(
        "SELECT balance FROM EconomySystemAccount WHERE guildId=$1 AND accountCode='ECY_CASINO'", str(guild_id),),
        row = await cursor.fetchone()
    bankroll = int(row[0]) if row else 0
    options_table = await db.fetchrow(
        "SELECT COALESCE(SUM(liabilityEcy),0) FROM CasinoBankrollReservation "
        "WHERE guildId=$1 AND status IN ('ACTIVE','REVIEW_REQUIRED')", str(guild_id),),
        reserved = int((await cursor.fetchone()[0])
    row = await db.fetchrow(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='EternalOptionReservation'"
    options_reserved = 0
    if options_table:
        pause = await db.fetchrow(
            "SELECT COALESCE(SUM(liabilityEcy),0) FROM EternalOptionReservation "
            "WHERE guildId=$1 AND status IN ('ACTIVE','REVIEW_REQUIRED')", str(guild_id),),
            options_reserved = int((await cursor.fetchone()[0])
    reserved += options_reserved
    available = bankroll - reserved
    return {"bankrollEcy": bankroll, "reservedLiabilityEcy": reserved,
            "optionsReservedLiabilityEcy": options_reserved,
            "availableBankrollEcy": available,
            "exposureCapEcy": max(0, available) * CASINO_EXPOSURE_BPS // 10_000}


async def casino_status(db_path, guild_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        capable = await phase5_capability(db)
        if not capable:
            return {"schemaCapable": False, "seeded": False, "paused": True,
                    "bankrollEcy": 0, "reservedLiabilityEcy": 0,
                    "availableBankrollEcy": 0, "exposureCapEcy": 0,
                    "unresolvedSessions": 0, "reviewRequired": 0}
        state = await _bankroll_state(db, guild_id)
        async with db.execute(
            "SELECT paused FROM EconomyFeatureState WHERE guildId=$1 AND feature='casino'", str(guild_id),),
        )
        replay = await db.fetchrow(
            "SELECT COUNT(*) FROM EconomySeedMarker WHERE guildId=$1 AND accountCode='ECY_CASINO'", str(guild_id),),
            seeded = int((await cursor.fetchone()[0]) > 0
        async with db.execute(
            "SELECT COUNT(*),SUM(CASE WHEN status='REVIEW_REQUIRED' THEN 1 ELSE 0 END) "
            "FROM CasinoSession WHERE guildId=$1 AND status IN ('RESERVED','ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED')", str(guild_id),),
            count, review = await cursor.fetchone()
    return {"schemaCapable": True, "seeded": seeded, "paused": bool(pause and pause[0]),
            **state, "unresolvedSessions": int(count), "reviewRequired": int(review or 0)}


def _planned_outcome(game, stake, payload, rng):
    game = str(game).upper()
    if game == "SLOT":
        return roll_slot(stake, rng)
    if game == "COINFLIP":
        return roll_coinflip(stake, payload.get("choice"), rng)
    if game == "RPS":
        return roll_rps(stake, payload.get("choice"), rng)
    if game == "NUMBER":
        return roll_number(stake, payload.get("guess"), rng)
    if game == "GACHA":
        return roll_gacha(rng)
    if game == "BOX":
        return roll_box(rng)
    if game == "BLACKJACK":
        return new_blackjack_plan(stake, rng)
    raise ValueError("Permainan Casino tidak dikenal.")


async def reserve_session(db_path, *, guild_id, user_id, request_id, game, stake,
                          payload=None, rng=None, now=None):
    game = str(game).upper()
    request_id = str(request_id)
    if not request_id or len(request_id) > 100:
        return CasinoResult(False, "invalid_request", "Identitas permintaan Casino tidak valid.")
    try:
        liability = validate_stake(game, stake)
        payload = validate_game_payload(game, payload)
    except ValueError as exc:
        return CasinoResult(False, "invalid_input", str(exc), request_id=request_id)
    rng = rng or SecureRng()
    session_id = str(uuid.uuid4()
    settlement_id = str(uuid.uuid4()
    reservation_id = str(uuid.uuid4())
    timestamp = now or utc_now()
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            if not await phase5_capability(db):
                await db.rollback()
                return CasinoResult(False, "schema_unavailable", "Schema Casino Phase 5 belum siap.", request_id=request_id)
            async with db.execute(
                "SELECT sessionId,status FROM CasinoSession WHERE requestId=$1", request_id,),
            )
            if replay:
                await db.rollback()
                return await get_session_result(db_path, replay[0], replayed=True)
            unresolved = await db.fetchrow(
                "SELECT sessionId,requestId FROM CasinoSession WHERE guildId=$1 AND userId=$2 "
                "AND status IN ('RESERVED','ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED') LIMIT 1", str(guild_id), str(user_id),
            )
            if unresolved:
                await db.rollback()
                return CasinoResult(False, "unresolved_session", "Selesaikan sesi Casino yang masih aktif.",
                                    unresolved[0], unresolved[1])
            previous = await db.fetchrow(
                "SELECT gameType,settledAt FROM CasinoSession WHERE guildId=$1 AND userId=$2 AND status='COMMITTED' "
                "ORDER BY settledAt DESC LIMIT 1", (str(guild_id), str(user_id),
            )
            if previous and previous[1]:
                committed_at = datetime.fromisoformat(str(previous[1]).replace("Z", "+00:00"))
                requested_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                cooldown = 5 if previous[0] in {"BLACKJACK", "GACHA", "BOX"} else 3
                remaining = cooldown - (requested_at - committed_at).total_seconds()
                if remaining > 0:
                    await db.rollback()
                    return CasinoResult(False, "cooldown", f"Tunggu {int(remaining) + 1} detik sebelum wager berikutnya.", request_id=request_id)
            wallet = await db.fetchrow(
                "SELECT COUNT(*) FROM CasinoSession WHERE guildId=$1 "
                "AND status IN ('RESERVED','ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED')", str(guild_id),),
                if int((await cursor.fetchone()[0]) >= CASINO_MAX_UNRESOLVED_GUILD:
                    await db.rollback()
                    return CasinoResult(False, "guild_limit", "Guild sudah memiliki 100 sesi Casino belum selesai.", request_id=request_id)
            async with db.execute(
                "SELECT paused FROM EconomyFeatureState WHERE guildId=$1 AND feature IN ('economy','casino') AND paused=1 LIMIT 1", str(guild_id),),
            )
                        if row:
                    await db.rollback()
                    return CasinoResult(False, "paused", "Casino sedang dijeda.", request_id=request_id)
            row = await db.fetchrow(
                "SELECT 1 FROM EconomySeedMarker WHERE guildId=$1 AND accountCode='ECY_CASINO' LIMIT 1", str(guild_id),),
                if not await cursor.fetchone():
                    await db.rollback()
                    return CasinoResult(False, "unseeded", "Bankroll Casino belum di-seed.", request_id=request_id)
            state = await _bankroll_state(db, guild_id)
            if liability > state["availableBankrollEcy"] or liability > state["exposureCapEcy"]:
                maximum = effective_maximum_stake(game, state["availableBankrollEcy"])
                await db.rollback()
                return CasinoResult(False, "exposure_limit",
                                    f"Liability melewati exposure. Maksimum efektif: {maximum:,} ECY.",
                                    request_id=request_id,
                                    receipt={"effectiveMaximumStakeEcy": maximum, **state})
            async with db.execute(
                "SELECT ecyBalance FROM EconomyWallet WHERE guildId=$1 AND userId=$2",
                (str(guild_id), str(user_id),
            )
            if not wallet or int(wallet[0]) < stake:
                await db.rollback()
                return CasinoResult(False, "insufficient_funds", "Saldo ECY tidak mencukupi.", request_id=request_id)
            outcome = _planned_outcome(game, stake, payload, rng)
            status = "ACTIVE" if game == "BLACKJACK" else "RESERVED"
            await db.execute(
                "INSERT INTO CasinoSession "
                "(sessionId,requestId,guildId,userId,gameType,stakeEcy,maximumGrossLiabilityEcy,outcomeJson,stateJson,status,reservationKey,createdAt) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)", session_id, request_id, str(guild_id), str(user_id), game, stake, liability,
                 _json(outcome), _json(outcome if game == "BLACKJACK" else {}), status,
                 f"casino:{guild_id}:{user_id}", timestamp),
            )
            await db.execute(
                "INSERT INTO CasinoSettlement (settlementId,sessionId,stakeEcy,grossPayoutEcy,status,createdAt) "
                "VALUES ($1,$2,$3,$4, 'PENDING',$5)",
                (settlement_id, session_id, stake, int(outcome.get("grossPayoutEcy", 0), timestamp),
            )
            if liability > 0:
                await db.execute(
                    "INSERT INTO CasinoBankrollReservation "
                    "(reservationId,sessionId,guildId,liabilityEcy,status,createdAt) VALUES ($1,$2,$3,$4, 'ACTIVE',$5)", reservation_id, session_id, str(guild_id), liability, timestamp),
                )
            await db.commit()
    except aiosqlite.IntegrityError:
        return CasinoResult(False, "concurrent_conflict", "Permintaan Casino bersamaan memakai reservasi yang sama.", request_id=request_id)
    if game == "BLACKJACK":
        entry = await _commit_blackjack_entry(
            db_path, session_id=session_id, guild_id=guild_id, user_id=user_id,
            request_id=request_id, stake=stake,
        )
        if not entry.ok:
            await _void_unfunded_session(db_path, session_id=session_id, reason_code=entry.code)
            return CasinoResult(False, entry.code, entry.message, session_id, request_id)
        if outcome.get("state") == "DEALER_TURN":
            return await settle_session(db_path, session_id=session_id)
        return CasinoResult(True, "active", "Sesi Blackjack aktif.", session_id, request_id,
                            _blackjack_public_state(json.loads((await _read_session_state(db_path, session_id)))
    settled = await settle_session(db_path, session_id=session_id)
    if not settled.ok and settled.code in {
        "insufficient_funds", "paused", "invalid_account", "invalid_amount", "invalid_entries", "unbalanced",
    }:
        await _void_unfunded_session(db_path, session_id=session_id, reason_code=settled.code)
    return settled


async def _read_session_state(db_path, session_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        row = await db.fetchrow("SELECT stateJson FROM CasinoSession WHERE sessionId=$1", str(session_id)
    return row[0] if row else "{}"


async def _void_unfunded_session(db_path, *, session_id, reason_code):
    now = utc_now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            "UPDATE CasinoSettlement SET status='VOID',voidReasonCode=$1,settledAt=$2 WHERE sessionId=$3 AND status='PENDING'", str(reason_code), now, str(session_id)),
        )
        await db.execute(
            "UPDATE CasinoBankrollReservation SET status='RELEASED',releasedAt=$1 WHERE sessionId=$2 AND status='ACTIVE'", now, str(session_id),
        )
        await db.execute(
            "UPDATE CasinoSession SET status='VOID',reservationKey=NULL,settledAt=$1,lastErrorCode=$2 "
            "WHERE sessionId=$1 AND status IN ('RESERVED','ACTIVE')", now, str(reason_code), str(session_id),
        )
        await db.commit()


async def _commit_blackjack_entry(db_path, *, session_id, guild_id, user_id, request_id, stake):
    async def commit_entry(db, context):
        row = await db.fetchrow(
            "SELECT stateJson,version FROM CasinoSession WHERE sessionId=$1 AND status='ACTIVE'", str(session_id),),
        )
        if not row:
            raise EconomyMutationError("stale", "Sesi Blackjack berubah sebelum acceptance.")
        state = json.loads(row[0])
        state["entryTransactionId"] = context.transaction_id
        state["debitedStakeEcy"] = int(stake)
        await db.execute(
            "INSERT INTO CasinoSessionAction "
            "(actionId,sessionId,requestId,sequence,actorId,actionType,actionJson,resultJson,transactionId,createdAt) "
            "VALUES ($1,$2,$3,$4,$5,'ACCEPT',$6,$7,$8,$9)", str(uuid.uuid4(), str(session_id), f"entry:{request_id}", 1, str(user_id),
             _json({"stakeEcy": stake}), _json({"accepted": True}), context.transaction_id, context.now),
        )
        cursor = await db.execute(
            "UPDATE CasinoSession SET stateJson=$1,version=version+1 WHERE sessionId=$2 AND status='ACTIVE' AND version=$3", _json(state), str(session_id), int(row[1]),
        )
        if cursor.rowcount != 1:
            raise EconomyMutationError("stale", "Sesi Blackjack berubah saat acceptance.")
        return {"sessionId": str(session_id), "entryStakeEcy": int(stake)}
    return await execute_transaction(
        db_path, guild_id=guild_id, idempotency_key=f"casino:blackjack:entry:{request_id}",
        operation="CASINO_BLACKJACK_ENTRY", source="CASINO_V1", actor_id=user_id,
        reason="Acceptance stake Blackjack", reason_code="casino_blackjack_entry",
        reference_id=session_id,
        deltas=(AccountDelta("USER", str(user_id), "ECY", -stake, str(user_id),
                AccountDelta("SYSTEM", "ECY_CASINO", "ECY", stake)),
        feature="casino", before_commit=commit_entry,
        success_code="blackjack_entry", success_message="Stake awal Blackjack berhasil diproses.",
    )


async def get_session_result(db_path, session_id, *, replayed=False):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        row = await db.fetchrow(
            "SELECT s.requestId,s.status,x.receiptJson,s.gameType,s.stateJson FROM CasinoSession s "
            "JOIN CasinoSettlement x ON x.sessionId=s.sessionId WHERE s.sessionId=$1", str(session_id),),
        )
    if not row:
        return CasinoResult(False, "not_found", "Sesi Casino tidak ditemukan.", str(session_id)
    receipt = json.loads(row[2]) if row[2] else None
    if row[1] == "COMMITTED":
        return CasinoResult(True, "committed", "Sesi Casino sudah diselesaikan.", str(session_id), row[0], receipt, replayed)
    if row[1] == "REVIEW_REQUIRED":
        return CasinoResult(False, "review_required", "Sesi Casino memerlukan pemeriksaan recovery.", str(session_id), row[0])
    state = json.loads(row[4])
    public = _blackjack_public_state(state) if row[3] == "BLACKJACK" else {"game": row[3], "status": row[1]}
    return CasinoResult(True, "active", "Sesi Casino masih aktif.", str(session_id), row[0], public, replayed)


async def settle_session(db_path, *, session_id, result_override=None, recovery_authorized=False):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        row = await db.fetchrow(
            "SELECT s.guildId,s.userId,s.gameType,s.stakeEcy,s.status,s.outcomeJson,s.stateJson,s.requestId,"
            "x.grossPayoutEcy,x.status FROM CasinoSession s JOIN CasinoSettlement x ON x.sessionId=s.sessionId "
            "WHERE s.sessionId=$1", str(session_id),),
        )
    if not row:
        return CasinoResult(False, "not_found", "Sesi Casino tidak ditemukan.", str(session_id)
    guild_id, user_id, game, base_stake, status, outcome_raw, state_raw, request_id, stored_payout, settlement_status = row
    if status == "COMMITTED":
        return await get_session_result(db_path, session_id, replayed=True)
    if (status == "REVIEW_REQUIRED" or settlement_status == "REVIEW_REQUIRED") and not recovery_authorized:
        return CasinoResult(False, "review_required", "Sesi Casino memerlukan pemeriksaan recovery.", str(session_id), request_id)
    outcome = json.loads(outcome_raw)
    state = json.loads(state_raw)
    if game == "BLACKJACK":
        if result_override is None:
            if state.get("state") == "PLAYER_TURN":
                return CasinoResult(False, "active", "Blackjack masih menunggu aksi.", str(session_id), request_id)
            result = settle_blackjack_plan(state) if state.get("state") != "SETTLED" else state.get("result")
        else:
            result = result_override
        stake = sum(int(hand["stakeEcy"]) for hand in state["hands"])
        payout = int(result["grossPayoutEcy"])
    else:
        result = outcome
        stake = int(base_stake)
        payout = int(stored_payout)
    receipt = {"sessionId": str(session_id), "requestId": request_id, "game": game,
               "stakeEcy": stake, "grossPayoutEcy": payout, "result": result}
    if game == "BLACKJACK":
        receipt["entryTransactionId"] = state.get("entryTransactionId")
        receipt["debitedStakeEcy"] = int(state.get("debitedStakeEcy", base_stake))
        receipt["playerHands"] = [hand["cards"] for hand in state["hands"]]
        receipt["dealerCards"] = result.get("dealer", state.get("dealer", []))
        deltas = []
    else:
        deltas = [
            AccountDelta("USER", str(user_id), "ECY", -stake, str(user_id)),
            AccountDelta("SYSTEM", "ECY_CASINO", "ECY", stake),
        ]
    if payout:
        deltas.extend((
            AccountDelta("SYSTEM", "ECY_CASINO", "ECY", -payout),
            AccountDelta("USER", str(user_id), "ECY", payout, str(user_id)))

    async def finalize(db, context):
        locked = await db.fetchrow(
            "SELECT s.status,x.status,r.status FROM CasinoSession s JOIN CasinoSettlement x ON x.sessionId=s.sessionId "
            "LEFT JOIN CasinoBankrollReservation r ON r.sessionId=s.sessionId WHERE s.sessionId=$1", str(session_id),),
        )
        session_states = {"RESERVED", "ACTIVE", "SETTLEMENT_PENDING"} | ({"REVIEW_REQUIRED"} if recovery_authorized else set()
        settlement_states = {"PENDING"} | ({"REVIEW_REQUIRED"} if recovery_authorized else set())
        reservation_states = {"ACTIVE"} | ({"REVIEW_REQUIRED"} if recovery_authorized else set())
        reservation_valid = locked and (
            locked[2] in reservation_states or (game == "GACHA" and locked[2] is None)
        if not locked or locked[0] not in session_states or locked[1] not in settlement_states or not reservation_valid:
            raise EconomyMutationError("stale", "Status sesi Casino berubah sebelum settlement.")
        cursor = await db.execute(
            "UPDATE CasinoSettlement SET transactionId=$1,grossPayoutEcy=$2,status='COMMITTED',receiptJson=$3,settledAt=$4 "
            "WHERE sessionId=$1 AND status IN ('PENDING','REVIEW_REQUIRED') AND receiptJson IS NULL", context.transaction_id, payout, _json(receipt), context.now, str(session_id)),
        )
        if cursor.rowcount != 1:
            raise EconomyMutationError("stale", "Settlement Casino tidak dapat diselesaikan.")
        await db.execute(
            "UPDATE CasinoBankrollReservation SET status='RELEASED',releasedAt=$1 WHERE sessionId=$2 AND status IN ('ACTIVE','REVIEW_REQUIRED')", context.now, str(session_id),
        )
        await db.execute(
            "UPDATE CasinoSession SET status='COMMITTED',reservationKey=NULL,settledAt=$1,version=version+1,stateJson=$2 "
            "WHERE sessionId=$1 AND status IN ('RESERVED','ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED')", context.now, _json({**state, "result": result, "state": "SETTLED"}), str(session_id),
        )
        await db.execute(
            "INSERT INTO CasinoNotificationOutbox "
            "(eventId,eventKey,guildId,userId,sessionId,payloadJson,status,createdAt) VALUES ($1,$2,$3,$4,$5,$6,'PENDING',$7)", str(uuid.uuid4(), f"casino:settled:{session_id}", str(guild_id), str(user_id), str(session_id), _json(receipt), context.now),
        )
        return {"casinoReceipt": receipt}

    if not deltas:
        transaction_id = state.get("entryTransactionId")
        if not transaction_id:
            return CasinoResult(False, "review_required", "Transaction acceptance Blackjack tidak ditemukan.", str(session_id), request_id)
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            try:
                context = SimpleNamespace(
                    transaction_id=transaction_id,
                    now=utc_now(),
                )
                await finalize(db, context)
                await db.commit()
            except Exception:
                await db.rollback()
                return CasinoResult(False, "database_failure", "Settlement Blackjack gagal sebelum perubahan disimpan.", str(session_id), request_id)
        return await get_session_result(db_path, session_id)

    result_tx = await execute_transaction(
        db_path, guild_id=guild_id, idempotency_key=f"casino:settle:{request_id}",
        operation="CASINO_SETTLEMENT", source="CASINO_V1", actor_id=user_id,
        reason="Settlement sesi Casino V1", reason_code="casino_settlement",
        reference_id=session_id, deltas=tuple(deltas), feature=None if recovery_authorized else "casino",
        success_code="casino_committed", success_message="Sesi Casino berhasil diselesaikan.",
        before_commit=finalize,
    )
    if not result_tx.ok:
        return CasinoResult(False, result_tx.code, result_tx.message, str(session_id), request_id)
    return await get_session_result(db_path, session_id, replayed=result_tx.replayed)


async def resolve_review_session(db_path, *, guild_id, actor_id, session_id, resolution, request_id, reason,
                                 authorization_override=False):
    if not authorization_override and not await is_casino_authorized(db_path, guild_id, actor_id, "CASINO_RECOVERY"):
        return CasinoResult(False, "unauthorized", "CASINO_RECOVERY diperlukan untuk resolusi review.", str(session_id))
    resolution = str(resolution).upper()
    if resolution == "RETRY":
        return await settle_session(db_path, session_id=session_id, recovery_authorized=True)
    if resolution != "REFUND":
        return CasinoResult(False, "invalid_resolution", "Resolusi harus RETRY atau REFUND.", str(session_id))
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        session = await db.fetchrow(
            "SELECT status FROM CasinoSession WHERE sessionId=$1 AND guildId=$2", str(session_id), str(guild_id),
        )
        if not session or session[0] != "REVIEW_REQUIRED":
            return CasinoResult(False, "invalid_status", "Sesi tidak berada pada REVIEW_REQUIRED.", str(session_id))
        row = await db.fetchrow(
            "SELECT l.accountKind,l.accountId,l.userId,l.currency,SUM(l.amount) "
            "FROM EconomyLedger l JOIN EconomyTransaction t ON t.transactionId=l.transactionId "
            "WHERE t.guildId=$1 AND t.referenceId=$2 AND t.status='COMMITTED' "
            "GROUP BY l.accountKind,l.accountId,l.userId,l.currency HAVING SUM(l.amount)<>0", str(guild_id), str(session_id),
        )
    if not rows:
        now = utc_now()
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                "UPDATE CasinoSettlement SET status='VOID',voidReasonCode='review_no_mutation',settledAt=$1 "
                "WHERE sessionId=$1 AND status='REVIEW_REQUIRED'", now, str(session_id),
            )
            await db.execute(
                "UPDATE CasinoBankrollReservation SET status='RELEASED',releasedAt=$1 WHERE sessionId=$2 AND status='REVIEW_REQUIRED'", now, str(session_id),
            )
            await db.execute(
                "UPDATE CasinoSession SET status='VOID',reservationKey=NULL,settledAt=$1 WHERE sessionId=$2 AND status='REVIEW_REQUIRED'", now, str(session_id),
            )
            await db.execute(
                "UPDATE CasinoRecoveryReview SET status='RESOLVED',resolvedAt=$1 WHERE entityId=$2 AND status='OPEN'", now, str(session_id),
            )
            await db.commit()
        return CasinoResult(True, "void", "Sesi tanpa mutasi ekonomi telah di-void.", str(session_id))
    deltas = tuple(AccountDelta(row[0], row[1], row[3], -int(row[4]), row[2]) for row in rows)

    async def finalize_refund(db, context):
        await db.execute(
            "UPDATE CasinoSettlement SET status='VOID',transactionId=$1,voidReasonCode='review_refund',settledAt=$2 "
            "WHERE sessionId=$1 AND status='REVIEW_REQUIRED'", context.transaction_id, context.now, str(session_id),
        )
        await db.execute(
            "UPDATE CasinoBankrollReservation SET status='RELEASED',releasedAt=$1 WHERE sessionId=$2 AND status='REVIEW_REQUIRED'", context.now, str(session_id),
        )
        await db.execute(
            "UPDATE CasinoSession SET status='VOID',reservationKey=NULL,settledAt=$1 WHERE sessionId=$2 AND status='REVIEW_REQUIRED'", context.now, str(session_id),
        )
        await db.execute(
            "UPDATE CasinoRecoveryReview SET status='RESOLVED',resolvedAt=$1 WHERE entityId=$2 AND status='OPEN'", context.now, str(session_id),
        )
        return {"sessionId": str(session_id), "resolution": "REFUND"}

    transaction = await execute_transaction(
        db_path, guild_id=guild_id, idempotency_key=f"casino:recovery:{request_id}",
        operation="CASINO_RECOVERY_REFUND", source="CASINO_RECOVERY", actor_id=actor_id,
        reason=reason, reason_code="casino_review_refund", reference_id=session_id,
        deltas=deltas, feature=None, before_commit=finalize_refund,
        success_code="refunded", success_message="Sesi Casino direfund melalui compensating transaction.",
    )
    return CasinoResult(transaction.ok, transaction.code, transaction.message, str(session_id))


async def blackjack_action(db_path, *, session_id, user_id, action, action_request_id, now=None):
    timestamp = now or utc_now()
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            async with db.execute(
                "SELECT guildId,userId,status,stateJson,requestId,version FROM CasinoSession WHERE sessionId=$1 AND gameType='BLACKJACK'", str(session_id),),
            )
            if not row or row[1] != str(user_id):
                return CasinoResult(False, "unauthorized", "Sesi Blackjack bukan milik user ini.", str(session_id)
            replay = await db.fetchrow(
                "SELECT resultJson FROM CasinoSessionAction WHERE sessionId=$1 AND requestId=$2", str(session_id), str(action_request_id),
            )
            if replay:
                return CasinoResult(True, "action_replayed", "Aksi Blackjack sudah diproses.", str(session_id), row[4], json.loads(replay[0]), True)
            if row[2] != "ACTIVE":
                return CasinoResult(False, "invalid_status", "Sesi Blackjack tidak aktif.", str(session_id), row[4])
            state = json.loads(row[3])
            before_total = sum(int(hand["stakeEcy"]) for hand in state["hands"])
            apply_blackjack_action(state, action)
            after_total = sum(int(hand["stakeEcy"]) for hand in state["hands"])
            additional = after_total - before_total
        state["debitedStakeEcy"] = int(state.get("debitedStakeEcy", before_total)) + additional
        result_data = {**_blackjack_public_state(state), "additionalStakeEcy": additional}

        async def write_action(db, transaction_id=None, context_now=timestamp):
            locked = await db.fetchrow(
                "SELECT status,version FROM CasinoSession WHERE sessionId=$1", str(session_id),),
            )
            if not locked or locked[0] != "ACTIVE" or int(locked[1]) != int(row[5]):
                raise EconomyMutationError("stale", "Sesi Blackjack berubah saat aksi diproses.")
            row = await db.fetchrow(
                "SELECT 1 FROM CasinoSessionAction WHERE sessionId=$1 AND requestId=$2",
                (str(session_id), str(action_request_id),
            )
                        if row:
                    raise EconomyMutationError("stale", "Aksi Blackjack sudah diproses.")
            async with db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM CasinoSessionAction WHERE sessionId=$1", str(session_id) as cursor:
                sequence = int((await cursor.fetchone())[0])
            await db.execute(
                "INSERT INTO CasinoSessionAction "
                "(actionId,sessionId,requestId,sequence,actorId,actionType,actionJson,resultJson,transactionId,createdAt) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)", str(uuid.uuid4(), str(session_id), str(action_request_id), sequence, str(user_id), str(action).upper(),
                 _json({"action": str(action).upper()}), _json(result_data), transaction_id, context_now),
            )
            cursor = await db.execute(
                "UPDATE CasinoSession SET stateJson=$1,version=version+1,lastAttemptedAt=$2 "
                "WHERE sessionId=$1 AND status='ACTIVE' AND version=$2", _json(state), context_now, str(session_id), int(row[5]),
            )
            if cursor.rowcount != 1:
                raise EconomyMutationError("stale", "Aksi Blackjack kehilangan ownership lock.")

        if additional:
            async def financial_action(db, context):
                await write_action(db, context.transaction_id, context.now)
                return {"sessionId": str(session_id), "action": str(action).upper(), "additionalStakeEcy": additional}
            transaction = await execute_transaction(
                db_path, guild_id=row[0], idempotency_key=f"casino:blackjack:action:{session_id}:{action_request_id}",
                operation="CASINO_BLACKJACK_ACTION", source="CASINO_V1", actor_id=user_id,
                reason="Additional stake Blackjack", reason_code="casino_blackjack_action",
                reference_id=session_id,
                deltas=(AccountDelta("USER", str(user_id), "ECY", -additional, str(user_id)),
                        AccountDelta("SYSTEM", "ECY_CASINO", "ECY", additional)),
                feature="casino", before_commit=financial_action,
                success_code="blackjack_action", success_message="Additional stake Blackjack berhasil diproses.",
            )
            if not transaction.ok:
                return CasinoResult(False, transaction.code, transaction.message, str(session_id), row[4])
        else:
            async with aiosqlite.connect(db_path) as db:
                await configure_connection(db)
                await db.execute("BEGIN IMMEDIATE")
                try:
                    await write_action(db)
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
    except (ValueError, IndexError) as exc:
        return CasinoResult(False, "invalid_action", str(exc), str(session_id))
    except (EconomyMutationError, aiosqlite.IntegrityError) as exc:
        return CasinoResult(False, getattr(exc, "code", "stale"), "Aksi Blackjack berubah saat diproses.", str(session_id))
    if state["state"] == "DEALER_TURN":
        return await settle_session(db_path, session_id=session_id)
    return CasinoResult(True, "action_committed", "Aksi Blackjack berhasil diproses.", str(session_id), row[4], result_data)


async def is_casino_authorized(db_path, guild_id, user_id, permission_class):
    if permission_class not in CASINO_AUTH_CLASSES:
        return False
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        try:
            async with db.execute(
                "SELECT enabled FROM CasinoAuthorization WHERE guildId=$1 AND userId=$2 AND permissionClass=$3", str(guild_id), str(user_id), permission_class),
            )
            return bool(row and int(row[0]) == 1)
        except aiosqlite.OperationalError:
            return False


async def set_casino_paused(db_path, *, guild_id, actor_id, paused, reason):
    """Ubah emergency state Casino hanya melalui izin CASINO_CONTROL."""
    if not await is_casino_authorized(db_path, guild_id, actor_id, "CASINO_CONTROL"):
        return EconomyResult(False, "unauthorized", "CASINO_CONTROL diperlukan untuk pause atau resume Casino.")
    try:
        normalized = normalize_control_reason(reason)
        await set_feature_paused(
            db_path, guild_id=guild_id, feature="casino", paused=bool(paused),
            actor_id=actor_id, reason=normalized,
        )
    except ValueError as exc:
        return EconomyResult(False, "invalid_reason", str(exc)
    return EconomyResult(
        True, "paused" if paused else "resumed",
        "Casino berhasil dijeda." if paused else "Casino berhasil dilanjutkan.",
    )


async def set_casino_authorization(db_path, *, guild_id, user_id, permission_class, enabled, actor_id, reason):
    if permission_class not in CASINO_AUTH_CLASSES:
        raise ValueError("Kelas otorisasi Casino tidak valid.")
    reason = str(reason or "").strip()
    if not 1 <= len(reason) <= 300 or "\n" in reason or "\r" in reason:
        raise ValueError("Alasan otorisasi wajib 1-300 karakter dalam satu baris.")
    now = utc_now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        if not await phase5_capability(db):
            await db.rollback()
            raise ValueError("Schema Casino Phase 5 belum siap.")
        old = await db.fetchrow(
            "SELECT enabled FROM CasinoAuthorization WHERE guildId=$1 AND userId=$2 AND permissionClass=$3", str(guild_id), str(user_id), permission_class),
        )
        await db.execute(
            "INSERT INTO CasinoAuthorization (guildId,userId,permissionClass,enabled,grantedById,reasonCode,createdAt,updatedAt) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT(guildId,userId,permissionClass) DO UPDATE SET "
            "enabled=excluded.enabled,grantedById=excluded.grantedById,reasonCode=excluded.reasonCode,updatedAt=excluded.updatedAt", str(guild_id), str(user_id), permission_class, int(bool(enabled), str(actor_id), reason, now, now),
        )
        await db.execute(
            "INSERT INTO CasinoAuthorizationAudit "
            "(auditId,guildId,userId,permissionClass,oldEnabled,newEnabled,actionType,actorId,reasonCode,createdAt) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)", str(uuid.uuid4(), str(guild_id), str(user_id), permission_class,
             int(old[0]) if old else None, int(bool(enabled), "GRANT" if enabled else "REVOKE",
             str(actor_id), reason, now),
        )
        await db.commit()


async def record_owner_recovery_override(db_path, *, guild_id, actor_id, reason):
    reason = str(reason or "").strip()
    if not 1 <= len(reason) <= 300 or "\n" in reason or "\r" in reason:
        raise ValueError("Owner override memerlukan alasan audit 1-300 karakter.")
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute(
            "INSERT INTO CasinoAuthorizationAudit "
            "(auditId,guildId,userId,permissionClass,oldEnabled,newEnabled,actionType,actorId,reasonCode,createdAt) "
            "VALUES ($1,$2,$3,$4,NULL,0,'OWNER_OVERRIDE',$5,$6,$7)", str(uuid.uuid4(), str(guild_id), str(actor_id), "CASINO_RECOVERY",
             str(actor_id), reason, utc_now()),
        )
        await db.commit()


async def list_casino_authorizations(db_path, guild_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        issuance = await db.fetchrow(
            "SELECT userId,permissionClass,enabled,grantedById,updatedAt FROM CasinoAuthorization WHERE guildId=$1 ORDER BY userId,permissionClass", str(guild_id),),
            return await cursor.fetchall()


async def seed_casino_bankroll(db_path, *, guild_id, actor_id, active_members):
    if not await is_casino_authorized(db_path, guild_id, actor_id, "CASINO_FINANCIAL"):
        return EconomyResult(False, "unauthorized", "CASINO_FINANCIAL diperlukan untuk seed Casino.")
    members = max(0, int(active_members)
    amount = max(25_000_000, 100_000 * members)
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        if not await phase5_capability(db):
            return EconomyResult(False, "schema_unavailable", "Schema Casino Phase 5 belum siap.")
        await ensure_system_accounts(db, guild_id, utc_now())
        async with db.execute(
            "SELECT currency,accountClass,allowNegative FROM EconomySystemAccount WHERE guildId=$1 AND accountCode='ECY_ISSUANCE'", str(guild_id),),
        )
        await db.commit()
    if issuance != ("ECY", "ISSUANCE", 1):
        return EconomyResult(False, "issuance_unavailable", "Akun ECY_ISSUANCE canonical tidak tersedia.")
    return await system_seed(
        db_path, guild_id=guild_id, account_code="ECY_CASINO", amount=amount,
        seed_key=f"phase5-casino-initial:{guild_id}", reason="Initial seed Casino Phase 5",
        idempotency_key=f"casino:seed:{guild_id}",
    )


async def adjust_casino_bankroll(db_path, *, guild_id, actor_id, amount, direction, request_id, reason):
    if not await is_casino_authorized(db_path, guild_id, actor_id, "CASINO_FINANCIAL"):
        return EconomyResult(False, "unauthorized", "CASINO_FINANCIAL diperlukan untuk adjustment Casino.")
    amount = int(amount)
    if amount <= 0 or amount > ECONOMY_MAX_AMOUNT:
        return EconomyResult(False, "invalid_amount", "Jumlah adjustment Casino tidak valid.")
    direction = str(direction).lower()
    if direction not in {"top-up", "withdraw"}:
        return EconomyResult(False, "invalid_direction", "Arah adjustment harus top-up atau withdraw.")
    source, target = ("ECY_GENERAL", "ECY_CASINO") if direction == "top-up" else ("ECY_CASINO", "ECY_GENERAL")
    async def marker(db, context):
        if direction == "withdraw":
            paused = await db.fetchrow(
                "SELECT balance FROM EconomySystemAccount WHERE guildId=$1 AND accountCode='ECY_CASINO'", str(guild_id),),
                remaining = int((await cursor.fetchone()[0])
            async with db.execute(
                "SELECT COALESCE(SUM(liabilityEcy),0) FROM CasinoBankrollReservation "
                "WHERE guildId=$1 AND status IN ('ACTIVE','REVIEW_REQUIRED')", str(guild_id),),
                reserved = int((await cursor.fetchone()[0])
            if remaining < reserved:
                raise EconomyMutationError(
                    "reserved_exposure", "Withdrawal akan mengurangi bankroll di bawah liability yang masih ditahan."
        receipt = {"direction": direction, "amountEcy": amount, "source": source, "target": target}
        await db.execute(
            "INSERT INTO CasinoBankrollDistribution "
            "(distributionId,guildId,transactionId,operationType,amountEcy,actorId,reasonCode,receiptJson,createdAt) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)", str(uuid.uuid4(), str(guild_id), context.transaction_id,
             "ADJUST_TOP_UP" if direction == "top-up" else "ADJUST_WITHDRAW", amount,
             str(actor_id), str(reason), _json(receipt), context.now),
        )
        return receipt
    return await execute_transaction(
        db_path, guild_id=guild_id, idempotency_key=f"casino:adjust:{request_id}",
        operation="CASINO_BANKROLL_ADJUST", source="CASINO_STAFF", actor_id=actor_id,
        reason=reason, reason_code="casino_bankroll_adjust", reference_id=request_id,
        deltas=(AccountDelta("SYSTEM", source, "ECY", -amount), AccountDelta("SYSTEM", target, "ECY", amount),
        feature=None, require_spendable_system_debits=True, before_commit=marker,
        success_code="adjusted", success_message="Bankroll Casino berhasil disesuaikan.",
    )


async def distribute_casino_excess(db_path, *, guild_id, actor_id, active_members, request_id, reason):
    if not await is_casino_authorized(db_path, guild_id, actor_id, "CASINO_FINANCIAL"):
        return EconomyResult(False, "unauthorized", "CASINO_FINANCIAL diperlukan untuk distribusi Casino.")
    safe_requirement = max(25_000_000, 100_000 * max(0, int(active_members)))
    status = await casino_status(db_path, guild_id)
    amount = int(status["bankrollEcy"]) - int(status["reservedLiabilityEcy"]) - safe_requirement
    if amount <= 0:
        return EconomyResult(False, "no_excess", "Tidak ada excess bankroll yang aman untuk didistribusikan.")
    general = amount * 60 // 100
    reserve = amount * 20 // 100
    burn = amount - general - reserve
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT paused FROM EconomyFeatureState WHERE guildId=$1 AND feature='casino'", str(guild_id),),
        )
    if not paused or not int(paused[0]):
        return EconomyResult(False, "not_paused", "Distribusi excess hanya dapat dilakukan saat Casino dijeda.")
    async def marker(db, context):
        async with db.execute(
            "SELECT balance FROM EconomySystemAccount WHERE guildId=$1 AND accountCode='ECY_CASINO'",
            (str(guild_id),),
            remaining = int((await cursor.fetchone()[0])
        async with db.execute(
            "SELECT COALESCE(SUM(liabilityEcy),0) FROM CasinoBankrollReservation "
            "WHERE guildId=$1 AND status IN ('ACTIVE','REVIEW_REQUIRED')", str(guild_id),),
            reserved = int((await cursor.fetchone()[0])
        if remaining < safe_requirement + reserved:
            raise EconomyMutationError("unsafe_distribution", "Distribusi akan melewati safe bankroll requirement.")
        receipt = {"amountEcy": amount, "generalEcy": general, "reserveEcy": reserve, "burnEcy": burn}
        await db.execute(
            "INSERT INTO CasinoBankrollDistribution "
            "(distributionId,guildId,transactionId,operationType,amountEcy,generalEcy,reserveEcy,burnEcy,actorId,reasonCode,receiptJson,createdAt) "
            "VALUES ($1,$2,$3,'EXCESS_DISTRIBUTION',$4,$5,$6,$7,$8,$9,$10,$11)", str(uuid.uuid4(), str(guild_id), context.transaction_id, amount, general, reserve, burn,
             str(actor_id), str(reason), _json(receipt), context.now),
        )
        return receipt
    return await execute_transaction(
        db_path, guild_id=guild_id, idempotency_key=f"casino:distribute:{request_id}",
        operation="CASINO_EXCESS_DISTRIBUTION", source="CASINO_STAFF", actor_id=actor_id,
        reason=reason, reason_code="casino_excess_distribution", reference_id=request_id,
        deltas=(
            AccountDelta("SYSTEM", "ECY_CASINO", "ECY", -amount),
            AccountDelta("SYSTEM", "ECY_GENERAL", "ECY", general),
            AccountDelta("SYSTEM", "ECY_RESERVE", "ECY", reserve),
            AccountDelta("SYSTEM", "ECY_BURN", "ECY", burn),
        ), feature=None, require_spendable_system_debits=True, before_commit=marker,
        success_code="distributed", success_message="Excess bankroll Casino berhasil didistribusikan.",
    )
