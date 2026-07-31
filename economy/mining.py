"""Layanan Mining Phase 7 dengan accrual deterministik dan settlement atomik."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import gcd
import hashlib
import json
import uuid

import aiosqlite

from .constants import (
    ASSET_UNIT_SCALE, CRYPTO_ASSETS, ECONOMY_MAX_AMOUNT, MINING_AUTH_CLASSES,
    MINING_RIG_CATALOG, SQLITE_MAX_INTEGER,
)
from .database import configure_connection
from .ledger import AccountDelta, EconomyMutationError, apply_deltas_in_connection
from .phase7_schema import PHASE7_CATALOG_VERSION, phase7_capability


DAY_SECONDS = 86_400
FRACTION_SCALE = 1_000_000_000


@dataclass(frozen=True)
class MiningResult:
    ok: bool
    code: str
    message: str
    receipt: dict | None = None
    replayed: bool = False


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def _as_datetime(value):
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


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _safe_int(value, name, *, minimum=0, maximum=SQLITE_MAX_INTEGER):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > maximum:
        raise OverflowError(f"{name} di luar batas INTEGER SQLite.")
    return value


def mining_allocation(amount):
    amount = _safe_int(int(amount), "amount", minimum=1, maximum=min(ECONOMY_MAX_AMOUNT, SQLITE_MAX_INTEGER))
    mining = amount * 80 // 100
    reserve = amount * 10 // 100
    burn = amount - mining - reserve
    if min(mining, reserve, burn) < 0 or mining + reserve + burn != amount:
        raise OverflowError("Alokasi Mining tidak valid.")
    return mining, reserve, burn


def calculate_mining_yield(gross_per_day, rewarded_seconds, average_price,
                           previous_carry=0, pending_units=0):
    """Hitung yield tanpa intermediate SQLite dan simpan carry billionths."""
from __future__ import annotations
    gross = _safe_int(int(gross_per_day), "grossPerDay", minimum=1)
    seconds = _safe_int(int(rewarded_seconds), "rewardedSeconds", maximum=DAY_SECONDS)
    price = _safe_int(int(average_price), "averagePrice", minimum=1)
    carry = _safe_int(int(previous_carry), "previousCarry", maximum=FRACTION_SCALE - 1)
    pending = _safe_int(int(pending_units), "pendingUnits")
    full_numerator = gross * seconds * ASSET_UNIT_SCALE
    full_denominator = DAY_SECONDS * price
    if full_numerator < 0 or full_denominator <= 0:
        raise OverflowError("Komponen yield tidak valid.")
    factor = gcd(full_numerator, full_denominator)
    numerator = full_numerator // factor
    denominator = full_denominator // factor
    whole_units, remainder = divmod(numerator, denominator)
    fractional, _sub_billionth = divmod(remainder * FRACTION_SCALE, denominator)
    carried_units, resulting_carry = divmod(fractional + carry, FRACTION_SCALE)
    credited_units = whole_units + carried_units
    _safe_int(credited_units, "creditedUnits")
    _safe_int(pending + credited_units, "pendingUnitsAfter")
    calculation = {
        "numerator": str(full_numerator), "denominator": str(full_denominator),
        "reducedNumerator": str(numerator), "reducedDenominator": str(denominator),
        "previousCarry": carry, "creditedUnits": credited_units,
        "resultingCarry": resulting_carry,
    }
    calculation_hash = hashlib.sha256(_canonical_json(calculation).encode("ascii")).hexdigest()
    return {
        **calculation,
        "calculationHash": calculation_hash,
        "pendingUnitsAfter": pending + credited_units,
    }


def slot_limit(level):
    level = int(level)
    return 4 if level >= 70 else 3 if level >= 45 else 2 if level >= 25 else 1 if level >= 10 else 0


async def _profile_locked(db, guild_id, user_id):
    async with db.execute(
        "SELECT level FROM RpgProfile WHERE guildId=? AND userId=?",
        (str(guild_id), str(user_id)),
    ) as cursor:
        rows = await cursor.fetchall()
    if len(rows) != 1 or isinstance(rows[0][0], bool) or not 1 <= int(rows[0][0]) <= 100:
        raise EconomyMutationError("invalid_profile", "Profil RPG Phase 3 tidak tersedia atau tidak valid.")
    level = int(rows[0][0])
    if level < 10:
        raise EconomyMutationError("level_required", "Mining memerlukan Level 10.")
    return level


async def _readiness_locked(db, guild_id):
    if not await phase7_capability(db):
        raise EconomyMutationError("schema_unavailable", "Schema Mining Phase 7 belum siap.")
    async with db.execute(
        "SELECT 1 FROM EconomyFeatureState WHERE guildId=? AND feature IN ('economy','mining') AND paused=1 LIMIT 1",
        (str(guild_id),),
    ) as cursor:
        if await cursor.fetchone():
            raise EconomyMutationError("paused", "Mining sedang dijeda.")
    async with db.execute(
        "SELECT currency FROM EconomySystemAccount WHERE guildId=? AND accountCode='ECY_MINING'",
        (str(guild_id),),
    ) as cursor:
        row = await cursor.fetchone()
    if not row or row[0] != "ECY":
        raise EconomyMutationError("mining_account_missing", "Akun ECY_MINING belum tersedia.")


async def mining_readiness(db_path, guild_id, user_id=None):
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await _readiness_locked(db, guild_id)
            level = await _profile_locked(db, guild_id, user_id) if user_id is not None else None
            return {"ready": True, "code": "ready", "level": level,
                    "slotLimit": slot_limit(level) if level is not None else None}
    except (aiosqlite.Error, EconomyMutationError) as exc:
        return {"ready": False, "code": getattr(exc, "code", "schema_unavailable")}


async def _operation_by_request(db, guild_id, request_id):
    async with db.execute(
        "SELECT operationId,status,resultJson,outcomeJson FROM MiningOperation WHERE guildId=? AND requestId=?",
        (str(guild_id), str(request_id)),
    ) as cursor:
        return await cursor.fetchone()


def _replay(row):
    if row and row[1] in ("COMMITTED", "VOID"):
        receipt = json.loads(row[2])
        return MiningResult(row[1] == "COMMITTED", "already_committed" if row[1] == "COMMITTED" else "void",
                            "Operasi Mining sudah diproses.", receipt, True)
    return None


async def _reserve(db_path, *, guild_id, user_id, request_id, operation_type,
                   reservation_key, outcome, rig_instance_id=None, transaction_id=None):
    if not request_id or len(str(request_id)) > 200:
        return MiningResult(False, "invalid_request", "Identitas request Mining tidak valid."), None
    operation_id = str(uuid.uuid4())
    now = utc_now()
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            await _readiness_locked(db, guild_id)
            await _profile_locked(db, guild_id, user_id)
            existing = await _operation_by_request(db, guild_id, request_id)
            replay = _replay(existing)
            if replay:
                await db.rollback()
                return replay, existing[0]
            if existing:
                await db.rollback()
                # The request owns this persisted operation. Resume it so a concurrent
                # duplicate click cannot fail or create a replacement identity.
                return None, existing[0]
            try:
                await db.execute(
                    "INSERT INTO MiningOperation "
                    "(operationId,requestId,guildId,userId,operationType,rigInstanceId,reservationKey,outcomeJson,resultJson,transactionId,status,retryCount,lastAttemptedAt,createdAt) "
                    "VALUES (?,?,?,?,?,?,?,?,NULL,?,'RESERVED',0,?,?)",
                    (operation_id, str(request_id), str(guild_id), str(user_id), operation_type,
                     rig_instance_id, reservation_key, _canonical_json(outcome), transaction_id, now, now),
                )
            except aiosqlite.IntegrityError:
                async with db.execute(
                    "SELECT operationId,status,resultJson FROM MiningOperation WHERE reservationKey=? AND status IN ('RESERVED','REVIEW_REQUIRED')",
                    (reservation_key,),
                ) as cursor:
                    conflict = await cursor.fetchone()
                await db.rollback()
                return MiningResult(False, "operation_pending", "Operasi Mining untuk resource ini masih diproses."), conflict[0] if conflict else None
            await db.commit()
        return None, operation_id
    except (aiosqlite.Error, EconomyMutationError) as exc:
        return MiningResult(False, getattr(exc, "code", "reserve_failed"), str(exc)), None


async def _void_operation(db, operation_id, code, message, now):
    receipt = {"operationId": operation_id, "voidReasonCode": code}
    await db.execute(
        "UPDATE MiningOperation SET status='VOID',reservationKey=NULL,resultJson=?,lastErrorCode=?,lastAttemptedAt=?,settledAt=? WHERE operationId=? AND status='RESERVED'",
        (_canonical_json(receipt), code, now, now, operation_id),
    )
    return MiningResult(False, code, message, receipt)


async def _load_operation_locked(db, operation_id):
    async with db.execute(
        "SELECT operationId,requestId,guildId,userId,operationType,rigInstanceId,outcomeJson,resultJson,transactionId,status FROM MiningOperation WHERE operationId=?",
        (operation_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise EconomyMutationError("operation_missing", "Operasi Mining tidak ditemukan.")
    return row


async def _price_reference_locked(db, symbol, observed_at):
    end = _as_datetime(observed_at)
    start = end - timedelta(days=7)
    async with db.execute(
        "SELECT h.historyId,h.currentPriceEcy,h.occurredAt FROM CryptoPriceHistory h "
        "JOIN CryptoMarketTick t ON t.tickId=h.tickId AND t.status='COMMITTED' "
        "WHERE h.symbol=? AND h.occurredAt>? AND h.occurredAt<=? ORDER BY h.occurredAt,h.historyId",
        (symbol, start.isoformat(), end.isoformat()),
    ) as cursor:
        rows = await cursor.fetchall()
    if not rows:
        raise EconomyMutationError("price_history_missing", "Riwayat harga tujuh hari belum tersedia.")
    price_sum = sum(int(row[1]) for row in rows)
    _safe_int(price_sum, "priceSum")
    average = price_sum // len(rows)
    evidence = {"symbol": symbol, "windowStart": start.isoformat(), "windowEnd": end.isoformat(),
                "sampleCount": len(rows), "priceSum": price_sum, "averagePriceEcy": average,
                "latestHistoryId": rows[-1][0]}
    evidence["priceReferenceHash"] = hashlib.sha256(_canonical_json(evidence).encode("ascii")).hexdigest()
    return evidence


async def _accrue_locked(db, *, operation_id, rig, observed_at):
    (rig_id, definition_id, symbol, status, paid_through, accrued_through, rig_version) = rig
    observed = _as_datetime(observed_at)
    previous = _as_datetime(accrued_through)
    if observed < previous:
        raise EconomyMutationError("invalid_time", "Waktu accrual Mining mundur.")
    elapsed = int((observed - previous).total_seconds())
    paid_end = _as_datetime(paid_through) if paid_through else previous
    eligible_end = min(observed, paid_end)
    eligible = max(0, int((eligible_end - previous).total_seconds())) if status == "ACTIVE" else 0
    rewarded = min(eligible, DAY_SECONDS)
    discarded = max(0, elapsed - rewarded)
    async with db.execute(
        "SELECT grossEquivalentPerDay FROM MiningRigCatalog WHERE rigDefinitionId=?",
        (definition_id,),
    ) as cursor:
        catalog = await cursor.fetchone()
    if not catalog:
        raise EconomyMutationError("catalog_missing", "Definisi rig Mining tidak tersedia.")
    async with db.execute(
        "SELECT pendingUnits,fractionalBillionths,version FROM MiningPendingAsset WHERE rigInstanceId=? AND symbol=?",
        (rig_id, symbol),
    ) as cursor:
        pending_row = await cursor.fetchone()
    pending, carry, pending_version = (int(pending_row[0]), int(pending_row[1]), int(pending_row[2])) if pending_row else (0, 0, None)
    reference = await _price_reference_locked(db, symbol, observed_at) if rewarded else {
        "windowStart": None, "windowEnd": None, "sampleCount": 0, "priceSum": 0,
        "averagePriceEcy": None, "latestHistoryId": None, "priceReferenceHash": None,
    }
    calculation = calculate_mining_yield(int(catalog[0]), rewarded, reference["averagePriceEcy"], carry, pending) if rewarded else {
        "numerator": "0", "denominator": "1", "calculationHash": hashlib.sha256(b"0/1").hexdigest(),
        "creditedUnits": 0, "previousCarry": carry, "resultingCarry": carry, "pendingUnitsAfter": pending,
    }
    if pending_row:
        cursor = await db.execute(
            "UPDATE MiningPendingAsset SET pendingUnits=?,fractionalBillionths=?,version=version+1,updatedAt=? "
            "WHERE rigInstanceId=? AND symbol=? AND version=?",
            (calculation["pendingUnitsAfter"], calculation["resultingCarry"], observed_at,
             rig_id, symbol, pending_version),
        )
        if cursor.rowcount != 1:
            raise EconomyMutationError("stale", "Pending Mining berubah saat accrual.")
    else:
        await db.execute(
            "INSERT INTO MiningPendingAsset (rigInstanceId,symbol,pendingUnits,fractionalBillionths,version,updatedAt) VALUES (?,?,?,?,0,?)",
            (rig_id, symbol, calculation["pendingUnitsAfter"], calculation["resultingCarry"], observed_at),
        )
    new_status = "MAINTENANCE_DUE" if paid_through and observed >= paid_end else status
    cursor = await db.execute(
        "UPDATE MiningRigInstance SET status=?,accruedThrough=?,version=version+1,updatedAt=? WHERE rigInstanceId=? AND version=?",
        (new_status, observed_at, observed_at, rig_id, rig_version),
    )
    if cursor.rowcount != 1:
        raise EconomyMutationError("stale", "Rig berubah saat accrual.")
    checkpoint_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO MiningAccrualCheckpoint "
        "(checkpointId,operationId,rigInstanceId,symbol,observedAt,previousAccruedThrough,rewardedSeconds,discardedSeconds,windowStart,windowEnd,sampleCount,priceSum,averagePriceEcy,latestHistoryId,priceReferenceHash,numeratorText,denominatorText,calculationHash,creditedUnits,previousCarry,resultingCarry,createdAt) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (checkpoint_id, operation_id, rig_id, symbol, observed_at, accrued_through, rewarded, discarded,
         reference["windowStart"], reference["windowEnd"], reference["sampleCount"], reference["priceSum"],
         reference["averagePriceEcy"], reference["latestHistoryId"], reference["priceReferenceHash"],
         calculation["numerator"], calculation["denominator"], calculation["calculationHash"],
         calculation["creditedUnits"], calculation["previousCarry"], calculation["resultingCarry"], observed_at),
    )
    return {"checkpointId": checkpoint_id, "symbol": symbol, "rewardedSeconds": rewarded,
            "discardedSeconds": discarded, "creditedUnits": calculation["creditedUnits"],
            "resultingCarry": calculation["resultingCarry"], "averagePriceEcy": reference["averagePriceEcy"]}


async def purchase_rig(db_path, *, guild_id, user_id, request_id, rig_definition_id,
                       target_symbol="ETHR", observed_at=None, _failure_stage=None):
    definition, symbol = str(rig_definition_id), str(target_symbol).upper()
    if definition not in MINING_RIG_CATALOG or symbol not in CRYPTO_ASSETS:
        return MiningResult(False, "invalid_input", "Rig atau target Mining tidak valid.")
    now = observed_at or utc_now()
    rig_id, purchase_id, transaction_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    outcome = {"rigInstanceId": rig_id, "purchaseId": purchase_id, "transactionId": transaction_id,
               "rigDefinitionId": definition, "catalogVersion": PHASE7_CATALOG_VERSION,
               "targetSymbol": symbol, "priceEcy": MINING_RIG_CATALOG[definition][1], "observedAt": now}
    pending, operation_id = await _reserve(
        db_path, guild_id=guild_id, user_id=user_id, request_id=request_id,
        operation_type="PURCHASE", reservation_key=f"mining-purchase:{guild_id}:{user_id}",
        outcome=outcome, transaction_id=transaction_id,
    )
    if pending:
        return pending
    return await settle_operation(db_path, operation_id, _failure_stage=_failure_stage)


async def pay_maintenance(db_path, *, guild_id, user_id, request_id, rig_instance_id,
                          observed_at=None, _failure_stage=None):
    now = observed_at or utc_now()
    transaction_id = str(uuid.uuid4())
    outcome = {"paymentId": str(uuid.uuid4()), "transactionId": transaction_id,
               "rigInstanceId": str(rig_instance_id), "observedAt": now}
    pending, operation_id = await _reserve(
        db_path, guild_id=guild_id, user_id=user_id, request_id=request_id,
        operation_type="MAINTENANCE", reservation_key=f"mining-rig:{rig_instance_id}",
        outcome=outcome, rig_instance_id=str(rig_instance_id), transaction_id=transaction_id,
    )
    if pending:
        return pending
    return await settle_operation(db_path, operation_id, _failure_stage=_failure_stage)


async def change_target(db_path, *, guild_id, user_id, request_id, rig_instance_id,
                        target_symbol, observed_at=None, _failure_stage=None):
    symbol = str(target_symbol).upper()
    if symbol not in CRYPTO_ASSETS:
        return MiningResult(False, "invalid_symbol", "Target Crypto tidak valid.")
    now = observed_at or utc_now()
    outcome = {"changeId": str(uuid.uuid4()), "rigInstanceId": str(rig_instance_id),
               "targetSymbol": symbol, "observedAt": now}
    pending, operation_id = await _reserve(
        db_path, guild_id=guild_id, user_id=user_id, request_id=request_id,
        operation_type="TARGET_CHANGE", reservation_key=f"mining-rig:{rig_instance_id}",
        outcome=outcome, rig_instance_id=str(rig_instance_id),
    )
    if pending:
        return pending
    return await settle_operation(db_path, operation_id, _failure_stage=_failure_stage)


async def accrue_rig(db_path, *, guild_id, user_id, request_id, rig_instance_id,
                     observed_at=None, _failure_stage=None):
    now = observed_at or utc_now()
    outcome = {"rigInstanceId": str(rig_instance_id), "observedAt": now}
    pending, operation_id = await _reserve(
        db_path, guild_id=guild_id, user_id=user_id, request_id=request_id,
        operation_type="ACCRUAL", reservation_key=f"mining-rig:{rig_instance_id}",
        outcome=outcome, rig_instance_id=str(rig_instance_id),
    )
    if pending:
        return pending
    return await settle_operation(db_path, operation_id, _failure_stage=_failure_stage)


async def claim_rig(db_path, *, guild_id, user_id, request_id, rig_instance_id,
                    observed_at=None, _failure_stage=None):
    now = observed_at or utc_now()
    outcome = {"claimId": str(uuid.uuid4()), "rigInstanceId": str(rig_instance_id),
               "observedAt": now, "currencyTransaction": None}
    pending, operation_id = await _reserve(
        db_path, guild_id=guild_id, user_id=user_id, request_id=request_id,
        operation_type="CLAIM", reservation_key=f"mining-rig:{rig_instance_id}",
        outcome=outcome, rig_instance_id=str(rig_instance_id),
    )
    if pending:
        return pending
    return await settle_operation(db_path, operation_id, _failure_stage=_failure_stage)


async def settle_operation(db_path, operation_id, *, recovery=False, _failure_stage=None):
    now_attempt = utc_now()
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            row = await _load_operation_locked(db, operation_id)
            replay = _replay((row[0], row[9], row[7], row[6]))
            if replay:
                await db.rollback()
                return replay
            if row[9] == "REVIEW_REQUIRED" and not recovery:
                await db.rollback()
                return MiningResult(False, "review_required", "Operasi Mining memerlukan recovery review.")
            guild_id, user_id, operation_type = row[2], row[3], row[4]
            await _readiness_locked(db, guild_id)
            level = await _profile_locked(db, guild_id, user_id)
            outcome = json.loads(row[6])
            observed_at = outcome["observedAt"]
            async with db.execute(
                "SELECT rigInstanceId,rigDefinitionId,targetSymbol,status,paidThrough,accruedThrough,version "
                "FROM MiningRigInstance WHERE rigInstanceId=? AND guildId=? AND userId=?",
                (row[5] or outcome.get("rigInstanceId"), guild_id, user_id),
            ) as cursor:
                rig = await cursor.fetchone()
            if operation_type == "PURCHASE":
                async with db.execute(
                    "SELECT COUNT(*) FROM MiningRigInstance WHERE guildId=? AND userId=? AND status IN ('ACTIVE','MAINTENANCE_DUE','REVIEW_REQUIRED')",
                    (guild_id, user_id),
                ) as cursor:
                    count = int((await cursor.fetchone())[0])
                if count >= slot_limit(level):
                    result = await _void_operation(db, operation_id, "slot_limit", "Slot rig Mining sudah penuh.", now_attempt)
                    await db.commit()
                    return result
                definition = outcome["rigDefinitionId"]
                price = int(outcome["priceEcy"])
                mining, reserve, burn = mining_allocation(price)
                await db.execute(
                    "INSERT INTO EconomyTransaction "
                    "(transactionId,guildId,idempotencyKey,operation,source,referenceId,actorId,reasonCode,reasonText,metadataJson,status,createdAt) "
                    "VALUES (?,?,?,?,?,?,?,NULL,?,'{}','PENDING',?)",
                    (outcome["transactionId"], guild_id, f"phase7-mining-purchase:{row[1]}",
                     "MINING_PURCHASE", "MINING", outcome["purchaseId"], user_id,
                     "Pembelian rig Mining Phase 7", observed_at),
                )
                await db.execute(
                    "INSERT INTO MiningRigInstance "
                    "(rigInstanceId,guildId,userId,rigDefinitionId,catalogVersion,targetSymbol,status,durabilityBps,paidThrough,accruedThrough,version,createdAt,updatedAt) "
                    "VALUES (?,?,?,?,?,?,'MAINTENANCE_DUE',10000,NULL,?,0,?,?)",
                    (outcome["rigInstanceId"], guild_id, user_id, definition, PHASE7_CATALOG_VERSION,
                     outcome["targetSymbol"], observed_at, observed_at, observed_at),
                )
                await apply_deltas_in_connection(
                    db, transaction_id=outcome["transactionId"], guild_id=guild_id,
                    operation="MINING_PURCHASE", source="MINING", reference_id=outcome["purchaseId"], now=observed_at,
                    deltas=(AccountDelta("USER", user_id, "ECY", -price, user_id),
                            AccountDelta("SYSTEM", "ECY_MINING", "ECY", mining),
                            AccountDelta("SYSTEM", "ECY_RESERVE", "ECY", reserve),
                            AccountDelta("SYSTEM", "ECY_BURN", "ECY", burn)),
                )
                await db.execute(
                    "INSERT INTO MiningPurchase (purchaseId,operationId,rigInstanceId,priceEcy,miningEcy,reserveEcy,burnEcy,transactionId,createdAt) VALUES (?,?,?,?,?,?,?,?,?)",
                    (outcome["purchaseId"], operation_id, outcome["rigInstanceId"], price, mining, reserve, burn,
                     outcome["transactionId"], observed_at),
                )
                receipt = {**outcome, "status": "COMMITTED", "maintenanceStatus": "MAINTENANCE_DUE"}
            else:
                if not rig:
                    result = await _void_operation(db, operation_id, "rig_missing", "Rig Mining tidak ditemukan.", now_attempt)
                    await db.commit()
                    return result
                if rig[3] == "REVIEW_REQUIRED":
                    raise EconomyMutationError("rig_review_required", "Rig Mining memerlukan review.")
                checkpoint = await _accrue_locked(db, operation_id=operation_id, rig=rig, observed_at=observed_at)
                if _failure_stage == "after_accrual":
                    raise RuntimeError("Injected Mining failure")
                if operation_type == "ACCRUAL":
                    receipt = {"operationId": operation_id, "rigInstanceId": rig[0], "checkpoint": checkpoint}
                elif operation_type == "TARGET_CHANGE":
                    if outcome["targetSymbol"] == rig[2]:
                        raise EconomyMutationError("same_target", "Target Mining sudah aktif.")
                    cursor = await db.execute(
                        "UPDATE MiningRigInstance SET targetSymbol=?,version=version+1,updatedAt=? WHERE rigInstanceId=? AND version=?",
                        (outcome["targetSymbol"], observed_at, rig[0], rig[6] + 1),
                    )
                    if cursor.rowcount != 1:
                        raise EconomyMutationError("stale", "Rig berubah saat target diperbarui.")
                    await db.execute(
                        "INSERT INTO MiningTargetChange (changeId,operationId,rigInstanceId,previousSymbol,targetSymbol,changedAt) VALUES (?,?,?,?,?,?)",
                        (outcome["changeId"], operation_id, rig[0], rig[2], outcome["targetSymbol"], observed_at),
                    )
                    receipt = {"operationId": operation_id, "rigInstanceId": rig[0], "previousSymbol": rig[2],
                               "targetSymbol": outcome["targetSymbol"], "checkpoint": checkpoint}
                elif operation_type == "MAINTENANCE":
                    if rig[4] and _as_datetime(rig[4]) > _as_datetime(observed_at):
                        raise EconomyMutationError("maintenance_active", "Periode maintenance masih aktif dan tidak dapat diprepay.")
                    async with db.execute(
                        "SELECT maintenancePriceEcy FROM MiningRigCatalog WHERE rigDefinitionId=?", (rig[1],),
                    ) as cursor:
                        price = int((await cursor.fetchone())[0])
                    mining, reserve, burn = mining_allocation(price)
                    period_end = (_as_datetime(observed_at) + timedelta(days=1)).isoformat()
                    await db.execute(
                        "INSERT INTO EconomyTransaction "
                        "(transactionId,guildId,idempotencyKey,operation,source,referenceId,actorId,reasonCode,reasonText,metadataJson,status,createdAt) "
                        "VALUES (?,?,?,?,?,?,?,NULL,?,'{}','PENDING',?)",
                        (outcome["transactionId"], guild_id, f"phase7-mining-maintenance:{row[1]}",
                         "MINING_MAINTENANCE", "MINING", outcome["paymentId"], user_id,
                         "Maintenance rig Mining Phase 7", observed_at),
                    )
                    await apply_deltas_in_connection(
                        db, transaction_id=outcome["transactionId"], guild_id=guild_id,
                        operation="MINING_MAINTENANCE", source="MINING", reference_id=outcome["paymentId"], now=observed_at,
                        deltas=(AccountDelta("USER", user_id, "ECY", -price, user_id),
                                AccountDelta("SYSTEM", "ECY_MINING", "ECY", mining),
                                AccountDelta("SYSTEM", "ECY_RESERVE", "ECY", reserve),
                                AccountDelta("SYSTEM", "ECY_BURN", "ECY", burn)),
                    )
                    cursor = await db.execute(
                        "UPDATE MiningRigInstance SET status='ACTIVE',paidThrough=?,version=version+1,updatedAt=? WHERE rigInstanceId=? AND version=?",
                        (period_end, observed_at, rig[0], rig[6] + 1),
                    )
                    if cursor.rowcount != 1:
                        raise EconomyMutationError("stale", "Rig berubah saat maintenance.")
                    await db.execute(
                        "INSERT INTO MiningMaintenancePayment "
                        "(paymentId,operationId,rigInstanceId,periodStart,periodEnd,priceEcy,miningEcy,reserveEcy,burnEcy,transactionId,createdAt) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (outcome["paymentId"], operation_id, rig[0], observed_at, period_end, price,
                         mining, reserve, burn, outcome["transactionId"], observed_at),
                    )
                    receipt = {"operationId": operation_id, "rigInstanceId": rig[0], "periodStart": observed_at,
                               "periodEnd": period_end, "priceEcy": price, "transactionId": outcome["transactionId"],
                               "checkpoint": checkpoint}
                elif operation_type == "CLAIM":
                    async with db.execute(
                        "SELECT symbol,pendingUnits,version FROM MiningPendingAsset WHERE rigInstanceId=? AND pendingUnits>0 ORDER BY symbol",
                        (rig[0],),
                    ) as cursor:
                        assets = await cursor.fetchall()
                    if not assets:
                        raise EconomyMutationError("nothing_to_claim", "Belum ada hasil Mining untuk diklaim.")
                    claim_assets = []
                    for symbol, units, pending_version in assets:
                        units = _safe_int(int(units), "claimedUnits", minimum=1)
                        async with db.execute(
                            "SELECT units,totalCostBasisEcy,realizedProfitEcy,status,version FROM CryptoHolding WHERE guildId=? AND userId=? AND symbol=?",
                            (guild_id, user_id, symbol),
                        ) as cursor:
                            holding = await cursor.fetchone()
                        before_holding = int(holding[0]) if holding else 0
                        after_holding = _safe_int(before_holding + units, "holdingAfter")
                        cursor = await db.execute(
                            "UPDATE MiningPendingAsset SET pendingUnits=0,version=version+1,updatedAt=? WHERE rigInstanceId=? AND symbol=? AND version=? AND pendingUnits=?",
                            (observed_at, rig[0], symbol, pending_version, units),
                        )
                        if cursor.rowcount != 1:
                            raise EconomyMutationError("stale", "Pending Mining berubah saat klaim.")
                        if holding:
                            if holding[3] != "ACTIVE":
                                raise EconomyMutationError("holding_review_required", "Holding Crypto memerlukan review.")
                            cursor = await db.execute(
                                "UPDATE CryptoHolding SET units=?,version=version+1,updatedAt=? WHERE guildId=? AND userId=? AND symbol=? AND version=?",
                                (after_holding, observed_at, guild_id, user_id, symbol, holding[4]),
                            )
                            if cursor.rowcount != 1:
                                raise EconomyMutationError("stale", "Holding Crypto berubah saat klaim.")
                        else:
                            await db.execute(
                                "INSERT INTO CryptoHolding (guildId,userId,symbol,units,totalCostBasisEcy,realizedProfitEcy,status,version,createdAt,updatedAt) "
                                "VALUES (?,?,?,?,0,0,'ACTIVE',0,?,?)",
                                (guild_id, user_id, symbol, after_holding, observed_at, observed_at),
                            )
                        claim_assets.append({"symbol": symbol, "units": units, "pendingBefore": units,
                                             "pendingAfter": 0, "holdingBefore": before_holding,
                                             "holdingAfter": after_holding})
                    receipt = {"claimId": outcome["claimId"], "operationId": operation_id,
                               "rigInstanceId": rig[0], "assets": claim_assets,
                               "currencyTransaction": None, "checkpoint": checkpoint}
                    receipt_json = _canonical_json(receipt)
                    await db.execute(
                        "INSERT INTO MiningClaim (claimId,operationId,requestId,guildId,userId,rigInstanceId,outcomeJson,receiptJson,status,createdAt,settledAt) "
                        "VALUES (?,?,?,?,?,?,?,?, 'COMMITTED',?,?)",
                        (outcome["claimId"], operation_id, row[1], guild_id, user_id, rig[0], row[6], receipt_json,
                         observed_at, observed_at),
                    )
                    for item in claim_assets:
                        await db.execute(
                            "INSERT INTO MiningClaimAsset (claimId,symbol,units,pendingBefore,pendingAfter,holdingBefore,holdingAfter) VALUES (?,?,?,?,?,?,?)",
                            (outcome["claimId"], item["symbol"], item["units"], item["pendingBefore"], 0,
                             item["holdingBefore"], item["holdingAfter"]),
                        )
                        await db.executemany(
                            "INSERT INTO MiningAssetLedger (entryId,claimId,operationId,symbol,accountType,accountId,unitsDelta,createdAt) VALUES (?,?,?,?,?,?,?,?)",
                            ((str(uuid.uuid4()), outcome["claimId"], operation_id, item["symbol"], "RIG_PENDING", rig[0], -item["units"], observed_at),
                             (str(uuid.uuid4()), outcome["claimId"], operation_id, item["symbol"], "USER_HOLDING", f"{guild_id}:{user_id}", item["units"], observed_at)),
                        )
                    async with db.execute(
                        "SELECT symbol,SUM(unitsDelta) FROM MiningAssetLedger WHERE claimId=? GROUP BY symbol",
                        (outcome["claimId"],),
                    ) as cursor:
                        if any(int(total) != 0 for _, total in await cursor.fetchall()):
                            raise EconomyMutationError("unbalanced_asset", "Ledger asset Mining tidak seimbang.")
            if _failure_stage == "before_receipt":
                raise RuntimeError("Injected Mining failure")
            receipt_json = _canonical_json(receipt)
            if operation_type in ("PURCHASE", "MAINTENANCE"):
                await db.execute(
                    "UPDATE EconomyTransaction SET metadataJson=?,status='COMMITTED',committedAt=? WHERE transactionId=? AND status='PENDING'",
                    (_canonical_json({"result_code": "success", "result_message": "Operasi Mining berhasil.", "receipt": receipt}),
                     observed_at, outcome["transactionId"]),
                )
            await db.execute(
                "INSERT INTO MiningNotificationOutbox (outboxId,operationId,guildId,userId,eventType,payloadJson,status,createdAt) VALUES (?,?,?,?,?,?,'PENDING',?)",
                (str(uuid.uuid4()), operation_id, guild_id, user_id, operation_type, receipt_json, observed_at),
            )
            cursor = await db.execute(
                "UPDATE MiningOperation SET status='COMMITTED',reservationKey=NULL,resultJson=?,lastAttemptedAt=?,settledAt=? WHERE operationId=? AND status IN ('RESERVED','REVIEW_REQUIRED')",
                (receipt_json, now_attempt, observed_at, operation_id),
            )
            if cursor.rowcount != 1:
                raise EconomyMutationError("stale", "Status operasi Mining berubah.")
            await db.commit()
            return MiningResult(True, "success", "Operasi Mining berhasil.", receipt)
    except (EconomyMutationError, OverflowError) as exc:
        code = getattr(exc, "code", "integer_overflow")
        try:
            async with aiosqlite.connect(db_path) as db:
                await configure_connection(db)
                await db.execute("BEGIN IMMEDIATE")
                row = await _load_operation_locked(db, operation_id)
                if row[9] == "RESERVED":
                    result = await _void_operation(db, operation_id, code, str(exc), utc_now())
                    await db.commit()
                    return result
                await db.rollback()
        except aiosqlite.Error:
            return MiningResult(False, code, "Operasi gagal dan terminalisasi VOID tidak dapat diverifikasi.")
        return MiningResult(False, code, str(exc))
    except Exception as exc:
        try:
            async with aiosqlite.connect(db_path) as db:
                await configure_connection(db)
                await db.execute("BEGIN IMMEDIATE")
                await db.execute(
                    "UPDATE MiningOperation SET status='REVIEW_REQUIRED',retryCount=retryCount+1,lastErrorCode='settlement_error',lastAttemptedAt=?,reviewMetadataJson=? WHERE operationId=? AND status='RESERVED'",
                    (utc_now(), _canonical_json({"errorType": type(exc).__name__}), operation_id),
                )
                await db.commit()
        except aiosqlite.Error:
            return MiningResult(False, "recovery_write_failed", "Review recovery Mining tidak dapat dicatat.")
        return MiningResult(False, "settlement_error", "Settlement Mining memerlukan recovery review.")


async def list_rigs(db_path, guild_id, user_id):
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            if not await phase7_capability(db):
                return []
            async with db.execute(
                "SELECT r.rigInstanceId,c.name,r.targetSymbol,r.status,r.paidThrough,r.durabilityBps,r.createdAt "
                "FROM MiningRigInstance r JOIN MiningRigCatalog c ON c.rigDefinitionId=r.rigDefinitionId "
                "WHERE r.guildId=? AND r.userId=? ORDER BY r.createdAt,r.rigInstanceId",
                (str(guild_id), str(user_id)),
            ) as cursor:
                return await cursor.fetchall()
    except aiosqlite.Error:
        return []


async def rig_details(db_path, guild_id, user_id, rig_instance_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        if not await phase7_capability(db):
            return None
        async with db.execute(
            "SELECT r.rigInstanceId,c.name,r.targetSymbol,r.status,r.paidThrough,r.accruedThrough,r.durabilityBps,r.version "
            "FROM MiningRigInstance r JOIN MiningRigCatalog c ON c.rigDefinitionId=r.rigDefinitionId "
            "WHERE r.rigInstanceId=? AND r.guildId=? AND r.userId=?",
            (str(rig_instance_id), str(guild_id), str(user_id)),
        ) as cursor:
            rig = await cursor.fetchone()
        if not rig:
            return None
        async with db.execute(
            "SELECT symbol,pendingUnits,fractionalBillionths FROM MiningPendingAsset WHERE rigInstanceId=? ORDER BY symbol",
            (str(rig_instance_id),),
        ) as cursor:
            pending = await cursor.fetchall()
        return {"rig": rig, "pending": pending}


async def mining_history(db_path, guild_id, user_id, limit=20):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        if not await phase7_capability(db):
            return []
        async with db.execute(
            "SELECT operationType,status,resultJson,createdAt,settledAt FROM MiningOperation "
            "WHERE guildId=? AND userId=? ORDER BY createdAt DESC LIMIT ?",
            (str(guild_id), str(user_id), max(1, min(int(limit), 50))),
        ) as cursor:
            return await cursor.fetchall()


async def is_mining_authorized(db_path, guild_id, user_id, permission_class):
    permission = str(permission_class).upper()
    if permission not in MINING_AUTH_CLASSES:
        return False
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            async with db.execute(
                "SELECT enabled FROM MiningAuthorization WHERE guildId=? AND userId=? AND permissionClass=?",
                (str(guild_id), str(user_id), permission),
            ) as cursor:
                row = await cursor.fetchone()
        return bool(row and row[0])
    except aiosqlite.Error:
        return False


async def set_mining_authorization(db_path, *, guild_id, user_id, permission_class,
                                   enabled, actor_id, reason):
    permission = str(permission_class).upper()
    if permission not in MINING_AUTH_CLASSES:
        raise ValueError("Kelas otorisasi Mining tidak valid.")
    cleaned = " ".join(str(reason or "").split())[:200]
    if not cleaned:
        raise ValueError("Alasan otorisasi wajib diisi.")
    now = utc_now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        if not await phase7_capability(db):
            await db.rollback()
            raise ValueError("Schema Mining Phase 7 belum siap.")
        await db.execute(
            "INSERT INTO MiningAuthorization (guildId,userId,permissionClass,enabled,grantedById,reason,version,createdAt,updatedAt) "
            "VALUES (?,?,?,?,?,?,0,?,?) ON CONFLICT(guildId,userId,permissionClass) DO UPDATE SET "
            "enabled=excluded.enabled,grantedById=excluded.grantedById,reason=excluded.reason,version=MiningAuthorization.version+1,updatedAt=excluded.updatedAt",
            (str(guild_id), str(user_id), permission, int(bool(enabled)), str(actor_id), cleaned, now, now),
        )
        await db.execute(
            "INSERT INTO MiningAuthorizationAudit (auditId,guildId,actorId,subjectId,permissionClass,enabled,reason,createdAt) VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), str(guild_id), str(actor_id), str(user_id), permission, int(bool(enabled)), cleaned, now),
        )
        await db.commit()


async def list_mining_authorizations(db_path, guild_id):
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            async with db.execute(
                "SELECT userId,permissionClass,enabled,reason,updatedAt FROM MiningAuthorization WHERE guildId=? ORDER BY userId,permissionClass",
                (str(guild_id),),
            ) as cursor:
                return await cursor.fetchall()
    except aiosqlite.Error:
        return []
