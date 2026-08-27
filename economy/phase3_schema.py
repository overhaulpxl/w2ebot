"""Schema Phase 3 yang hanya diterapkan oleh migrasi staging eksplisit."""

import hashlib
import json
import sqlite3
import uuid

import aiosqlite

from .database import configure_connection


PHASE3_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS RpgCatalogManifest (
    catalogVersion TEXT PRIMARY KEY, catalogHash TEXT NOT NULL,
    seededAt TEXT NOT NULL, detailsJson TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS RpgCatalogItem (
    catalogVersion TEXT NOT NULL, itemId TEXT NOT NULL, itemType TEXT NOT NULL,
    name TEXT NOT NULL, rarity TEXT NOT NULL, slot TEXT, requiredLevel INTEGER NOT NULL DEFAULT 1,
    tradeable INTEGER NOT NULL CHECK(tradeable IN (0,1)), definitionJson TEXT NOT NULL,
    PRIMARY KEY(catalogVersion,itemId)
);
CREATE TABLE IF NOT EXISTS RpgCatalogDefinition (
    catalogVersion TEXT NOT NULL, definitionType TEXT NOT NULL,
    definitionId TEXT NOT NULL, definitionJson TEXT NOT NULL,
    PRIMARY KEY(catalogVersion,definitionType,definitionId)
);
CREATE TABLE IF NOT EXISTS RpgInventoryStack (
    guildId TEXT NOT NULL, userId TEXT NOT NULL, itemId TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity >= 0), version INTEGER NOT NULL DEFAULT 0,
    createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId,userId,itemId)
);
CREATE TABLE IF NOT EXISTS RpgEquipmentInstance (
    equipmentInstanceId TEXT PRIMARY KEY, guildId TEXT NOT NULL, ownerId TEXT NOT NULL,
    itemId TEXT NOT NULL, catalogVersion TEXT NOT NULL, slot TEXT NOT NULL,
    enhancementLevel INTEGER NOT NULL DEFAULT 0 CHECK(enhancementLevel BETWEEN 0 AND 15),
    pityBps INTEGER NOT NULL DEFAULT 0 CHECK(pityBps BETWEEN 0 AND 2000),
    bindingStatus TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'OWNED',
    acquiredSource TEXT NOT NULL, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS RpgPetInstance (
    petInstanceId TEXT PRIMARY KEY, guildId TEXT NOT NULL, ownerId TEXT NOT NULL,
    petId TEXT NOT NULL, catalogVersion TEXT NOT NULL, rarity TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1 CHECK(level BETWEEN 1 AND 50),
    xp INTEGER NOT NULL DEFAULT 0 CHECK(xp >= 0), evolutionState TEXT NOT NULL DEFAULT 'BASE',
    status TEXT NOT NULL DEFAULT 'OWNED', acquiredSource TEXT NOT NULL,
    createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS RpgOperation (
    operationId TEXT PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    operationType TEXT NOT NULL, reservationKey TEXT, status TEXT NOT NULL
        CHECK(status IN ('RESERVED','AWAITING_FUNDS','COMMITTED','VOID','REVIEW_REQUIRED')),
    sourceResourceId TEXT, outcomeJson TEXT NOT NULL, resultJson TEXT,
    transactionId TEXT, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL, settledAt TEXT,
    retryCount INTEGER NOT NULL DEFAULT 0 CHECK(retryCount >= 0),
    lastErrorCode TEXT, lastAttemptedAt TEXT,
    recoveryReviewJson TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId)
);
CREATE TABLE IF NOT EXISTS RpgStarterGrant (
    grantId TEXT PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','REVIEW_REQUIRED','VOID')),
    weaponInstanceId TEXT, armorInstanceId TEXT, accessoryInstanceId TEXT, petInstanceId TEXT,
    retryCount INTEGER NOT NULL DEFAULT 0 CHECK(retryCount >= 0),
    lastErrorCode TEXT, lastAttemptedAt TEXT,
    recoveryReviewJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL, committedAt TEXT,
    UNIQUE(guildId,userId)
);
CREATE TABLE IF NOT EXISTS RpgLegacyAsset (
    assetId TEXT PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    sourceType TEXT NOT NULL, sourceKey TEXT NOT NULL, sourceHash TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity >= 0),
    bindingStatus TEXT NOT NULL DEFAULT 'LEGACY_BOUND' CHECK(bindingStatus='LEGACY_BOUND'),
    migrationStatus TEXT NOT NULL CHECK(migrationStatus IN ('QUARANTINED','REVIEW_REQUIRED','REPLAYED','MALFORMED')),
    metadataJson TEXT NOT NULL DEFAULT '{}', migratedAt TEXT NOT NULL,
    UNIQUE(guildId,userId,sourceType,sourceKey)
);
CREATE TABLE IF NOT EXISTS RpgRecoveryReview (
    reviewId TEXT PRIMARY KEY, operationId TEXT, grantId TEXT,
    guildId TEXT NOT NULL, userId TEXT, reviewCode TEXT NOT NULL,
    metadataJson TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'OPEN',
    createdAt TEXT NOT NULL, resolvedAt TEXT,
    UNIQUE(operationId,reviewCode), UNIQUE(grantId,reviewCode)
);
CREATE TABLE IF NOT EXISTS RpgEnhancementAttempt (
    operationId TEXT PRIMARY KEY, equipmentInstanceId TEXT NOT NULL,
    targetLevel INTEGER NOT NULL, successRoll INTEGER NOT NULL,
    FOREIGN KEY(operationId) REFERENCES RpgOperation(operationId)
);
CREATE TABLE IF NOT EXISTS RpgOpenAttempt (
    operationId TEXT PRIMARY KEY, itemId TEXT NOT NULL, resultDefinitionId TEXT NOT NULL,
    FOREIGN KEY(operationId) REFERENCES RpgOperation(operationId)
);
CREATE TABLE IF NOT EXISTS RpgHuntRun (
    operationId TEXT PRIMARY KEY, areaId TEXT NOT NULL, playerXp INTEGER NOT NULL,
    activePetInstanceId TEXT, FOREIGN KEY(operationId) REFERENCES RpgOperation(operationId)
);
CREATE TABLE IF NOT EXISTS RpgDungeonRun (
    operationId TEXT PRIMARY KEY, dungeonId TEXT NOT NULL, playerXp INTEGER NOT NULL,
    activePetInstanceId TEXT, entryMethod TEXT NOT NULL,
    FOREIGN KEY(operationId) REFERENCES RpgOperation(operationId)
);
CREATE TABLE IF NOT EXISTS RpgCraftAttempt (
    operationId TEXT PRIMARY KEY, targetItemId TEXT NOT NULL, baseEquipmentInstanceId TEXT NOT NULL,
    blueprintItemId TEXT, FOREIGN KEY(operationId) REFERENCES RpgOperation(operationId)
);
CREATE TABLE IF NOT EXISTS RpgBossRaid (
    raidId TEXT PRIMARY KEY, guildId TEXT NOT NULL, tier TEXT NOT NULL,
    level INTEGER NOT NULL, maxHp INTEGER NOT NULL, currentHp INTEGER NOT NULL CHECK(currentHp >= 0),
    defense INTEGER NOT NULL, status TEXT NOT NULL
        CHECK(status IN ('ACTIVE','DEFEATED','AWAITING_FUNDS','SETTLED','CANCELLED')),
    startKey TEXT NOT NULL, rewardPlanJson TEXT, noValidParticipants INTEGER NOT NULL DEFAULT 0,
    lastHitUserId TEXT, settlementTransactionId TEXT, createdAt TEXT NOT NULL,
    defeatedAt TEXT, settledAt TEXT, updatedAt TEXT NOT NULL,
    UNIQUE(guildId,startKey)
);
CREATE TABLE IF NOT EXISTS RpgBossContribution (
    guildId TEXT NOT NULL, raidId TEXT NOT NULL, userId TEXT NOT NULL,
    committedDamage INTEGER NOT NULL DEFAULT 0 CHECK(committedDamage >= 0),
    attackCount INTEGER NOT NULL DEFAULT 0 CHECK(attackCount >= 0), updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId,raidId,userId), FOREIGN KEY(raidId) REFERENCES RpgBossRaid(raidId)
);
CREATE TABLE IF NOT EXISTS RpgBossAttack (
    operationId TEXT PRIMARY KEY, raidId TEXT NOT NULL, committedDamage INTEGER,
    FOREIGN KEY(operationId) REFERENCES RpgOperation(operationId),
    FOREIGN KEY(raidId) REFERENCES RpgBossRaid(raidId)
);
CREATE TABLE IF NOT EXISTS RpgBossParticipantReward (
    raidId TEXT NOT NULL, userId TEXT NOT NULL, rank INTEGER NOT NULL,
    eligible INTEGER NOT NULL CHECK(eligible IN (0,1)), damage INTEGER NOT NULL,
    etmAmount INTEGER NOT NULL DEFAULT 0, dropJson TEXT NOT NULL DEFAULT '{}',
    activePetInstanceId TEXT, petXp INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PLANNED', transactionId TEXT,
    PRIMARY KEY(raidId,userId), FOREIGN KEY(raidId) REFERENCES RpgBossRaid(raidId)
);
CREATE TABLE IF NOT EXISTS RpgQuestAssignment (
    guildId TEXT NOT NULL, userId TEXT NOT NULL, questType TEXT NOT NULL
        CHECK(questType IN ('DAILY','WEEKLY')), periodKey TEXT NOT NULL,
    periodStartUtc TEXT NOT NULL, periodEndUtc TEXT NOT NULL,
    assignedPlayerLevel INTEGER NOT NULL, bossDamageTarget INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','COMPLETED','CLAIMED')),
    claimedTransactionId TEXT, claimedAt TEXT, createdAt TEXT NOT NULL,
    UNIQUE(guildId,userId,questType,periodKey)
);
CREATE TABLE IF NOT EXISTS RpgAchievementGrant (
    grantId TEXT PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    achievementId TEXT NOT NULL, referenceId TEXT NOT NULL, grantedAt TEXT NOT NULL,
    UNIQUE(guildId,userId,achievementId,referenceId)
);
CREATE TABLE IF NOT EXISTS RpgPhase3MigrationReview (
    reviewId TEXT PRIMARY KEY, runId TEXT NOT NULL, guildId TEXT, userId TEXT,
    entityType TEXT NOT NULL, sourceKey TEXT NOT NULL, warningCode TEXT NOT NULL,
    detailsJson TEXT NOT NULL DEFAULT '{}', createdAt TEXT NOT NULL,
    UNIQUE(runId,entityType,sourceKey,warningCode)
);
CREATE INDEX IF NOT EXISTS idx_rpg_inventory_user ON RpgInventoryStack(guildId,userId,itemId);
CREATE INDEX IF NOT EXISTS idx_rpg_equipment_owner ON RpgEquipmentInstance(guildId,ownerId,status,slot);
CREATE INDEX IF NOT EXISTS idx_rpg_pet_owner ON RpgPetInstance(guildId,ownerId,status);
CREATE INDEX IF NOT EXISTS idx_rpg_operation_user ON RpgOperation(guildId,userId,operationType,status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rpg_operation_unresolved_key
ON RpgOperation(guildId,reservationKey)
WHERE reservationKey IS NOT NULL AND status IN ('RESERVED','AWAITING_FUNDS','REVIEW_REQUIRED');
CREATE UNIQUE INDEX IF NOT EXISTS idx_rpg_boss_one_unresolved
ON RpgBossRaid(guildId)
WHERE status IN ('ACTIVE','DEFEATED','AWAITING_FUNDS');
CREATE INDEX IF NOT EXISTS idx_rpg_boss_contribution_rank
ON RpgBossContribution(raidId,committedDamage DESC,userId ASC);
CREATE INDEX IF NOT EXISTS idx_rpg_quest_period
ON RpgQuestAssignment(guildId,userId,periodStartUtc,periodEndUtc);
CREATE INDEX IF NOT EXISTS idx_rpg_legacy_status
ON RpgLegacyAsset(guildId,migrationStatus,sourceType);
"""

PHASE3_TRIGGER_SQL = (
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_operation_plan_immutable
    BEFORE UPDATE ON RpgOperation
    WHEN NEW.outcomeJson IS NOT OLD.outcomeJson
      OR NEW.operationType IS NOT OLD.operationType
      OR NEW.sourceResourceId IS NOT OLD.sourceResourceId
      OR NEW.guildId IS NOT OLD.guildId OR NEW.userId IS NOT OLD.userId
    BEGIN SELECT RAISE(ABORT,'RpgOperation planned outcome is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_operation_result_once
    BEFORE UPDATE ON RpgOperation
    WHEN (OLD.resultJson IS NOT NULL AND NEW.resultJson IS NOT OLD.resultJson)
      OR (OLD.resultJson IS NULL AND NEW.resultJson IS NOT NULL AND NOT (
        (OLD.status='RESERVED' AND NEW.status IN ('COMMITTED','VOID')) OR
        (OLD.status='AWAITING_FUNDS' AND NEW.status IN ('COMMITTED','VOID')) OR
        (OLD.status='REVIEW_REQUIRED' AND NEW.status IN ('COMMITTED','VOID')
          AND NEW.recoveryReviewJson!='{}')
      ))
      OR (NEW.status IN ('COMMITTED','VOID') AND NEW.resultJson IS NULL)
      OR (NEW.status IN ('RESERVED','AWAITING_FUNDS','REVIEW_REQUIRED') AND NEW.resultJson IS NOT NULL)
    BEGIN SELECT RAISE(ABORT,'RpgOperation result transition invalid'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_operation_status_transition
    BEFORE UPDATE OF status ON RpgOperation
    WHEN NEW.status IS NOT OLD.status AND NOT (
      (OLD.status='RESERVED' AND NEW.status IN ('COMMITTED','VOID','REVIEW_REQUIRED','AWAITING_FUNDS')) OR
      (OLD.status='AWAITING_FUNDS' AND NEW.status IN ('COMMITTED','VOID','REVIEW_REQUIRED')) OR
      (OLD.status='REVIEW_REQUIRED' AND NEW.status IN ('COMMITTED','VOID') AND NEW.recoveryReviewJson!='{}')
    BEGIN SELECT RAISE(ABORT,'RpgOperation status transition invalid'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_operation_reservation_update
    BEFORE UPDATE ON RpgOperation
    WHEN (NEW.status IN ('RESERVED','AWAITING_FUNDS','REVIEW_REQUIRED') AND
          (NEW.reservationKey IS NULL OR NEW.reservationKey IS NOT OLD.reservationKey))
      OR (NEW.status IN ('COMMITTED','VOID') AND NEW.reservationKey IS NOT NULL)
    BEGIN SELECT RAISE(ABORT,'RpgOperation reservation transition invalid'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_operation_insert_shape
    BEFORE INSERT ON RpgOperation
    WHEN NEW.status NOT IN ('RESERVED','AWAITING_FUNDS','REVIEW_REQUIRED')
      OR NEW.reservationKey IS NULL OR NEW.resultJson IS NOT NULL
    BEGIN SELECT RAISE(ABORT,'RpgOperation insert shape invalid'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_operation_no_delete
    BEFORE DELETE ON RpgOperation
    BEGIN SELECT RAISE(ABORT,'RpgOperation cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_boss_plan_immutable
    BEFORE UPDATE OF rewardPlanJson ON RpgBossRaid
    WHEN OLD.rewardPlanJson IS NOT NULL AND NEW.rewardPlanJson IS NOT OLD.rewardPlanJson
    BEGIN SELECT RAISE(ABORT,'Boss reward plan is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_boss_reward_allocation_immutable
    BEFORE UPDATE ON RpgBossParticipantReward
    WHEN NEW.rank!=OLD.rank OR NEW.eligible!=OLD.eligible OR NEW.damage!=OLD.damage
      OR NEW.etmAmount!=OLD.etmAmount OR NEW.dropJson IS NOT OLD.dropJson
      OR NEW.activePetInstanceId IS NOT OLD.activePetInstanceId OR NEW.petXp!=OLD.petXp
    BEGIN SELECT RAISE(ABORT,'Boss participant allocation is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_boss_reward_allocation_no_delete
    BEFORE DELETE ON RpgBossParticipantReward
    BEGIN SELECT RAISE(ABORT,'Boss participant allocation cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_enhancement_outcome_immutable
    BEFORE UPDATE ON RpgEnhancementAttempt
    WHEN NEW.operationId!=OLD.operationId OR NEW.equipmentInstanceId!=OLD.equipmentInstanceId
      OR NEW.targetLevel!=OLD.targetLevel OR NEW.successRoll!=OLD.successRoll
    BEGIN SELECT RAISE(ABORT,'Enhancement outcome is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_open_outcome_immutable
    BEFORE UPDATE ON RpgOpenAttempt
    WHEN NEW.operationId!=OLD.operationId OR NEW.itemId!=OLD.itemId
      OR NEW.resultDefinitionId!=OLD.resultDefinitionId
    BEGIN SELECT RAISE(ABORT,'Open outcome is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_hunt_outcome_immutable
    BEFORE UPDATE ON RpgHuntRun
    WHEN NEW.operationId!=OLD.operationId OR NEW.areaId!=OLD.areaId
      OR NEW.playerXp!=OLD.playerXp OR NEW.activePetInstanceId IS NOT OLD.activePetInstanceId
    BEGIN SELECT RAISE(ABORT,'Hunt outcome is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_dungeon_outcome_immutable
    BEFORE UPDATE ON RpgDungeonRun
    WHEN NEW.operationId!=OLD.operationId OR NEW.dungeonId!=OLD.dungeonId
      OR NEW.playerXp!=OLD.playerXp OR NEW.activePetInstanceId IS NOT OLD.activePetInstanceId
      OR NEW.entryMethod!=OLD.entryMethod
    BEGIN SELECT RAISE(ABORT,'Dungeon outcome is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_craft_outcome_immutable
    BEFORE UPDATE ON RpgCraftAttempt
    WHEN NEW.operationId!=OLD.operationId OR NEW.targetItemId!=OLD.targetItemId
      OR NEW.baseEquipmentInstanceId!=OLD.baseEquipmentInstanceId
      OR NEW.blueprintItemId IS NOT OLD.blueprintItemId
    BEGIN SELECT RAISE(ABORT,'Craft outcome is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_boss_attack_outcome_immutable
    BEFORE UPDATE ON RpgBossAttack
    WHEN NEW.operationId!=OLD.operationId OR NEW.raidId!=OLD.raidId
      OR NEW.committedDamage IS NOT OLD.committedDamage
    BEGIN SELECT RAISE(ABORT,'Boss attack outcome is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_enhancement_outcome_no_delete
    BEFORE DELETE ON RpgEnhancementAttempt
    BEGIN SELECT RAISE(ABORT,'Enhancement outcome cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_open_outcome_no_delete
    BEFORE DELETE ON RpgOpenAttempt
    BEGIN SELECT RAISE(ABORT,'Open outcome cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_hunt_outcome_no_delete
    BEFORE DELETE ON RpgHuntRun
    BEGIN SELECT RAISE(ABORT,'Hunt outcome cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_dungeon_outcome_no_delete
    BEFORE DELETE ON RpgDungeonRun
    BEGIN SELECT RAISE(ABORT,'Dungeon outcome cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_craft_outcome_no_delete
    BEFORE DELETE ON RpgCraftAttempt
    BEGIN SELECT RAISE(ABORT,'Craft outcome cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_boss_attack_outcome_no_delete
    BEFORE DELETE ON RpgBossAttack
    BEGIN SELECT RAISE(ABORT,'Boss attack outcome cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_rpg_starter_children_immutable
    BEFORE UPDATE ON RpgStarterGrant
    WHEN OLD.status='COMMITTED' AND (
      NEW.weaponInstanceId IS NOT OLD.weaponInstanceId OR
      NEW.armorInstanceId IS NOT OLD.armorInstanceId OR
      NEW.accessoryInstanceId IS NOT OLD.accessoryInstanceId OR
      NEW.petInstanceId IS NOT OLD.petInstanceId OR
      NEW.guildId IS NOT OLD.guildId OR NEW.userId IS NOT OLD.userId
    BEGIN SELECT RAISE(ABORT,'Starter grant identity is immutable'); END""",
)

PHASE3_HARDENING_VERSION = 301
PHASE3_HARDENING_CHECKSUM = hashlib.sha256(
    (PHASE3_SCHEMA_SQL + "\n" + "\n".join(PHASE3_TRIGGER_SQL)).encode("utf-8")
).hexdigest()


async def _column_names(db, table):
    migration = await db.fetchrow(f"PRAGMA table_info({table})") as cursor:
        return {row[1] for row in await cursor.fetchall()}


def _split_sql(script):
    statements, buffer = [], ""
    for line in script.splitlines():
        buffer += line + "\n"
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                statements.append(statement)
            buffer = ""
    if buffer.strip():
        raise ValueError("Schema SQL tidak lengkap.")
    return statements


async def _table_exists(db, table):
    async with db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=$1", table,),
        return await cursor.fetchone() is not None


async def _add_column(db, table, name, definition):
    if name not in await _column_names(db, table):
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


async def _profile_rows(db, table):
    columns = (
        "guildId,userId,level,xp,maxHp,currentHp,attack,defense,critBps,energy,"
        "energyUpdatedAt,activeWeaponInstanceId,activeArmorInstanceId,"
        "activeAccessoryInstanceId,activePetInstanceId,migrationSourceHash,version,createdAt,updatedAt"
    async with db.execute(f"SELECT {columns} FROM {table} ORDER BY guildId,userId") as cursor:
        return await cursor.fetchall()


def _rows_checksum(rows):
    return hashlib.sha256(json.dumps(rows, separators=(",", ":"), default=str).encode().hexdigest()


def _injected_failure(actual, expected):
    if expected == actual:
        raise RuntimeError(f"Injected profile rebuild failure: {actual}")


async def _rebuild_profile(db, now, *, failure_stage=None):
    source_rows = await _profile_rows(db, "RpgProfile")
    source_keys = {(row[0], row[1]) for row in source_rows}
    await db.execute("DROP TABLE IF EXISTS RpgProfile_new")
    await db.execute("""CREATE TABLE RpgProfile_new (
        guildId TEXT NOT NULL, userId TEXT NOT NULL,
        level INTEGER NOT NULL DEFAULT 1 CHECK(level BETWEEN 1 AND 100),
        xp INTEGER NOT NULL DEFAULT 0 CHECK(xp >= 0),
        maxHp INTEGER NOT NULL DEFAULT 1000 CHECK(maxHp > 0),
        currentHp INTEGER NOT NULL DEFAULT 1000 CHECK(currentHp >= 0),
        attack INTEGER NOT NULL DEFAULT 50 CHECK(attack >= 0),
        defense INTEGER NOT NULL DEFAULT 25 CHECK(defense >= 0),
        critBps INTEGER NOT NULL DEFAULT 500 CHECK(critBps BETWEEN 0 AND 5000),
        energy INTEGER NOT NULL DEFAULT 100 CHECK(energy BETWEEN 0 AND 100),
        energyUpdatedAt TEXT NOT NULL,
        activeWeaponInstanceId TEXT, activeArmorInstanceId TEXT,
        activeAccessoryInstanceId TEXT, activePetInstanceId TEXT,
        migrationSourceHash TEXT, version INTEGER NOT NULL DEFAULT 0,
        createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
        starterPackClaimed INTEGER NOT NULL DEFAULT 0 CHECK(starterPackClaimed IN (0,1)),
        starterPackClaimedAt TEXT,
        PRIMARY KEY(guildId,userId)
    )""")
    _injected_failure("after_create", failure_stage)
    for row in source_rows:
        xp = 0 if int(row[2]) == 100 and int(row[3]) > 0 else int(row[3])
        await db.execute(
            "INSERT INTO RpgProfile_new "
            "(guildId,userId,level,xp,maxHp,currentHp,attack,defense,critBps,energy,energyUpdatedAt,"
            "activeWeaponInstanceId,activeArmorInstanceId,activeAccessoryInstanceId,activePetInstanceId,"
            "migrationSourceHash,version,createdAt,updatedAt,starterPackClaimed,starterPackClaimedAt) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,0,NULL)", *row[:3], xp, *row[4:]),
        )
        if int(row[2]) == 100 and int(row[3]) > 0:
            await db.execute(
                "INSERT OR IGNORE INTO RpgPhase3MigrationReview "
                "(reviewId,runId,guildId,userId,entityType,sourceKey,warningCode,detailsJson,createdAt) "
                "VALUES ($1,$2,$3,$4,$5 ,$6,'LEVEL_100_XP_RESET','{}',$7)", str(uuid.uuid4(), f"schema-{PHASE3_HARDENING_VERSION}", row[0], row[1],
                 "profile", f"{row[0]}:{row[1]}", now),
            )
    _injected_failure("after_copy", failure_stage)
    target_rows = await _profile_rows(db, "RpgProfile_new")
    if len(target_rows) != len(source_rows):
        raise ValueError("Jumlah row profile berubah saat rebuild.")
    if {(row[0], row[1]) for row in target_rows} != source_keys:
        raise ValueError("Key profile berubah saat rebuild.")
    # XP level 100 adalah satu-satunya transformasi yang diizinkan.
    normalized_source = [tuple((*row[:3], 0 if int(row[2]) == 100 and int(row[3]) > 0 else row[3], *row[4:]) for row in source_rows]
    if _rows_checksum(normalized_source) != _rows_checksum(target_rows):
        raise ValueError("Checksum profile berubah di luar transformasi yang diizinkan.")
    _injected_failure("after_validate", failure_stage)
    await db.execute("DROP TABLE RpgProfile")
    _injected_failure("after_drop", failure_stage)
    await db.execute("ALTER TABLE RpgProfile_new RENAME TO RpgProfile")
    _injected_failure("after_rename", failure_stage)
    await db.execute("CREATE INDEX idx_rpg_profile_level ON RpgProfile(guildId,level DESC,xp DESC)")
    await db.execute("CREATE INDEX idx_rpg_profile_user ON RpgProfile(userId)")


async def migrate_phase3_schema(db_path, *, rebuild_profile=True, _failure_stage=None):
    """Terapkan schema hanya pada target staging/temporary yang dipilih operator."""
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                "SELECT checksum,status FROM EconomySchemaMigration WHERE version=$1", PHASE3_HARDENING_VERSION,),
            )
            if migration and migration[1] == "COMPLETED":
                if migration[0] != PHASE3_HARDENING_CHECKSUM:
                    raise ValueError("Checksum schema hardening tidak cocok.")
                await db.rollback()
                return
            now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
            await db.execute(
                "INSERT OR REPLACE INTO EconomySchemaMigration "
                "(version,name,checksum,status,startedAt,detailsJson) VALUES ($1,$2,$3,$4,$5,'{}')",
                (PHASE3_HARDENING_VERSION, "phase3-hardening", PHASE3_HARDENING_CHECKSUM,
                 "RUNNING", now),
            )
            activity_columns = await _column_names(db, "EconomyActivityEvent")
            if "metricValue" not in activity_columns:
                await db.execute(
                    "ALTER TABLE EconomyActivityEvent ADD COLUMN metricValue "
                    "INTEGER NOT NULL DEFAULT 0 CHECK(metricValue >= 0)"
            schema_statements = _split_sql(PHASE3_SCHEMA_SQL)
            for statement in schema_statements:
                if statement.lstrip().upper().startswith(("CREATE INDEX", "CREATE UNIQUE INDEX"):
                    continue
                await db.execute(statement)
            await _add_column(db, "RpgOperation", "retryCount", "INTEGER NOT NULL DEFAULT 0 CHECK(retryCount>=0)")
            await _add_column(db, "RpgOperation", "lastErrorCode", "TEXT")
            await _add_column(db, "RpgOperation", "lastAttemptedAt", "TEXT")
            await _add_column(db, "RpgOperation", "recoveryReviewJson", "TEXT NOT NULL DEFAULT '{}'")
            starter_columns = {
                "grantId": "TEXT", "guildId": "TEXT", "userId": "TEXT",
                "status": "TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED'",
                "weaponInstanceId": "TEXT", "armorInstanceId": "TEXT",
                "accessoryInstanceId": "TEXT", "petInstanceId": "TEXT",
                "retryCount": "INTEGER NOT NULL DEFAULT 0", "lastErrorCode": "TEXT",
                "lastAttemptedAt": "TEXT", "recoveryReviewJson": "TEXT NOT NULL DEFAULT '{}'",
                "createdAt": "TEXT", "updatedAt": "TEXT", "committedAt": "TEXT",
            }
            for name, definition in starter_columns.items():
                await _add_column(db, "RpgStarterGrant", name, definition)
            legacy_columns = {
                "assetId": "TEXT", "guildId": "TEXT", "userId": "TEXT",
                "sourceType": "TEXT", "sourceKey": "TEXT", "sourceHash": "TEXT",
                "quantity": "INTEGER NOT NULL DEFAULT 1",
                "bindingStatus": "TEXT NOT NULL DEFAULT 'LEGACY_BOUND'",
                "migrationStatus": "TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED'",
                "metadataJson": "TEXT NOT NULL DEFAULT '{}'", "migratedAt": "TEXT",
            }
            for name, definition in legacy_columns.items():
                await _add_column(db, "RpgLegacyAsset", name, definition)
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_rpg_starter_grant_user "
                "ON RpgStarterGrant(guildId,userId)"
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_rpg_legacy_source "
                "ON RpgLegacyAsset(guildId,userId,sourceType,sourceKey)"
            for statement in schema_statements:
                if statement.lstrip().upper().startswith(("CREATE INDEX", "CREATE UNIQUE INDEX")):
                    await db.execute(statement)
            # Existing review rows from the pre-hardening build receive a stable key.
            await db.execute(
                "UPDATE RpgOperation SET reservationKey='recovery:'||guildId||':'||operationId "
                "WHERE status='REVIEW_REQUIRED' AND reservationKey IS NULL"
            await db.execute(
                "UPDATE RpgOperation SET resultJson=COALESCE(resultJson,'{\"code\":\"legacy_void\"}') "
                "WHERE status='VOID'"
            await db.execute(
                "UPDATE RpgOperation SET resultJson=COALESCE(resultJson,'{\"code\":\"legacy_committed\"}') "
                "WHERE status='COMMITTED'"
            await db.execute("DROP INDEX IF EXISTS idx_rpg_operation_unresolved_key")
            await db.execute(
                "CREATE UNIQUE INDEX idx_rpg_operation_unresolved_key ON RpgOperation(guildId,reservationKey) "
                "WHERE reservationKey IS NOT NULL AND status IN ('RESERVED','AWAITING_FUNDS','REVIEW_REQUIRED')"
            if rebuild_profile and await _table_exists(db, "RpgProfile"):
                profile_sql = (await (await db.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='RpgProfile'"
                )).fetchone())[0]
                profile_columns = await _column_names(db, "RpgProfile")
                if "currentHp <= maxHp" in profile_sql or "starterPackClaimed" not in profile_columns:
                    await db.execute("DROP INDEX IF EXISTS idx_rpg_profile_level")
                    await db.execute("DROP INDEX IF EXISTS idx_rpg_profile_user")
                await _rebuild_profile(db, now, failure_stage=_failure_stage)
            for trigger in PHASE3_TRIGGER_SQL:
                await db.execute(trigger)
            async with db.execute("PRAGMA foreign_key_check") as cursor:
                if await cursor.fetchall():
                    raise ValueError("foreign_key_check gagal setelah migrasi Phase 3.")
            async with db.execute("PRAGMA integrity_check") as cursor:
                if (await cursor.fetchone())[0] != "ok":
                    raise ValueError("integrity_check gagal setelah migrasi Phase 3.")
            await db.execute(
                "UPDATE EconomySchemaMigration SET status='COMPLETED',completedAt=$1 WHERE version=$2",
                (now, PHASE3_HARDENING_VERSION),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
