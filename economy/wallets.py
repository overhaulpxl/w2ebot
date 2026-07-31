from .ledger import AccountDelta, execute_transaction


async def admin_mint(db_path, *, guild_id, actor_id, target_user_id, currency, amount, reason, idempotency_key):
    currency = str(currency).upper()
    return await execute_transaction(
        db_path,
        guild_id=guild_id,
        idempotency_key=idempotency_key,
        operation="ADMIN_MINT",
        source="ADMIN_MINT",
        actor_id=actor_id,
        reason=reason,
        reason_code="admin_mint",
        reference_id=target_user_id,
        require_whitelist=True,
        deltas=(
            AccountDelta("SYSTEM", f"{currency}_ISSUANCE", currency, -amount),
            AccountDelta("USER", str(target_user_id), currency, amount, str(target_user_id)),
        ),
        success_code="minted",
        success_message="Mint berhasil diproses dan dicatat di ledger.",
    )


async def admin_remove(db_path, *, guild_id, actor_id, target_user_id, currency, amount, reason, idempotency_key):
    currency = str(currency).upper()
    return await execute_transaction(
        db_path,
        guild_id=guild_id,
        idempotency_key=idempotency_key,
        operation="ADMIN_REMOVE",
        source="ADMIN_REMOVE",
        actor_id=actor_id,
        reason=reason,
        reason_code="admin_remove",
        reference_id=target_user_id,
        require_whitelist=True,
        deltas=(
            AccountDelta("USER", str(target_user_id), currency, -amount, str(target_user_id)),
            AccountDelta("SYSTEM", f"{currency}_BURN", currency, amount),
        ),
        success_code="removed",
        success_message="Saldo berhasil dihapus dan dipindahkan ke burn account.",
    )
