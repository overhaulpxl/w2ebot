import aiosqlite

from .constants import SYSTEM_ACCOUNT_DEFINITIONS
from .database import configure_connection
from .ledger import AccountDelta, EconomyResult, execute_transaction


async def treasury_grant(
    db_path, *, guild_id, actor_id, target_user_id, currency, amount,
    account_code, reason, idempotency_key,
):
    currency = str(currency).upper()
    account_code = str(account_code).upper()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT currency,accountClass,spendable FROM EconomySystemAccount WHERE guildId=? AND accountCode=?",
            (str(guild_id), account_code),
        ) as cursor:
            row = await cursor.fetchone()
    if not row or row[0] != currency or row[1] != "TREASURY" or int(row[2]) != 1:
        return EconomyResult(False, "invalid_account", "Treasury account tidak dapat digunakan untuk grant.")
    return await execute_transaction(
        db_path,
        guild_id=guild_id,
        idempotency_key=idempotency_key,
        operation="TREASURY_GRANT",
        source="TREASURY_PAID",
        actor_id=actor_id,
        reason=reason,
        reason_code="treasury_grant",
        reference_id=target_user_id,
        require_whitelist=True,
        require_spendable_system_debits=True,
        deltas=(
            AccountDelta("SYSTEM", account_code, currency, -amount),
            AccountDelta("USER", str(target_user_id), currency, amount, str(target_user_id)),
        ),
        success_code="granted",
        success_message="Treasury grant berhasil diproses.",
    )


async def get_supply_report(db_path, guild_id):
    report = {}
    try:
        async with aiosqlite.connect(db_path) as db:
            await configure_connection(db)
            for currency, wallet_column in (("ETM", "etmBalance"), ("ECY", "ecyBalance")):
                async with db.execute(
                    f"SELECT COALESCE(SUM({wallet_column}),0) FROM EconomyWallet WHERE guildId=?",
                    (str(guild_id),),
                ) as cursor:
                    user_wallets = int((await cursor.fetchone())[0])
                async with db.execute(
                    "SELECT "
                    "COALESCE(SUM(CASE WHEN accountClass='TREASURY' AND spendable=1 THEN balance ELSE 0 END),0),"
                    "COALESCE(SUM(CASE WHEN accountClass='RESERVE' THEN balance ELSE 0 END),0),"
                    "COALESCE(SUM(CASE WHEN accountClass='BURN' THEN balance ELSE 0 END),0),"
                    "COALESCE(SUM(CASE WHEN accountClass='ISSUANCE' THEN balance ELSE 0 END),0) "
                    "FROM EconomySystemAccount WHERE guildId=? AND currency=?",
                    (str(guild_id), currency),
                ) as cursor:
                    spendable, reserve, burned, issuance = [int(v) for v in await cursor.fetchone()]
                net_issued = user_wallets + spendable + reserve + burned
                circulating = user_wallets + spendable
                report[currency] = {
                    "user_wallet_balances": user_wallets,
                    "spendable_treasury_balances": spendable,
                    "locked_reserve_balances": reserve,
                    "burn_account_balance": burned,
                    "net_issued_supply": net_issued,
                    "circulating_supply": circulating,
                    "non_circulating_supply": reserve,
                    "burned_supply": burned,
                    "issuance_balance": issuance,
                    "issuance_matches": -issuance == net_issued,
                }
            async with db.execute(
                "SELECT COUNT(*) FROM ("
                "SELECT l.transactionId,l.currency,SUM(l.amount) total FROM EconomyLedger l "
                "JOIN EconomyTransaction t ON t.transactionId=l.transactionId "
                "WHERE t.guildId=? AND t.status='COMMITTED' "
                "GROUP BY l.transactionId,l.currency HAVING total<>0)",
                (str(guild_id),),
            ) as cursor:
                unbalanced_count = int((await cursor.fetchone())[0])
        report["ledger_zero_sum"] = unbalanced_count == 0
        return report
    except aiosqlite.OperationalError:
        # Read-only dashboard calls before Phase 1 schema installation remain safe.
        for currency in ("ETM", "ECY"):
            report[currency] = {
                "user_wallet_balances": 0, "spendable_treasury_balances": 0,
                "locked_reserve_balances": 0, "burn_account_balance": 0,
                "net_issued_supply": 0, "circulating_supply": 0,
                "non_circulating_supply": 0, "burned_supply": 0,
                "issuance_balance": 0, "issuance_matches": True,
            }
        report["ledger_zero_sum"] = True
        return report


async def system_seed(db_path, *, guild_id, account_code, amount, seed_key, reason, idempotency_key):
    account_code = str(account_code).upper()
    definition = SYSTEM_ACCOUNT_DEFINITIONS.get(account_code)
    if not definition or definition[1] != "TREASURY":
        return EconomyResult(False, "invalid_account", "Seed target harus operational treasury account.")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        return EconomyResult(False, "invalid_amount", "Seed amount harus lebih dari nol.")
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        async with db.execute(
            "SELECT m.transactionId,t.status FROM EconomySeedMarker m "
            "JOIN EconomyTransaction t ON t.transactionId=m.transactionId "
            "WHERE m.guildId=? AND m.seedKey=?",
            (str(guild_id), str(seed_key)),
        ) as cursor:
            row = await cursor.fetchone()
    if row:
        if row[1] == "COMMITTED":
            return EconomyResult(True, "already_seeded", "System seed ini sudah diproses.", row[0], replayed=True)
        return EconomyResult(False, "idempotency_conflict", "System seed sebelumnya belum committed.", row[0])
    currency = definition[0]
    deterministic_key = f"seed:{guild_id}:{seed_key}"
    return await execute_transaction(
        db_path,
        guild_id=guild_id,
        idempotency_key=deterministic_key,
        operation="SYSTEM_SEED",
        source="SYSTEM_SEED",
        actor_id=None,
        reason=reason,
        reason_code="system_seed",
        reference_id=seed_key,
        deltas=(
            AccountDelta("SYSTEM", f"{currency}_ISSUANCE", currency, -amount),
            AccountDelta("SYSTEM", account_code, currency, amount),
        ),
        success_code="seeded",
        success_message="System seed berhasil dicatat.",
        marker={"seed_key": str(seed_key), "account_code": account_code, "currency": currency, "amount": amount},
    )
