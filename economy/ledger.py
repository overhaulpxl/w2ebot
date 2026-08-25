from __future__ import annotations
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


from .constants import CURRENCIES, ECONOMY_MAX_AMOUNT
from .database import configure_connection, ensure_system_accounts


@dataclass(frozen=True)
class AccountDelta:
    account_kind: str
    account_id: str
    currency: str
    amount: int
    user_id: str | None = None


@dataclass(frozen=True)
class EconomyResult:
    ok: bool
    code: str
    message: str
    transaction_id: str | None = None
    replayed: bool = False
    balances: dict | None = None


@dataclass(frozen=True)
class TransactionContext:
    transaction_id: str
    guild_id: str
    actor_id: str | None
    operation: str
    now: str


class EconomyMutationError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def _transaction_now(value):
    if value is None:
        return utc_now()
    if not isinstance(value, datetime):
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def normalize_reason(reason):
    text = str(reason or "").strip()
    if not 1 <= len(text) <= 300 or "\n" in text or "\r" in text:
        raise EconomyMutationError("invalid_reason", "Alasan wajib 1-300 karakter dalam satu baris.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise EconomyMutationError("invalid_reason", "Alasan mengandung karakter yang tidak diizinkan.")
    return text


def _validate_delta(delta):
    if delta.account_kind not in ("USER", "SYSTEM"):
        raise EconomyMutationError("invalid_account", "Jenis akun ekonomi tidak valid.")
    if delta.currency not in CURRENCIES:
        raise EconomyMutationError("invalid_currency", "Currency harus ETM atau ECY.")
    if isinstance(delta.amount, bool) or not isinstance(delta.amount, int):
        raise EconomyMutationError("invalid_amount", "Mutasi ekonomi wajib berupa integer.")
    if delta.amount == 0 or abs(delta.amount) > ECONOMY_MAX_AMOUNT:
        raise EconomyMutationError("invalid_amount", "Jumlah mutasi ekonomi tidak valid.")
    if delta.account_kind == "USER" and not str(delta.user_id or "").isdigit():
        raise EconomyMutationError("invalid_user", "User wallet tidak valid.")


async def _existing_result(db, guild_id, idempotency_key):
    row = await db.fetchrow(
        "SELECT transactionId,status,metadataJson FROM EconomyTransaction WHERE guildId=$1 AND idempotencyKey=$2",
        (str(guild_id), str(idempotency_key)),
    )
    if not row:
        return None
    transaction_id, status, metadata_raw = row
    if status != "COMMITTED":
        return EconomyResult(False, "idempotency_conflict", "Transaksi sebelumnya belum dapat dipakai ulang.", transaction_id)
    try:
        metadata = json.loads(metadata_raw or "{}")
    except (TypeError, ValueError):
        metadata = {}
    return EconomyResult(
        True,
        metadata.get("result_code", "already_committed"),
        metadata.get("result_message", "Transaksi ini sudah diproses."),
        transaction_id,
        replayed=True,
        balances=metadata.get("balances") or {},
    )


async def _mutate_wallet(db, guild_id, delta, now):
    column = "etmBalance" if delta.currency == "ETM" else "ecyBalance"
    await db.execute(
        "INSERT OR IGNORE INTO EconomyWallet (guildId,userId,etmBalance,ecyBalance,version,createdAt,updatedAt) "
        "VALUES (?,?,0,0,0,?,?)",
        (str(guild_id), str(delta.user_id), now, now),
    )
    row = await db.fetchrow(
        f"SELECT {column},version FROM EconomyWallet WHERE guildId=$1 AND userId=$2",
        (str(guild_id), str(delta.user_id)),
    )
    before, version = int(row[0]), int(row[1])
    after = before + delta.amount
    if after < 0:
        raise EconomyMutationError("insufficient_funds", "Saldo tidak mencukupi.")
    cursor = await db.execute(
        f"UPDATE EconomyWallet SET {column}=$1,version=version+1,updatedAt=$2 "
        "WHERE guildId=? AND userId=? AND version=?",
        (after, now, str(guild_id), str(delta.user_id), version),
    )
    if cursor.rowcount != 1:
        raise EconomyMutationError("stale", "Saldo berubah saat transaksi diproses.")
    return before, after


async def _mutate_system(db, guild_id, delta, now):
    row = await db.fetchrow(
        "SELECT currency,balance,allowNegative,version FROM EconomySystemAccount "
        "WHERE guildId=? AND accountCode=?",
        (str(guild_id), delta.account_id),
    )
    if not row or row[0] != delta.currency:
        raise EconomyMutationError("invalid_account", "System account tidak valid untuk currency ini.")
    before, allow_negative, version = int(row[1]), bool(row[2]), int(row[3])
    after = before + delta.amount
    if after < 0 and not allow_negative:
        raise EconomyMutationError("insufficient_funds", "Saldo system account tidak mencukupi.")
    cursor = await db.execute(
        "UPDATE EconomySystemAccount SET balance=$1,version=version+1,updatedAt=$2 "
        "WHERE guildId=? AND accountCode=? AND version=?",
        (after, now, str(guild_id), delta.account_id, version),
    )
    if cursor.rowcount != 1:
        raise EconomyMutationError("stale", "System account berubah saat transaksi diproses.")
    return before, after


async def apply_deltas_in_connection(
    db, *, transaction_id, guild_id, operation, source, deltas,
    now, reference_id=None,
):
    """Apply and ledger balanced deltas on an already locked connection."""
    deltas = tuple(deltas)
    if not deltas:
        raise EconomyMutationError("invalid_entries", "Ledger transaction tidak memiliki entry.")
    totals = {}
    for delta in deltas:
        _validate_delta(delta)
        totals[delta.currency] = totals.get(delta.currency, 0) + delta.amount
    if any(total != 0 for total in totals.values()):
        raise EconomyMutationError("unbalanced", "Ledger transaction tidak seimbang.")
    await ensure_system_accounts(db, guild_id, now)
    balances, ledger_rows = {}, []
    for sequence, delta in enumerate(deltas, start=1):
        if delta.account_kind == "USER":
            before, after = await _mutate_wallet(db, guild_id, delta, now)
            account_id = str(delta.user_id)
            balances[f"USER:{account_id}:{delta.currency}"] = after
        else:
            before, after = await _mutate_system(db, guild_id, delta, now)
            account_id = delta.account_id
            balances[f"SYSTEM:{account_id}"] = after
        ledger_rows.append((
            str(transaction_id), sequence, str(guild_id), delta.account_kind, account_id,
            str(delta.user_id) if delta.user_id else None, delta.currency, str(operation),
            delta.amount, before, after,
            str(reference_id) if reference_id is not None else None, str(source), now,
        ))
    await db.executemany(
        "INSERT INTO EconomyLedger "
        "(transactionId,sequence,guildId,accountKind,accountId,userId,currency,transactionType,"
        "amount,balanceBefore,balanceAfter,referenceId,source,createdAt) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)",
        ledger_rows,
    )
    row = await db.fetchrow(
        "SELECT currency,SUM(amount) FROM EconomyLedger WHERE transactionId=$1 GROUP BY currency",
        (str(transaction_id),),
    ) as cursor:
        rows = await cursor.fetchall()
    if not rows or any(int(row[1]) != 0 for row in rows):
        raise EconomyMutationError("unbalanced", "Ledger invariant gagal setelah penulisan.")
    return balances


async def execute_transaction(
    db_path,
    *,
    guild_id,
    idempotency_key,
    operation,
    source,
    actor_id,
    reason,
    deltas,
    reference_id=None,
    reason_code=None,
    require_whitelist=False,
    feature="economy",
    success_message="Transaksi ekonomi berhasil diproses.",
    success_code="success",
    marker=None,
    require_spendable_system_debits=False,
    reverse_original_transaction_id=None,
    before_commit=None,
    now_override=None,
):
    transaction_id = str(uuid.uuid4())
    try:
        reason_text = normalize_reason(reason)
        if not idempotency_key or len(str(idempotency_key)) > 200:
            raise EconomyMutationError("invalid_idempotency_key", "Idempotency key tidak valid.")
        deltas = tuple(deltas)
        if not deltas:
            raise EconomyMutationError("invalid_entries", "Ledger transaction tidak memiliki entry.")
        for delta in deltas:
            _validate_delta(delta)
        totals = {}
        for delta in deltas:
            totals[delta.currency] = totals.get(delta.currency, 0) + delta.amount
        if any(value != 0 for value in totals.values()):
            raise EconomyMutationError("unbalanced", "Ledger transaction tidak seimbang.")

        async with _pool.acquire() as db:
            
            async with db.transaction():
            try:
                existing = await _existing_result(db, guild_id, idempotency_key)
                if existing:
                    # await db.rollback()
                    return existing

                now = _transaction_now(now_override)
                await db.execute(
                    "INSERT INTO EconomyTransaction "
                    "(transactionId,guildId,idempotencyKey,operation,source,referenceId,actorId,reasonCode,reasonText,metadataJson,status,createdAt) "
                    "VALUES ($15,$16,$17,$18,$19,$20,$21,$22,$23,$24,'PENDING',$1)",
                    (transaction_id, str(guild_id), str(idempotency_key), operation, source,
                     str(reference_id) if reference_id is not None else None,
                     str(actor_id) if actor_id is not None else None, reason_code, reason_text, "{}", now),
                )

                # Account bootstrap and every subsequent validation/mutation are
                # inside the same transaction and happen after the PENDING header.
                await ensure_system_accounts(db, guild_id, now)
                if feature:
                    invariant_rows = await db.fetch(
                        "SELECT paused FROM EconomyFeatureState WHERE guildId=$1 AND feature IN ($2, 'economy') AND paused=1 LIMIT 1",
                        (str(guild_id), str(feature)),
                    ) as cursor:
                        if await cursor.fetchone():
                            raise EconomyMutationError("paused", "Fitur ekonomi sedang dijeda.")
                if require_whitelist:
                    async with db.execute(
                        "SELECT enabled FROM EconomyMintWhitelist WHERE guildId=$1 AND userId=$2",
                        (str(guild_id), str(actor_id)),
                    )
                    if not row or int(row[0]) != 1:
                        raise EconomyMutationError("unauthorized", "User ID ini tidak terdaftar di whitelist ekonomi.")
                if reverse_original_transaction_id:
                    original = await db.fetchrow(
                        "SELECT status FROM EconomyTransaction WHERE transactionId=$1 AND guildId=$2",
                        (str(reverse_original_transaction_id), str(guild_id)),
                    )
                    if not original or original[0] != "COMMITTED":
                        raise EconomyMutationError("invalid_status", "Transaksi asal tidak dapat direverse.")
                if require_spendable_system_debits:
                    for delta in deltas:
                        if delta.account_kind != "SYSTEM" or delta.amount >= 0:
                            continue
                        system_row = await db.fetchrow(
                            "SELECT accountClass,spendable FROM EconomySystemAccount WHERE guildId=$1 AND accountCode=$2",
                            (str(guild_id), delta.account_id),
                        )
                        if not system_row or system_row[0] != "TREASURY" or int(system_row[1]) != 1:
                            raise EconomyMutationError("invalid_account", "System debit wajib memakai treasury spendable.")

                balances = {}
                ledger_rows = []
                for sequence, delta in enumerate(deltas, start=1):
                    if delta.account_kind == "USER":
                        before, after = await _mutate_wallet(db, guild_id, delta, now)
                        account_id = str(delta.user_id)
                        balances[f"USER:{account_id}:{delta.currency}"] = after
                    else:
                        before, after = await _mutate_system(db, guild_id, delta, now)
                        account_id = delta.account_id
                        balances[f"SYSTEM:{account_id}"] = after
                    ledger_rows.append((
                        transaction_id, sequence, str(guild_id), delta.account_kind, account_id,
                        str(delta.user_id) if delta.user_id else None, delta.currency, operation,
                        delta.amount, before, after,
                        str(reference_id) if reference_id is not None else None, source, now,
                    ))

                await db.executemany(
                    "INSERT INTO EconomyLedger "
                    "(transactionId,sequence,guildId,accountKind,accountId,userId,currency,transactionType,amount,balanceBefore,balanceAfter,referenceId,source,createdAt) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)",
                    ledger_rows,
                )
                header = await db.fetchrow(
                    "SELECT currency,SUM(amount) FROM EconomyLedger WHERE transactionId=$1 GROUP BY currency",
                    (transaction_id,),
                )
                if not invariant_rows or any(int(total) != 0 for _, total in invariant_rows):
                    raise EconomyMutationError("unbalanced", "Ledger invariant gagal setelah penulisan.")

                if marker:
                    await db.execute(
                        "INSERT INTO EconomySeedMarker (guildId,seedKey,accountCode,currency,amount,transactionId,appliedAt) "
                        "VALUES ($15,$16,$17,$18,$19,$20,$21)",
                        (str(guild_id), marker["seed_key"], marker["account_code"],
                         marker["currency"], marker["amount"], transaction_id, now),
                    )

                if reverse_original_transaction_id:
                    cursor = await db.execute(
                        "UPDATE EconomyTransaction SET status='REVERSED' "
                        "WHERE transactionId=$25 AND guildId=$26 AND status='COMMITTED'",
                        (str(reverse_original_transaction_id), str(guild_id)),
                    )
                    if cursor.rowcount != 1:
                        raise EconomyMutationError("stale", "Status transaksi asal berubah saat reversal.")

                extension_metadata = {}
                if before_commit is not None:
                    extension_metadata = await before_commit(
                        db,
                        TransactionContext(
                            transaction_id=transaction_id,
                            guild_id=str(guild_id),
                            actor_id=str(actor_id) if actor_id is not None else None,
                            operation=str(operation),
                            now=now,
                        ),
                    ) or {}
                    if not isinstance(extension_metadata, dict):
                        raise EconomyMutationError("invalid_extension", "Hasil transaction extension tidak valid.")

                metadata = json.dumps({
                    "result_code": success_code,
                    "result_message": success_message,
                    "balances": balances,
                    "extension": extension_metadata,
                }, separators=(",", ":"), sort_keys=True)
                cursor = await db.execute(
                    "UPDATE EconomyTransaction SET status='COMMITTED',metadataJson=$1,committedAt=$2 "
                    "WHERE transactionId=$27 AND status='PENDING'",
                    (metadata, now, transaction_id),
                )
                if cursor.rowcount != 1:
                    raise EconomyMutationError("stale", "Transaction header tidak dapat diselesaikan.")
                # await db.commit() (managed by asyncpg/pool)
                return EconomyResult(True, success_code, success_message, transaction_id, balances=balances)
            except Exception:
                # await db.rollback()
                raise
    except EconomyMutationError as exc:
        return EconomyResult(False, exc.code, exc.message)
    except aiosqlite.IntegrityError:
        # A concurrent writer can win the unique idempotency key after this
        # connection began. Read the committed result in a fresh transaction.
        async with _pool.acquire() as db:
            
            existing = await _existing_result(db, guild_id, idempotency_key)
            if existing:
                return existing
        return EconomyResult(False, "database_failure", "Transaksi gagal sebelum perubahan disimpan.")
    except Exception:
        return EconomyResult(False, "database_failure", "Transaksi gagal sebelum perubahan disimpan.")


async def reverse_committed_transaction(
    db_path, *, guild_id, actor_id, original_transaction_id, reason, idempotency_key,
):
    async with _pool.acquire() as db:
        
        rows = await db.fetch(
            "SELECT accountKind,accountId,userId,currency,amount FROM EconomyLedger "
            "WHERE transactionId=$1 ORDER BY sequence",
            (str(original_transaction_id),),
        )
    if not rows:
        return EconomyResult(False, "not_found", "Ledger transaksi asal tidak ditemukan.")
    deltas = tuple(
        AccountDelta(row[0], row[1], row[3], -int(row[4]), row[2]) for row in rows
    )
    return await execute_transaction(
        db_path,
        guild_id=guild_id,
        idempotency_key=idempotency_key,
        operation="REVERSAL",
        source="REVERSAL",
        actor_id=actor_id,
        reason=reason,
        reason_code="transaction_reversal",
        reference_id=original_transaction_id,
        deltas=deltas,
        success_code="reversed",
        success_message="Compensating transaction berhasil diproses.",
        reverse_original_transaction_id=original_transaction_id,
    )


async def settle_pending_transaction(
    db_path, *, transaction_id, guild_id, deltas, feature="economy",
    success_code="success", success_message="Transaksi ekonomi berhasil diproses.",
    before_commit=None, now_override=None,
):
    """Selesaikan header PENDING yang sudah direservasi tanpa membuat identity baru."""
    deltas = tuple(deltas)
    for delta in deltas:
        _validate_delta(delta)
    totals = {}
    for delta in deltas:
        totals[delta.currency] = totals.get(delta.currency, 0) + delta.amount
    if not deltas or any(total != 0 for total in totals.values()):
        return EconomyResult(False, "unbalanced", "Transaksi ekonomi tidak seimbang.", transaction_id)
    async with _pool.acquire() as db:
        
        async with db.transaction():
        try:
            rows = await db.fetch(
                "SELECT status,operation,actorId,metadataJson FROM EconomyTransaction "
                "WHERE transactionId=$2 AND guildId=$3", (str(transaction_id), str(guild_id)),
            )
            if not header:
                # await db.rollback()
                return EconomyResult(False, "missing_transaction", "Reservasi transaksi tidak ditemukan.", transaction_id)
            if header[0] == "COMMITTED":
                try:
                    metadata = json.loads(header[3] or "{}")
                except (TypeError, ValueError):
                    metadata = {}
                # await db.rollback()
                return EconomyResult(True, metadata.get("result_code", "already_committed"),
                                     metadata.get("result_message", "Transaksi sudah diproses."),
                                     transaction_id, replayed=True,
                                     balances=metadata.get("balances") or {})
            if header[0] != "PENDING":
                # await db.rollback()
                return EconomyResult(False, "invalid_status", "Reservasi transaksi tidak dapat diselesaikan.", transaction_id)
            async with db.execute(
                "SELECT 1 FROM EconomyLedger WHERE transactionId=$1 LIMIT 1", (str(transaction_id),),
            ) as cursor:
                if await cursor.fetchone():
                    # await db.rollback()
                    return EconomyResult(False, "review_required", "Transaksi memerlukan rekonsiliasi manual.", transaction_id)
            if feature:
                async with db.execute(
                    "SELECT 1 FROM EconomyFeatureState WHERE guildId=$1 AND feature IN ($2, 'economy') "
                    "AND paused=1 LIMIT 1", (str(guild_id), str(feature)),
                ) as cursor:
                    if await cursor.fetchone():
                        # await db.rollback()
                        return EconomyResult(False, "paused", "Fitur ekonomi sedang dijeda.", transaction_id)
            now = _transaction_now(now_override)
            await ensure_system_accounts(db, guild_id, now)
            balances, ledger_rows = {}, []
            for sequence, delta in enumerate(deltas, start=1):
                if delta.account_kind == "USER":
                    before, after = await _mutate_wallet(db, guild_id, delta, now)
                    account_id = str(delta.user_id)
                    balances[f"USER:{account_id}:{delta.currency}"] = after
                else:
                    before, after = await _mutate_system(db, guild_id, delta, now)
                    account_id = delta.account_id
                    balances[f"SYSTEM:{account_id}"] = after
                ledger_rows.append((
                    str(transaction_id), sequence, str(guild_id), delta.account_kind, account_id,
                    str(delta.user_id) if delta.user_id else None, delta.currency, header[1],
                    delta.amount, before, after, None, "marketplace", now,
                ))
            await db.executemany(
                "INSERT INTO EconomyLedger "
                "(transactionId,sequence,guildId,accountKind,accountId,userId,currency,transactionType,"
                "amount,balanceBefore,balanceAfter,referenceId,source,createdAt) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)",
                ledger_rows,
            )
            if before_commit:
                extension = await before_commit(
                    db, TransactionContext(str(transaction_id), str(guild_id), header[2], header[1], now)
                ) or {}
            else:
                extension = {}
            async with db.execute(
                "SELECT currency,SUM(amount) FROM EconomyLedger WHERE transactionId=$1 GROUP BY currency",
                (str(transaction_id),),
            )
            if not rows or any(int(row[1]) != 0 for row in rows):
                raise EconomyMutationError("unbalanced", "Ledger marketplace tidak seimbang.")
            metadata = json.dumps({"result_code": success_code, "result_message": success_message,
                                   "balances": balances, "extension": extension},
                                  sort_keys=True, separators=(",", ":"))
            cursor = await db.execute(
                "UPDATE EconomyTransaction SET status='COMMITTED',metadataJson=$1,committedAt=$2 "
                "WHERE transactionId=? AND status='PENDING'",
                (metadata, now, str(transaction_id)),
            )
            if cursor.rowcount != 1:
                raise EconomyMutationError("stale", "Header transaksi marketplace berubah.")
            # await db.commit() (managed by asyncpg/pool)
            return EconomyResult(True, success_code, success_message, str(transaction_id), balances=balances)
        except EconomyMutationError as exc:
            # await db.rollback()
            return EconomyResult(False, exc.code, exc.message, str(transaction_id))
        except ValueError:
            # await db.rollback()
            return EconomyResult(False, "stale", "State transaksi berubah sebelum settlement.", str(transaction_id))
        except aiosqlite.Error:
            # await db.rollback()
            return EconomyResult(False, "database_failure", "Transaksi gagal sebelum perubahan disimpan.", str(transaction_id))
        except Exception:
            # await db.rollback()
            return EconomyResult(False, "database_failure", "Transaksi gagal sebelum perubahan disimpan.", str(transaction_id))
