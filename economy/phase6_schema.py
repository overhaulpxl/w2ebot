"""Schema Crypto V1 Phase 6; hanya dipasang oleh migration eksplisit."""

import hashlib
import re

from .constants import CRYPTO_ASSETS, ECONOMY_PHASE6_MIGRATION_VERSION


PHASE6_MIGRATION_NAME = "phase6-crypto"

PHASE6_TABLE_SQL = r"""
CREATE TABLE IF NOT EXISTS CryptoAssetDefinition (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    basePriceEcy INTEGER NOT NULL CHECK(basePriceEcy>0),
    minimumPriceEcy INTEGER NOT NULL CHECK(minimumPriceEcy>0),
    maximumPriceEcy INTEGER NOT NULL CHECK(maximumPriceEcy>=minimumPriceEcy),
    maximumNormalChangeBps INTEGER NOT NULL CHECK(maximumNormalChangeBps>0),
    volatilityLevel TEXT NOT NULL CHECK(volatilityLevel IN ('LOW','MODERATE','HIGH','EXTREME')),
    catalogVersion TEXT NOT NULL,
    createdAt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS CryptoMarketTick (
    tickId TEXT PRIMARY KEY,
    scheduledAt TEXT NOT NULL UNIQUE,
    outcomeJson TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('RESERVED','COMMITTED','REVIEW_REQUIRED')),
    resultJson TEXT,
    retryCount INTEGER NOT NULL DEFAULT 0 CHECK(retryCount>=0),
    lastErrorCode TEXT,
    createdAt TEXT NOT NULL,
    committedAt TEXT,
    CHECK((status='COMMITTED' AND resultJson IS NOT NULL AND committedAt IS NOT NULL)
       OR (status IN ('RESERVED','REVIEW_REQUIRED') AND resultJson IS NULL AND committedAt IS NULL))
);
CREATE TABLE IF NOT EXISTS CryptoMarketState (
    symbol TEXT PRIMARY KEY,
    currentPriceEcy INTEGER NOT NULL CHECK(currentPriceEcy>0),
    lastTickId TEXT,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    updatedAt TEXT NOT NULL,
    FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol),
    FOREIGN KEY(lastTickId) REFERENCES CryptoMarketTick(tickId)
);
CREATE TABLE IF NOT EXISTS CryptoPriceHistory (
    historyId TEXT PRIMARY KEY,
    tickId TEXT NOT NULL,
    symbol TEXT NOT NULL,
    previousPriceEcy INTEGER NOT NULL CHECK(previousPriceEcy>0),
    currentPriceEcy INTEGER NOT NULL CHECK(currentPriceEcy>0),
    movementBps INTEGER NOT NULL,
    movementType TEXT NOT NULL CHECK(movementType IN ('INITIAL','NORMAL','NORMAL_EVENT','MAJOR_EVENT')),
    occurredAt TEXT NOT NULL,
    UNIQUE(tickId,symbol),
    FOREIGN KEY(tickId) REFERENCES CryptoMarketTick(tickId),
    FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol)
);
CREATE TABLE IF NOT EXISTS CryptoHolding (
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    symbol TEXT NOT NULL,
    units INTEGER NOT NULL CHECK(units>=0),
    totalCostBasisEcy INTEGER NOT NULL CHECK(totalCostBasisEcy>=0),
    realizedProfitEcy INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','REVIEW_REQUIRED')),
    migrationSourceHash TEXT,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId,userId,symbol),
    FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol)
);
CREATE TABLE IF NOT EXISTS CryptoTrade (
    tradeId TEXT PRIMARY KEY,
    requestId TEXT NOT NULL,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
    quantityText TEXT NOT NULL,
    units INTEGER NOT NULL CHECK(units>0),
    priceEcy INTEGER NOT NULL CHECK(priceEcy>0),
    priceTickId TEXT,
    grossEcy INTEGER NOT NULL CHECK(grossEcy>=50),
    feeEcy INTEGER NOT NULL CHECK(feeEcy>0),
    marketFeeEcy INTEGER NOT NULL CHECK(marketFeeEcy>=0),
    treasuryFeeEcy INTEGER NOT NULL CHECK(treasuryFeeEcy>=0),
    burnFeeEcy INTEGER NOT NULL CHECK(burnFeeEcy>=0),
    costBasisDeltaEcy INTEGER NOT NULL CHECK(costBasisDeltaEcy>=0),
    realizedProfitEcy INTEGER NOT NULL,
    transactionId TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','VOID','REVIEW_REQUIRED')),
    receiptJson TEXT,
    voidReasonCode TEXT,
    retryCount INTEGER NOT NULL DEFAULT 0 CHECK(retryCount>=0),
    lastErrorCode TEXT,
    createdAt TEXT NOT NULL,
    settledAt TEXT,
    UNIQUE(guildId,requestId),
    FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol),
    FOREIGN KEY(priceTickId) REFERENCES CryptoMarketTick(tickId),
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId),
    CHECK(marketFeeEcy+treasuryFeeEcy+burnFeeEcy=feeEcy),
    CHECK((status='COMMITTED' AND receiptJson IS NOT NULL AND voidReasonCode IS NULL AND settledAt IS NOT NULL)
       OR (status='VOID' AND receiptJson IS NULL AND voidReasonCode IS NOT NULL AND settledAt IS NOT NULL)
       OR (status IN ('PENDING','REVIEW_REQUIRED') AND receiptJson IS NULL AND voidReasonCode IS NULL AND settledAt IS NULL))
);
CREATE TABLE IF NOT EXISTS CryptoNewsEvent (
    newsId TEXT PRIMARY KEY,
    eventKey TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    previousPriceEcy INTEGER NOT NULL CHECK(previousPriceEcy>0),
    currentPriceEcy INTEGER NOT NULL CHECK(currentPriceEcy>0),
    changeBps INTEGER NOT NULL,
    newsType TEXT NOT NULL CHECK(newsType IN ('ALERT','SURGE','CRASH')),
    comparisonStartedAt TEXT NOT NULL,
    occurredAt TEXT NOT NULL,
    FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol)
);
CREATE TABLE IF NOT EXISTS CryptoNewsOutbox (
    outboxId TEXT PRIMARY KEY,
    newsId TEXT NOT NULL,
    guildId TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','CLAIMED','SENT','FAILED','REVIEW_REQUIRED')),
    leaseOwner TEXT,
    leaseExpiresAt TEXT,
    attemptCount INTEGER NOT NULL DEFAULT 0 CHECK(attemptCount>=0),
    messageId TEXT,
    lastErrorCode TEXT,
    createdAt TEXT NOT NULL,
    sentAt TEXT,
    UNIQUE(newsId,guildId),
    FOREIGN KEY(newsId) REFERENCES CryptoNewsEvent(newsId)
);
CREATE TABLE IF NOT EXISTS CryptoRecoveryReview (
    reviewId TEXT PRIMARY KEY,
    guildId TEXT,
    entityType TEXT NOT NULL,
    entityId TEXT NOT NULL,
    errorCode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','RESOLVED')),
    sanitizedMetadataJson TEXT NOT NULL DEFAULT '{}',
    firstDetectedAt TEXT NOT NULL,
    lastAttemptedAt TEXT NOT NULL,
    resolvedAt TEXT,
    UNIQUE(guildId,entityType,entityId,errorCode)
);
CREATE TABLE IF NOT EXISTS CryptoLegacyHoldingMigration (
    sourceUserId TEXT NOT NULL,
    sourceSymbol TEXT NOT NULL,
    sourceHash TEXT NOT NULL,
    targetGuildId TEXT,
    targetUnits INTEGER,
    status TEXT NOT NULL CHECK(status IN ('MIGRATED','REVIEW_REQUIRED')),
    errorCode TEXT,
    sanitizedMetadataJson TEXT NOT NULL DEFAULT '{}',
    migratedAt TEXT NOT NULL,
    PRIMARY KEY(sourceUserId,sourceSymbol)
);
CREATE TABLE IF NOT EXISTS CryptoAuthorization (
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    permissionClass TEXT NOT NULL CHECK(permissionClass IN ('CRYPTO_CONTROL','CRYPTO_FINANCIAL','CRYPTO_RECOVERY')),
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    grantedById TEXT NOT NULL,
    reason TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId,userId,permissionClass)
);
CREATE TABLE IF NOT EXISTS CryptoAuthorizationAudit (
    auditId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    actorId TEXT NOT NULL,
    subjectId TEXT NOT NULL,
    permissionClass TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    reason TEXT NOT NULL,
    createdAt TEXT NOT NULL
);
"""

PHASE6_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_crypto_trade_user_unresolved ON CryptoTrade(guildId,userId) WHERE status IN ('PENDING','REVIEW_REQUIRED')",
    "CREATE INDEX IF NOT EXISTS idx_crypto_trade_history ON CryptoTrade(guildId,userId,createdAt DESC)",
    "CREATE INDEX IF NOT EXISTS idx_crypto_holding_user ON CryptoHolding(guildId,userId,status,symbol)",
    "CREATE INDEX IF NOT EXISTS idx_crypto_price_symbol_time ON CryptoPriceHistory(symbol,occurredAt DESC)",
    "CREATE INDEX IF NOT EXISTS idx_crypto_tick_status ON CryptoMarketTick(status,scheduledAt)",
    "CREATE INDEX IF NOT EXISTS idx_crypto_news_symbol_time ON CryptoNewsEvent(symbol,occurredAt DESC)",
    "CREATE INDEX IF NOT EXISTS idx_crypto_outbox_status ON CryptoNewsOutbox(status,leaseExpiresAt,createdAt)",
    "CREATE INDEX IF NOT EXISTS idx_crypto_review_status ON CryptoRecoveryReview(status,lastAttemptedAt)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_crypto_tick_unresolved ON CryptoMarketTick((1)) WHERE status IN ('RESERVED','REVIEW_REQUIRED')",
    "CREATE INDEX IF NOT EXISTS idx_crypto_auth_user ON CryptoAuthorization(guildId,userId,enabled)",
)

PHASE6_TRIGGER_SQL = (
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_asset_no_update BEFORE UPDATE ON CryptoAssetDefinition BEGIN SELECT RAISE(ABORT,'crypto asset definitions are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_asset_no_delete BEFORE DELETE ON CryptoAssetDefinition BEGIN SELECT RAISE(ABORT,'crypto asset definitions cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_tick_outcome_immutable BEFORE UPDATE ON CryptoMarketTick WHEN NEW.outcomeJson<>OLD.outcomeJson OR NEW.scheduledAt<>OLD.scheduledAt BEGIN SELECT RAISE(ABORT,'crypto tick outcome is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_tick_transition BEFORE UPDATE OF status ON CryptoMarketTick WHEN NOT ((OLD.status='RESERVED' AND NEW.status IN ('COMMITTED','REVIEW_REQUIRED')) OR (OLD.status='REVIEW_REQUIRED' AND NEW.status='COMMITTED') OR OLD.status=NEW.status) BEGIN SELECT RAISE(ABORT,'invalid crypto tick transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_tick_terminal BEFORE UPDATE ON CryptoMarketTick WHEN OLD.status='COMMITTED' BEGIN SELECT RAISE(ABORT,'committed crypto tick is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_tick_no_delete BEFORE DELETE ON CryptoMarketTick BEGIN SELECT RAISE(ABORT,'crypto tick history cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_price_no_update BEFORE UPDATE ON CryptoPriceHistory BEGIN SELECT RAISE(ABORT,'crypto price history is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_price_no_delete BEFORE DELETE ON CryptoPriceHistory BEGIN SELECT RAISE(ABORT,'crypto price history cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_trade_plan_immutable BEFORE UPDATE ON CryptoTrade WHEN NEW.requestId<>OLD.requestId OR NEW.guildId<>OLD.guildId OR NEW.userId<>OLD.userId OR NEW.symbol<>OLD.symbol OR NEW.side<>OLD.side OR NEW.quantityText<>OLD.quantityText OR NEW.units<>OLD.units OR NEW.priceEcy<>OLD.priceEcy OR NEW.priceTickId IS NOT OLD.priceTickId OR NEW.grossEcy<>OLD.grossEcy OR NEW.feeEcy<>OLD.feeEcy OR NEW.marketFeeEcy<>OLD.marketFeeEcy OR NEW.treasuryFeeEcy<>OLD.treasuryFeeEcy OR NEW.burnFeeEcy<>OLD.burnFeeEcy OR NEW.costBasisDeltaEcy<>OLD.costBasisDeltaEcy OR NEW.realizedProfitEcy<>OLD.realizedProfitEcy OR NEW.transactionId<>OLD.transactionId BEGIN SELECT RAISE(ABORT,'crypto trade plan is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_trade_transition BEFORE UPDATE OF status ON CryptoTrade WHEN NOT ((OLD.status='PENDING' AND NEW.status IN ('COMMITTED','VOID','REVIEW_REQUIRED')) OR (OLD.status='REVIEW_REQUIRED' AND NEW.status IN ('COMMITTED','VOID')) OR OLD.status=NEW.status) BEGIN SELECT RAISE(ABORT,'invalid crypto trade transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_trade_receipt BEFORE UPDATE ON CryptoTrade WHEN (OLD.receiptJson IS NOT NULL AND NEW.receiptJson IS NOT OLD.receiptJson) OR (OLD.receiptJson IS NULL AND NEW.receiptJson IS NOT NULL AND NEW.status<>'COMMITTED') OR OLD.status IN ('COMMITTED','VOID') BEGIN SELECT RAISE(ABORT,'crypto trade receipt is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_trade_no_delete BEFORE DELETE ON CryptoTrade BEGIN SELECT RAISE(ABORT,'crypto trade history cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_news_no_update BEFORE UPDATE ON CryptoNewsEvent BEGIN SELECT RAISE(ABORT,'crypto news history is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_news_no_delete BEFORE DELETE ON CryptoNewsEvent BEGIN SELECT RAISE(ABORT,'crypto news history cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_outbox_transition BEFORE UPDATE OF status ON CryptoNewsOutbox WHEN NOT ((OLD.status IN ('PENDING','FAILED') AND NEW.status IN ('CLAIMED','REVIEW_REQUIRED')) OR (OLD.status='CLAIMED' AND NEW.status IN ('SENT','FAILED','REVIEW_REQUIRED')) OR OLD.status=NEW.status) BEGIN SELECT RAISE(ABORT,'invalid crypto outbox transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_outbox_no_delete BEFORE DELETE ON CryptoNewsOutbox BEGIN SELECT RAISE(ABORT,'crypto outbox history cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_review_no_delete BEFORE DELETE ON CryptoRecoveryReview BEGIN SELECT RAISE(ABORT,'crypto recovery review cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_legacy_no_update BEFORE UPDATE ON CryptoLegacyHoldingMigration BEGIN SELECT RAISE(ABORT,'crypto legacy migration is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_legacy_no_delete BEFORE DELETE ON CryptoLegacyHoldingMigration BEGIN SELECT RAISE(ABORT,'crypto legacy migration cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_auth_audit_no_update BEFORE UPDATE ON CryptoAuthorizationAudit BEGIN SELECT RAISE(ABORT,'crypto authorization audit is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_crypto_auth_audit_no_delete BEFORE DELETE ON CryptoAuthorizationAudit BEGIN SELECT RAISE(ABORT,'crypto authorization audit cannot be deleted'); END""",
)


def _canonical(value):
    return " ".join(str(value).split())


PHASE6_SCHEMA_CHECKSUM = hashlib.sha256(
    (PHASE6_MIGRATION_NAME + "\n" + _canonical(PHASE6_TABLE_SQL) + "\n" +
     "\n".join(_canonical(value) for value in PHASE6_INDEX_SQL + PHASE6_TRIGGER_SQL)).encode("utf-8")
).hexdigest()

REQUIRED_PHASE6_TABLES = {
    "CryptoAssetDefinition", "CryptoMarketTick", "CryptoMarketState", "CryptoPriceHistory",
    "CryptoHolding", "CryptoTrade", "CryptoNewsEvent", "CryptoNewsOutbox",
    "CryptoRecoveryReview", "CryptoLegacyHoldingMigration",
    "CryptoAuthorization", "CryptoAuthorizationAudit",
}
REQUIRED_PHASE6_INDEXES = {re.search(r"INDEX IF NOT EXISTS (\w+)", value).group(1) for value in PHASE6_INDEX_SQL}
REQUIRED_PHASE6_TRIGGERS = {re.search(r"TRIGGER IF NOT EXISTS (\w+)", value).group(1) for value in PHASE6_TRIGGER_SQL}
REQUIRED_PHASE6_COLUMNS = {
    "CryptoAssetDefinition": {"symbol", "name", "basePriceEcy", "minimumPriceEcy", "maximumPriceEcy", "maximumNormalChangeBps", "volatilityLevel", "catalogVersion", "createdAt"},
    "CryptoMarketTick": {"tickId", "scheduledAt", "outcomeJson", "status", "resultJson", "retryCount", "lastErrorCode", "createdAt", "committedAt"},
    "CryptoMarketState": {"symbol", "currentPriceEcy", "lastTickId", "version", "updatedAt"},
    "CryptoPriceHistory": {"historyId", "tickId", "symbol", "previousPriceEcy", "currentPriceEcy", "movementBps", "movementType", "occurredAt"},
    "CryptoHolding": {"guildId", "userId", "symbol", "units", "totalCostBasisEcy", "realizedProfitEcy", "status", "migrationSourceHash", "version", "createdAt", "updatedAt"},
    "CryptoTrade": {"tradeId", "requestId", "guildId", "userId", "symbol", "side", "quantityText", "units", "priceEcy", "priceTickId", "grossEcy", "feeEcy", "marketFeeEcy", "treasuryFeeEcy", "burnFeeEcy", "costBasisDeltaEcy", "realizedProfitEcy", "transactionId", "status", "receiptJson", "voidReasonCode", "retryCount", "lastErrorCode", "createdAt", "settledAt"},
    "CryptoNewsEvent": {"newsId", "eventKey", "symbol", "previousPriceEcy", "currentPriceEcy", "changeBps", "newsType", "comparisonStartedAt", "occurredAt"},
    "CryptoNewsOutbox": {"outboxId", "newsId", "guildId", "status", "leaseOwner", "leaseExpiresAt", "attemptCount", "messageId", "lastErrorCode", "createdAt", "sentAt"},
    "CryptoRecoveryReview": {"reviewId", "guildId", "entityType", "entityId", "errorCode", "status", "sanitizedMetadataJson", "firstDetectedAt", "lastAttemptedAt", "resolvedAt"},
    "CryptoLegacyHoldingMigration": {"sourceUserId", "sourceSymbol", "sourceHash", "targetGuildId", "targetUnits", "status", "errorCode", "sanitizedMetadataJson", "migratedAt"},
    "CryptoAuthorization": {"guildId", "userId", "permissionClass", "enabled", "grantedById", "reason", "version", "createdAt", "updatedAt"},
    "CryptoAuthorizationAudit": {"auditId", "guildId", "actorId", "subjectId", "permissionClass", "enabled", "reason", "createdAt"},
}


def phase6_capability_sync(connection):
    marker = connection.execute(
        "SELECT checksum,status FROM EconomySchemaMigration WHERE version=?",
        (ECONOMY_PHASE6_MIGRATION_VERSION,),
    ).fetchone()
    if not marker or marker != (PHASE6_SCHEMA_CHECKSUM, "COMPLETED"):
        return False
    objects = dict(connection.execute(
        "SELECT name,type FROM sqlite_master WHERE name LIKE 'Crypto%' OR name LIKE 'idx_crypto_%' OR name LIKE 'uq_crypto_%' OR name LIKE 'trg_crypto_%'"
    ).fetchall())
    structure_ready = (all(objects.get(name) == "table" for name in REQUIRED_PHASE6_TABLES)
                       and all(objects.get(name) == "index" for name in REQUIRED_PHASE6_INDEXES)
                       and all(objects.get(name) == "trigger" for name in REQUIRED_PHASE6_TRIGGERS))
    if not structure_ready:
        return False
    for table, required in REQUIRED_PHASE6_COLUMNS.items():
        observed = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()}
        if not required.issubset(observed):
            return False
    definitions = connection.execute(
        "SELECT symbol,name,basePriceEcy,maximumNormalChangeBps,volatilityLevel "
        "FROM CryptoAssetDefinition ORDER BY symbol"
    ).fetchall()
    expected = sorted(
        (symbol, name, price, maximum_bps, level)
        for symbol, (name, price, maximum_bps, level) in CRYPTO_ASSETS.items()
    )
    state_symbols = [row[0] for row in connection.execute(
        "SELECT symbol FROM CryptoMarketState ORDER BY symbol"
    ).fetchall()]
    return definitions == expected and state_symbols == sorted(CRYPTO_ASSETS)


async def phase6_capability(db):
    async with db.execute(
        "SELECT checksum,status FROM EconomySchemaMigration WHERE version=?",
        (ECONOMY_PHASE6_MIGRATION_VERSION,),
    ) as cursor:
        marker = await cursor.fetchone()
    if not marker or tuple(marker) != (PHASE6_SCHEMA_CHECKSUM, "COMPLETED"):
        return False
    async with db.execute(
        "SELECT name,type FROM sqlite_master WHERE name LIKE 'Crypto%' OR name LIKE 'idx_crypto_%' OR name LIKE 'uq_crypto_%' OR name LIKE 'trg_crypto_%'"
    ) as cursor:
        objects = dict(await cursor.fetchall())
    structure_ready = (all(objects.get(name) == "table" for name in REQUIRED_PHASE6_TABLES)
                       and all(objects.get(name) == "index" for name in REQUIRED_PHASE6_INDEXES)
                       and all(objects.get(name) == "trigger" for name in REQUIRED_PHASE6_TRIGGERS))
    if not structure_ready:
        return False
    for table, required in REQUIRED_PHASE6_COLUMNS.items():
        async with db.execute(f'PRAGMA table_info("{table}")') as cursor:
            observed = {row[1] for row in await cursor.fetchall()}
        if not required.issubset(observed):
            return False
    async with db.execute(
        "SELECT symbol,name,basePriceEcy,maximumNormalChangeBps,volatilityLevel "
        "FROM CryptoAssetDefinition ORDER BY symbol"
    ) as cursor:
        definitions = await cursor.fetchall()
    expected = sorted(
        (symbol, name, price, maximum_bps, level)
        for symbol, (name, price, maximum_bps, level) in CRYPTO_ASSETS.items()
    )
    async with db.execute("SELECT symbol FROM CryptoMarketState ORDER BY symbol") as cursor:
        state_symbols = [row[0] for row in await cursor.fetchall()]
    return definitions == expected and state_symbols == sorted(CRYPTO_ASSETS)
