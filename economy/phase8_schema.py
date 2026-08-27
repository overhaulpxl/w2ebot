"""Schema eksplisit Phase 8 Giveaway dan Eternal Options."""

import hashlib
import re

import aiosqlite

from .constants import ECONOMY_PHASE8_MIGRATION_VERSION
from .phase5_schema import PHASE5_SCHEMA_CHECKSUM, phase5_capability, phase5_capability_sync
from .phase6_schema import PHASE6_SCHEMA_CHECKSUM, phase6_capability, phase6_capability_sync


PHASE8_MIGRATION_NAME = "phase8-giveaway-options"

PHASE8_TABLE_SQL = r"""
CREATE TABLE IF NOT EXISTS Phase8Operation (
    operationId TEXT PRIMARY KEY,
    requestId TEXT NOT NULL,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    operationType TEXT NOT NULL CHECK(operationType IN
      ('GIVEAWAY_CREATE','GIVEAWAY_ENTER','GIVEAWAY_END','GIVEAWAY_CANCEL','GIVEAWAY_REDRAW',
       'OPTIONS_OPEN','OPTIONS_SETTLE')),
    entityId TEXT,
    reservationKey TEXT,
    outcomeJson TEXT NOT NULL,
    resultJson TEXT,
    transactionId TEXT,
    status TEXT NOT NULL CHECK(status IN ('RESERVED','COMMITTED','VOID','REVIEW_REQUIRED')),
    retryCount INTEGER NOT NULL DEFAULT 0 CHECK(retryCount>=0),
    lastErrorCode TEXT,
    lastAttemptedAt TEXT,
    reviewMetadataJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL,
    settledAt TEXT,
    UNIQUE(guildId,requestId),
    CHECK((status IN ('RESERVED','REVIEW_REQUIRED') AND reservationKey IS NOT NULL AND resultJson IS NULL AND settledAt IS NULL)
       OR (status IN ('COMMITTED','VOID') AND reservationKey IS NULL AND resultJson IS NOT NULL AND settledAt IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS GiveawayV1 (
    giveawayId TEXT PRIMARY KEY,
    requestId TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    channelId TEXT NOT NULL,
    messageId TEXT,
    hostId TEXT NOT NULL,
    prize TEXT NOT NULL CHECK(length(prize) BETWEEN 1 AND 300),
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','DRAW_PENDING','AWAITING_CLAIM','COMPLETED','CANCELLED','REVIEW_REQUIRED')),
    startsAt TEXT NOT NULL,
    endsAt TEXT NOT NULL,
    claimDeadline TEXT,
    currentWinnerId TEXT,
    drawSequence INTEGER NOT NULL DEFAULT 0 CHECK(drawSequence>=0),
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS GiveawayTicket (
    ticketId TEXT PRIMARY KEY,
    giveawayId TEXT NOT NULL,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    amountEcy INTEGER NOT NULL CHECK(amountEcy=10000),
    eligibilityEvidenceJson TEXT NOT NULL,
    evidenceHash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PAID','REFUNDED','ALLOCATED')),
    entryTransactionId TEXT NOT NULL UNIQUE,
    refundTransactionId TEXT UNIQUE,
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    UNIQUE(giveawayId,userId),
    FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId),
    FOREIGN KEY(entryTransactionId) REFERENCES EconomyTransaction(transactionId),
    FOREIGN KEY(refundTransactionId) REFERENCES EconomyTransaction(transactionId)
);
CREATE TABLE IF NOT EXISTS GiveawayEligibilityEvidence (
    evidenceId TEXT PRIMARY KEY,
    giveawayId TEXT NOT NULL,
    userId TEXT NOT NULL,
    stage TEXT NOT NULL CHECK(stage IN ('ENTRY','DRAW','REDRAW')),
    drawSequence INTEGER NOT NULL DEFAULT 0 CHECK(drawSequence>=0),
    eligible INTEGER NOT NULL CHECK(eligible IN (0,1)),
    evidenceJson TEXT NOT NULL,
    evidenceHash TEXT NOT NULL,
    observedAt TEXT NOT NULL,
    UNIQUE(giveawayId,userId,stage,drawSequence),
    FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId)
);
CREATE TABLE IF NOT EXISTS GiveawayEscrow (
    giveawayId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    paidTickets INTEGER NOT NULL DEFAULT 0 CHECK(paidTickets>=0),
    amountEcy INTEGER NOT NULL DEFAULT 0 CHECK(amountEcy=paidTickets*10000),
    status TEXT NOT NULL CHECK(status IN ('OPEN','ALLOCATED','REFUNDED','REVIEW_REQUIRED')),
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    updatedAt TEXT NOT NULL,
    FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId)
);
CREATE TABLE IF NOT EXISTS GiveawayDraw (
    drawId TEXT PRIMARY KEY,
    giveawayId TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence>0),
    requestId TEXT NOT NULL UNIQUE,
    participantEvidenceJson TEXT NOT NULL,
    poolJson TEXT NOT NULL,
    poolHash TEXT NOT NULL,
    randomIndex INTEGER,
    winnerId TEXT,
    noEligibleParticipants INTEGER NOT NULL CHECK(noEligibleParticipants IN (0,1)),
    receiptJson TEXT NOT NULL,
    createdAt TEXT NOT NULL,
    UNIQUE(giveawayId,sequence),
    FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId)
);
CREATE TABLE IF NOT EXISTS GiveawayWinner (
    winnerId TEXT PRIMARY KEY,
    giveawayId TEXT NOT NULL,
    drawId TEXT NOT NULL UNIQUE,
    userId TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence>0),
    status TEXT NOT NULL CHECK(status IN ('AWAITING_CLAIM','CLAIMED','INVALIDATED')),
    eligibilityEvidenceJson TEXT NOT NULL,
    claimDeadline TEXT NOT NULL,
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    UNIQUE(giveawayId,sequence),
    FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId),
    FOREIGN KEY(drawId) REFERENCES GiveawayDraw(drawId)
);
CREATE TABLE IF NOT EXISTS GiveawayClaim (
    claimId TEXT PRIMARY KEY,
    giveawayId TEXT NOT NULL UNIQUE,
    winnerId TEXT NOT NULL UNIQUE,
    userId TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status='ACKNOWLEDGED'),
    receiptJson TEXT NOT NULL,
    claimedAt TEXT NOT NULL,
    FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId),
    FOREIGN KEY(winnerId) REFERENCES GiveawayWinner(winnerId)
);
CREATE TABLE IF NOT EXISTS GiveawayWinnerReview (
    reviewId TEXT PRIMARY KEY,
    giveawayId TEXT NOT NULL,
    winnerId TEXT NOT NULL,
    reasonCode TEXT NOT NULL CHECK(reasonCode IN ('CLAIM_EXPIRED','WINNER_DEPARTED','WINNER_INVALID','RULE_VIOLATION')),
    evidenceType TEXT NOT NULL,
    evidenceReference TEXT NOT NULL,
    evidenceHash TEXT NOT NULL,
    reviewerId TEXT NOT NULL,
    reviewedAt TEXT NOT NULL,
    priorWinnerStateJson TEXT NOT NULL,
    sanitizedMetadataJson TEXT NOT NULL DEFAULT '{}',
    auditReceiptJson TEXT NOT NULL,
    consumed INTEGER NOT NULL DEFAULT 0 CHECK(consumed IN (0,1)),
    consumedAt TEXT,
    UNIQUE(giveawayId,winnerId,reasonCode,evidenceHash),
    FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId),
    FOREIGN KEY(winnerId) REFERENCES GiveawayWinner(winnerId)
);
CREATE TABLE IF NOT EXISTS GiveawayRefund (
    refundId TEXT PRIMARY KEY,
    giveawayId TEXT NOT NULL,
    ticketId TEXT NOT NULL UNIQUE,
    userId TEXT NOT NULL,
    amountEcy INTEGER NOT NULL CHECK(amountEcy=10000),
    transactionId TEXT NOT NULL UNIQUE,
    receiptJson TEXT NOT NULL,
    createdAt TEXT NOT NULL,
    FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId),
    FOREIGN KEY(ticketId) REFERENCES GiveawayTicket(ticketId),
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId)
);
CREATE TABLE IF NOT EXISTS GiveawayFundAllocation (
    allocationId TEXT PRIMARY KEY,
    giveawayId TEXT NOT NULL UNIQUE,
    totalEcy INTEGER NOT NULL CHECK(totalEcy>=0),
    retainedEcy INTEGER NOT NULL CHECK(retainedEcy>=0),
    reserveEcy INTEGER NOT NULL CHECK(reserveEcy>=0),
    burnEcy INTEGER NOT NULL CHECK(burnEcy>=0),
    transactionId TEXT,
    receiptJson TEXT NOT NULL,
    createdAt TEXT NOT NULL,
    CHECK(retainedEcy+reserveEcy+burnEcy=totalEcy),
    FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId),
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId)
);
CREATE TABLE IF NOT EXISTS GiveawayVoiceQualification (
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    channelId TEXT NOT NULL,
    qualifiedStartAt TEXT NOT NULL,
    awardedThroughAt TEXT NOT NULL,
    lastObservedAt TEXT NOT NULL,
    nextBlockSequence INTEGER NOT NULL DEFAULT 1 CHECK(nextBlockSequence>0),
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','CLOSED')),
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    PRIMARY KEY(guildId,userId)
);
CREATE TABLE IF NOT EXISTS GiveawayVoiceBlock (
    blockId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    channelId TEXT NOT NULL,
    qualifiedStartAt TEXT NOT NULL,
    blockSequence INTEGER NOT NULL CHECK(blockSequence>0),
    blockEndAt TEXT NOT NULL,
    activityEventId TEXT NOT NULL UNIQUE,
    createdAt TEXT NOT NULL,
    UNIQUE(guildId,userId,qualifiedStartAt,blockSequence),
    FOREIGN KEY(activityEventId) REFERENCES EconomyActivityEvent(eventId)
);
CREATE TABLE IF NOT EXISTS GiveawayLegacySnapshot (
    snapshotId TEXT PRIMARY KEY,
    sourceType TEXT NOT NULL,
    sourceIdentity TEXT NOT NULL,
    sourceHash TEXT NOT NULL,
    rawSourceJson TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('READ_ONLY','REVIEW_REQUIRED')),
    createdAt TEXT NOT NULL,
    UNIQUE(sourceType,sourceIdentity,sourceHash)
);
CREATE TABLE IF NOT EXISTS EternalOptionPosition (
    positionId TEXT PRIMARY KEY,
    requestId TEXT NOT NULL,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('UP','DOWN')),
    stakeEcy INTEGER NOT NULL CHECK(stakeEcy BETWEEN 1000 AND 500000 AND stakeEcy%1000=0),
    liabilityEcy INTEGER NOT NULL CHECK(liabilityEcy=stakeEcy*19000/10000),
    durationMinutes INTEGER NOT NULL CHECK(durationMinutes IN (5,10,30)),
    entryHistoryId TEXT NOT NULL,
    entryPriceEcy INTEGER NOT NULL CHECK(entryPriceEcy>0),
    expiresAt TEXT NOT NULL,
    expiryHistoryId TEXT,
    expiryPriceEcy INTEGER CHECK(expiryPriceEcy>0),
    openingTransactionId TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','SETTLEMENT_PENDING','COMMITTED','REVIEW_REQUIRED')),
    resultCode TEXT CHECK(resultCode IN ('WIN','LOSS','TIE') OR resultCode IS NULL),
    receiptJson TEXT,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    createdAt TEXT NOT NULL,
    settledAt TEXT,
    UNIQUE(guildId,requestId),
    FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol),
    FOREIGN KEY(entryHistoryId) REFERENCES CryptoPriceHistory(historyId),
    FOREIGN KEY(expiryHistoryId) REFERENCES CryptoPriceHistory(historyId),
    FOREIGN KEY(openingTransactionId) REFERENCES EconomyTransaction(transactionId)
);
CREATE TABLE IF NOT EXISTS EternalOptionReservation (
    reservationId TEXT PRIMARY KEY,
    positionId TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    liabilityEcy INTEGER NOT NULL CHECK(liabilityEcy>0),
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','RELEASED','REVIEW_REQUIRED')),
    createdAt TEXT NOT NULL,
    releasedAt TEXT,
    FOREIGN KEY(positionId) REFERENCES EternalOptionPosition(positionId)
);
CREATE TABLE IF NOT EXISTS EternalOptionSettlement (
    settlementId TEXT PRIMARY KEY,
    positionId TEXT NOT NULL UNIQUE,
    resultCode TEXT NOT NULL CHECK(resultCode IN ('WIN','LOSS','TIE')),
    payoutEcy INTEGER NOT NULL CHECK(payoutEcy>=0),
    transactionId TEXT UNIQUE,
    openingTransactionId TEXT NOT NULL,
    receiptJson TEXT NOT NULL,
    settledAt TEXT NOT NULL,
    FOREIGN KEY(positionId) REFERENCES EternalOptionPosition(positionId),
    FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId),
    FOREIGN KEY(openingTransactionId) REFERENCES EconomyTransaction(transactionId),
    CHECK((resultCode='LOSS' AND transactionId IS NULL AND payoutEcy=0) OR
          (resultCode IN ('WIN','TIE') AND transactionId IS NOT NULL AND payoutEcy>0))
);
CREATE TABLE IF NOT EXISTS Phase8NotificationOutbox (
    outboxId TEXT PRIMARY KEY,
    eventKey TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    channelId TEXT,
    userId TEXT,
    entityType TEXT NOT NULL,
    entityId TEXT NOT NULL,
    payloadJson TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','CLAIMED','SENT','FAILED','REVIEW_REQUIRED')),
    leaseOwner TEXT,
    leaseExpiresAt TEXT,
    attemptCount INTEGER NOT NULL DEFAULT 0 CHECK(attemptCount>=0),
    messageId TEXT,
    lastErrorCode TEXT,
    createdAt TEXT NOT NULL,
    sentAt TEXT
);
CREATE TABLE IF NOT EXISTS Phase8RecoveryReview (
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
CREATE TABLE IF NOT EXISTS Phase8Audit (
    auditId TEXT PRIMARY KEY,
    guildId TEXT NOT NULL,
    actorId TEXT,
    actionType TEXT NOT NULL,
    entityType TEXT NOT NULL,
    entityId TEXT NOT NULL,
    receiptJson TEXT NOT NULL,
    createdAt TEXT NOT NULL
);
"""

PHASE8_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_giveaway_active_channel ON GiveawayV1(guildId,channelId) WHERE status IN ('ACTIVE','DRAW_PENDING','AWAITING_CLAIM','REVIEW_REQUIRED')",
    "CREATE INDEX IF NOT EXISTS idx_giveaway_active_guild ON GiveawayV1(guildId,status,endsAt)",
    "CREATE INDEX IF NOT EXISTS idx_giveaway_ticket_user ON GiveawayTicket(guildId,userId,status)",
    "CREATE INDEX IF NOT EXISTS idx_giveaway_evidence_identity ON GiveawayEligibilityEvidence(giveawayId,stage,drawSequence,userId)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_phase8_operation_reservation ON Phase8Operation(reservationKey) WHERE status IN ('RESERVED','REVIEW_REQUIRED')",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_options_user_request_unresolved ON Phase8Operation(guildId,userId) WHERE operationType='OPTIONS_OPEN' AND status IN ('RESERVED','REVIEW_REQUIRED')",
    "CREATE INDEX IF NOT EXISTS idx_options_active_user ON EternalOptionPosition(guildId,userId,status,expiresAt)",
    "CREATE INDEX IF NOT EXISTS idx_options_expiry ON EternalOptionPosition(status,expiresAt)",
    "CREATE INDEX IF NOT EXISTS idx_options_reservation_exposure ON EternalOptionReservation(guildId,status,liabilityEcy)",
    "CREATE INDEX IF NOT EXISTS idx_phase8_outbox ON Phase8NotificationOutbox(status,leaseExpiresAt,createdAt)",
    "CREATE INDEX IF NOT EXISTS idx_phase8_review ON Phase8RecoveryReview(status,lastAttemptedAt)",
)

PHASE8_TRIGGER_SQL = (
    """CREATE TRIGGER IF NOT EXISTS trg_phase8_operation_plan_immutable BEFORE UPDATE ON Phase8Operation WHEN NEW.requestId<>OLD.requestId OR NEW.guildId<>OLD.guildId OR NEW.userId<>OLD.userId OR NEW.operationType<>OLD.operationType OR NEW.entityId IS NOT OLD.entityId OR NEW.outcomeJson<>OLD.outcomeJson OR NEW.transactionId IS NOT OLD.transactionId BEGIN SELECT RAISE(ABORT,'phase8 operation plan is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_phase8_operation_transition BEFORE UPDATE OF status ON Phase8Operation WHEN NOT ((OLD.status='RESERVED' AND NEW.status IN ('COMMITTED','VOID','REVIEW_REQUIRED')) OR (OLD.status='REVIEW_REQUIRED' AND NEW.status IN ('COMMITTED','VOID'))) BEGIN SELECT RAISE(ABORT,'invalid phase8 operation transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_phase8_operation_result BEFORE UPDATE ON Phase8Operation WHEN (OLD.resultJson IS NOT NULL AND NEW.resultJson IS NOT OLD.resultJson) OR (OLD.resultJson IS NULL AND NEW.resultJson IS NOT NULL AND NEW.status NOT IN ('COMMITTED','VOID')) BEGIN SELECT RAISE(ABORT,'invalid phase8 result write'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_phase8_operation_no_delete BEFORE DELETE ON Phase8Operation BEGIN SELECT RAISE(ABORT,'phase8 financial operation cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_giveaway_guild_limit BEFORE INSERT ON GiveawayV1 WHEN NEW.status IN ('ACTIVE','DRAW_PENDING','AWAITING_CLAIM','REVIEW_REQUIRED') AND (SELECT COUNT(*) FROM GiveawayV1 WHERE guildId=NEW.guildId AND status IN ('ACTIVE','DRAW_PENDING','AWAITING_CLAIM','REVIEW_REQUIRED'))>=3 BEGIN SELECT RAISE(ABORT,'giveaway guild limit reached'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_giveaway_transition BEFORE UPDATE OF status ON GiveawayV1 WHEN NOT (NEW.status=OLD.status OR (OLD.status='ACTIVE' AND NEW.status IN ('DRAW_PENDING','AWAITING_CLAIM','COMPLETED','CANCELLED','REVIEW_REQUIRED')) OR (OLD.status='DRAW_PENDING' AND NEW.status IN ('AWAITING_CLAIM','COMPLETED','CANCELLED','REVIEW_REQUIRED')) OR (OLD.status='AWAITING_CLAIM' AND NEW.status IN ('AWAITING_CLAIM','COMPLETED','REVIEW_REQUIRED')) OR (OLD.status='REVIEW_REQUIRED' AND NEW.status IN ('AWAITING_CLAIM','COMPLETED','CANCELLED'))) BEGIN SELECT RAISE(ABORT,'invalid giveaway transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_giveaway_terminal_immutable BEFORE UPDATE ON GiveawayV1 WHEN OLD.status IN ('COMPLETED','CANCELLED') BEGIN SELECT RAISE(ABORT,'giveaway is terminal'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_giveaway_ticket_transition BEFORE UPDATE OF status ON GiveawayTicket WHEN NOT (OLD.status='PAID' AND NEW.status IN ('REFUNDED','ALLOCATED')) BEGIN SELECT RAISE(ABORT,'invalid giveaway ticket transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_giveaway_evidence_no_update BEFORE UPDATE ON GiveawayEligibilityEvidence BEGIN SELECT RAISE(ABORT,'giveaway eligibility evidence is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_giveaway_evidence_no_delete BEFORE DELETE ON GiveawayEligibilityEvidence BEGIN SELECT RAISE(ABORT,'giveaway eligibility evidence is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_giveaway_draw_immutable BEFORE UPDATE ON GiveawayDraw BEGIN SELECT RAISE(ABORT,'giveaway draw is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_giveaway_draw_no_delete BEFORE DELETE ON GiveawayDraw BEGIN SELECT RAISE(ABORT,'giveaway draw cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_giveaway_ticket_no_delete BEFORE DELETE ON GiveawayTicket BEGIN SELECT RAISE(ABORT,'giveaway ticket cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_giveaway_review_immutable BEFORE UPDATE ON GiveawayWinnerReview WHEN NEW.giveawayId<>OLD.giveawayId OR NEW.winnerId<>OLD.winnerId OR NEW.reasonCode<>OLD.reasonCode OR NEW.evidenceType<>OLD.evidenceType OR NEW.evidenceReference<>OLD.evidenceReference OR NEW.evidenceHash<>OLD.evidenceHash OR NEW.reviewerId<>OLD.reviewerId OR NEW.reviewedAt<>OLD.reviewedAt OR NEW.priorWinnerStateJson<>OLD.priorWinnerStateJson OR NEW.auditReceiptJson<>OLD.auditReceiptJson BEGIN SELECT RAISE(ABORT,'winner review evidence is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_giveaway_review_consume_once BEFORE UPDATE OF consumed ON GiveawayWinnerReview WHEN OLD.consumed<>0 OR NEW.consumed<>1 BEGIN SELECT RAISE(ABORT,'winner review can be consumed once'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_giveaway_voice_block_no_update BEFORE UPDATE ON GiveawayVoiceBlock BEGIN SELECT RAISE(ABORT,'voice block is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_giveaway_voice_block_no_delete BEFORE DELETE ON GiveawayVoiceBlock BEGIN SELECT RAISE(ABORT,'voice block is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_option_plan_immutable BEFORE UPDATE ON EternalOptionPosition WHEN NEW.requestId<>OLD.requestId OR NEW.guildId<>OLD.guildId OR NEW.userId<>OLD.userId OR NEW.symbol<>OLD.symbol OR NEW.direction<>OLD.direction OR NEW.stakeEcy<>OLD.stakeEcy OR NEW.liabilityEcy<>OLD.liabilityEcy OR NEW.durationMinutes<>OLD.durationMinutes OR NEW.entryHistoryId<>OLD.entryHistoryId OR NEW.entryPriceEcy<>OLD.entryPriceEcy OR NEW.expiresAt<>OLD.expiresAt OR NEW.openingTransactionId<>OLD.openingTransactionId BEGIN SELECT RAISE(ABORT,'option plan is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_option_user_limits BEFORE INSERT ON EternalOptionPosition WHEN NEW.status IN ('ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED') AND ((SELECT COUNT(*) FROM EternalOptionPosition WHERE guildId=NEW.guildId AND userId=NEW.userId AND status IN ('ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED'))>=3 OR (SELECT COALESCE(SUM(stakeEcy),0) FROM EternalOptionPosition WHERE guildId=NEW.guildId AND userId=NEW.userId AND status IN ('ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED'))+NEW.stakeEcy>500000) BEGIN SELECT RAISE(ABORT,'option user limit reached'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_option_transition BEFORE UPDATE OF status ON EternalOptionPosition WHEN NOT (NEW.status=OLD.status OR (OLD.status='ACTIVE' AND NEW.status IN ('SETTLEMENT_PENDING','COMMITTED','REVIEW_REQUIRED')) OR (OLD.status='SETTLEMENT_PENDING' AND NEW.status IN ('COMMITTED','REVIEW_REQUIRED')) OR (OLD.status='REVIEW_REQUIRED' AND NEW.status='COMMITTED')) BEGIN SELECT RAISE(ABORT,'invalid option transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_option_terminal_immutable BEFORE UPDATE ON EternalOptionPosition WHEN OLD.status='COMMITTED' BEGIN SELECT RAISE(ABORT,'option is terminal'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_option_receipt_first_write BEFORE UPDATE OF receiptJson ON EternalOptionPosition WHEN (OLD.receiptJson IS NOT NULL) OR NEW.status<>'COMMITTED' BEGIN SELECT RAISE(ABORT,'invalid option receipt write'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_option_no_delete BEFORE DELETE ON EternalOptionPosition BEGIN SELECT RAISE(ABORT,'option cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_option_settlement_no_update BEFORE UPDATE ON EternalOptionSettlement BEGIN SELECT RAISE(ABORT,'option settlement is immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_option_settlement_no_delete BEFORE DELETE ON EternalOptionSettlement BEGIN SELECT RAISE(ABORT,'option settlement cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_option_reservation_transition BEFORE UPDATE OF status ON EternalOptionReservation WHEN NOT ((OLD.status='ACTIVE' AND NEW.status IN ('RELEASED','REVIEW_REQUIRED')) OR (OLD.status='REVIEW_REQUIRED' AND NEW.status='RELEASED')) BEGIN SELECT RAISE(ABORT,'invalid option reservation transition'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_phase8_audit_no_update BEFORE UPDATE ON Phase8Audit BEGIN SELECT RAISE(ABORT,'phase8 audit is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_phase8_audit_no_delete BEFORE DELETE ON Phase8Audit BEGIN SELECT RAISE(ABORT,'phase8 audit is append-only'); END""",
)


def _canonical_sql(value):
    return " ".join(str(value).split())


PHASE8_SCHEMA_CHECKSUM = hashlib.sha256(
    (PHASE8_MIGRATION_NAME + "\n" + _canonical_sql(PHASE8_TABLE_SQL) + "\n" +
     "\n".join(_canonical_sql(value) for value in PHASE8_INDEX_SQL + PHASE8_TRIGGER_SQL)).encode("utf-8")
).hexdigest()

REQUIRED_PHASE8_TABLES = {
    "Phase8Operation", "GiveawayV1", "GiveawayTicket", "GiveawayEligibilityEvidence", "GiveawayEscrow", "GiveawayDraw",
    "GiveawayWinner", "GiveawayClaim", "GiveawayWinnerReview", "GiveawayRefund",
    "GiveawayFundAllocation", "GiveawayVoiceQualification", "GiveawayVoiceBlock",
    "GiveawayLegacySnapshot", "EternalOptionPosition", "EternalOptionReservation",
    "EternalOptionSettlement", "Phase8NotificationOutbox", "Phase8RecoveryReview", "Phase8Audit",
}
REQUIRED_PHASE8_INDEXES = {re.search(r"INDEX IF NOT EXISTS (\w+)", sql).group(1) for sql in PHASE8_INDEX_SQL}
REQUIRED_PHASE8_TRIGGERS = {re.search(r"TRIGGER IF NOT EXISTS (\w+)", sql).group(1) for sql in PHASE8_TRIGGER_SQL}


def phase2_activity_capability_sync(connection):
    columns = {row[1] for row in connection.execute("PRAGMA table_info(EconomyActivityEvent)")}
    triggers = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='EconomyActivityEvent'"
    )}
    return ({"eventId", "guildId", "userId", "eventType", "eventKey", "points", "metricValue",
             "transactionId", "referenceId", "occurredAt", "createdAt"}.issubset(columns)
            and {"trg_activity_no_update", "trg_activity_no_delete"}.issubset(triggers))


async def phase2_activity_capability(db):
    marker = await db.fetchrow("PRAGMA table_info(EconomyActivityEvent)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='EconomyActivityEvent'"
        triggers = {row[0] for row in await cursor.fetchall()}
    return ({"eventId", "guildId", "userId", "eventType", "eventKey", "points", "metricValue",
             "transactionId", "referenceId", "occurredAt", "createdAt"}.issubset(columns)
            and {"trg_activity_no_update", "trg_activity_no_delete"}.issubset(triggers))


def phase8_capability_sync(connection):
    marker = connection.execute(
        "SELECT checksum,name,status FROM EconomySchemaMigration WHERE version=$1", ECONOMY_PHASE8_MIGRATION_VERSION,),
    ).fetchone()
    if marker != (PHASE8_SCHEMA_CHECKSUM, PHASE8_MIGRATION_NAME, "COMPLETED"):
        return False
    if (not phase2_activity_capability_sync(connection) or not phase5_capability_sync(connection)
            or not phase6_capability_sync(connection):
        return False
    objects = {row[0]: row[1] for row in connection.execute(
        "SELECT name,type FROM sqlite_master WHERE type IN ('table','index','trigger')"
    )}
    return (all(objects.get(name) == "table" for name in REQUIRED_PHASE8_TABLES)
            and all(objects.get(name) == "index" for name in REQUIRED_PHASE8_INDEXES)
            and all(objects.get(name) == "trigger" for name in REQUIRED_PHASE8_TRIGGERS))


async def phase8_capability(db):
    try:
        async with db.execute(
            "SELECT checksum,name,status FROM EconomySchemaMigration WHERE version=$1", ECONOMY_PHASE8_MIGRATION_VERSION,),
        )
        if tuple(marker or () != (PHASE8_SCHEMA_CHECKSUM, PHASE8_MIGRATION_NAME, "COMPLETED"):
            return False
        if (not await phase2_activity_capability(db) or not await phase5_capability(db)
                or not await phase6_capability(db)):
            return False
        async with db.execute(
            "SELECT name,type FROM sqlite_master WHERE type IN ('table','index','trigger')"
            objects = {row[0]: row[1] for row in await cursor.fetchall()}
        return (all(objects.get(name) == "table" for name in REQUIRED_PHASE8_TABLES)
                and all(objects.get(name) == "index" for name in REQUIRED_PHASE8_INDEXES)
                and all(objects.get(name) == "trigger" for name in REQUIRED_PHASE8_TRIGGERS))
    except aiosqlite.Error:
        return False
