import aiosqlite

from .constants import SYSTEM_ACCOUNT_DEFINITIONS


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS EconomySchemaMigration (
    version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','COMPLETED','FAILED')),
    startedAt TEXT, completedAt TEXT, backupPath TEXT, manifestSha256 TEXT,
    detailsJson TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS EconomyMigrationRun (
    runId TEXT PRIMARY KEY, migrationVersion INTEGER NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('DRY_RUN','APPLY','RECOVERY','ROLLBACK')),
    status TEXT NOT NULL, guildId TEXT NOT NULL, sourceDbSha256 TEXT NOT NULL,
    backupPath TEXT, manifestPath TEXT, startedById TEXT, startedAt TEXT NOT NULL,
    completedAt TEXT, totalsJson TEXT NOT NULL DEFAULT '{}', errorCode TEXT
);
CREATE TABLE IF NOT EXISTS EconomyMigrationItem (
    runId TEXT NOT NULL, entityType TEXT NOT NULL, sourceKey TEXT NOT NULL,
    sourceHash TEXT NOT NULL, targetKey TEXT, status TEXT NOT NULL, errorCode TEXT,
    attemptCount INTEGER NOT NULL DEFAULT 0, updatedAt TEXT NOT NULL,
    PRIMARY KEY(runId, entityType, sourceKey),
    FOREIGN KEY(runId) REFERENCES EconomyMigrationRun(runId)
);
CREATE TABLE IF NOT EXISTS EconomyWallet (
    guildId TEXT NOT NULL, userId TEXT NOT NULL,
    etmBalance INTEGER NOT NULL DEFAULT 0 CHECK(etmBalance >= 0),
    ecyBalance INTEGER NOT NULL DEFAULT 0 CHECK(ecyBalance >= 0),
    version INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId, userId)
);
CREATE TABLE IF NOT EXISTS EconomySystemAccount (
    guildId TEXT NOT NULL, accountCode TEXT NOT NULL,
    currency TEXT NOT NULL CHECK(currency IN ('ETM','ECY')),
    accountClass TEXT NOT NULL CHECK(accountClass IN ('TREASURY','RESERVE','BURN','ISSUANCE')),
    balance INTEGER NOT NULL DEFAULT 0, spendable INTEGER NOT NULL DEFAULT 0 CHECK(spendable IN (0,1)),
    allowNegative INTEGER NOT NULL DEFAULT 0 CHECK(allowNegative IN (0,1)),
    version INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId, accountCode)
);
CREATE TABLE IF NOT EXISTS EconomyTransaction (
    transactionId TEXT PRIMARY KEY, guildId TEXT NOT NULL, idempotencyKey TEXT NOT NULL,
    operation TEXT NOT NULL, source TEXT NOT NULL, referenceId TEXT, actorId TEXT,
    reasonCode TEXT, reasonText TEXT, metadataJson TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','REVERSED')),
    createdAt TEXT NOT NULL, committedAt TEXT,
    UNIQUE(guildId, idempotencyKey)
);
CREATE TABLE IF NOT EXISTS EconomyLedger (
    id INTEGER PRIMARY KEY AUTOINCREMENT, transactionId TEXT NOT NULL,
    sequence INTEGER NOT NULL, guildId TEXT NOT NULL,
    accountKind TEXT NOT NULL CHECK(accountKind IN ('USER','SYSTEM')),
    accountId TEXT NOT NULL, userId TEXT,
    currency TEXT NOT NULL CHECK(currency IN ('ETM','ECY')),
    transactionType TEXT NOT NULL, amount INTEGER NOT NULL,
    balanceBefore INTEGER NOT NULL, balanceAfter INTEGER NOT NULL,
    referenceId TEXT, source TEXT NOT NULL, createdAt TEXT NOT NULL,
    UNIQUE(transactionId, sequence),
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId)
);
CREATE TABLE IF NOT EXISTS EconomyMintWhitelist (
    guildId TEXT NOT NULL, userId TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
    addedById TEXT NOT NULL, reasonCode TEXT NOT NULL, createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL, PRIMARY KEY(guildId, userId)
);
CREATE TABLE IF NOT EXISTS EconomyFeatureState (
    guildId TEXT NOT NULL, feature TEXT NOT NULL, paused INTEGER NOT NULL DEFAULT 0,
    reasonCode TEXT, changedById TEXT, changedAt TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(guildId, feature)
);
CREATE TABLE IF NOT EXISTS EconomySeedMarker (
    guildId TEXT NOT NULL, seedKey TEXT NOT NULL, accountCode TEXT NOT NULL,
    currency TEXT NOT NULL, amount INTEGER NOT NULL, transactionId TEXT NOT NULL,
    appliedAt TEXT NOT NULL, PRIMARY KEY(guildId, seedKey), UNIQUE(transactionId)
);
CREATE TABLE IF NOT EXISTS RpgProfile (
    guildId TEXT NOT NULL, userId TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1 CHECK(level BETWEEN 1 AND 100),
    xp INTEGER NOT NULL DEFAULT 0 CHECK(xp >= 0),
    maxHp INTEGER NOT NULL DEFAULT 1000 CHECK(maxHp > 0),
    currentHp INTEGER NOT NULL DEFAULT 1000 CHECK(currentHp >= 0 AND currentHp <= maxHp),
    attack INTEGER NOT NULL DEFAULT 50 CHECK(attack >= 0),
    defense INTEGER NOT NULL DEFAULT 25 CHECK(defense >= 0),
    critBps INTEGER NOT NULL DEFAULT 500 CHECK(critBps BETWEEN 0 AND 5000),
    energy INTEGER NOT NULL DEFAULT 100 CHECK(energy BETWEEN 0 AND 100),
    energyUpdatedAt TEXT NOT NULL,
    activeWeaponInstanceId TEXT, activeArmorInstanceId TEXT,
    activeAccessoryInstanceId TEXT, activePetInstanceId TEXT,
    migrationSourceHash TEXT, version INTEGER NOT NULL DEFAULT 0,
    createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId, userId)
);
CREATE TABLE IF NOT EXISTS EconomyClaimState (
    guildId TEXT NOT NULL, userId TEXT NOT NULL,
    claimType TEXT NOT NULL CHECK(claimType IN ('DAILY','WEEKLY')),
    lastClaimAt TEXT, nextEligibleAt TEXT, lastTransactionId TEXT,
    migrationSourceHash TEXT, version INTEGER NOT NULL DEFAULT 0,
    createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId, userId, claimType),
    FOREIGN KEY(lastTransactionId) REFERENCES EconomyTransaction(transactionId)
);
CREATE TABLE IF NOT EXISTS EconomyWorkState (
    guildId TEXT NOT NULL, userId TEXT NOT NULL,
    periodDate TEXT, successCount INTEGER NOT NULL DEFAULT 0 CHECK(successCount >= 0),
    lastSuccessAt TEXT, pendingRollId TEXT, migrationSourceHash TEXT,
    version INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId, userId),
    UNIQUE(pendingRollId)
);
CREATE TABLE IF NOT EXISTS EconomyRewardRoll (
    rollId TEXT PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    rewardType TEXT NOT NULL CHECK(rewardType IN ('WORK')),
    currency TEXT NOT NULL CHECK(currency IN ('ETM','ECY')),
    amount INTEGER NOT NULL CHECK(amount > 0),
    status TEXT NOT NULL CHECK(status IN ('RESERVED','COMMITTED','VOID')),
    transactionId TEXT, createdAt TEXT NOT NULL, settledAt TEXT, voidedAt TEXT,
    UNIQUE(transactionId),
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId)
);
CREATE TABLE IF NOT EXISTS EconomyDailyUsage (
    guildId TEXT NOT NULL, userId TEXT NOT NULL, periodDate TEXT NOT NULL,
    usageType TEXT NOT NULL CHECK(usageType IN ('TRANSFER_ETM','EXCHANGE_ETM')),
    submittedAmount INTEGER NOT NULL DEFAULT 0 CHECK(submittedAmount >= 0),
    version INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId, userId, periodDate, usageType)
);
CREATE TABLE IF NOT EXISTS EconomyActivityEvent (
    eventId TEXT PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    eventType TEXT NOT NULL, eventKey TEXT NOT NULL,
    points INTEGER NOT NULL CHECK(points >= 0),
    metricValue INTEGER NOT NULL DEFAULT 0 CHECK(metricValue >= 0),
    transactionId TEXT NULL, referenceId TEXT NULL,
    occurredAt TEXT NOT NULL, createdAt TEXT NOT NULL,
    UNIQUE(guildId, eventKey),
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId)
);
CREATE TABLE IF NOT EXISTS EconomyCutoverState (
    guildId TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK(state IN ('LEGACY','STAGING_READY','FORWARD_ONLY')),
    firstProductionTransactionId TEXT, changedById TEXT, changedAt TEXT NOT NULL,
    detailsJson TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(firstProductionTransactionId) REFERENCES EconomyTransaction(transactionId)
);
CREATE INDEX IF NOT EXISTS idx_economy_migration_status ON EconomyMigrationRun(migrationVersion, status);
CREATE INDEX IF NOT EXISTS idx_economy_migration_started ON EconomyMigrationRun(startedAt);
CREATE INDEX IF NOT EXISTS idx_economy_migration_item_status ON EconomyMigrationItem(entityType, status);
CREATE INDEX IF NOT EXISTS idx_economy_migration_item_hash ON EconomyMigrationItem(sourceHash);
CREATE INDEX IF NOT EXISTS idx_economy_wallet_etm ON EconomyWallet(guildId, etmBalance DESC);
CREATE INDEX IF NOT EXISTS idx_economy_wallet_ecy ON EconomyWallet(guildId, ecyBalance DESC);
CREATE INDEX IF NOT EXISTS idx_economy_wallet_user ON EconomyWallet(userId);
CREATE INDEX IF NOT EXISTS idx_economy_transaction_created ON EconomyTransaction(guildId, createdAt);
CREATE INDEX IF NOT EXISTS idx_economy_transaction_operation ON EconomyTransaction(guildId, operation, createdAt);
CREATE INDEX IF NOT EXISTS idx_economy_transaction_reference ON EconomyTransaction(guildId, referenceId);
CREATE INDEX IF NOT EXISTS idx_economy_transaction_actor ON EconomyTransaction(actorId, createdAt);
CREATE INDEX IF NOT EXISTS idx_economy_ledger_user ON EconomyLedger(guildId, userId, currency, createdAt);
CREATE INDEX IF NOT EXISTS idx_economy_ledger_account ON EconomyLedger(guildId, accountId, createdAt);
CREATE INDEX IF NOT EXISTS idx_economy_ledger_transaction ON EconomyLedger(transactionId);
CREATE INDEX IF NOT EXISTS idx_economy_ledger_reference ON EconomyLedger(referenceId);
CREATE INDEX IF NOT EXISTS idx_economy_whitelist_enabled ON EconomyMintWhitelist(guildId, enabled, userId);
CREATE INDEX IF NOT EXISTS idx_economy_feature_paused ON EconomyFeatureState(guildId, paused, feature);
CREATE INDEX IF NOT EXISTS idx_rpg_profile_level ON RpgProfile(guildId, level DESC, xp DESC);
CREATE INDEX IF NOT EXISTS idx_rpg_profile_user ON RpgProfile(userId);
CREATE INDEX IF NOT EXISTS idx_claim_eligibility ON EconomyClaimState(guildId, claimType, nextEligibleAt);
CREATE INDEX IF NOT EXISTS idx_work_last_success ON EconomyWorkState(guildId, lastSuccessAt);
CREATE INDEX IF NOT EXISTS idx_reward_roll_status_age ON EconomyRewardRoll(status, createdAt);
CREATE INDEX IF NOT EXISTS idx_reward_roll_user ON EconomyRewardRoll(guildId, userId, status);
CREATE INDEX IF NOT EXISTS idx_daily_usage_lookup ON EconomyDailyUsage(guildId, userId, periodDate, usageType);
CREATE INDEX IF NOT EXISTS idx_activity_user_occurred ON EconomyActivityEvent(guildId, userId, occurredAt);
CREATE INDEX IF NOT EXISTS idx_activity_transaction ON EconomyActivityEvent(transactionId);
CREATE INDEX IF NOT EXISTS idx_activity_type_occurred ON EconomyActivityEvent(guildId, eventType, occurredAt);
CREATE INDEX IF NOT EXISTS idx_cutover_state ON EconomyCutoverState(state, changedAt);
CREATE TRIGGER IF NOT EXISTS trg_activity_no_update
BEFORE UPDATE ON EconomyActivityEvent
BEGIN SELECT RAISE(ABORT, 'EconomyActivityEvent is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_activity_no_delete
BEFORE DELETE ON EconomyActivityEvent
BEGIN SELECT RAISE(ABORT, 'EconomyActivityEvent is append-only'); END;
"""


def ensure_phase1_schema(connection):
    connection.executescript(SCHEMA_SQL)


async def configure_connection(db):
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA busy_timeout=5000")


async def ensure_system_accounts(db, guild_id, now):
    for code, (currency, account_class, spendable, allow_negative) in SYSTEM_ACCOUNT_DEFINITIONS.items():
        await db.execute(
            "INSERT OR IGNORE INTO EconomySystemAccount "
            "(guildId,accountCode,currency,accountClass,balance,spendable,allowNegative,version,createdAt,updatedAt) "
            "VALUES (?,?,?,?,0,?,?,0,?,?)",
            (str(guild_id), code, currency, account_class, spendable, allow_negative, now, now),
        )


async def initialize_database(db_path):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.executescript(SCHEMA_SQL)
        await db.commit()
