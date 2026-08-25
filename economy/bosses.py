"""Boss raid, attack, immutable reward plan, dan settlement retry."""

import json
import secrets
import uuid
from datetime import timedelta


from .activity import append_activity_event
from .catalog import BOSSES, BOSS_DROPS, EQUIPMENT, RPG_PHASE3_CATALOG_VERSION, roll_drops
from .combat import final_damage
from .constants import RPG_BOSS_ATTACK_COOLDOWN_SECONDS
from .database import configure_connection
from .equipment import get_effective_stats
from .ledger import AccountDelta, EconomyMutationError, EconomyResult, execute_transaction
from .operations import reserve_operation
from .pets import grant_pet_xp_in_transaction
from .time_policy import utc_datetime, utc_iso


ACHIEVEMENTS = {
    "NORMAL": "achievement_boss_last_hit_normal",
    "ELITE": "achievement_boss_last_hit_elite",
    "WORLD": "achievement_boss_last_hit_world",
}


async def start_boss(db_path, *, guild_id, tier, start_key, authorized, now=None):
    if not authorized:
        raise PermissionError("Hanya Administrator atau internal API yang dapat memulai Boss.")
    tier = str(tier).upper()
    if tier not in BOSSES:
        raise ValueError("Tier Boss tidak valid.")
    timestamp = utc_iso(now)
    definition = BOSSES[tier]
    async with _pool.acquire() as db:
        
        async with db.transaction():
        try:
            existing = await db.fetchrow(
                "SELECT raidId,tier,status FROM RpgBossRaid WHERE guildId=$1 "
                "AND status IN ('ACTIVE','DEFEATED','AWAITING_FUNDS')",
                (str(guild_id),),
            )
            if existing:
                await db.rollback()
                return {"raid_id": existing[0], "tier": existing[1], "status": existing[2], "replayed": True}
            raid_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO RpgBossRaid "
                "(raidId,guildId,tier,level,maxHp,currentHp,defense,status,startKey,createdAt,updatedAt) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,'ACTIVE',$1,$2,$3)",
                (raid_id, str(guild_id), tier, definition["level"], definition["max_hp"],
                 definition["max_hp"], definition["defense"], str(start_key), timestamp, timestamp),
            )
            await db.commit()
            return {"raid_id": raid_id, "tier": tier, "status": "ACTIVE", "replayed": False}
        except aiosqlite.IntegrityError:
            await db.rollback()
            existing = await db.fetchrow(
                "SELECT raidId,tier,status FROM RpgBossRaid WHERE guildId=$1 AND status IN ('ACTIVE','DEFEATED','AWAITING_FUNDS')",
                (str(guild_id),),
            )
            if existing:
                return {"raid_id": existing[0], "tier": existing[1], "status": existing[2], "replayed": True}
            raise
        except Exception:
            await db.rollback()
            raise


async def boss_status(db_path, guild_id):
    async with _pool.acquire() as db:
        
        db.row_factory = aiosqlite.Row
        raid = await db.fetchrow(
            "SELECT raidId,tier,maxHp,currentHp,status,rewardPlanJson,noValidParticipants,settlementTransactionId "
            "FROM RpgBossRaid WHERE guildId=$1 ORDER BY createdAt DESC LIMIT 1", (str(guild_id),),
        )
        if not raid:
            return None
        fund = await db.fetchrow(
            "SELECT COUNT(*) FROM RpgBossContribution WHERE raidId=$1", (raid["raidId"],),
        ) as cursor:
            participants = int((await cursor.fetchone())[0])
        contributions = await db.fetch(
            "SELECT balance FROM EconomySystemAccount WHERE guildId=$1 AND accountCode='ETM_BOSS_DUNGEON'",
            (str(guild_id),),
        )
    result = dict(raid)
    result["participant_count"] = participants
    result["treasury_balance"] = int(fund[0]) if fund else 0
    result["treasury_ready"] = result["treasury_balance"] >= BOSSES[result["tier"]]["pool"]
    result["manual_settlement_required"] = result["status"] == "AWAITING_FUNDS"
    return result


async def reserve_boss_attack(db_path, *, guild_id, user_id, now=None):
    timestamp = utc_datetime(now)
    async with _pool.acquire() as db:
        
        raid = await db.fetchrow(
            "SELECT raidId,tier,level,defense,status FROM RpgBossRaid WHERE guildId=$1 AND status='ACTIVE'",
            (str(guild_id),),
        )
        if not raid:
            raise ValueError("Tidak ada Boss aktif.")
        player = await db.fetchrow(
            "SELECT level FROM RpgProfile WHERE guildId=$1 AND userId=$2",
            (str(guild_id), str(user_id)),
        )
        if not player:
            raise ValueError("Profile RPG belum tersedia.")
        last = await db.fetchrow(
            "SELECT occurredAt FROM EconomyActivityEvent WHERE guildId=$1 AND userId=$2 AND eventType='BOSS_ATTACK' "
            "AND referenceId=$1 ORDER BY occurredAt DESC LIMIT 1",
            (str(guild_id), str(user_id), raid[0]),
        )
        if last and (timestamp - utc_datetime(last[0])).total_seconds() < RPG_BOSS_ATTACK_COOLDOWN_SECONDS:
            raise ValueError("Boss attack masih cooldown.")
    stats = await get_effective_stats(db_path, guild_id, user_id, context="BOSS")
    if not stats:
        raise ValueError("Profile RPG belum tersedia.")
    variance = 9000 + secrets.randbelow(2001)
    crit_roll = secrets.randbelow(10_000)
    context_bps = stats.all_damage_bps + stats.boss_damage_bps
    damage = final_damage(
        attack=stats.attack, attacker_level=int(player[0]), defender_defense=raid[3],
        variance_bps=variance, critical=crit_roll < stats.crit_bps,
        context_damage_bps=context_bps,
    )
    outcome = {"catalog_version": RPG_PHASE3_CATALOG_VERSION,
               "raid_id": raid[0], "damage": damage, "variance_bps": variance,
               "critical": crit_roll < stats.crit_bps}
    operation_id, _, saved, replayed = await reserve_operation(
        db_path, guild_id=guild_id, user_id=user_id, operation_type="BOSS_ATTACK",
        reservation_key=f"boss-attack:{guild_id}:{raid[0]}:{user_id}",
        source_resource_id=raid[0], outcome=outcome, now=now,
    )
    if not replayed:
        async with _pool.acquire() as db:
            
            await db.execute(
                "INSERT INTO RpgBossAttack (operationId,raidId,committedDamage) VALUES ($1,$2,$3)",
                (operation_id, raid[0], damage),
            )
            await db.commit()
    return operation_id, saved, replayed


async def _build_reward_plan(db, raid_id, tier):
    pet = await db.fetchrow(
        "SELECT userId,committedDamage FROM RpgBossContribution WHERE raidId=$1 ORDER BY committedDamage DESC,userId ASC",
        (str(raid_id),),
    )
    definition = BOSSES[tier]
    minimum = (definition["max_hp"] * definition["minimum_bps"] + 9_999) // 10_000
    valid = [(str(user_id), int(damage)) for user_id, damage in contributions if int(damage) >= minimum]
    if not valid:
        return {"tier": tier, "catalog_version": RPG_PHASE3_CATALOG_VERSION,
                "minimum_damage": minimum, "participants": [], "no_valid_participants": True}
    pool = definition["pool"]
    equal_pool, proportional_pool = pool * 20 // 100, pool * 65 // 100
    top_pool = pool - equal_pool - proportional_pool
    total_damage = sum(damage for _, damage in valid)
    payouts = {user_id: equal_pool // len(valid) for user_id, _ in valid}
    for index, (user_id, _) in enumerate(valid[:equal_pool % len(valid)]):
        payouts[user_id] += 1
    spent_prop = 0
    for user_id, damage in valid:
        share = proportional_pool * damage // total_damage
        payouts[user_id] += share
        spent_prop += share
    for user_id, _ in valid[:proportional_pool - spent_prop]:
        payouts[user_id] += 1
    top_count = min(10, len(valid))
    for user_id, _ in valid[:top_count]:
        payouts[user_id] += top_pool // top_count
    for user_id, _ in valid[:top_pool % top_count]:
        payouts[user_id] += 1
    participants = []
    for rank, (user_id, damage) in enumerate(valid, 1):
        async with db.execute(
            "SELECT activePetInstanceId FROM RpgProfile WHERE guildId=(SELECT guildId FROM RpgBossRaid WHERE raidId=$1) AND userId=$2",
            (str(raid_id), user_id),
        )
        drop = roll_drops(BOSS_DROPS[tier])
        participants.append({"user_id": user_id, "damage": damage, "rank": rank,
                             "etm": payouts[user_id], "drop": drop,
                             "equipment_instance_id": str(uuid.uuid4()) if drop.get("equipment") else None,
                             "pet_instance_id": pet[0] if pet else None,
                             "pet_xp": definition["pet_xp"]})
    return {"tier": tier, "catalog_version": RPG_PHASE3_CATALOG_VERSION,
            "minimum_damage": minimum, "participants": participants,
            "no_valid_participants": False}


async def commit_boss_attack(db_path, *, guild_id, user_id, operation_id, now=None):
    timestamp = utc_iso(now)
    should_settle = False
    raid_id = None
    async with _pool.acquire() as db:
        
        async with db.transaction():
        try:
            operation = await db.fetchrow(
                "SELECT status,outcomeJson,resultJson FROM RpgOperation WHERE operationId=$1 AND guildId=$2 AND userId=$3 AND operationType='BOSS_ATTACK'",
                (str(operation_id), str(guild_id), str(user_id)),
            )
            if not operation:
                raise ValueError("Boss attack tidak ditemukan.")
            if operation[0] == "COMMITTED":
                await db.rollback()
                return json.loads(operation[2]), True
            if operation[0] != "RESERVED":
                raise ValueError("Boss attack tidak dapat diproses.")
            outcome = json.loads(operation[1])
            raid_id = outcome["raid_id"]
            raid = await db.fetchrow(
                "SELECT tier,currentHp,status FROM RpgBossRaid WHERE raidId=$1 AND guildId=$2",
                (raid_id, str(guild_id)),
            )
            if not raid or raid[2] != "ACTIVE":
                raise ValueError("Status Boss sudah berubah.")
            damage = min(int(outcome["damage"]), int(raid[1]))
            next_hp = int(raid[1]) - damage
            await db.execute(
                "INSERT INTO RpgBossContribution (guildId,raidId,userId,committedDamage,attackCount,updatedAt) "
                "VALUES ($1,$2,$3,0,0,$4) ON CONFLICT(guildId,raidId,userId) DO NOTHING",
                (str(guild_id), raid_id, str(user_id), timestamp),
            )
            await db.execute(
                "UPDATE RpgBossContribution SET committedDamage=committedDamage+$1,attackCount=attackCount+1,updatedAt=$2 "
                "WHERE guildId=$1 AND raidId=$2 AND userId=$3",
                (damage, timestamp, str(guild_id), raid_id, str(user_id)),
            )
            await append_activity_event(
                db, guild_id=guild_id, user_id=user_id, event_type="BOSS_ATTACK",
                event_key=f"boss-attack:{operation_id}", points=0, metric_value=damage,
                occurred_at=timestamp, reference_id=raid_id,
            )
            status = "ACTIVE"
            if next_hp == 0:
                plan = await _build_reward_plan(db, raid_id, raid[0])
                status = "DEFEATED"
                await db.execute(
                    "UPDATE RpgBossRaid SET currentHp=0,status='DEFEATED',lastHitUserId=$1,rewardPlanJson=$2,defeatedAt=$3,updatedAt=$4 WHERE raidId=$5 AND status='ACTIVE'",
                    (str(user_id), json.dumps(plan, sort_keys=True), timestamp, timestamp, raid_id),
                )
                should_settle = True
            else:
                await db.execute(
                    "UPDATE RpgBossRaid SET currentHp=$1,updatedAt=$2 WHERE raidId=$3 AND status='ACTIVE'",
                    (next_hp, timestamp, raid_id),
                )
            result = {"raid_id": raid_id, "damage": damage, "boss_hp": next_hp, "raid_status": status}
            await db.execute(
                "UPDATE RpgOperation SET status='COMMITTED',reservationKey=NULL,resultJson=$1,updatedAt=$2,settledAt=$3 "
                "WHERE operationId=$1 AND status='RESERVED'",
                (json.dumps(result, sort_keys=True), timestamp, timestamp, operation_id),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    if should_settle:
        result["settlement"] = await settle_boss(db_path, guild_id=guild_id, raid_id=raid_id, authorized=True, now=now)
    return result, False


async def settle_boss(db_path, *, guild_id, raid_id=None, authorized=False, now=None):
    if not authorized:
        raise PermissionError("Hanya Administrator atau internal API yang dapat settle Boss.")
    async with _pool.acquire() as db:
        
        query = "SELECT raidId,tier,status,rewardPlanJson,lastHitUserId,settlementTransactionId,noValidParticipants FROM RpgBossRaid WHERE guildId=$1"
        params = [str(guild_id)]
        if raid_id:
            query += " AND raidId=$1"
            params.append(str(raid_id))
        query += " ORDER BY createdAt DESC LIMIT 1"
        raid = await db.fetchrow(query, tuple(params))
    if not raid:
        return EconomyResult(False, "not_found", "Boss raid tidak ditemukan.")
    raid_id, tier, status, raw_plan, last_hit, transaction_id, no_valid = raid
    if status == "SETTLED":
        return EconomyResult(True, "boss_settled", "Boss raid sudah diselesaikan.", transaction_id, replayed=True)
    if status not in ("DEFEATED", "AWAITING_FUNDS") or not raw_plan:
        return EconomyResult(False, "invalid_status", "Boss belum dapat diselesaikan.")
    plan = json.loads(raw_plan)
    participants = plan["participants"]
    if not participants:
        async with _pool.acquire() as db:
            
            cursor = await db.execute(
                "UPDATE RpgBossRaid SET status='SETTLED',noValidParticipants=1,settledAt=$1,updatedAt=$2 "
                "WHERE raidId=$2 AND status IN ('DEFEATED','AWAITING_FUNDS')",
                (utc_iso(now), utc_iso(now), raid_id),
            )
            await db.commit()
        return EconomyResult(True, "boss_settled_no_participants", "Boss selesai tanpa peserta valid.")
    total = sum(int(row["etm"]) for row in participants)
    if await _mark_boss_awaiting_if_underfunded(
        db_path, guild_id=guild_id, raid_id=raid_id, expected_plan=raw_plan,
        required_amount=total, now=now,
    ):
        return EconomyResult(False, "awaiting_funds", "Fund Boss dan Dungeon belum mencukupi.")
    deltas = [AccountDelta("SYSTEM", "ETM_BOSS_DUNGEON", "ETM", -total)]
    deltas.extend(AccountDelta("USER", row["user_id"], "ETM", int(row["etm"]), row["user_id"]) for row in participants)

    async def extension(db, context):
        latest = await db.fetchrow(
            "SELECT status,rewardPlanJson FROM RpgBossRaid WHERE raidId=$1", (raid_id,),
        )
        if not latest or latest[0] not in ("DEFEATED", "AWAITING_FUNDS") or latest[1] != raw_plan:
            raise EconomyMutationError("stale", "Reward plan Boss sudah berubah.")
        for row in participants:
            try:
                await grant_pet_xp_in_transaction(
                    db, guild_id=guild_id, user_id=row["user_id"],
                    pet_instance_id=row.get("pet_instance_id"), amount=int(row["pet_xp"]), now=context.now,
                )
            except ValueError as exc:
                raise EconomyMutationError("pet_snapshot_invalid", str(exc)) from exc
            await append_activity_event(
                db, guild_id=guild_id, user_id=row["user_id"], event_type="BOSS_PARTICIPATION",
                event_key=f"boss-participation:{raid_id}:{row['user_id']}", points=5, metric_value=1,
                occurred_at=context.now, transaction_id=context.transaction_id, reference_id=raid_id,
            )
            for item_id in row.get("drop", {}).get("stacks", ()):
                from .inventory import adjust_stack
                await adjust_stack(
                    db, guild_id, row["user_id"], item_id, 1, context.now,
                    catalog_version=plan["catalog_version"],
                )
            equipment_item_id = row.get("drop", {}).get("equipment")
            if equipment_item_id:
                definition = EQUIPMENT[equipment_item_id]
                await db.execute(
                    "INSERT INTO RpgEquipmentInstance "
                    "(equipmentInstanceId,guildId,ownerId,itemId,catalogVersion,slot,enhancementLevel,pityBps,bindingStatus,status,acquiredSource,createdAt,updatedAt) "
                    "VALUES ($1,$2,$3,$4,$5,$6,0,0,'BOUND_ON_EQUIP','OWNED','BOSS',$1,$2)",
                    (str(row["equipment_instance_id"]), str(guild_id), row["user_id"], equipment_item_id,
                     plan["catalog_version"], definition["slot"], context.now, context.now),
                )
            await db.execute(
                "INSERT INTO RpgBossParticipantReward "
                "(raidId,userId,rank,eligible,damage,etmAmount,dropJson,activePetInstanceId,petXp,status,transactionId) "
                "VALUES ($3,$4,$5,$6,$7,$8,$9,$10,$11,'COMMITTED',$1) "
                "ON CONFLICT(raidId,userId) DO UPDATE SET status='COMMITTED',"
                "transactionId=excluded.transactionId",
                (raid_id, row["user_id"], row["rank"], 1, row["damage"], row["etm"],
                 json.dumps(row.get("drop", {})), row.get("pet_instance_id"), row["pet_xp"], context.transaction_id),
            )
        if last_hit:
            await db.execute(
                "INSERT OR IGNORE INTO RpgAchievementGrant (grantId,guildId,userId,achievementId,referenceId,grantedAt) VALUES ($1,$2,$3,$4,$5,$6)",
                (str(uuid.uuid4()), str(guild_id), str(last_hit), ACHIEVEMENTS[tier], raid_id, context.now),
            )
        await db.execute(
            "UPDATE RpgBossRaid SET status='SETTLED',settlementTransactionId=$1,settledAt=$2,updatedAt=$3 "
            "WHERE raidId=$3 AND status IN ('DEFEATED','AWAITING_FUNDS')",
            (context.transaction_id, context.now, context.now, raid_id),
        )
        return {"raid_id": raid_id, "participant_count": len(participants)}

    result = await execute_transaction(
        db_path, guild_id=guild_id, idempotency_key=f"boss-settlement:{raid_id}",
        operation="RPG_BOSS_SETTLEMENT", source="RPG_BOSS", actor_id=None,
        reason="boss settlement", reason_code="rpg_boss", reference_id=raid_id,
        deltas=tuple(deltas), before_commit=extension, feature="rpg",
        require_spendable_system_debits=True, success_code="boss_settled",
        success_message="Boss raid berhasil diselesaikan.",
    )
    if result.code == "insufficient_funds":
        await _mark_boss_awaiting_if_underfunded(
            db_path, guild_id=guild_id, raid_id=raid_id, expected_plan=raw_plan,
            required_amount=total, now=now,
        )
        return EconomyResult(False, "awaiting_funds", "Fund Boss dan Dungeon belum mencukupi.")
    if result.code == "pet_snapshot_invalid":
        async with _pool.acquire() as db:
            
            for row in participants:
                await db.execute(
                    "INSERT OR IGNORE INTO RpgBossParticipantReward "
                    "(raidId,userId,rank,eligible,damage,etmAmount,dropJson,activePetInstanceId,petXp,status) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'REVIEW_REQUIRED')",
                    (raid_id, row["user_id"], row["rank"], 1, row["damage"], row["etm"],
                     json.dumps(row.get("drop", {})), row.get("pet_instance_id"), row["pet_xp"]),
                )
            await db.commit()
    return result


async def _mark_boss_awaiting_if_underfunded(
    db_path, *, guild_id, raid_id, expected_plan, required_amount, now=None,
):
    """Re-fetch raid dan treasury di bawah satu SQLite write lock."""
    async with _pool.acquire() as db:
        
        async with db.transaction():
        try:
            raid = await db.fetchrow(
                "SELECT status,rewardPlanJson FROM RpgBossRaid WHERE raidId=$1 AND guildId=$2",
                (str(raid_id), str(guild_id)),
            )
            fund = await db.fetchrow(
                "SELECT balance FROM EconomySystemAccount WHERE guildId=$1 "
                "AND accountCode='ETM_BOSS_DUNGEON'",
                (str(guild_id),),
            )
            underfunded = not fund or int(fund[0]) < int(required_amount)
            if (raid and raid[0] in ("DEFEATED", "AWAITING_FUNDS")
                    and raid[1] == expected_plan and underfunded):
                await db.execute(
                    "UPDATE RpgBossRaid SET status='AWAITING_FUNDS',updatedAt=$1 "
                    "WHERE raidId=? AND status IN ('DEFEATED','AWAITING_FUNDS')",
                    (utc_iso(now), str(raid_id)),
                )
            await db.commit()
            return bool(underfunded)
        except Exception:
            await db.rollback()
            raise
