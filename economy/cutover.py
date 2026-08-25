
from .database import configure_connection


async def get_cutover_readiness(db_path, guild_id):
    async with _pool.acquire() as db:
        
        row = await db.fetchrow(
            "SELECT state,firstProductionTransactionId,changedAt,detailsJson "
            "FROM EconomyCutoverState WHERE guildId=$1",
            (str(guild_id),),
        )
    if not row:
        return {
            "state": "LEGACY", "first_production_transaction_id": None,
            "forward_only": False, "changed_at": None,
        }
    return {
        "state": row[0], "first_production_transaction_id": row[1],
        "forward_only": row[0] == "FORWARD_ONLY", "changed_at": row[2],
    }
