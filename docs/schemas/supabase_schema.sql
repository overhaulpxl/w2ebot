-- W2E Bot PostgreSQL Schema for Supabase
-- Generated perfectly from Legacy SQLite schemas

CREATE TABLE IF NOT EXISTS json_store (filename VARCHAR(255) PRIMARY KEY, content TEXT);

CREATE TABLE IF NOT EXISTS DiscordStat (
            id VARCHAR(255) PRIMARY KEY,
            displayName TEXT,
            coins INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            lastDaily TEXT,
            updatedAt TEXT
        );

CREATE TABLE IF NOT EXISTS ChatMemory (
            id SERIAL PRIMARY KEY,
            timestamp TEXT,
            content TEXT
        );

CREATE TABLE IF NOT EXISTS Reminder (
            id SERIAL PRIMARY KEY,
            user_id TEXT,
            channel_id TEXT,
            message TEXT,
            fire_at TEXT,
            created_at TEXT
        );

CREATE TABLE IF NOT EXISTS Giveaway (
            id SERIAL PRIMARY KEY,
            channel_id TEXT,
            message_id TEXT,
            prize TEXT,
            host_id TEXT,
            end_at TEXT,
            ended INTEGER DEFAULT 0
        );

CREATE TABLE IF NOT EXISTS AuditLog (
            id SERIAL PRIMARY KEY,
            ts TEXT,
            action TEXT,
            target_id TEXT,
            detail TEXT,
            source TEXT
        );

CREATE TABLE IF NOT EXISTS dealAuditLogConfig (
            guildId VARCHAR(255) PRIMARY KEY,
            channelId TEXT,
            enabled INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT
        );

CREATE TABLE IF NOT EXISTS DealConfig (
            guildId VARCHAR(255) PRIMARY KEY,
            middlemanRoleId TEXT,
            ownerRoleId TEXT,
            dealLogChannelId TEXT,
            vouchChannelId TEXT,
            dealStaffRoleIds TEXT DEFAULT '[]',
            allowedTicketCategoryIds TEXT DEFAULT '[]',
            dealIdPrefix TEXT DEFAULT 'MM',
            pingCooldownSeconds INTEGER DEFAULT 3600,
            reminderEnabled INTEGER DEFAULT 0,
            reminderIntervals TEXT DEFAULT '{}',
            requirePaymentProof INTEGER DEFAULT 0,
            requireTransferProof INTEGER DEFAULT 0,
            allowUserCancelRequest INTEGER DEFAULT 1,
            autoTimeoutEnabled INTEGER DEFAULT 0,
            trustedRoleThreshold INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT
        );

CREATE TABLE IF NOT EXISTS Deal (
            id SERIAL PRIMARY KEY,
            dealId TEXT,
            guildId TEXT NOT NULL,
            ticketChannelId TEXT NOT NULL,
            createdById TEXT NOT NULL,
            buyerId TEXT NOT NULL,
            sellerId TEXT NOT NULL,
            middlemanId TEXT NOT NULL,
            paymentPenjual TEXT,
            paymentPembeli TEXT,
            nominalItem INTEGER,
            feeType TEXT,
            mmFee INTEGER,
            buyerPays INTEGER,
            sellerReceives INTEGER,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'Menunggu Form',
            warningMessageId TEXT,
            summaryMessageId TEXT,
            fundsReceivedStageMessageId TEXT,
            buyerConfirmStageMessageId TEXT,
            payoutStageMessageId TEXT,
            doneStageMessageId TEXT,
            completedSummaryMessageId TEXT,
            vouchProgressMessageId TEXT,
            cancelledById TEXT,
            cancelledAt TEXT,
            cancelReason TEXT,
            disputedById TEXT,
            disputedAt TEXT,
            disputeReason TEXT,
            disputeProofUrl TEXT,
            disputePreviousStatus TEXT,
            statusBeforeDispute TEXT,
            disputeResolvedById TEXT,
            disputeResolvedAt TEXT,
            disputeResolution TEXT,
            paymentProofUrl TEXT,
            paymentProofNotes TEXT,
            paymentProofMessageId TEXT,
            paymentProofChannelId TEXT,
            paymentProofSubmittedById TEXT,
            paymentProofSubmittedAt TEXT,
            paymentProofInvalidatedAt TEXT,
            paymentProofInvalidatedById TEXT,
            paymentProofInvalidationReason TEXT,
            paymentProofConfirmationMessageId TEXT,
            transferProofUrl TEXT,
            transferProofNotes TEXT,
            transferProofMessageId TEXT,
            transferProofChannelId TEXT,
            transferProofSubmittedById TEXT,
            transferProofSubmittedAt TEXT,
            sellerPayoutPlatform TEXT,
            sellerPayoutAccount TEXT,
            sellerPayoutName TEXT,
            sellerPayoutSubmittedById TEXT,
            sellerPayoutSubmittedAt TEXT,
            formSubmittedById TEXT,
            formSubmittedAt TEXT,
            paymentInstructionOwnerId TEXT,
            paymentInstructionMessageId TEXT,
            paymentInstructionSentAt TEXT,
            paymentInstructionPayloadHash TEXT,
            fundsReceivedNotes TEXT,
            fundsReceivedById TEXT,
            fundsReceivedAt TEXT,
            itemSentById TEXT,
            itemSentAt TEXT,
            buyerConfirmedById TEXT,
            buyerConfirmedAt TEXT,
            buyerConfirmationSource TEXT,
            completedById TEXT,
            completedAt TEXT,
            isVouchEligible INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT,
            UNIQUE(guildId, dealId)
        );

CREATE TABLE IF NOT EXISTS DealLog (
            id SERIAL PRIMARY KEY,
            guildId TEXT,
            dealId TEXT,
            action TEXT,
            actorId TEXT,
            oldValue TEXT,
            newValue TEXT,
            reason TEXT,
            createdAt TEXT
        );

CREATE TABLE IF NOT EXISTS dealPaymentProfiles (
            id SERIAL PRIMARY KEY,
            guildId TEXT NOT NULL,
            userId TEXT NOT NULL,
            title TEXT,
            paymentText TEXT,
            qrisNote TEXT,
            note TEXT,
            footerText TEXT,
            imageUrl TEXT,
            imageFilename TEXT,
            enabled INTEGER DEFAULT 1,
            createdAt TEXT,
            updatedAt TEXT,
            UNIQUE(guildId, userId)
        );

CREATE TABLE IF NOT EXISTS Vouch (
            id SERIAL PRIMARY KEY,
            guildId TEXT,
            dealId TEXT,
            reviewerId TEXT,
            targetId TEXT,
            reviewerRole TEXT,
            targetRole TEXT,
            rating INTEGER,
            review TEXT,
            proofUrl TEXT,
            verifiedDeal INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',
            removedBy TEXT,
            removeReason TEXT,
            createdAt TEXT,
            updatedAt TEXT,
            UNIQUE(guildId, dealId, reviewerId, targetId)
        );

CREATE TABLE IF NOT EXISTS DealNote (
            id SERIAL PRIMARY KEY,
            guildId TEXT,
            dealId TEXT,
            actorId TEXT,
            note TEXT,
            createdAt TEXT
        );

CREATE TABLE IF NOT EXISTS DealReminderLog (
            id SERIAL PRIMARY KEY,
            guildId TEXT,
            dealId TEXT,
            reminderType TEXT,
            sentAt TEXT,
            UNIQUE(guildId, dealId, reminderType)
        );

CREATE TABLE IF NOT EXISTS dealArchives (
            id SERIAL PRIMARY KEY,
            guildId TEXT,
            dealId TEXT,
            channelId TEXT,
            buyerId TEXT,
            sellerId TEXT,
            middlemanId TEXT,
            finalStatus TEXT,
            paymentProofSubmitted INTEGER DEFAULT 0,
            transferProofSubmitted INTEGER DEFAULT 0,
            vouchEligible INTEGER DEFAULT 0,
            disputeOpened INTEGER DEFAULT 0,
            disputeResolved INTEGER DEFAULT 0,
            cancelled INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            finalActionById TEXT,
            cancelledById TEXT,
            completedById TEXT,
            disputeOpenedById TEXT,
            disputeResolvedById TEXT,
            safeReason TEXT,
            safeResolution TEXT,
            createdAt TEXT,
            finalizedAt TEXT,
            archivedAt TEXT,
            UNIQUE(guildId, dealId)
        );

CREATE TABLE IF NOT EXISTS dealPanels (
            id SERIAL PRIMARY KEY,
            guildId TEXT,
            panelType TEXT,
            channelId TEXT,
            messageId TEXT,
            enabled INTEGER DEFAULT 0,
            lastPayloadHash TEXT,
            createdAt TEXT,
            updatedAt TEXT,
            UNIQUE(guildId, panelType)
        );

CREATE TABLE IF NOT EXISTS dealPanelEvents (
            id SERIAL PRIMARY KEY,
            guildId TEXT,
            panelType TEXT,
            eventType TEXT,
            eventKey TEXT,
            messageId TEXT,
            channelId TEXT,
            createdAt TEXT,
            UNIQUE(guildId, panelType, eventKey)
        );

CREATE TABLE IF NOT EXISTS middlemanStatus (
            guildId TEXT,
            userId TEXT,
            status TEXT DEFAULT 'offline',
            note TEXT,
            updatedAt TEXT,
            updatedById TEXT,
            createdAt TEXT,
            PRIMARY KEY (guildId, userId)
        );

CREATE TABLE IF NOT EXISTS rateLimitEvents (
            id SERIAL PRIMARY KEY,
            guildId TEXT,
            userId TEXT,
            actionType TEXT,
            targetId TEXT,
            eventKey TEXT,
            createdAt TEXT
        );

CREATE TABLE IF NOT EXISTS VouchReport (
            id SERIAL PRIMARY KEY,
            guildId TEXT,
            vouchId INTEGER,
            reporterId TEXT,
            reason TEXT,
            proofUrl TEXT,
            status TEXT DEFAULT 'open',
            handledBy TEXT,
            handledAt TEXT,
            createdAt TEXT
        );

CREATE TABLE IF NOT EXISTS manualVouchReviewConfig (
            guildId VARCHAR(255) PRIMARY KEY,
            reviewChannelId TEXT,
            enabled INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT
        );

CREATE TABLE IF NOT EXISTS manualVouchPanelConfig (
            guildId VARCHAR(255) PRIMARY KEY,
            channelId TEXT,
            messageId TEXT,
            enabled INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT
        );

CREATE TABLE IF NOT EXISTS scammerReports (
            id SERIAL PRIMARY KEY,
            guildId TEXT,
            reporterId TEXT,
            reportedUserId TEXT,
            reportedRaw TEXT,
            reportedResolved INTEGER DEFAULT 0,
            reason TEXT,
            chronology TEXT,
            nominalItem TEXT,
            notes TEXT,
            proofCount INTEGER DEFAULT 0,
            proofData TEXT,
            proofSubmittedAt TEXT,
            status TEXT DEFAULT 'pending',
            reviewMessageId TEXT,
            reviewChannelId TEXT,
            evidenceThreadId TEXT,
            reviewedById TEXT,
            rejectedById TEXT,
            rejectedAt TEXT,
            rejectionReason TEXT,
            resolvedById TEXT,
            resolvedAt TEXT,
            resolution TEXT,
            staffNotes TEXT,
            createdAt TEXT,
            updatedAt TEXT
        );

CREATE TABLE IF NOT EXISTS scamReportReviewConfig (
            guildId VARCHAR(255) PRIMARY KEY,
            reviewChannelId TEXT,
            enabled INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT
        );

CREATE TABLE IF NOT EXISTS scamReportPanelConfig (
            guildId VARCHAR(255) PRIMARY KEY,
            channelId TEXT,
            messageId TEXT,
            enabled INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT
        );

CREATE TABLE IF NOT EXISTS trustModerationStatus (
            guildId TEXT,
            userId TEXT,
            status TEXT DEFAULT 'clear',
            reason TEXT,
            sourceType TEXT,
            sourceId TEXT,
            updatedById TEXT,
            updatedAt TEXT,
            createdAt TEXT,
            PRIMARY KEY (guildId, userId)
        );

CREATE TABLE IF NOT EXISTS UserReputation (
            guildId TEXT,
            userId TEXT,
            totalVouches INTEGER DEFAULT 0,
            verifiedVouches INTEGER DEFAULT 0,
            verifiedDealVouches INTEGER DEFAULT 0,
            manualApprovedVouches INTEGER DEFAULT 0,
            averageRating REAL DEFAULT 0,
            trustScore REAL DEFAULT 0,
            buyerVouches INTEGER DEFAULT 0,
            sellerVouches INTEGER DEFAULT 0,
            middlemanVouches INTEGER DEFAULT 0,
            removedVouches INTEGER DEFAULT 0,
            reports INTEGER DEFAULT 0,
            trustLevel TEXT DEFAULT 'New User',
            updatedAt TEXT,
            PRIMARY KEY (guildId, userId)
        );

CREATE TABLE IF NOT EXISTS EconomySchemaMigration (
    version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','COMPLETED','FAILED')),
    startedAt TEXT, completedAt TEXT, backupPath TEXT, manifestSha256 TEXT,
    detailsJson TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS EconomyMigrationRun (
    runId VARCHAR(255) PRIMARY KEY, migrationVersion INTEGER NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('DRY_RUN','APPLY','RECOVERY','ROLLBACK')),
    status TEXT NOT NULL, guildId TEXT NOT NULL, sourceDbSha256 TEXT NOT NULL,
    backupPath TEXT, manifestPath TEXT, startedById TEXT, startedAt TEXT NOT NULL,
    completedAt TEXT, totalsJson TEXT NOT NULL DEFAULT '{}', errorCode TEXT
);

CREATE TABLE IF NOT EXISTS EconomyMigrationItem (
    runId TEXT NOT NULL, entityType TEXT NOT NULL, sourceKey TEXT NOT NULL,
    sourceHash TEXT NOT NULL, targetKey TEXT, status TEXT NOT NULL, errorCode TEXT,
    attemptCount INTEGER NOT NULL DEFAULT 0, updatedAt TEXT NOT NULL,
    PRIMARY KEY(runId, entityType, sourceKey)
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
    transactionId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, idempotencyKey TEXT NOT NULL,
    operation TEXT NOT NULL, source TEXT NOT NULL, referenceId TEXT, actorId TEXT,
    reasonCode TEXT, reasonText TEXT, metadataJson TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','REVERSED')),
    createdAt TEXT NOT NULL, committedAt TEXT,
    UNIQUE(guildId, idempotencyKey)
);

CREATE TABLE IF NOT EXISTS EconomyLedger (
    id SERIAL PRIMARY KEY, transactionId TEXT NOT NULL,
    sequence INTEGER NOT NULL, guildId TEXT NOT NULL,
    accountKind TEXT NOT NULL CHECK(accountKind IN ('USER','SYSTEM')),
    accountId TEXT NOT NULL, userId TEXT,
    currency TEXT NOT NULL CHECK(currency IN ('ETM','ECY')),
    transactionType TEXT NOT NULL, amount INTEGER NOT NULL,
    balanceBefore INTEGER NOT NULL, balanceAfter INTEGER NOT NULL,
    referenceId TEXT, source TEXT NOT NULL, createdAt TEXT NOT NULL,
    UNIQUE(transactionId, sequence)
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
    PRIMARY KEY(guildId, userId, claimType)
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
    rollId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    rewardType TEXT NOT NULL CHECK(rewardType IN ('WORK')),
    currency TEXT NOT NULL CHECK(currency IN ('ETM','ECY')),
    amount INTEGER NOT NULL CHECK(amount > 0),
    status TEXT NOT NULL CHECK(status IN ('RESERVED','COMMITTED','VOID')),
    transactionId TEXT, createdAt TEXT NOT NULL, settledAt TEXT, voidedAt TEXT,
    UNIQUE(transactionId)
);

CREATE TABLE IF NOT EXISTS EconomyDailyUsage (
    guildId TEXT NOT NULL, userId TEXT NOT NULL, periodDate TEXT NOT NULL,
    usageType TEXT NOT NULL CHECK(usageType IN ('TRANSFER_ETM','EXCHANGE_ETM')),
    submittedAmount INTEGER NOT NULL DEFAULT 0 CHECK(submittedAmount >= 0),
    version INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId, userId, periodDate, usageType)
);

CREATE TABLE IF NOT EXISTS EconomyActivityEvent (
    eventId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    eventType TEXT NOT NULL, eventKey TEXT NOT NULL,
    points INTEGER NOT NULL CHECK(points >= 0),
    metricValue INTEGER NOT NULL DEFAULT 0 CHECK(metricValue >= 0),
    transactionId TEXT NULL, referenceId TEXT NULL,
    occurredAt TEXT NOT NULL, createdAt TEXT NOT NULL,
    UNIQUE(guildId, eventKey)
);

CREATE TABLE IF NOT EXISTS EconomyCutoverState (
    guildId VARCHAR(255) PRIMARY KEY,
    state TEXT NOT NULL CHECK(state IN ('LEGACY','STAGING_READY','FORWARD_ONLY')),
    firstProductionTransactionId TEXT, changedById TEXT, changedAt TEXT NOT NULL,
    detailsJson TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS RpgCatalogManifest (
    catalogVersion VARCHAR(255) PRIMARY KEY, catalogHash TEXT NOT NULL,
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
    equipmentInstanceId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, ownerId TEXT NOT NULL,
    itemId TEXT NOT NULL, catalogVersion TEXT NOT NULL, slot TEXT NOT NULL,
    enhancementLevel INTEGER NOT NULL DEFAULT 0 CHECK(enhancementLevel BETWEEN 0 AND 15),
    pityBps INTEGER NOT NULL DEFAULT 0 CHECK(pityBps BETWEEN 0 AND 2000),
    bindingStatus TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'OWNED',
    acquiredSource TEXT NOT NULL, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS RpgPetInstance (
    petInstanceId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, ownerId TEXT NOT NULL,
    petId TEXT NOT NULL, catalogVersion TEXT NOT NULL, rarity TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1 CHECK(level BETWEEN 1 AND 50),
    xp INTEGER NOT NULL DEFAULT 0 CHECK(xp >= 0), evolutionState TEXT NOT NULL DEFAULT 'BASE',
    status TEXT NOT NULL DEFAULT 'OWNED', acquiredSource TEXT NOT NULL,
    createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS RpgOperation (
    operationId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    operationType TEXT NOT NULL, reservationKey TEXT, status TEXT NOT NULL
        CHECK(status IN ('RESERVED','AWAITING_FUNDS','COMMITTED','VOID','REVIEW_REQUIRED')),
    sourceResourceId TEXT, outcomeJson TEXT NOT NULL, resultJson TEXT,
    transactionId TEXT, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL, settledAt TEXT,
    retryCount INTEGER NOT NULL DEFAULT 0 CHECK(retryCount >= 0),
    lastErrorCode TEXT, lastAttemptedAt TEXT,
    recoveryReviewJson TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS RpgStarterGrant (
    grantId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','REVIEW_REQUIRED','VOID')),
    weaponInstanceId TEXT, armorInstanceId TEXT, accessoryInstanceId TEXT, petInstanceId TEXT,
    retryCount INTEGER NOT NULL DEFAULT 0 CHECK(retryCount >= 0),
    lastErrorCode TEXT, lastAttemptedAt TEXT,
    recoveryReviewJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL, committedAt TEXT,
    UNIQUE(guildId,userId)
);

CREATE TABLE IF NOT EXISTS RpgLegacyAsset (
    assetId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    sourceType TEXT NOT NULL, sourceKey TEXT NOT NULL, sourceHash TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity >= 0),
    bindingStatus TEXT NOT NULL DEFAULT 'LEGACY_BOUND' CHECK(bindingStatus='LEGACY_BOUND'),
    migrationStatus TEXT NOT NULL CHECK(migrationStatus IN ('QUARANTINED','REVIEW_REQUIRED','REPLAYED','MALFORMED')),
    metadataJson TEXT NOT NULL DEFAULT '{}', migratedAt TEXT NOT NULL,
    UNIQUE(guildId,userId,sourceType,sourceKey)
);

CREATE TABLE IF NOT EXISTS RpgRecoveryReview (
    reviewId VARCHAR(255) PRIMARY KEY, operationId TEXT, grantId TEXT,
    guildId TEXT NOT NULL, userId TEXT, reviewCode TEXT NOT NULL,
    metadataJson TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'OPEN',
    createdAt TEXT NOT NULL, resolvedAt TEXT,
    UNIQUE(operationId,reviewCode), UNIQUE(grantId,reviewCode)
);

CREATE TABLE IF NOT EXISTS RpgEnhancementAttempt (
    operationId VARCHAR(255) PRIMARY KEY, equipmentInstanceId TEXT NOT NULL,
    targetLevel INTEGER NOT NULL, successRoll INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS RpgOpenAttempt (
    operationId VARCHAR(255) PRIMARY KEY, itemId TEXT NOT NULL, resultDefinitionId TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS RpgHuntRun (
    operationId VARCHAR(255) PRIMARY KEY, areaId TEXT NOT NULL, playerXp INTEGER NOT NULL,
    activePetInstanceId TEXT
);

CREATE TABLE IF NOT EXISTS RpgDungeonRun (
    operationId VARCHAR(255) PRIMARY KEY, dungeonId TEXT NOT NULL, playerXp INTEGER NOT NULL,
    activePetInstanceId TEXT, entryMethod TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS RpgCraftAttempt (
    operationId VARCHAR(255) PRIMARY KEY, targetItemId TEXT NOT NULL, baseEquipmentInstanceId TEXT NOT NULL,
    blueprintItemId TEXT
);

CREATE TABLE IF NOT EXISTS RpgBossRaid (
    raidId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, tier TEXT NOT NULL,
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
    PRIMARY KEY(guildId,raidId,userId)
);

CREATE TABLE IF NOT EXISTS RpgBossAttack (
    operationId VARCHAR(255) PRIMARY KEY, raidId TEXT NOT NULL, committedDamage INTEGER
);

CREATE TABLE IF NOT EXISTS RpgBossParticipantReward (
    raidId TEXT NOT NULL, userId TEXT NOT NULL, rank INTEGER NOT NULL,
    eligible INTEGER NOT NULL CHECK(eligible IN (0,1)), damage INTEGER NOT NULL,
    etmAmount INTEGER NOT NULL DEFAULT 0, dropJson TEXT NOT NULL DEFAULT '{}',
    activePetInstanceId TEXT, petXp INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PLANNED', transactionId TEXT,
    PRIMARY KEY(raidId,userId)
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
    grantId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    achievementId TEXT NOT NULL, referenceId TEXT NOT NULL, grantedAt TEXT NOT NULL,
    UNIQUE(guildId,userId,achievementId,referenceId)
);

CREATE TABLE IF NOT EXISTS RpgPhase3MigrationReview (
    reviewId VARCHAR(255) PRIMARY KEY, runId TEXT NOT NULL, guildId TEXT, userId TEXT,
    entityType TEXT NOT NULL, sourceKey TEXT NOT NULL, warningCode TEXT NOT NULL,
    detailsJson TEXT NOT NULL DEFAULT '{}', createdAt TEXT NOT NULL,
    UNIQUE(runId,entityType,sourceKey,warningCode)
);
CREATE INDEX IF NOT EXISTS idx_rpg_inventory_user ON RpgInventoryStack(guildId,userId,itemId);

CREATE TABLE IF NOT EXISTS MarketplaceListing (
    listingId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, sellerId TEXT NOT NULL,
    assetType TEXT NOT NULL CHECK(assetType IN ('EQUIPMENT','STACK')),
    equipmentInstanceId TEXT, stackItemId TEXT, catalogVersion TEXT NOT NULL,
    stackBindingStatus TEXT, originalQuantity INTEGER NOT NULL CHECK(originalQuantity>0),
    remainingQuantity INTEGER NOT NULL CHECK(remainingQuantity>=0 AND remainingQuantity<=originalQuantity),
    unitPriceEtm INTEGER NOT NULL CHECK(unitPriceEtm>0),
    totalListingValue INTEGER NOT NULL CHECK(totalListingValue>0),
    assetSnapshotJson TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN
      ('ACTIVE','PARTIALLY_FILLED','PAUSED','REVIEW_REQUIRED','CANCELLED','EXPIRED','SOLD','RETURNED')),
    escrowId TEXT NOT NULL UNIQUE, idempotencyKey TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL, expiresAt TEXT,
    cancelledAt TEXT, completedAt TEXT, moderationCode TEXT, moderationActorId TEXT,
    moderationReasonCode TEXT, moderatedAt TEXT,
    UNIQUE(guildId,idempotencyKey),
    CHECK((assetType='EQUIPMENT' AND equipmentInstanceId IS NOT NULL AND stackItemId IS NULL
           AND stackBindingStatus IS NULL AND originalQuantity=1)
       OR (assetType='STACK' AND equipmentInstanceId IS NULL AND stackItemId IS NOT NULL
           AND stackBindingStatus IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS MarketplaceEscrow (
    escrowId VARCHAR(255) PRIMARY KEY, listingId TEXT NOT NULL UNIQUE, guildId TEXT NOT NULL,
    authoritativeOwnerId TEXT NOT NULL, assetType TEXT NOT NULL CHECK(assetType IN ('EQUIPMENT','STACK')),
    equipmentInstanceId TEXT, stackItemId TEXT, catalogVersion TEXT NOT NULL,
    stackBindingStatus TEXT, originalQuantity INTEGER NOT NULL CHECK(originalQuantity>0),
    remainingQuantity INTEGER NOT NULL CHECK(remainingQuantity>=0 AND remainingQuantity<=originalQuantity),
    assetSnapshotJson TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('HELD','PARTIAL','SOLD','RETURNED','REVIEW_REQUIRED')),
    version INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL, releasedAt TEXT,
    CHECK((assetType='EQUIPMENT' AND equipmentInstanceId IS NOT NULL AND stackItemId IS NULL
           AND stackBindingStatus IS NULL AND originalQuantity=1)
       OR (assetType='STACK' AND equipmentInstanceId IS NULL AND stackItemId IS NOT NULL
           AND stackBindingStatus IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS MarketplaceSale (
    saleId VARCHAR(255) PRIMARY KEY, transactionId TEXT NOT NULL UNIQUE, guildId TEXT NOT NULL,
    listingId TEXT NOT NULL, escrowId TEXT NOT NULL, sellerId TEXT NOT NULL, buyerId TEXT NOT NULL,
    assetType TEXT NOT NULL CHECK(assetType IN ('EQUIPMENT','STACK')),
    equipmentInstanceId TEXT, stackItemId TEXT, catalogVersion TEXT NOT NULL, stackBindingStatus TEXT,
    quantity INTEGER NOT NULL CHECK(quantity>0), unitPriceEtm INTEGER NOT NULL CHECK(unitPriceEtm>0),
    grossEtm INTEGER NOT NULL CHECK(grossEtm>0), feeEtm INTEGER NOT NULL CHECK(feeEtm>=0),
    sellerProceedsEtm INTEGER NOT NULL CHECK(sellerProceedsEtm>=0),
    treasuryEtm INTEGER NOT NULL CHECK(treasuryEtm>=0), reserveEtm INTEGER NOT NULL CHECK(reserveEtm>=0),
    burnEtm INTEGER NOT NULL CHECK(burnEtm>=0), expectedListingVersion INTEGER NOT NULL,
    expectedEscrowVersion INTEGER NOT NULL, idempotencyKey TEXT NOT NULL,
    authorizationSource TEXT NOT NULL DEFAULT 'DISCORD',
    status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','REVIEW_REQUIRED','VOID')),
    buyerReceiptJson TEXT, sellerReceiptJson TEXT, voidReasonCode TEXT, reviewReasonCode TEXT,
    createdAt TEXT NOT NULL, completedAt TEXT,
    UNIQUE(guildId,idempotencyKey),
    CHECK((status='COMMITTED' AND buyerReceiptJson IS NOT NULL AND sellerReceiptJson IS NOT NULL
           AND voidReasonCode IS NULL)
       OR (status IN ('PENDING','REVIEW_REQUIRED') AND buyerReceiptJson IS NULL
           AND sellerReceiptJson IS NULL AND voidReasonCode IS NULL)
       OR (status='VOID' AND buyerReceiptJson IS NULL AND sellerReceiptJson IS NULL
           AND voidReasonCode IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS MarketplaceReturn (
    returnId VARCHAR(255) PRIMARY KEY, listingId TEXT NOT NULL, escrowId TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL, recipientId TEXT NOT NULL,
    assetType TEXT NOT NULL CHECK(assetType IN ('EQUIPMENT','STACK')),
    equipmentInstanceId TEXT, stackItemId TEXT, catalogVersion TEXT NOT NULL, stackBindingStatus TEXT,
    quantity INTEGER NOT NULL CHECK(quantity>0), reasonCode TEXT NOT NULL,
    initiatedById TEXT, authorizationSource TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','REVIEW_REQUIRED')),
    idempotencyKey TEXT NOT NULL, receiptJson TEXT, createdAt TEXT NOT NULL,
    completedAt TEXT, lastAttemptedAt TEXT, lastErrorCode TEXT,
    UNIQUE(guildId,idempotencyKey),
    CHECK((status='COMMITTED' AND receiptJson IS NOT NULL) OR
          (status!='COMMITTED' AND receiptJson IS NULL))
);

CREATE TABLE IF NOT EXISTS MarketplaceWatch (
    guildId TEXT NOT NULL, userId TEXT NOT NULL, listingId TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), createdAt TEXT NOT NULL,
    removedAt TEXT, lastObservedVersion INTEGER, pendingEventKey TEXT,
    notificationStatus TEXT CHECK(notificationStatus IS NULL OR notificationStatus IN ('PENDING','SENT','FAILED')),
    notificationMessageId TEXT, updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId,userId,listingId)
);

CREATE TABLE IF NOT EXISTS MarketplaceReport (
    reportId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, listingId TEXT NOT NULL,
    reporterId TEXT NOT NULL, reasonCategory TEXT NOT NULL, sanitizedDetails TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('OPEN','IN_REVIEW','RESOLVED','DISMISSED')),
    staffActorId TEXT, resolutionCode TEXT, resolutionMetadataJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL, reviewedAt TEXT, resolvedAt TEXT
);

CREATE TABLE IF NOT EXISTS MarketplaceUserState (
    guildId TEXT NOT NULL, userId TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','RESTRICTED','FROZEN')),
    reasonCode TEXT, staffActorId TEXT, authorizationSource TEXT,
    version INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId,userId)
);

CREATE TABLE IF NOT EXISTS MarketplaceUserStateAudit (
    auditId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, userId TEXT NOT NULL,
    oldStatus TEXT, newStatus TEXT NOT NULL CHECK(newStatus IN ('ACTIVE','RESTRICTED','FROZEN')),
    actorId TEXT NOT NULL, authorizationSource TEXT NOT NULL, reasonCode TEXT NOT NULL,
    stateVersion INTEGER NOT NULL CHECK(stateVersion>=0), createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MarketplaceQuantityMutation (
    mutationId VARCHAR(255) PRIMARY KEY, listingId TEXT NOT NULL, escrowId TEXT NOT NULL,
    operationType TEXT NOT NULL CHECK(operationType IN ('SALE','RETURN','MODERATION','RECOVERY','RECONCILIATION')),
    expectedListingVersion INTEGER NOT NULL, expectedEscrowVersion INTEGER NOT NULL,
    expectedOldQuantity INTEGER NOT NULL CHECK(expectedOldQuantity>=0),
    newQuantity INTEGER NOT NULL CHECK(newQuantity>=0),
    expectedListingStatus TEXT NOT NULL, expectedEscrowStatus TEXT NOT NULL,
    newListingStatus TEXT NOT NULL, newEscrowStatus TEXT NOT NULL,
    saleId TEXT, returnId TEXT, actorId TEXT, authorizationSource TEXT,
    createdAt TEXT NOT NULL, applied INTEGER NOT NULL DEFAULT 0 CHECK(applied IN (0,1)),
    CHECK((operationType='SALE' AND saleId IS NOT NULL AND returnId IS NULL)
       OR (operationType='RETURN' AND returnId IS NOT NULL AND saleId IS NULL)
       OR (operationType IN ('MODERATION','RECOVERY','RECONCILIATION') AND saleId IS NULL))
);

CREATE TABLE IF NOT EXISTS MarketplaceSettlementEvidence (
    saleId VARCHAR(255) PRIMARY KEY, transactionId TEXT NOT NULL UNIQUE, guildId TEXT NOT NULL,
    listingId TEXT NOT NULL, escrowId TEXT NOT NULL, assetType TEXT NOT NULL,
    equipmentInstanceId TEXT, stackItemId TEXT, catalogVersion TEXT NOT NULL,
    stackBindingStatus TEXT, quantity INTEGER NOT NULL CHECK(quantity>0),
    buyerId TEXT NOT NULL, sellerId TEXT NOT NULL,
    buyerStackBefore INTEGER, buyerStackAfter INTEGER,
    quantityMutationId TEXT NOT NULL UNIQUE, createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MarketplaceRecoveryReview (
    reviewId VARCHAR(255) PRIMARY KEY, guildId TEXT NOT NULL, entityType TEXT NOT NULL,
    entityId TEXT NOT NULL, listingId TEXT, errorCode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','RESOLVED')),
    retryCount INTEGER NOT NULL DEFAULT 1 CHECK(retryCount>0),
    firstDetectedAt TEXT NOT NULL, lastAttemptedAt TEXT NOT NULL,
    sanitizedMetadataJson TEXT NOT NULL DEFAULT '{}', resolvedAt TEXT,
    UNIQUE(guildId,entityType,entityId,errorCode)
);

CREATE TABLE IF NOT EXISTS MarketplaceNotificationOutbox (
    eventId VARCHAR(255) PRIMARY KEY, eventKey TEXT NOT NULL UNIQUE, guildId TEXT NOT NULL,
    userId TEXT NOT NULL, listingId TEXT NOT NULL, listingVersion INTEGER NOT NULL,
    eventType TEXT NOT NULL, sanitizedPayloadJson TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','SENDING','SENT','REVIEW_REQUIRED')),
    leaseOwner TEXT, leaseExpiresAt TEXT, attemptCount INTEGER NOT NULL DEFAULT 0 CHECK(attemptCount>=0),
    messageId TEXT, createdAt TEXT NOT NULL, sentAt TEXT, lastAttemptedAt TEXT, lastErrorCode TEXT
);
CREATE INDEX IF NOT EXISTS idx_market_listing_browse ON MarketplaceListing(guildId,status,assetType,createdAt);

CREATE TABLE IF NOT EXISTS CasinoSession (
    sessionId VARCHAR(255) PRIMARY KEY,
    requestId TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    gameType TEXT NOT NULL CHECK(gameType IN ('BLACKJACK','SLOT','COINFLIP','RPS','NUMBER','GACHA','BOX')),
    stakeEcy INTEGER NOT NULL CHECK(stakeEcy>=0),
    maximumGrossLiabilityEcy INTEGER NOT NULL CHECK(maximumGrossLiabilityEcy>=0),
    outcomeJson TEXT NOT NULL,
    stateJson TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK(status IN ('RESERVED','ACTIVE','SETTLEMENT_PENDING','COMMITTED','VOID','REVIEW_REQUIRED')),
    reservationKey TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    retryCount INTEGER NOT NULL DEFAULT 0 CHECK(retryCount>=0),
    lastErrorCode TEXT,
    lastAttemptedAt TEXT,
    reviewMetadataJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL,
    expiresAt TEXT,
    settledAt TEXT,
    CHECK((status IN ('RESERVED','ACTIVE','SETTLEMENT_PENDING','REVIEW_REQUIRED') AND reservationKey IS NOT NULL)
       OR (status IN ('COMMITTED','VOID') AND reservationKey IS NULL))
);

CREATE TABLE IF NOT EXISTS CasinoSettlement (
    settlementId VARCHAR(255) PRIMARY KEY,
    sessionId TEXT NOT NULL UNIQUE,
    transactionId TEXT UNIQUE,
    stakeEcy INTEGER NOT NULL CHECK(stakeEcy>=0),
    grossPayoutEcy INTEGER NOT NULL CHECK(grossPayoutEcy>=0),
    status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','VOID','REVIEW_REQUIRED')),
    receiptJson TEXT,
    voidReasonCode TEXT,
    createdAt TEXT NOT NULL,
    settledAt TEXT,
    CHECK((status='COMMITTED' AND transactionId IS NOT NULL AND receiptJson IS NOT NULL AND voidReasonCode IS NULL)
       OR (status='VOID' AND receiptJson IS NULL AND voidReasonCode IS NOT NULL)
       OR (status IN ('PENDING','REVIEW_REQUIRED') AND receiptJson IS NULL AND voidReasonCode IS NULL))
);

CREATE TABLE IF NOT EXISTS CasinoBankrollReservation (
    reservationId VARCHAR(255) PRIMARY KEY,
    sessionId TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    liabilityEcy INTEGER NOT NULL CHECK(liabilityEcy>=0),
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','RELEASED','REVIEW_REQUIRED')),
    createdAt TEXT NOT NULL,
    releasedAt TEXT,
    CHECK((status='RELEASED' AND releasedAt IS NOT NULL) OR (status!='RELEASED' AND releasedAt IS NULL))
);

CREATE TABLE IF NOT EXISTS CasinoSessionAction (
    actionId VARCHAR(255) PRIMARY KEY,
    sessionId TEXT NOT NULL,
    requestId TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence>=1),
    actorId TEXT NOT NULL,
    actionType TEXT NOT NULL,
    actionJson TEXT NOT NULL,
    resultJson TEXT NOT NULL,
    transactionId TEXT UNIQUE,
    createdAt TEXT NOT NULL,
    UNIQUE(sessionId,requestId),
    UNIQUE(sessionId,sequence)
);

CREATE TABLE IF NOT EXISTS CasinoBankrollDistribution (
    distributionId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    transactionId TEXT NOT NULL UNIQUE,
    operationType TEXT NOT NULL CHECK(operationType IN ('ADJUST_TOP_UP','ADJUST_WITHDRAW','EXCESS_DISTRIBUTION','INITIAL_SEED')),
    amountEcy INTEGER NOT NULL CHECK(amountEcy>0),
    generalEcy INTEGER NOT NULL DEFAULT 0 CHECK(generalEcy>=0),
    reserveEcy INTEGER NOT NULL DEFAULT 0 CHECK(reserveEcy>=0),
    burnEcy INTEGER NOT NULL DEFAULT 0 CHECK(burnEcy>=0),
    actorId TEXT,
    reasonCode TEXT NOT NULL,
    receiptJson TEXT NOT NULL,
    createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS CasinoNotificationOutbox (
    eventId VARCHAR(255) PRIMARY KEY,
    eventKey TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    sessionId TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS CasinoRecoveryReview (
    reviewId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    entityType TEXT NOT NULL,
    entityId TEXT NOT NULL,
    errorCode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','RESOLVED')),
    retryCount INTEGER NOT NULL DEFAULT 1 CHECK(retryCount>0),
    sanitizedMetadataJson TEXT NOT NULL DEFAULT '{}',
    firstDetectedAt TEXT NOT NULL,
    lastAttemptedAt TEXT NOT NULL,
    resolvedAt TEXT,
    UNIQUE(guildId,entityType,entityId,errorCode)
);

CREATE TABLE IF NOT EXISTS CasinoLegacyStatistic (
    snapshotId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    sourceKey TEXT NOT NULL,
    sourceHash TEXT NOT NULL,
    sanitizedSnapshotJson TEXT NOT NULL,
    migrationStatus TEXT NOT NULL CHECK(migrationStatus IN ('SNAPSHOT','REVIEW_REQUIRED')),
    createdAt TEXT NOT NULL,
    UNIQUE(guildId,userId,sourceKey)
);

CREATE TABLE IF NOT EXISTS CasinoAuthorization (
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    permissionClass TEXT NOT NULL CHECK(permissionClass IN ('CASINO_CONTROL','CASINO_FINANCIAL','CASINO_RECOVERY')),
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    grantedById TEXT NOT NULL,
    reasonCode TEXT NOT NULL,
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId,userId,permissionClass)
);

CREATE TABLE IF NOT EXISTS CasinoAuthorizationAudit (
    auditId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    permissionClass TEXT NOT NULL,
    oldEnabled INTEGER,
    newEnabled INTEGER NOT NULL CHECK(newEnabled IN (0,1)),
    actionType TEXT NOT NULL CHECK(actionType IN ('GRANT','REVOKE','OWNER_OVERRIDE','USE')),
    actorId TEXT NOT NULL,
    reasonCode TEXT NOT NULL,
    createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS CryptoAssetDefinition (
    symbol VARCHAR(255) PRIMARY KEY,
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
    tickId VARCHAR(255) PRIMARY KEY,
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
    symbol VARCHAR(255) PRIMARY KEY,
    currentPriceEcy INTEGER NOT NULL CHECK(currentPriceEcy>0),
    lastTickId TEXT,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    updatedAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS CryptoPriceHistory (
    historyId VARCHAR(255) PRIMARY KEY,
    tickId TEXT NOT NULL,
    symbol TEXT NOT NULL,
    previousPriceEcy INTEGER NOT NULL CHECK(previousPriceEcy>0),
    currentPriceEcy INTEGER NOT NULL CHECK(currentPriceEcy>0),
    movementBps INTEGER NOT NULL,
    movementType TEXT NOT NULL CHECK(movementType IN ('INITIAL','NORMAL','NORMAL_EVENT','MAJOR_EVENT')),
    occurredAt TEXT NOT NULL,
    UNIQUE(tickId,symbol)
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
    PRIMARY KEY(guildId,userId,symbol)
);

CREATE TABLE IF NOT EXISTS CryptoTrade (
    tradeId VARCHAR(255) PRIMARY KEY,
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
    CHECK(marketFeeEcy+treasuryFeeEcy+burnFeeEcy=feeEcy),
    CHECK((status='COMMITTED' AND receiptJson IS NOT NULL AND voidReasonCode IS NULL AND settledAt IS NOT NULL)
       OR (status='VOID' AND receiptJson IS NULL AND voidReasonCode IS NOT NULL AND settledAt IS NOT NULL)
       OR (status IN ('PENDING','REVIEW_REQUIRED') AND receiptJson IS NULL AND voidReasonCode IS NULL AND settledAt IS NULL))
);

CREATE TABLE IF NOT EXISTS CryptoNewsEvent (
    newsId VARCHAR(255) PRIMARY KEY,
    eventKey TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    previousPriceEcy INTEGER NOT NULL CHECK(previousPriceEcy>0),
    currentPriceEcy INTEGER NOT NULL CHECK(currentPriceEcy>0),
    changeBps INTEGER NOT NULL,
    newsType TEXT NOT NULL CHECK(newsType IN ('ALERT','SURGE','CRASH')),
    comparisonStartedAt TEXT NOT NULL,
    occurredAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS CryptoNewsOutbox (
    outboxId VARCHAR(255) PRIMARY KEY,
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
    UNIQUE(newsId,guildId)
);

CREATE TABLE IF NOT EXISTS CryptoRecoveryReview (
    reviewId VARCHAR(255) PRIMARY KEY,
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
    auditId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    actorId TEXT NOT NULL,
    subjectId TEXT NOT NULL,
    permissionClass TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    reason TEXT NOT NULL,
    createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MiningRigCatalog (
    rigDefinitionId VARCHAR(255) PRIMARY KEY,
    name TEXT NOT NULL,
    purchasePriceEcy INTEGER NOT NULL CHECK(purchasePriceEcy>0),
    grossEquivalentPerDay INTEGER NOT NULL CHECK(grossEquivalentPerDay>0),
    maintenancePriceEcy INTEGER NOT NULL CHECK(maintenancePriceEcy>0),
    catalogVersion TEXT NOT NULL,
    createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MiningRigInstance (
    rigInstanceId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    rigDefinitionId TEXT NOT NULL,
    catalogVersion TEXT NOT NULL,
    targetSymbol TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','MAINTENANCE_DUE','REVIEW_REQUIRED')),
    durabilityBps INTEGER NOT NULL DEFAULT 10000 CHECK(durabilityBps=10000),
    paidThrough TEXT,
    accruedThrough TEXT NOT NULL,
    migrationSourceHash TEXT,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MiningPendingAsset (
    rigInstanceId TEXT NOT NULL,
    symbol TEXT NOT NULL,
    pendingUnits INTEGER NOT NULL DEFAULT 0 CHECK(pendingUnits>=0),
    fractionalBillionths INTEGER NOT NULL DEFAULT 0 CHECK(fractionalBillionths BETWEEN 0 AND 999999999),
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    updatedAt TEXT NOT NULL,
    PRIMARY KEY(rigInstanceId,symbol)
);

CREATE TABLE IF NOT EXISTS MiningOperation (
    operationId VARCHAR(255) PRIMARY KEY,
    requestId TEXT NOT NULL,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    operationType TEXT NOT NULL CHECK(operationType IN ('PURCHASE','MAINTENANCE','TARGET_CHANGE','ACCRUAL','CLAIM')),
    rigInstanceId TEXT,
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

CREATE TABLE IF NOT EXISTS MiningPurchase (
    purchaseId VARCHAR(255) PRIMARY KEY,
    operationId TEXT NOT NULL UNIQUE,
    rigInstanceId TEXT NOT NULL UNIQUE,
    priceEcy INTEGER NOT NULL CHECK(priceEcy>0),
    miningEcy INTEGER NOT NULL CHECK(miningEcy>=0),
    reserveEcy INTEGER NOT NULL CHECK(reserveEcy>=0),
    burnEcy INTEGER NOT NULL CHECK(burnEcy>=0),
    transactionId TEXT NOT NULL UNIQUE,
    createdAt TEXT NOT NULL,
    CHECK(miningEcy+reserveEcy+burnEcy=priceEcy)
);

CREATE TABLE IF NOT EXISTS MiningMaintenancePayment (
    paymentId VARCHAR(255) PRIMARY KEY,
    operationId TEXT NOT NULL UNIQUE,
    rigInstanceId TEXT NOT NULL,
    periodStart TEXT NOT NULL,
    periodEnd TEXT NOT NULL,
    priceEcy INTEGER NOT NULL CHECK(priceEcy>0),
    miningEcy INTEGER NOT NULL CHECK(miningEcy>=0),
    reserveEcy INTEGER NOT NULL CHECK(reserveEcy>=0),
    burnEcy INTEGER NOT NULL CHECK(burnEcy>=0),
    transactionId TEXT NOT NULL UNIQUE,
    createdAt TEXT NOT NULL,
    CHECK(miningEcy+reserveEcy+burnEcy=priceEcy)
);

CREATE TABLE IF NOT EXISTS MiningTargetChange (
    changeId VARCHAR(255) PRIMARY KEY,
    operationId TEXT NOT NULL UNIQUE,
    rigInstanceId TEXT NOT NULL,
    previousSymbol TEXT NOT NULL,
    targetSymbol TEXT NOT NULL,
    changedAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MiningAccrualCheckpoint (
    checkpointId VARCHAR(255) PRIMARY KEY,
    operationId TEXT NOT NULL UNIQUE,
    rigInstanceId TEXT NOT NULL,
    symbol TEXT NOT NULL,
    observedAt TEXT NOT NULL,
    previousAccruedThrough TEXT NOT NULL,
    rewardedSeconds INTEGER NOT NULL CHECK(rewardedSeconds BETWEEN 0 AND 86400),
    discardedSeconds INTEGER NOT NULL CHECK(discardedSeconds>=0),
    windowStart TEXT,
    windowEnd TEXT,
    sampleCount INTEGER NOT NULL CHECK(sampleCount>=0),
    priceSum INTEGER NOT NULL CHECK(priceSum>=0),
    averagePriceEcy INTEGER CHECK(averagePriceEcy>0),
    latestHistoryId TEXT,
    priceReferenceHash TEXT,
    numeratorText TEXT NOT NULL,
    denominatorText TEXT NOT NULL,
    calculationHash TEXT NOT NULL,
    creditedUnits INTEGER NOT NULL CHECK(creditedUnits>=0),
    previousCarry INTEGER NOT NULL CHECK(previousCarry BETWEEN 0 AND 999999999),
    resultingCarry INTEGER NOT NULL CHECK(resultingCarry BETWEEN 0 AND 999999999),
    createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MiningClaim (
    claimId VARCHAR(255) PRIMARY KEY,
    operationId TEXT NOT NULL UNIQUE,
    requestId TEXT NOT NULL,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    rigInstanceId TEXT NOT NULL,
    outcomeJson TEXT NOT NULL,
    receiptJson TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status='COMMITTED'),
    createdAt TEXT NOT NULL,
    settledAt TEXT NOT NULL,
    UNIQUE(guildId,requestId)
);

CREATE TABLE IF NOT EXISTS MiningClaimAsset (
    claimId TEXT NOT NULL,
    symbol TEXT NOT NULL,
    units INTEGER NOT NULL CHECK(units>0),
    pendingBefore INTEGER NOT NULL CHECK(pendingBefore>=units),
    pendingAfter INTEGER NOT NULL CHECK(pendingAfter>=0),
    holdingBefore INTEGER NOT NULL CHECK(holdingBefore>=0),
    holdingAfter INTEGER NOT NULL CHECK(holdingAfter>=units),
    PRIMARY KEY(claimId,symbol)
);

CREATE TABLE IF NOT EXISTS MiningAssetLedger (
    entryId VARCHAR(255) PRIMARY KEY,
    claimId TEXT NOT NULL,
    operationId TEXT NOT NULL,
    symbol TEXT NOT NULL,
    accountType TEXT NOT NULL CHECK(accountType IN ('RIG_PENDING','USER_HOLDING')),
    accountId TEXT NOT NULL,
    unitsDelta INTEGER NOT NULL CHECK(unitsDelta<>0),
    createdAt TEXT NOT NULL,
    UNIQUE(claimId,symbol,accountType)
);

CREATE TABLE IF NOT EXISTS MiningNotificationOutbox (
    outboxId VARCHAR(255) PRIMARY KEY,
    operationId TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    eventType TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS MiningRecoveryReview (
    reviewId VARCHAR(255) PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS MiningLegacyRigMigration (
    sourceUserId TEXT NOT NULL,
    sourceSymbol TEXT NOT NULL,
    sourceTierText TEXT NOT NULL,
    sourceOrdinal INTEGER NOT NULL CHECK(sourceOrdinal>0),
    sourceHash TEXT NOT NULL,
    targetGuildId TEXT,
    rigInstanceId TEXT,
    status TEXT NOT NULL CHECK(status IN ('MIGRATED','REVIEW_REQUIRED')),
    errorCode TEXT,
    rawSourceJson TEXT NOT NULL,
    sanitizedMetadataJson TEXT NOT NULL DEFAULT '{}',
    migratedAt TEXT NOT NULL,
    PRIMARY KEY(sourceUserId,sourceSymbol,sourceTierText,sourceOrdinal)
);

CREATE TABLE IF NOT EXISTS MiningAuthorization (
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    permissionClass TEXT NOT NULL CHECK(permissionClass IN ('MINING_CONTROL','MINING_RECOVERY')),
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    grantedById TEXT NOT NULL,
    reason TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    PRIMARY KEY(guildId,userId,permissionClass)
);

CREATE TABLE IF NOT EXISTS MiningAuthorizationAudit (
    auditId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    actorId TEXT NOT NULL,
    subjectId TEXT NOT NULL,
    permissionClass TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    reason TEXT NOT NULL,
    createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Phase8Operation (
    operationId VARCHAR(255) PRIMARY KEY,
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
    giveawayId VARCHAR(255) PRIMARY KEY,
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
    ticketId VARCHAR(255) PRIMARY KEY,
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
    UNIQUE(giveawayId,userId)
);

CREATE TABLE IF NOT EXISTS GiveawayEligibilityEvidence (
    evidenceId VARCHAR(255) PRIMARY KEY,
    giveawayId TEXT NOT NULL,
    userId TEXT NOT NULL,
    stage TEXT NOT NULL CHECK(stage IN ('ENTRY','DRAW','REDRAW')),
    drawSequence INTEGER NOT NULL DEFAULT 0 CHECK(drawSequence>=0),
    eligible INTEGER NOT NULL CHECK(eligible IN (0,1)),
    evidenceJson TEXT NOT NULL,
    evidenceHash TEXT NOT NULL,
    observedAt TEXT NOT NULL,
    UNIQUE(giveawayId,userId,stage,drawSequence)
);

CREATE TABLE IF NOT EXISTS GiveawayEscrow (
    giveawayId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    paidTickets INTEGER NOT NULL DEFAULT 0 CHECK(paidTickets>=0),
    amountEcy INTEGER NOT NULL DEFAULT 0 CHECK(amountEcy=paidTickets*10000),
    status TEXT NOT NULL CHECK(status IN ('OPEN','ALLOCATED','REFUNDED','REVIEW_REQUIRED')),
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    updatedAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS GiveawayDraw (
    drawId VARCHAR(255) PRIMARY KEY,
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
    UNIQUE(giveawayId,sequence)
);

CREATE TABLE IF NOT EXISTS GiveawayWinner (
    winnerId VARCHAR(255) PRIMARY KEY,
    giveawayId TEXT NOT NULL,
    drawId TEXT NOT NULL UNIQUE,
    userId TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence>0),
    status TEXT NOT NULL CHECK(status IN ('AWAITING_CLAIM','CLAIMED','INVALIDATED')),
    eligibilityEvidenceJson TEXT NOT NULL,
    claimDeadline TEXT NOT NULL,
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    UNIQUE(giveawayId,sequence)
);

CREATE TABLE IF NOT EXISTS GiveawayClaim (
    claimId VARCHAR(255) PRIMARY KEY,
    giveawayId TEXT NOT NULL UNIQUE,
    winnerId TEXT NOT NULL UNIQUE,
    userId TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status='ACKNOWLEDGED'),
    receiptJson TEXT NOT NULL,
    claimedAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS GiveawayWinnerReview (
    reviewId VARCHAR(255) PRIMARY KEY,
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
    UNIQUE(giveawayId,winnerId,reasonCode,evidenceHash)
);

CREATE TABLE IF NOT EXISTS GiveawayRefund (
    refundId VARCHAR(255) PRIMARY KEY,
    giveawayId TEXT NOT NULL,
    ticketId TEXT NOT NULL UNIQUE,
    userId TEXT NOT NULL,
    amountEcy INTEGER NOT NULL CHECK(amountEcy=10000),
    transactionId TEXT NOT NULL UNIQUE,
    receiptJson TEXT NOT NULL,
    createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS GiveawayFundAllocation (
    allocationId VARCHAR(255) PRIMARY KEY,
    giveawayId TEXT NOT NULL UNIQUE,
    totalEcy INTEGER NOT NULL CHECK(totalEcy>=0),
    retainedEcy INTEGER NOT NULL CHECK(retainedEcy>=0),
    reserveEcy INTEGER NOT NULL CHECK(reserveEcy>=0),
    burnEcy INTEGER NOT NULL CHECK(burnEcy>=0),
    transactionId TEXT,
    receiptJson TEXT NOT NULL,
    createdAt TEXT NOT NULL,
    CHECK(retainedEcy+reserveEcy+burnEcy=totalEcy)
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
    blockId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    channelId TEXT NOT NULL,
    qualifiedStartAt TEXT NOT NULL,
    blockSequence INTEGER NOT NULL CHECK(blockSequence>0),
    blockEndAt TEXT NOT NULL,
    activityEventId TEXT NOT NULL UNIQUE,
    createdAt TEXT NOT NULL,
    UNIQUE(guildId,userId,qualifiedStartAt,blockSequence)
);

CREATE TABLE IF NOT EXISTS GiveawayLegacySnapshot (
    snapshotId VARCHAR(255) PRIMARY KEY,
    sourceType TEXT NOT NULL,
    sourceIdentity TEXT NOT NULL,
    sourceHash TEXT NOT NULL,
    rawSourceJson TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('READ_ONLY','REVIEW_REQUIRED')),
    createdAt TEXT NOT NULL,
    UNIQUE(sourceType,sourceIdentity,sourceHash)
);

CREATE TABLE IF NOT EXISTS EternalOptionPosition (
    positionId VARCHAR(255) PRIMARY KEY,
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
    UNIQUE(guildId,requestId)
);

CREATE TABLE IF NOT EXISTS EternalOptionReservation (
    reservationId VARCHAR(255) PRIMARY KEY,
    positionId TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    liabilityEcy INTEGER NOT NULL CHECK(liabilityEcy>0),
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','RELEASED','REVIEW_REQUIRED')),
    createdAt TEXT NOT NULL,
    releasedAt TEXT
);

CREATE TABLE IF NOT EXISTS EternalOptionSettlement (
    settlementId VARCHAR(255) PRIMARY KEY,
    positionId TEXT NOT NULL UNIQUE,
    resultCode TEXT NOT NULL CHECK(resultCode IN ('WIN','LOSS','TIE')),
    payoutEcy INTEGER NOT NULL CHECK(payoutEcy>=0),
    transactionId TEXT UNIQUE,
    openingTransactionId TEXT NOT NULL,
    receiptJson TEXT NOT NULL,
    settledAt TEXT NOT NULL,
    CHECK((resultCode='LOSS' AND transactionId IS NULL AND payoutEcy=0) OR
          (resultCode IN ('WIN','TIE') AND transactionId IS NOT NULL AND payoutEcy>0))
);

CREATE TABLE IF NOT EXISTS Phase8NotificationOutbox (
    outboxId VARCHAR(255) PRIMARY KEY,
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
    reviewId VARCHAR(255) PRIMARY KEY,
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
    auditId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    actorId TEXT,
    actionType TEXT NOT NULL,
    entityType TEXT NOT NULL,
    entityId TEXT NOT NULL,
    receiptJson TEXT NOT NULL,
    createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS DashboardIdentity (
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','DISABLED')),
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    PRIMARY KEY(guildId,userId)
);

CREATE TABLE IF NOT EXISTS DashboardOperatorPermission (
    assignmentId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    permissionClass TEXT NOT NULL CHECK(permissionClass IN (
      'DASHBOARD_VIEW','DASHBOARD_CONFIGURATION','ECONOMY_PAUSE_CONTROL',
      'REVIEWED_RECOVERY_CONTROL','NOTIFICATION_ROUTING_CONTROL',
      'OPERATOR_AUDIT_READ','DASHBOARD_SECURITY_ADMIN')),
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVOKED')),
    grantedById TEXT NOT NULL,
    grantedAt TEXT NOT NULL,
    revokedById TEXT,
    revokedAt TEXT,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    CHECK((status='ACTIVE' AND revokedById IS NULL AND revokedAt IS NULL) OR
          (status='REVOKED' AND revokedById IS NOT NULL AND revokedAt IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS DashboardAuthorizationAudit (
    auditId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    targetUserId TEXT NOT NULL,
    permissionClass TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('BOOTSTRAP','GRANT','REVOKE')),
    executorUserId TEXT NOT NULL,
    requestId TEXT NOT NULL,
    assignmentId TEXT NOT NULL,
    previousVersion INTEGER,
    resultingVersion INTEGER NOT NULL,
    receiptHash TEXT NOT NULL,
    metadataJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL,
    UNIQUE(guildId,requestId)
);

CREATE TABLE IF NOT EXISTS DashboardSigningKeyVersion (
    keyId VARCHAR(255) PRIMARY KEY,
    purpose TEXT NOT NULL CHECK(purpose IN ('INTERNAL_REQUEST','SESSION_HASH','IP_HASH')),
    fingerprintSha256 TEXT NOT NULL CHECK(length(fingerprintSha256)=64),
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','RETIRED','REVOKED')),
    activatedAt TEXT NOT NULL,
    retiredAt TEXT,
    createdById TEXT NOT NULL,
    CHECK((status='ACTIVE' AND retiredAt IS NULL) OR status IN ('RETIRED','REVOKED'))
);

CREATE TABLE IF NOT EXISTS DashboardSession (
    sessionId VARCHAR(255) PRIMARY KEY,
    tokenHash TEXT NOT NULL UNIQUE CHECK(length(tokenHash)=64),
    guildId TEXT NOT NULL,
    userId TEXT NOT NULL,
    signingKeyId TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVOKED','EXPIRED')),
    createdAt TEXT NOT NULL,
    lastSeenAt TEXT NOT NULL,
    idleExpiresAt TEXT NOT NULL,
    absoluteExpiresAt TEXT NOT NULL,
    revokedAt TEXT,
    revokeReasonCode TEXT,
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    CHECK((status='ACTIVE' AND revokedAt IS NULL) OR status IN ('REVOKED','EXPIRED'))
);

CREATE TABLE IF NOT EXISTS DashboardOAuthAttempt (
    attemptId VARCHAR(255) PRIMARY KEY,
    stateHash TEXT NOT NULL UNIQUE CHECK(length(stateHash)=64),
    pkceChallenge TEXT NOT NULL,
    returnPath TEXT NOT NULL CHECK(returnPath='/'),
    ipHash TEXT NOT NULL CHECK(length(ipHash)=64),
    status TEXT NOT NULL CHECK(status IN ('PENDING','CONSUMED','EXPIRED','REJECTED')),
    createdAt TEXT NOT NULL,
    expiresAt TEXT NOT NULL,
    consumedAt TEXT
);

CREATE TABLE IF NOT EXISTS DashboardCsrfToken (
    csrfId VARCHAR(255) PRIMARY KEY,
    tokenHash TEXT NOT NULL UNIQUE CHECK(length(tokenHash)=64),
    sessionId TEXT NOT NULL,
    method TEXT NOT NULL,
    canonicalRoute TEXT NOT NULL,
    requestId TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','CONSUMED','EXPIRED','REVOKED')),
    createdAt TEXT NOT NULL,
    expiresAt TEXT NOT NULL,
    consumedAt TEXT
);

CREATE TABLE IF NOT EXISTS DashboardInternalNonce (
    keyId TEXT NOT NULL,
    nonceHash TEXT NOT NULL CHECK(length(nonceHash)=64),
    requestId TEXT NOT NULL,
    canonicalRoute TEXT NOT NULL,
    createdAt TEXT NOT NULL,
    expiresAt TEXT NOT NULL,
    consumedAt TEXT NOT NULL,
    PRIMARY KEY(keyId,nonceHash)
);

CREATE TABLE IF NOT EXISTS DashboardControlledOperation (
    operationId VARCHAR(255) PRIMARY KEY,
    requestId TEXT NOT NULL UNIQUE,
    guildId TEXT NOT NULL,
    actorId TEXT NOT NULL,
    permissionClass TEXT NOT NULL,
    operationType TEXT NOT NULL,
    targetType TEXT NOT NULL,
    targetId TEXT NOT NULL,
    payloadHash TEXT NOT NULL CHECK(length(payloadHash)=64),
    expectedVersion INTEGER,
    resultingVersion INTEGER,
    status TEXT NOT NULL CHECK(status IN ('PENDING','COMMITTED','VOID','REVIEW_REQUIRED')),
    receiptJson TEXT,
    receiptHash TEXT,
    errorCode TEXT,
    createdAt TEXT NOT NULL,
    settledAt TEXT,
    CHECK((status='COMMITTED' AND receiptJson IS NOT NULL AND receiptHash IS NOT NULL AND settledAt IS NOT NULL) OR
          (status IN ('PENDING','REVIEW_REQUIRED') AND receiptJson IS NULL AND receiptHash IS NULL) OR
          (status='VOID' AND settledAt IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS DashboardOperatorAudit (
    auditId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    executorUserId TEXT NOT NULL,
    permissionClass TEXT NOT NULL,
    operationType TEXT NOT NULL,
    targetType TEXT NOT NULL,
    targetId TEXT NOT NULL,
    requestId TEXT NOT NULL UNIQUE,
    previousVersion INTEGER,
    resultingVersion INTEGER,
    resultStatus TEXT NOT NULL,
    payloadHash TEXT NOT NULL CHECK(length(payloadHash)=64),
    receiptHash TEXT,
    metadataJson TEXT NOT NULL DEFAULT '{}',
    sourceRoute TEXT NOT NULL,
    sourceIpHash TEXT CHECK(sourceIpHash IS NULL OR length(sourceIpHash)=64),
    createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS DashboardSecurityEvent (
    eventId VARCHAR(255) PRIMARY KEY,
    guildId TEXT,
    actorId TEXT,
    eventType TEXT NOT NULL,
    safeErrorCode TEXT NOT NULL,
    requestId TEXT,
    route TEXT NOT NULL,
    sourceIpHash TEXT CHECK(sourceIpHash IS NULL OR length(sourceIpHash)=64),
    metadataJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS DashboardRateLimitBucket (
    scopeHash TEXT NOT NULL CHECK(length(scopeHash)=64),
    routeGroup TEXT NOT NULL,
    windowStartedAt TEXT NOT NULL,
    requestCount INTEGER NOT NULL CHECK(requestCount>=0),
    expiresAt TEXT NOT NULL,
    PRIMARY KEY(scopeHash,routeGroup,windowStartedAt)
);

CREATE TABLE IF NOT EXISTS DashboardLegacyRouteSnapshot (
    snapshotId VARCHAR(255) PRIMARY KEY,
    method TEXT NOT NULL,
    route TEXT NOT NULL,
    disposition TEXT NOT NULL CHECK(disposition IN ('DISABLED_READ','DISABLED_WRITE','INTERNAL_SIGNED','PUBLIC_HEALTH')),
    sourceHash TEXT NOT NULL CHECK(length(sourceHash)=64),
    createdAt TEXT NOT NULL,
    UNIQUE(method,route)
);

CREATE TABLE IF NOT EXISTS DashboardNotificationRoute (
    guildId TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN (
      'GENERAL','MARKET_CRYPTO','MARKETPLACE','GIVEAWAY','CASINO','ETERNAL_OPTIONS',
      'MINING','BOSS','LEVEL_UP','BIRTHDAY','BOOSTER','RECOVERY','SECURITY','OPERATOR_AUDIT')),
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    channelId TEXT,
    roleMentionId TEXT,
    eventFilterJson TEXT NOT NULL DEFAULT '{"eventTypes":[]}',
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    updatedById TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    lastSuccessfulDeliveryAt TEXT,
    lastFailedDeliveryAt TEXT,
    lastFailureCode TEXT,
    PRIMARY KEY(guildId,category),
    CHECK((enabled=0) OR (channelId IS NOT NULL AND length(channelId)>=17)),
    CHECK(channelId IS NULL OR channelId !~ '[^0-9]'),
    CHECK(roleMentionId IS NULL OR (length(roleMentionId)>=17 AND roleMentionId !~ '[^0-9]'))
);

CREATE TABLE IF NOT EXISTS DashboardNotificationDelivery (
    deliveryId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    deliveryKind TEXT NOT NULL CHECK(deliveryKind IN ('EVENT','TEST')),
    sourceType TEXT NOT NULL,
    sourceKey TEXT NOT NULL,
    category TEXT NOT NULL,
    routeVersion INTEGER NOT NULL CHECK(routeVersion>=0),
    channelId TEXT NOT NULL,
    roleMentionId TEXT,
    eventType TEXT NOT NULL,
    payloadJson TEXT NOT NULL,
    payloadHash TEXT NOT NULL CHECK(length(payloadHash)=64),
    marker TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('RESERVED','LEASED','SENT','FAILED','REVIEW_REQUIRED')),
    leaseOwner TEXT,
    leaseExpiresAt TEXT,
    attemptCount INTEGER NOT NULL DEFAULT 0 CHECK(attemptCount>=0),
    messageId TEXT,
    lastFailureCode TEXT,
    requestId TEXT,
    actorId TEXT,
    receiptJson TEXT,
    receiptHash TEXT CHECK(receiptHash IS NULL OR length(receiptHash)=64),
    createdAt TEXT NOT NULL,
    attemptedAt TEXT,
    completedAt TEXT,
    UNIQUE(guildId,deliveryKind,sourceType,sourceKey),
    CHECK((status='LEASED' AND leaseOwner IS NOT NULL AND leaseExpiresAt IS NOT NULL)
       OR (status<>'LEASED' AND leaseOwner IS NULL AND leaseExpiresAt IS NULL)),
    CHECK((status='SENT' AND messageId IS NOT NULL AND receiptJson IS NOT NULL AND receiptHash IS NOT NULL AND completedAt IS NOT NULL)
       OR (status='REVIEW_REQUIRED' AND receiptJson IS NOT NULL AND receiptHash IS NOT NULL AND completedAt IS NOT NULL)
       OR (status IN ('RESERVED','LEASED','FAILED') AND receiptJson IS NULL AND receiptHash IS NULL AND completedAt IS NULL))
);

CREATE TABLE IF NOT EXISTS DashboardNotificationLegacySnapshot (
    snapshotId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    sourceKey TEXT NOT NULL,
    mappedCategory TEXT,
    destinationId TEXT,
    sourceFileHash TEXT NOT NULL CHECK(length(sourceFileHash)=64),
    sourceValueHash TEXT NOT NULL CHECK(length(sourceValueHash)=64),
    capabilityManifestHash TEXT CHECK(capabilityManifestHash IS NULL OR length(capabilityManifestHash)=64),
    disposition TEXT NOT NULL CHECK(disposition IN (
      'IMPORTED','INVALID','MISSING','FOREIGN_GUILD','UNWRITABLE','DEPRECATED','UNRECOGNIZED')),
    evidenceJson TEXT NOT NULL DEFAULT '{}',
    createdAt TEXT NOT NULL,
    UNIQUE(guildId,sourceKey,sourceValueHash)
);

CREATE TABLE IF NOT EXISTS DashboardEconomyReconciliationRun (
    runId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    schemaChecksum TEXT NOT NULL CHECK(length(schemaChecksum)=64),
    status TEXT NOT NULL CHECK(status IN ('PASSED','FAILED')),
    integrityResult TEXT NOT NULL,
    foreignKeyErrorCount INTEGER NOT NULL CHECK(foreignKeyErrorCount>=0),
    ledgerUnbalancedCount INTEGER NOT NULL CHECK(ledgerUnbalancedCount>=0),
    supplyMismatchCount INTEGER NOT NULL CHECK(supplyMismatchCount>=0),
    liabilityMismatchCount INTEGER NOT NULL CHECK(liabilityMismatchCount>=0),
    routeIssueCount INTEGER NOT NULL CHECK(routeIssueCount>=0),
    outboxIssueCount INTEGER NOT NULL CHECK(outboxIssueCount>=0),
    reportJson TEXT NOT NULL,
    reportHash TEXT NOT NULL CHECK(length(reportHash)=64),
    startedAt TEXT NOT NULL,
    completedAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS DashboardRecoveryControl (
    controlId VARCHAR(255) PRIMARY KEY,
    guildId TEXT NOT NULL,
    domain TEXT NOT NULL,
    entityType TEXT NOT NULL,
    entityId TEXT NOT NULL,
    sourceStateHash TEXT NOT NULL CHECK(length(sourceStateHash)=64),
    status TEXT NOT NULL CHECK(status IN ('OPEN','RESOLVED','REVIEW_REQUIRED')),
    version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
    lastOperationId TEXT,
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    UNIQUE(guildId,domain,entityType,entityId)
);



-- Deferred Foreign Keys --
ALTER TABLE EconomyMigrationItem ADD FOREIGN KEY(runId) REFERENCES EconomyMigrationRun(runId);
ALTER TABLE EconomyLedger ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE EconomyClaimState ADD FOREIGN KEY(lastTransactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE EconomyRewardRoll ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE EconomyActivityEvent ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE EconomyCutoverState ADD FOREIGN KEY(firstProductionTransactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE RpgOperation ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE RpgEnhancementAttempt ADD FOREIGN KEY(operationId) REFERENCES RpgOperation(operationId);
ALTER TABLE RpgOpenAttempt ADD FOREIGN KEY(operationId) REFERENCES RpgOperation(operationId);
ALTER TABLE RpgHuntRun ADD FOREIGN KEY(operationId) REFERENCES RpgOperation(operationId);
ALTER TABLE RpgDungeonRun ADD FOREIGN KEY(operationId) REFERENCES RpgOperation(operationId);
ALTER TABLE RpgCraftAttempt ADD FOREIGN KEY(operationId) REFERENCES RpgOperation(operationId);
ALTER TABLE RpgBossContribution ADD FOREIGN KEY(raidId) REFERENCES RpgBossRaid(raidId);
ALTER TABLE RpgBossAttack ADD FOREIGN KEY(operationId) REFERENCES RpgOperation(operationId);
ALTER TABLE RpgBossAttack ADD FOREIGN KEY(raidId) REFERENCES RpgBossRaid(raidId);
ALTER TABLE RpgBossParticipantReward ADD FOREIGN KEY(raidId) REFERENCES RpgBossRaid(raidId);
ALTER TABLE MarketplaceListing ADD FOREIGN KEY(escrowId) REFERENCES MarketplaceEscrow(escrowId) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE MarketplaceEscrow ADD FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE MarketplaceSale ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE MarketplaceSale ADD FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId);
ALTER TABLE MarketplaceSale ADD FOREIGN KEY(escrowId) REFERENCES MarketplaceEscrow(escrowId);
ALTER TABLE MarketplaceReturn ADD FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId);
ALTER TABLE MarketplaceReturn ADD FOREIGN KEY(escrowId) REFERENCES MarketplaceEscrow(escrowId);
ALTER TABLE MarketplaceWatch ADD FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId);
ALTER TABLE MarketplaceReport ADD FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId);
ALTER TABLE MarketplaceQuantityMutation ADD FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId);
ALTER TABLE MarketplaceQuantityMutation ADD FOREIGN KEY(escrowId) REFERENCES MarketplaceEscrow(escrowId);
ALTER TABLE MarketplaceQuantityMutation ADD FOREIGN KEY(saleId) REFERENCES MarketplaceSale(saleId);
ALTER TABLE MarketplaceQuantityMutation ADD FOREIGN KEY(returnId) REFERENCES MarketplaceReturn(returnId);
ALTER TABLE MarketplaceSettlementEvidence ADD FOREIGN KEY(saleId) REFERENCES MarketplaceSale(saleId);
ALTER TABLE MarketplaceSettlementEvidence ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE MarketplaceSettlementEvidence ADD FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId);
ALTER TABLE MarketplaceSettlementEvidence ADD FOREIGN KEY(escrowId) REFERENCES MarketplaceEscrow(escrowId);
ALTER TABLE MarketplaceSettlementEvidence ADD FOREIGN KEY(quantityMutationId) REFERENCES MarketplaceQuantityMutation(mutationId);
ALTER TABLE MarketplaceNotificationOutbox ADD FOREIGN KEY(listingId) REFERENCES MarketplaceListing(listingId);
ALTER TABLE CasinoSettlement ADD FOREIGN KEY(sessionId) REFERENCES CasinoSession(sessionId);
ALTER TABLE CasinoSettlement ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE CasinoBankrollReservation ADD FOREIGN KEY(sessionId) REFERENCES CasinoSession(sessionId);
ALTER TABLE CasinoSessionAction ADD FOREIGN KEY(sessionId) REFERENCES CasinoSession(sessionId);
ALTER TABLE CasinoSessionAction ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE CasinoBankrollDistribution ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE CasinoNotificationOutbox ADD FOREIGN KEY(sessionId) REFERENCES CasinoSession(sessionId);
ALTER TABLE CryptoMarketState ADD FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol);
ALTER TABLE CryptoMarketState ADD FOREIGN KEY(lastTickId) REFERENCES CryptoMarketTick(tickId);
ALTER TABLE CryptoPriceHistory ADD FOREIGN KEY(tickId) REFERENCES CryptoMarketTick(tickId);
ALTER TABLE CryptoPriceHistory ADD FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol);
ALTER TABLE CryptoHolding ADD FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol);
ALTER TABLE CryptoTrade ADD FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol);
ALTER TABLE CryptoTrade ADD FOREIGN KEY(priceTickId) REFERENCES CryptoMarketTick(tickId);
ALTER TABLE CryptoTrade ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE CryptoNewsEvent ADD FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol);
ALTER TABLE CryptoNewsOutbox ADD FOREIGN KEY(newsId) REFERENCES CryptoNewsEvent(newsId);
ALTER TABLE MiningRigInstance ADD FOREIGN KEY(rigDefinitionId) REFERENCES MiningRigCatalog(rigDefinitionId);
ALTER TABLE MiningRigInstance ADD FOREIGN KEY(targetSymbol) REFERENCES CryptoAssetDefinition(symbol);
ALTER TABLE MiningPendingAsset ADD FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId);
ALTER TABLE MiningPendingAsset ADD FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol);
ALTER TABLE MiningOperation ADD FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId);
ALTER TABLE MiningPurchase ADD FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId);
ALTER TABLE MiningPurchase ADD FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId);
ALTER TABLE MiningPurchase ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE MiningMaintenancePayment ADD FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId);
ALTER TABLE MiningMaintenancePayment ADD FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId);
ALTER TABLE MiningMaintenancePayment ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE MiningTargetChange ADD FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId);
ALTER TABLE MiningTargetChange ADD FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId);
ALTER TABLE MiningAccrualCheckpoint ADD FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId);
ALTER TABLE MiningAccrualCheckpoint ADD FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId);
ALTER TABLE MiningAccrualCheckpoint ADD FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol);
ALTER TABLE MiningClaim ADD FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId);
ALTER TABLE MiningClaim ADD FOREIGN KEY(rigInstanceId) REFERENCES MiningRigInstance(rigInstanceId);
ALTER TABLE MiningClaimAsset ADD FOREIGN KEY(claimId) REFERENCES MiningClaim(claimId);
ALTER TABLE MiningClaimAsset ADD FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol);
ALTER TABLE MiningAssetLedger ADD FOREIGN KEY(claimId) REFERENCES MiningClaim(claimId);
ALTER TABLE MiningAssetLedger ADD FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId);
ALTER TABLE MiningNotificationOutbox ADD FOREIGN KEY(operationId) REFERENCES MiningOperation(operationId);
ALTER TABLE GiveawayTicket ADD FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId);
ALTER TABLE GiveawayTicket ADD FOREIGN KEY(entryTransactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE GiveawayTicket ADD FOREIGN KEY(refundTransactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE GiveawayEligibilityEvidence ADD FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId);
ALTER TABLE GiveawayEscrow ADD FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId);
ALTER TABLE GiveawayDraw ADD FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId);
ALTER TABLE GiveawayWinner ADD FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId);
ALTER TABLE GiveawayWinner ADD FOREIGN KEY(drawId) REFERENCES GiveawayDraw(drawId);
ALTER TABLE GiveawayClaim ADD FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId);
ALTER TABLE GiveawayClaim ADD FOREIGN KEY(winnerId) REFERENCES GiveawayWinner(winnerId);
ALTER TABLE GiveawayWinnerReview ADD FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId);
ALTER TABLE GiveawayWinnerReview ADD FOREIGN KEY(winnerId) REFERENCES GiveawayWinner(winnerId);
ALTER TABLE GiveawayRefund ADD FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId);
ALTER TABLE GiveawayRefund ADD FOREIGN KEY(ticketId) REFERENCES GiveawayTicket(ticketId);
ALTER TABLE GiveawayRefund ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE GiveawayFundAllocation ADD FOREIGN KEY(giveawayId) REFERENCES GiveawayV1(giveawayId);
ALTER TABLE GiveawayFundAllocation ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE GiveawayVoiceBlock ADD FOREIGN KEY(activityEventId) REFERENCES EconomyActivityEvent(eventId);
ALTER TABLE EternalOptionPosition ADD FOREIGN KEY(symbol) REFERENCES CryptoAssetDefinition(symbol);
ALTER TABLE EternalOptionPosition ADD FOREIGN KEY(entryHistoryId) REFERENCES CryptoPriceHistory(historyId);
ALTER TABLE EternalOptionPosition ADD FOREIGN KEY(expiryHistoryId) REFERENCES CryptoPriceHistory(historyId);
ALTER TABLE EternalOptionPosition ADD FOREIGN KEY(openingTransactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE EternalOptionReservation ADD FOREIGN KEY(positionId) REFERENCES EternalOptionPosition(positionId);
ALTER TABLE EternalOptionSettlement ADD FOREIGN KEY(positionId) REFERENCES EternalOptionPosition(positionId);
ALTER TABLE EternalOptionSettlement ADD FOREIGN KEY(transactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE EternalOptionSettlement ADD FOREIGN KEY(openingTransactionId) REFERENCES EconomyTransaction(transactionId);
ALTER TABLE DashboardOperatorPermission ADD FOREIGN KEY(guildId,userId) REFERENCES DashboardIdentity(guildId,userId);
ALTER TABLE DashboardAuthorizationAudit ADD FOREIGN KEY(assignmentId) REFERENCES DashboardOperatorPermission(assignmentId);
ALTER TABLE DashboardSession ADD FOREIGN KEY(guildId,userId) REFERENCES DashboardIdentity(guildId,userId);
ALTER TABLE DashboardSession ADD FOREIGN KEY(signingKeyId) REFERENCES DashboardSigningKeyVersion(keyId);
ALTER TABLE DashboardCsrfToken ADD FOREIGN KEY(sessionId) REFERENCES DashboardSession(sessionId);
ALTER TABLE DashboardInternalNonce ADD FOREIGN KEY(keyId) REFERENCES DashboardSigningKeyVersion(keyId);
ALTER TABLE DashboardOperatorAudit ADD FOREIGN KEY(requestId) REFERENCES DashboardControlledOperation(requestId);
