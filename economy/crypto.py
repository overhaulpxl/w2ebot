from __future__ import annotations
"""Atomic ECY Crypto trading and portfolio accounting."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import sqlite3
import uuid

import aiosqlite

from .constants import (
    ASSET_UNIT_SCALE, CRYPTO_ASSETS, CRYPTO_FEE_BPS, CRYPTO_MIN_GROSS_ECY,
    ECONOMY_MAX_AMOUNT, SQLITE_MAX_INTEGER,
)
from .crypto_market import market_snapshot, utc_now
from .database import configure_connection, ensure_system_accounts
from .ledger import AccountDelta, EconomyMutationError, apply_deltas_in_connection
from .phase6_schema import phase6_capability
from .treasury import system_seed


@dataclass(frozen=True)
class CryptoResult:
    ok: bool
    code: str
    message: str
    receipt: dict | None = None
    replayed: bool = False


def format_units(units):
    value = int(units)
    whole, fraction = divmod(value, ASSET_UNIT_SCALE)
    if not fraction:
        return str(whole)
    return f"{whole}.{fraction:08d}".rstrip("0")


def parse_asset_units(value):
    text = str(value or "").strip().lower()
    if text == "all":
        return None
    if not text or text.startswith(("+", "-")) or "e" in text:
        raise ValueError("Jumlah Crypto tidak valid.")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Jumlah Crypto tidak valid.") from exc
    if not parsed.is_finite() or parsed <= 0 or -parsed.as_tuple().exponent > 8:
        raise ValueError("Jumlah Crypto harus positif dengan maksimal 8 desimal.")
    units = int(parsed * ASSET_UNIT_SCALE)
    if units <= 0 or units > SQLITE_MAX_INTEGER:
        raise ValueError("Jumlah Crypto di luar batas.")
    return units


def trade_amounts(units, price):
    units, price = int(units), int(price)
    if units <= 0 or price <= 0 or units > SQLITE_MAX_INTEGER // price:
        raise ValueError("Nilai perdagangan melebihi batas integer.")
    gross = units * price // ASSET_UNIT_SCALE
    if gross < CRYPTO_MIN_GROSS_ECY:
        raise ValueError(f"Nilai perdagangan minimum {CRYPTO_MIN_GROSS_ECY} ECY.")
    fee = gross * CRYPTO_FEE_BPS // 10_000
    if fee <= 0:
        raise ValueError("Fee perdagangan tidak valid.")
    market_fee = fee * 50 // 100
    treasury_fee = fee * 30 // 100
    burn_fee = fee - market_fee - treasury_fee
    values = (gross, fee, market_fee, treasury_fee, burn_fee, gross + fee, gross - fee)
    if any(value < 0 or value > min(ECONOMY_MAX_AMOUNT, SQLITE_MAX_INTEGER) for value in values):
        raise ValueError("Nilai perdagangan melebihi batas economy.")
    return {"gross": gross, "fee": fee, "marketFee": market_fee,
            "treasuryFee": treasury_fee, "burnFee": burn_fee,
            "buyTotal": gross + fee, "sellNet": gross - fee}


def _maximum_affordable_units(wallet_balance, price):
    balance, price = int(wallet_balance), int(price)
    if balance <= 0 or price <= 0:
        return 0
    high = min(SQLITE_MAX_INTEGER // price, ((balance + 1) * ASSET_UNIT_SCALE - 1) // price)
    low, best = 1, 0
    while low <= high:
        middle = (low + high) // 2
        gross = middle * price // ASSET_UNIT_SCALE
        fee = gross * CRYPTO_FEE_BPS // 10_000
        if gross + fee <= balance:
            best, low = middle, middle + 1
        else:
            high = middle - 1
    return best


async def _ready_locked(db, guild_id):
    if not await phase6_capability(db):
        return "schema_unavailable"
    async with db.execute(
        "SELECT 1 FROM EconomyFeatureState WHERE guildId=? AND feature IN ('economy','crypto') AND paused=1 LIMIT 1",
        (str(guild_id),),
    ) as cursor:
        if await cursor.fetchone():
            return "paused"
    async with db.execute(
        "SELECT t.status FROM EconomySeedMarker m JOIN EconomyTransaction t ON t.transactionId=m.transactionId "
        "WHERE m.guildId=? AND m.accountCode='ECY_MARKET' ORDER BY m.appliedAt LIMIT 1",
        (str(guild_id),),
    ) as cursor:
        seed = await cursor.fetchone()
    return None if seed and seed[0] == "COMMITTED" else "market_unseeded"


async def crypto_readiness(db_path, guild_id):
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            if not await phase6_capability(db):
                return {"ready": False, "code": "schema_unavailable"}
            code = await _ready_locked(db, guild_id)
            async with db.execute(
                "SELECT balance FROM EconomySystemAccount WHERE guildId=? AND accountCode='ECY_MARKET'",
                (str(guild_id),),
            ) as cursor:
                row = await cursor.fetchone()
            return {"ready": code is None, "code": code or "ready",
                    "marketReserveEcy": int(row[0]) if row else 0}
    except aiosqlite.OperationalError:
        return {"ready": False, "code": "schema_unavailable", "marketReserveEcy": 0}


async def is_crypto_authorized(db_path, guild_id, user_id, permission_class):
    permission = str(permission_class).upper()
    if permission not in ("CRYPTO_CONTROL", "CRYPTO_FINANCIAL", "CRYPTO_RECOVERY"):
        return False
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            async with db.execute(
                "SELECT enabled FROM CryptoAuthorization WHERE guildId=? AND userId=? AND permissionClass=?",
                (str(guild_id), str(user_id), permission),
            ) as cursor:
                row = await cursor.fetchone()
        return bool(row and row[0])
    except aiosqlite.OperationalError:
        return False


async def set_crypto_authorization(db_path, *, guild_id, user_id, permission_class,
                                   enabled, actor_id, reason):
    permission = str(permission_class).upper()
    if permission not in ("CRYPTO_CONTROL", "CRYPTO_FINANCIAL", "CRYPTO_RECOVERY"):
        raise ValueError("Kelas otorisasi Crypto tidak valid.")
    cleaned_reason = " ".join(str(reason or "").split())[:200]
    if not cleaned_reason:
        raise ValueError("Alasan otorisasi wajib diisi.")
    now = utc_now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        if not await phase6_capability(db):
            await db.rollback()
            raise ValueError("Schema Crypto Phase 6 belum siap.")
        await db.execute(
            "INSERT INTO CryptoAuthorization "
            "(guildId,userId,permissionClass,enabled,grantedById,reason,version,createdAt,updatedAt) "
            "VALUES (?,?,?,?,?,?,0,?,?) ON CONFLICT(guildId,userId,permissionClass) DO UPDATE SET "
            "enabled=excluded.enabled,grantedById=excluded.grantedById,reason=excluded.reason,"
            "version=CryptoAuthorization.version+1,updatedAt=excluded.updatedAt",
            (str(guild_id), str(user_id), permission, int(bool(enabled)), str(actor_id),
             cleaned_reason, now, now),
        )
        await db.execute(
            "INSERT INTO CryptoAuthorizationAudit "
            "(auditId,guildId,actorId,subjectId,permissionClass,enabled,reason,createdAt) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), str(guild_id), str(actor_id), str(user_id), permission,
             int(bool(enabled)), cleaned_reason, now),
        )
        await db.commit()


async def list_crypto_authorizations(db_path, guild_id):
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            async with db.execute(
                "SELECT userId,permissionClass,enabled,reason,updatedAt FROM CryptoAuthorization "
                "WHERE guildId=? ORDER BY userId,permissionClass", (str(guild_id),),
            ) as cursor:
                return await cursor.fetchall()
    except aiosqlite.OperationalError:
        return []


async def seed_market_reserve(db_path, *, guild_id, amount, actor_id=None, staging_override=False):
    if not staging_override and not await is_crypto_authorized(
        db_path, guild_id, actor_id, "CRYPTO_FINANCIAL"
    ):
        raise PermissionError("CASINO_FINANCIAL tidak berlaku; CRYPTO_FINANCIAL diperlukan.")
    return await system_seed(
        db_path, guild_id=guild_id, account_code="ECY_MARKET", amount=int(amount),
        seed_key=f"phase6-market-initial:{guild_id}", reason="Initial seed Market Reserve Phase 6",
        idempotency_key=f"phase6-market-seed:{guild_id}",
    )


async def execute_trade(db_path, *, guild_id, user_id, request_id, side, symbol, quantity,
                        _failure_stage=None):
    guild_id, user_id = str(guild_id), str(user_id)
    request_id = str(request_id or "")
    side, symbol = str(side).upper(), str(symbol).upper()
    quantity_text = str(quantity or "").strip().lower()
    if side not in ("BUY", "SELL") or symbol not in CRYPTO_ASSETS:
        return CryptoResult(False, "invalid_input", "Asset atau sisi perdagangan tidak valid.")
    if not request_id or len(request_id) > 200:
        return CryptoResult(False, "invalid_request", "Identitas request tidak valid.")
    try:
        requested_units = parse_asset_units(quantity_text)
    except ValueError as exc:
        return CryptoResult(False, "invalid_amount", str(exc))
    trade_id, transaction_id, now = str(uuid.uuid4()), str(uuid.uuid4()), utc_now()
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT status,receiptJson FROM CryptoTrade WHERE guildId=? AND requestId=?",
                (guild_id, request_id),
            ) as cursor:
                existing = await cursor.fetchone()
            if existing:
                await db.rollback()
                if existing[0] == "COMMITTED":
                    return CryptoResult(True, "committed", "Perdagangan sudah diproses.",
                                        json.loads(existing[1]), replayed=True)
                return CryptoResult(False, "idempotency_conflict", "Perdagangan sebelumnya memerlukan recovery.")
            async with db.execute(
                "SELECT 1 FROM CryptoTrade WHERE guildId=? AND userId=? AND status IN ('PENDING','REVIEW_REQUIRED') LIMIT 1",
                (guild_id, user_id),
            ) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return CryptoResult(False, "unresolved_trade", "Perdagangan sebelumnya belum diselesaikan.")
            ready_code = await _ready_locked(db, guild_id)
            if ready_code:
                await db.rollback()
                messages = {"paused": "Crypto sedang dijeda.", "market_unseeded": "Market Reserve belum memiliki seed."}
                return CryptoResult(False, ready_code, messages.get(ready_code, "Schema Crypto belum siap."))
            async with db.execute(
                "SELECT currentPriceEcy,lastTickId FROM CryptoMarketState WHERE symbol=?", (symbol,),
            ) as cursor:
                price_row = await cursor.fetchone()
            if not price_row:
                await db.rollback()
                return CryptoResult(False, "market_unavailable", "Harga Crypto tidak tersedia.")
            price, tick_id = int(price_row[0]), price_row[1]
            await ensure_system_accounts(db, guild_id, now)
            await db.execute(
                "INSERT OR IGNORE INTO EconomyWallet (guildId,userId,etmBalance,ecyBalance,version,createdAt,updatedAt) "
                "VALUES (?,?,0,0,0,?,?)", (guild_id, user_id, now, now),
            )
            async with db.execute(
                "SELECT ecyBalance FROM EconomyWallet WHERE guildId=? AND userId=?", (guild_id, user_id),
            ) as cursor:
                wallet = int((await cursor.fetchone())[0])
            async with db.execute(
                "SELECT units,totalCostBasisEcy,realizedProfitEcy,status,version FROM CryptoHolding "
                "WHERE guildId=? AND userId=? AND symbol=?", (guild_id, user_id, symbol),
            ) as cursor:
                holding = await cursor.fetchone()
            held_units = int(holding[0]) if holding else 0
            if holding and holding[3] != "ACTIVE":
                await db.rollback()
                return CryptoResult(False, "holding_review", "Holding Crypto memerlukan review.")
            if quantity_text == "all":
                units = _maximum_affordable_units(wallet, price) if side == "BUY" else held_units
            else:
                units = requested_units
            try:
                amounts = trade_amounts(units, price)
            except ValueError as exc:
                await db.rollback()
                return CryptoResult(False, "invalid_amount", str(exc))
            if side == "BUY" and wallet < amounts["buyTotal"]:
                await db.rollback()
                return CryptoResult(False, "insufficient_funds", "Saldo ECY tidak mencukupi.")
            if side == "SELL" and (not holding or units > held_units):
                await db.rollback()
                return CryptoResult(False, "insufficient_holding", "Holding Crypto tidak mencukupi.")
            async with db.execute(
                "SELECT balance FROM EconomySystemAccount WHERE guildId=? AND accountCode='ECY_MARKET'",
                (guild_id,),
            ) as cursor:
                reserve = await cursor.fetchone()
            if side == "SELL" and (not reserve or int(reserve[0]) < amounts["gross"]):
                await db.rollback()
                return CryptoResult(False, "reserve_insufficient", "Market Reserve tidak mencukupi.")
            old_basis = int(holding[1]) if holding else 0
            old_realized = int(holding[2]) if holding else 0
            if side == "BUY":
                basis_delta = amounts["buyTotal"]
                realized_delta = 0
                new_units, new_basis = held_units + units, old_basis + basis_delta
                deltas = [
                    AccountDelta("USER", user_id, "ECY", -amounts["buyTotal"], user_id),
                    AccountDelta("SYSTEM", "ECY_MARKET", "ECY", amounts["gross"] + amounts["marketFee"]),
                ]
            else:
                basis_delta = old_basis if units == held_units else old_basis * units // held_units
                realized_delta = amounts["sellNet"] - basis_delta
                new_units, new_basis = held_units - units, old_basis - basis_delta
                deltas = [
                    AccountDelta("SYSTEM", "ECY_MARKET", "ECY", -(amounts["gross"] - amounts["marketFee"])),
                    AccountDelta("USER", user_id, "ECY", amounts["sellNet"], user_id),
                ]
            if amounts["treasuryFee"]:
                deltas.append(AccountDelta("SYSTEM", "ECY_GENERAL", "ECY", amounts["treasuryFee"]))
            if amounts["burnFee"]:
                deltas.append(AccountDelta("SYSTEM", "ECY_BURN", "ECY", amounts["burnFee"]))
            await db.execute(
                "INSERT INTO EconomyTransaction "
                "(transactionId,guildId,idempotencyKey,operation,source,referenceId,actorId,reasonCode,reasonText,metadataJson,status,createdAt) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,'PENDING',?)",
                (transaction_id, guild_id, f"crypto:{guild_id}:{request_id}", f"CRYPTO_{side}",
                 "MARKET_SETTLEMENT", trade_id, user_id, f"crypto_{side.lower()}",
                 f"Crypto {side.lower()} {symbol}", "{}", now),
            )
            await db.execute(
                "INSERT INTO CryptoTrade "
                "(tradeId,requestId,guildId,userId,symbol,side,quantityText,units,priceEcy,priceTickId,grossEcy,feeEcy,marketFeeEcy,treasuryFeeEcy,burnFeeEcy,costBasisDeltaEcy,realizedProfitEcy,transactionId,status,createdAt) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'PENDING',?)",
                (trade_id, request_id, guild_id, user_id, symbol, side, quantity_text, units,
                 price, tick_id, amounts["gross"], amounts["fee"], amounts["marketFee"],
                 amounts["treasuryFee"], amounts["burnFee"], basis_delta, realized_delta,
                 transaction_id, now),
            )
            if _failure_stage == "after_envelope":
                raise RuntimeError("Injected Crypto trade failure")
            if holding:
                cursor = await db.execute(
                    "UPDATE CryptoHolding SET units=?,totalCostBasisEcy=?,realizedProfitEcy=?,version=version+1,updatedAt=? "
                    "WHERE guildId=? AND userId=? AND symbol=? AND version=? AND status='ACTIVE'",
                    (new_units, new_basis, old_realized + realized_delta, now,
                     guild_id, user_id, symbol, int(holding[4])),
                )
                if cursor.rowcount != 1:
                    raise EconomyMutationError("stale", "Holding berubah saat perdagangan diproses.")
            else:
                await db.execute(
                    "INSERT INTO CryptoHolding "
                    "(guildId,userId,symbol,units,totalCostBasisEcy,realizedProfitEcy,status,version,createdAt,updatedAt) "
                    "VALUES (?,?,?,?,?,0,'ACTIVE',0,?,?)",
                    (guild_id, user_id, symbol, new_units, new_basis, now, now),
                )
            if _failure_stage == "after_holding":
                raise RuntimeError("Injected Crypto trade failure")
            balances = await apply_deltas_in_connection(
                db, transaction_id=transaction_id, guild_id=guild_id,
                operation=f"CRYPTO_{side}", source="MARKET_SETTLEMENT",
                deltas=tuple(deltas), now=now, reference_id=trade_id,
            )
            if _failure_stage == "after_ledger":
                raise RuntimeError("Injected Crypto trade failure")
            receipt = {
                "tradeId": trade_id, "transactionId": transaction_id, "requestId": request_id,
                "side": side, "symbol": symbol, "units": units, "quantity": format_units(units),
                "priceEcy": price, "priceTickId": tick_id, **amounts,
                "costBasisDeltaEcy": basis_delta, "realizedProfitDeltaEcy": realized_delta,
                "holdingUnits": new_units, "holdingQuantity": format_units(new_units),
                "holdingCostBasisEcy": new_basis,
                "realizedProfitEcy": old_realized + realized_delta,
            }
            receipt_json = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
            cursor = await db.execute(
                "UPDATE CryptoTrade SET status='COMMITTED',receiptJson=?,settledAt=? WHERE tradeId=? AND status='PENDING'",
                (receipt_json, now, trade_id),
            )
            if cursor.rowcount != 1:
                raise EconomyMutationError("stale", "Trade Crypto gagal commit.")
            metadata = json.dumps({"result_code": "committed", "result_message": "Trade Crypto berhasil.",
                                   "balances": balances, "receipt": receipt},
                                  sort_keys=True, separators=(",", ":"))
            cursor = await db.execute(
                "UPDATE EconomyTransaction SET status='COMMITTED',metadataJson=?,committedAt=? "
                "WHERE transactionId=? AND status='PENDING'", (metadata, now, transaction_id),
            )
            if cursor.rowcount != 1:
                raise EconomyMutationError("stale", "Header transaksi Crypto gagal commit.")
            await db.commit()
            return CryptoResult(True, "committed", "Perdagangan Crypto berhasil.", receipt)
    except EconomyMutationError as exc:
        return CryptoResult(False, exc.code, exc.message)
    except (aiosqlite.IntegrityError, sqlite3.IntegrityError):
        return CryptoResult(False, "concurrency_conflict", "Perdagangan Crypto sedang diproses.")
    except aiosqlite.OperationalError:
        return CryptoResult(False, "schema_unavailable", "Schema Crypto Phase 6 belum siap.")


async def portfolio(db_path, *, guild_id, user_id, history_limit=10):
    snapshot = await market_snapshot(db_path)
    if not snapshot["available"]:
        return {"available": False, "holdings": [], "history": []}
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT symbol,units,totalCostBasisEcy,realizedProfitEcy,status FROM CryptoHolding "
            "WHERE guildId=? AND userId=? AND units>0 ORDER BY symbol",
            (str(guild_id), str(user_id)),
        ) as cursor:
            rows = await cursor.fetchall()
        holdings, total_value, total_unrealized = [], 0, 0
        for symbol, units, basis, realized, status in rows:
            price = snapshot["coins"][symbol]["price"]
            gross = int(units) * price // ASSET_UNIT_SCALE
            fee = gross * CRYPTO_FEE_BPS // 10_000
            unrealized = gross - fee - int(basis)
            total_value += gross
            total_unrealized += unrealized
            holdings.append({"symbol": symbol, "units": int(units), "quantity": format_units(units),
                             "averageBuyPriceEcy": int(basis) * ASSET_UNIT_SCALE // int(units),
                             "currentPriceEcy": price, "valueEcy": gross,
                             "costBasisEcy": int(basis), "realizedProfitEcy": int(realized),
                             "unrealizedProfitEcy": unrealized, "status": status})
        async with db.execute(
            "SELECT receiptJson FROM CryptoTrade WHERE guildId=? AND userId=? AND status='COMMITTED' "
            "ORDER BY createdAt DESC LIMIT ?", (str(guild_id), str(user_id), int(history_limit)),
        ) as cursor:
            history = [json.loads(row[0]) for row in await cursor.fetchall()]
    return {"available": True, "holdings": holdings, "history": history,
            "totalValueEcy": total_value, "totalUnrealizedProfitEcy": total_unrealized}
