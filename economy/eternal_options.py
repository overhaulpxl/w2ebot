"""Layanan Eternal Options berbasis harga Crypto Phase 6."""

from datetime import datetime, timedelta, timezone
import json
import uuid

import aiosqlite

from .casino import _bankroll_state
from .constants import (
    OPTIONS_DURATIONS_MINUTES, OPTIONS_GROSS_PAYOUT_BPS, OPTIONS_MAX_ACTIVE,
    OPTIONS_MAX_STAKE_ECY, OPTIONS_MIN_STAKE_ECY, OPTIONS_STAKE_STEP_ECY,
)
from .database import configure_connection, ensure_system_accounts
from .giveaways import Phase8Result
from .ledger import AccountDelta, EconomyMutationError, apply_deltas_in_connection
from .phase8_schema import phase8_capability


def _dt(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def option_liability(stake):
    if isinstance(stake, bool) or not isinstance(stake, int):
        raise ValueError("Stake Options wajib integer.")
    if not OPTIONS_MIN_STAKE_ECY <= stake <= OPTIONS_MAX_STAKE_ECY or stake % OPTIONS_STAKE_STEP_ECY:
        raise ValueError("Stake Options harus 1.000-500.000 ECY dalam kelipatan 1.000.")
    return stake * OPTIONS_GROSS_PAYOUT_BPS // 10_000


async def options_status(db_path, guild_id, user_id=None):
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            capable = await phase8_capability(db)
            if not capable:
                return {"schemaCapable": False, "paused": True, "activePositions": 0}
            state = await _bankroll_state(db, guild_id)
            async with db.execute(
                "SELECT paused FROM EconomyFeatureState WHERE guildId=? AND feature IN ('economy','options') AND paused=1 LIMIT 1",
                (str(guild_id),),
            ) as cursor:
                paused = bool(await cursor.fetchone())
            params = [str(guild_id)]
            query = "SELECT COUNT(*),COALESCE(SUM(stakeEcy),0) FROM EternalOptionPosition WHERE guildId=? AND status IN ('ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED')"
            if user_id is not None:
                query += " AND userId=?"
                params.append(str(user_id))
            async with db.execute(query, tuple(params)) as cursor:
                count, stake = await cursor.fetchone()
            return {"schemaCapable": True, "paused": paused, "activePositions": int(count),
                    "combinedStakeEcy": int(stake), **state}
    except aiosqlite.Error:
        return {"schemaCapable": False, "paused": True, "activePositions": 0}


async def open_option(db_path, *, guild_id, user_id, request_id, symbol, direction,
                      stake_eyc=None, stake_ecy=None, duration_minutes, accepted_at=None):
    stake = stake_ecy if stake_ecy is not None else stake_eyc
    try:
        stake = int(stake)
        liability = option_liability(stake)
    except (TypeError, ValueError) as exc:
        return Phase8Result(False, "invalid_stake", str(exc))
    symbol, direction = str(symbol).upper(), str(direction).upper()
    if direction not in {"UP", "DOWN"}:
        return Phase8Result(False, "invalid_direction", "Arah harus UP atau DOWN.")
    if int(duration_minutes) not in OPTIONS_DURATIONS_MINUTES:
        return Phase8Result(False, "invalid_duration", "Durasi Options harus 5, 10, atau 30 menit.")
    accepted = _dt(accepted_at)
    now_iso = accepted.isoformat()
    position_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:option:{guild_id}:{request_id}"))
    transaction_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:option-open:{guild_id}:{request_id}"))
    operation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:phase8-op:{guild_id}:{request_id}"))
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            if not await phase8_capability(db):
                raise EconomyMutationError("schema_unavailable", "Schema Phase 8 belum siap.")
            async with db.execute(
                "SELECT positionId,openingTransactionId,receiptJson,status FROM EternalOptionPosition WHERE guildId=? AND requestId=?",
                (str(guild_id), str(request_id)),
            ) as cursor:
                replay = await cursor.fetchone()
            if replay:
                async with db.execute(
                    "SELECT resultJson FROM Phase8Operation WHERE entityId=? AND operationType='OPTIONS_OPEN' AND status='COMMITTED'",
                    (replay[0],),
                ) as cursor:
                    operation_receipt = await cursor.fetchone()
                await db.rollback()
                return Phase8Result(True, "already_opened", "Posisi Options sudah dibuka.", replay[0], replay[1], True,
                                    json.loads(operation_receipt[0]) if operation_receipt else None)
            async with db.execute(
                "SELECT paused FROM EconomyFeatureState WHERE guildId=? AND feature IN ('economy','casino','options') AND paused=1 LIMIT 1",
                (str(guild_id),),
            ) as cursor:
                if await cursor.fetchone():
                    raise EconomyMutationError("paused", "Eternal Options sedang dijeda.")
            async with db.execute(
                "SELECT 1 FROM EconomySeedMarker WHERE guildId=? AND accountCode='ECY_CASINO' LIMIT 1",
                (str(guild_id),),
            ) as cursor:
                if not await cursor.fetchone():
                    raise EconomyMutationError("bankroll_unseeded", "Bankroll Casino belum memiliki seed marker.")
            async with db.execute(
                "SELECT COUNT(*),COALESCE(SUM(stakeEcy),0) FROM EternalOptionPosition WHERE guildId=? AND userId=? "
                "AND status IN ('ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED')",
                (str(guild_id), str(user_id)),
            ) as cursor:
                count, combined = await cursor.fetchone()
            if int(count) >= OPTIONS_MAX_ACTIVE:
                raise EconomyMutationError("position_limit", "Maksimum tiga posisi Options aktif.")
            if int(combined) + stake > OPTIONS_MAX_STAKE_ECY:
                raise EconomyMutationError("combined_stake_limit", "Total stake Options aktif melebihi 500.000 ECY.")
            async with db.execute(
                "SELECT h.historyId,h.currentPriceEcy,h.occurredAt FROM CryptoPriceHistory h "
                "JOIN CryptoMarketTick t ON t.tickId=h.tickId AND t.status='COMMITTED' "
                "WHERE h.symbol=? AND h.occurredAt<=? ORDER BY h.occurredAt DESC,h.historyId DESC LIMIT 1",
                (symbol, now_iso),
            ) as cursor:
                price = await cursor.fetchone()
            if not price:
                raise EconomyMutationError("price_unavailable", "Harga Crypto committed belum tersedia.")
            bankroll = await _bankroll_state(db, guild_id)
            if liability > int(bankroll["availableBankrollEcy"]) or liability > int(bankroll["exposureCapEcy"]):
                raise EconomyMutationError("exposure_unavailable", "Exposure Casino tidak cukup untuk posisi ini.")
            await db.execute(
                "INSERT INTO EconomyTransaction (transactionId,guildId,idempotencyKey,operation,source,referenceId,actorId,reasonCode,reasonText,metadataJson,status,createdAt) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,'PENDING',?)",
                (transaction_id, str(guild_id), f"phase8:option-open:{request_id}", "OPTIONS_OPEN",
                 "phase8", position_id, str(user_id), "STAKE", "Pembukaan Eternal Options", "{}", now_iso),
            )
            await ensure_system_accounts(db, guild_id, now_iso)
            balances = await apply_deltas_in_connection(
                db, transaction_id=transaction_id, guild_id=guild_id, operation="OPTIONS_OPEN",
                source="phase8", reference_id=position_id, now=now_iso,
                deltas=(AccountDelta("USER", str(user_id), "ECY", -stake, str(user_id)),
                        AccountDelta("SYSTEM", "ECY_CASINO", "ECY", stake)),
            )
            expires = accepted + timedelta(minutes=int(duration_minutes))
            opening_receipt = {"positionId": position_id, "requestId": str(request_id), "symbol": symbol,
                               "direction": direction, "stakeEcy": stake, "liabilityEcy": liability,
                               "entryHistoryId": price[0], "entryPriceEcy": int(price[1]),
                               "expiresAt": expires.isoformat(), "openingTransactionId": transaction_id,
                               "balances": balances}
            await db.execute(
                "INSERT INTO EternalOptionPosition (positionId,requestId,guildId,userId,symbol,direction,stakeEcy,liabilityEcy,durationMinutes,entryHistoryId,entryPriceEcy,expiresAt,openingTransactionId,status,createdAt) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',?)",
                (position_id, str(request_id), str(guild_id), str(user_id), symbol, direction, stake,
                 liability, int(duration_minutes), price[0], int(price[1]), expires.isoformat(), transaction_id, now_iso),
            )
            await db.execute(
                "INSERT INTO EternalOptionReservation (reservationId,positionId,guildId,liabilityEcy,status,createdAt) VALUES (?,?,?,?, 'ACTIVE',?)",
                (str(uuid.uuid4()), position_id, str(guild_id), liability, now_iso),
            )
            await db.execute(
                "INSERT INTO Phase8Operation (operationId,requestId,guildId,userId,operationType,entityId,reservationKey,outcomeJson,resultJson,transactionId,status,createdAt,settledAt) "
                "VALUES (?,?,?,?,?,?,NULL,?,?,?,?,?,?)",
                (operation_id, str(request_id), str(guild_id), str(user_id), "OPTIONS_OPEN", position_id,
                 _json(opening_receipt), _json(opening_receipt), transaction_id, "COMMITTED", now_iso, now_iso),
            )
            await db.execute(
                "UPDATE EconomyTransaction SET metadataJson=?,status='COMMITTED',committedAt=? WHERE transactionId=?",
                (_json({"result_code": "option_opened", "result_message": "Posisi Eternal Options dibuka.",
                        "receipt": opening_receipt, "balances": balances}), now_iso, transaction_id),
            )
            await db.commit()
        return Phase8Result(True, "opened", "Posisi Eternal Options berhasil dibuka.",
                            position_id, transaction_id, receipt=opening_receipt)
    except (EconomyMutationError, aiosqlite.Error) as exc:
        return Phase8Result(False, getattr(exc, "code", "database_error"),
                            getattr(exc, "message", "Posisi Eternal Options gagal dibuka."))


async def settle_option(db_path, position_id, *, now=None):
    observed = _dt(now)
    now_iso = observed.isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            if not await phase8_capability(db):
                raise EconomyMutationError("schema_unavailable", "Schema Phase 8 belum siap.")
            async with db.execute(
                "SELECT guildId,userId,symbol,direction,stakeEcy,liabilityEcy,entryPriceEcy,expiresAt,openingTransactionId,status,receiptJson "
                "FROM EternalOptionPosition WHERE positionId=?", (str(position_id),),
            ) as cursor:
                position = await cursor.fetchone()
            if not position:
                raise EconomyMutationError("not_found", "Posisi tidak ditemukan.")
            if position[9] == "COMMITTED":
                await db.rollback()
                return Phase8Result(True, "settlement_replayed", "Settlement sudah committed.", str(position_id),
                                    replayed=True, receipt=json.loads(position[10]))
            if observed < _dt(position[7]):
                raise EconomyMutationError("not_expired", "Posisi belum kedaluwarsa.")
            async with db.execute(
                "SELECT h.historyId,h.currentPriceEcy,h.occurredAt FROM CryptoPriceHistory h "
                "JOIN CryptoMarketTick t ON t.tickId=h.tickId AND t.status='COMMITTED' "
                "WHERE h.symbol=? AND h.occurredAt>=? ORDER BY h.occurredAt,h.historyId LIMIT 1",
                (position[2], position[7]),
            ) as cursor:
                expiry = await cursor.fetchone()
            if not expiry:
                await db.execute("UPDATE EternalOptionPosition SET status='SETTLEMENT_PENDING',version=version+1 WHERE positionId=? AND status='ACTIVE'",
                                 (str(position_id),))
                await db.commit()
                return Phase8Result(False, "expiry_price_pending", "Harga expiry committed belum tersedia.", str(position_id))
            entry, end = int(position[6]), int(expiry[1])
            won = (position[3] == "UP" and end > entry) or (position[3] == "DOWN" and end < entry)
            result = "WIN" if won else ("TIE" if end == entry else "LOSS")
            payout = int(position[5]) if won else (int(position[4]) if result == "TIE" else 0)
            transaction_id = None
            balances = {}
            if payout:
                transaction_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"w2e:option-settle:{position_id}"))
                await db.execute(
                    "INSERT INTO EconomyTransaction (transactionId,guildId,idempotencyKey,operation,source,referenceId,actorId,reasonCode,reasonText,metadataJson,status,createdAt) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,'PENDING',?)",
                    (transaction_id, position[0], f"phase8:option-settle:{position_id}", "OPTIONS_SETTLE",
                     "phase8", str(position_id), position[1], result, "Settlement Eternal Options", "{}", now_iso),
                )
                balances = await apply_deltas_in_connection(
                    db, transaction_id=transaction_id, guild_id=position[0], operation="OPTIONS_SETTLE",
                    source="phase8", reference_id=position_id, now=now_iso,
                    deltas=(AccountDelta("SYSTEM", "ECY_CASINO", "ECY", -payout),
                            AccountDelta("USER", str(position[1]), "ECY", payout, str(position[1]))),
                )
            receipt = {"positionId": str(position_id), "resultCode": result, "entryPriceEcy": entry,
                       "expiryPriceEcy": end, "expiryHistoryId": expiry[0], "payoutEcy": payout,
                       "openingTransactionId": position[8], "settlementTransactionId": transaction_id,
                       "balances": balances}
            await db.execute(
                "INSERT INTO EternalOptionSettlement (settlementId,positionId,resultCode,payoutEcy,transactionId,openingTransactionId,receiptJson,settledAt) VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), str(position_id), result, payout, transaction_id, position[8], _json(receipt), now_iso),
            )
            await db.execute(
                "UPDATE EternalOptionPosition SET expiryHistoryId=?,expiryPriceEcy=?,status='COMMITTED',resultCode=?,receiptJson=?,version=version+1,settledAt=? WHERE positionId=?",
                (expiry[0], end, result, _json(receipt), now_iso, str(position_id)),
            )
            await db.execute(
                "UPDATE EternalOptionReservation SET status='RELEASED',releasedAt=? WHERE positionId=? AND status IN ('ACTIVE','REVIEW_REQUIRED')",
                (now_iso, str(position_id)),
            )
            if transaction_id:
                await db.execute(
                    "UPDATE EconomyTransaction SET metadataJson=?,status='COMMITTED',committedAt=? WHERE transactionId=?",
                    (_json({"result_code": result.lower(), "result_message": "Settlement Eternal Options selesai.",
                            "receipt": receipt, "balances": balances}), now_iso, transaction_id),
                )
            await db.execute(
                "INSERT INTO Phase8NotificationOutbox (outboxId,eventKey,guildId,userId,entityType,entityId,payloadJson,status,createdAt) VALUES (?,?,?,?,?,?,?,'PENDING',?)",
                (str(uuid.uuid4()), f"option-settlement:{position_id}", position[0], position[1],
                 "OPTIONS_SETTLEMENT", str(position_id), _json(receipt), now_iso),
            )
            await db.commit()
        return Phase8Result(True, "settled", "Settlement Eternal Options selesai.", str(position_id),
                            transaction_id, receipt=receipt)
    except (EconomyMutationError, aiosqlite.Error) as exc:
        return Phase8Result(False, getattr(exc, "code", "database_error"),
                            getattr(exc, "message", "Settlement Eternal Options gagal."))


async def list_positions(db_path, guild_id, user_id, *, history=False, limit=25):
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            if not await phase8_capability(db):
                return []
            statuses = "('COMMITTED')" if history else "('ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED')"
            async with db.execute(
                f"SELECT positionId,symbol,direction,stakeEcy,status,entryPriceEcy,expiryPriceEcy,expiresAt,resultCode "
                f"FROM EternalOptionPosition WHERE guildId=? AND userId=? AND status IN {statuses} ORDER BY createdAt DESC LIMIT ?",
                (str(guild_id), str(user_id), max(1, min(int(limit), 100))),
            ) as cursor:
                return await cursor.fetchall()
    except aiosqlite.Error:
        return []


async def option_details(db_path, guild_id, user_id, position_id):
    rows = await list_positions(db_path, guild_id, user_id, history=False, limit=100)
    rows += await list_positions(db_path, guild_id, user_id, history=True, limit=100)
    return next((row for row in rows if row[0] == str(position_id)), None)
