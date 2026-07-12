"""Assignment dan claim quest berbasis activity event append-only."""

import json

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

import aiosqlite

from .activity import activity_metric, append_activity_event
from .database import configure_connection
from .inventory import adjust_stack
from .ledger import AccountDelta, EconomyMutationError, EconomyResult, execute_transaction
from .operations import reserve_operation
from .time_policy import JAKARTA, utc_datetime, utc_iso
from .xp import apply_player_xp


def quest_period(quest_type, *, now=None):
    local = utc_datetime(now).astimezone(JAKARTA)
    day_start = datetime.combine(local.date(), time.min, tzinfo=JAKARTA)
    if quest_type == "DAILY":
        start, end = day_start, day_start + timedelta(days=1)
        key = start.strftime("%Y-%m-%d")
    elif quest_type == "WEEKLY":
        start = day_start - timedelta(days=day_start.weekday())
        end = start + timedelta(days=7)
        key = start.strftime("%G-W%V")
    else:
        raise ValueError("Jenis quest tidak valid.")
    return key, start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def weekly_boss_target(level):
    level = int(level)
    if level <= 24:
        return 3_000
    if level <= 44:
        return 10_000
    if level <= 69:
        return 30_000
    if level <= 89:
        return 75_000
    return 150_000


async def ensure_quest_assignments(db_path, guild_id, user_id, *, now=None):
    timestamp = utc_iso(now)
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                "SELECT level FROM RpgProfile WHERE guildId=? AND userId=?",
                (str(guild_id), str(user_id)),
            ) as cursor:
                profile = await cursor.fetchone()
            if not profile:
                raise ValueError("Profile RPG belum tersedia.")
            level = int(profile[0])
            for quest_type in ("DAILY", "WEEKLY"):
                key, start, end = quest_period(quest_type, now=now)
                target = weekly_boss_target(level) if quest_type == "WEEKLY" else 0
                await db.execute(
                    "INSERT OR IGNORE INTO RpgQuestAssignment "
                    "(guildId,userId,questType,periodKey,periodStartUtc,periodEndUtc,assignedPlayerLevel,bossDamageTarget,status,createdAt) "
                    "VALUES (?,?,?,?,?,?,?,?, 'ACTIVE',?)",
                    (str(guild_id), str(user_id), quest_type, key, utc_iso(start), utc_iso(end), level, target, timestamp),
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def quest_progress(db_path, guild_id, user_id, *, now=None):
    await ensure_quest_assignments(db_path, guild_id, user_id, now=now)
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        results = {}
        for quest_type in ("DAILY", "WEEKLY"):
            key, _, _ = quest_period(quest_type, now=now)
            async with db.execute(
                "SELECT questType,periodKey,periodStartUtc,periodEndUtc,assignedPlayerLevel,bossDamageTarget,status,claimedTransactionId,claimedAt "
                "FROM RpgQuestAssignment WHERE guildId=? AND userId=? AND questType=? AND periodKey=?",
                (str(guild_id), str(user_id), quest_type, key),
            ) as cursor:
                assignment = await cursor.fetchone()
            if quest_type == "DAILY":
                metrics = {
                    "hunts": await activity_metric(db, guild_id=guild_id, user_id=user_id, event_type="HUNT_COMPLETED", start_utc=assignment[2], end_utc=assignment[3], aggregate="count"),
                    "work": await activity_metric(db, guild_id=guild_id, user_id=user_id, event_type="WORK_SUCCESS", start_utc=assignment[2], end_utc=assignment[3], aggregate="count"),
                    "boss_attacks": await activity_metric(db, guild_id=guild_id, user_id=user_id, event_type="BOSS_ATTACK", start_utc=assignment[2], end_utc=assignment[3], aggregate="count"),
                }
                targets = {"hunts": 3, "work": 2, "boss_attacks": 3}
            else:
                metrics = {
                    "hunts": await activity_metric(db, guild_id=guild_id, user_id=user_id, event_type="HUNT_COMPLETED", start_utc=assignment[2], end_utc=assignment[3], aggregate="count"),
                    "dungeons": await activity_metric(db, guild_id=guild_id, user_id=user_id, event_type="DUNGEON_COMPLETED", start_utc=assignment[2], end_utc=assignment[3], aggregate="count"),
                    "boss_damage": await activity_metric(db, guild_id=guild_id, user_id=user_id, event_type="BOSS_ATTACK", start_utc=assignment[2], end_utc=assignment[3], aggregate="sum"),
                }
                targets = {"hunts": 25, "dungeons": 5, "boss_damage": int(assignment[5])}
            results[quest_type] = {"assignment": dict(assignment), "progress": metrics, "targets": targets,
                                   "complete": all(metrics[key] >= value for key, value in targets.items())}
        return results


async def claim_quest(db_path, *, guild_id, user_id, quest_type, now=None):
    quest_type = str(quest_type).upper()
    progress = await quest_progress(db_path, guild_id, user_id, now=now)
    if quest_type not in progress:
        return EconomyResult(False, "invalid_quest", "Jenis quest tidak valid.")
    if not progress[quest_type]["complete"]:
        return EconomyResult(False, "not_complete", "Target quest belum selesai.")
    assignment = progress[quest_type]["assignment"]
    if assignment["status"] == "CLAIMED" and assignment["claimedTransactionId"]:
        return EconomyResult(
            True, "quest_claimed", "Reward quest sudah diklaim.",
            assignment["claimedTransactionId"], replayed=True,
        )
    etm = 80_000 if quest_type == "DAILY" else 600_000
    xp_reward = 150 if quest_type == "DAILY" else 1_000
    item_id = "item_dungeon_ticket" if quest_type == "DAILY" else "item_epic_chest"
    operation_id, _, outcome, _ = await reserve_operation(
        db_path, guild_id=guild_id, user_id=user_id, operation_type="QUEST_CLAIM",
        reservation_key=f"quest-claim:{guild_id}:{user_id}:{quest_type}:{assignment['periodKey']}",
        source_resource_id=f"{quest_type}:{assignment['periodKey']}",
        outcome={"quest_type": quest_type, "period_key": assignment["periodKey"],
                 "etm": etm, "xp": xp_reward, "item_id": item_id}, now=now,
    )

    async def extension(db, context):
        async with db.execute(
            "SELECT status,claimedTransactionId FROM RpgQuestAssignment WHERE guildId=? AND userId=? AND questType=? AND periodKey=?",
            (str(guild_id), str(user_id), quest_type, assignment["periodKey"]),
        ) as cursor:
            latest = await cursor.fetchone()
        if not latest or latest[0] == "CLAIMED":
            raise EconomyMutationError("stale", "Quest ini sudah diklaim.")
        async with db.execute(
            "SELECT status,outcomeJson FROM RpgOperation WHERE operationId=? AND operationType='QUEST_CLAIM'",
            (operation_id,),
        ) as cursor:
            operation = await cursor.fetchone()
        if not operation or operation[0] != "RESERVED" or json.loads(operation[1]) != outcome:
            raise EconomyMutationError("stale", "Reservasi claim quest sudah berubah.")
        async with db.execute(
            "SELECT level,xp FROM RpgProfile WHERE guildId=? AND userId=?",
            (str(guild_id), str(user_id)),
        ) as cursor:
            profile = await cursor.fetchone()
        level, xp, discarded = apply_player_xp(profile[0], profile[1], xp_reward)
        await db.execute(
            "UPDATE RpgProfile SET level=?,xp=?,version=version+1,updatedAt=? WHERE guildId=? AND userId=?",
            (level, xp, context.now, str(guild_id), str(user_id)),
        )
        await adjust_stack(db, guild_id, user_id, item_id, 1, context.now)
        cursor = await db.execute(
            "UPDATE RpgQuestAssignment SET status='CLAIMED',claimedTransactionId=?,claimedAt=? "
            "WHERE guildId=? AND userId=? AND questType=? AND periodKey=? AND status!='CLAIMED'",
            (context.transaction_id, context.now, str(guild_id), str(user_id), quest_type, assignment["periodKey"]),
        )
        if cursor.rowcount != 1:
            raise EconomyMutationError("stale", "Quest ini sudah diklaim.")
        await append_activity_event(
            db, guild_id=guild_id, user_id=user_id,
            event_type=f"{quest_type}_QUEST_COMPLETED",
            event_key=f"quest:{quest_type}:{assignment['periodKey']}:{user_id}",
            points=4 if quest_type == "DAILY" else 0, metric_value=1,
            occurred_at=context.now, transaction_id=context.transaction_id,
            reference_id=assignment["periodKey"],
        )
        receipt = {"xp": xp_reward, "xp_discarded_at_cap": discarded, "item_id": item_id,
                   "etm": etm, "assignment": f"{quest_type}:{assignment['periodKey']}"}
        cursor = await db.execute(
            "UPDATE RpgOperation SET status='COMMITTED',reservationKey=NULL,resultJson=?,"
            "transactionId=?,updatedAt=?,settledAt=? WHERE operationId=? AND status='RESERVED'",
            (json.dumps(receipt, sort_keys=True, separators=(",", ":")), context.transaction_id,
             context.now, context.now, operation_id),
        )
        if cursor.rowcount != 1:
            raise EconomyMutationError("stale", "Reservasi claim quest sudah diproses.")
        return receipt

    return await execute_transaction(
        db_path, guild_id=guild_id, idempotency_key=f"quest:{guild_id}:{user_id}:{quest_type}:{assignment['periodKey']}",
        operation=f"{quest_type}_QUEST", source="RPG_QUEST", actor_id=user_id,
        reason="quest reward", reason_code="rpg_quest", reference_id=assignment["periodKey"],
        deltas=(AccountDelta("SYSTEM", "ETM_ISSUANCE", "ETM", -etm),
                AccountDelta("USER", str(user_id), "ETM", etm, str(user_id))),
        before_commit=extension, feature="rpg", success_code="quest_claimed",
        success_message="Reward quest berhasil diklaim.",
    )
