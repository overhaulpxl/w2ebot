
from .database import configure_connection
from .rewards import recover_stale_work_rolls
from .phase4_recovery import recover_phase4_runtime


async def inspect_recovery_state(db_path):
    """Return startup safety state without mutating migration records."""
    async with _pool.acquire() as db:
        
        rows = await db.fetch(
            "SELECT runId,status,mode,errorCode FROM EconomyMigrationRun "
            "WHERE status IN ('RUNNING','FAILED') ORDER BY startedAt DESC"
        )
    return {
        "safe_to_enable": not rows,
        "unfinished": [
            {"run_id": row[0], "status": row[1], "mode": row[2], "error_code": row[3]}
            for row in rows
        ],
    }


async def recover_phase2_runtime(db_path, *, now=None):
    """Repair only restart-safe Phase 2 runtime state."""
    try:
        work_rolls = await recover_stale_work_rolls(db_path, now=now)
    except aiosqlite.OperationalError:
        work_rolls = {"scanned": 0, "voided": 0}
    return {"work_rolls": work_rolls}
