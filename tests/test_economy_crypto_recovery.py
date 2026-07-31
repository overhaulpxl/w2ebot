import json
import sqlite3
import unittest

from economy.crypto_market import DeterministicRng, reserve_market_tick
from economy.phase6_recovery import (
    claim_crypto_news_outbox, finalize_crypto_news_outbox, recover_phase6_runtime,
)
from tests.crypto_test_utils import TempCryptoDatabase


class CryptoRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = TempCryptoDatabase()

    async def asyncTearDown(self):
        self.database.close()

    async def test_reserved_tick_reuses_persisted_outcome(self):
        tick_id, outcome, _, _ = await reserve_market_tick(
            self.database.path, scheduled_at=None, rng=DeterministicRng(11),
        )
        result = await recover_phase6_runtime(self.database.path)
        self.assertEqual(result["ticks_committed"], 1)
        connection = sqlite3.connect(self.database.path)
        row = connection.execute(
            "SELECT outcomeJson,status FROM CryptoMarketTick WHERE tickId=?", (tick_id,),
        ).fetchone()
        connection.close()
        self.assertEqual(json.loads(row[0]), outcome)
        self.assertEqual(row[1], "COMMITTED")

    async def test_pending_trade_is_retained_for_review(self):
        connection = sqlite3.connect(self.database.path)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO EconomyTransaction "
            "(transactionId,guildId,idempotencyKey,operation,source,referenceId,actorId,reasonCode,reasonText,metadataJson,status,createdAt) "
            "VALUES ('tx','1','pending','CRYPTO_BUY','MARKET_SETTLEMENT','trade','2','crypto_buy','test','{}','PENDING','2026')"
        )
        connection.execute(
            "INSERT INTO CryptoTrade "
            "(tradeId,requestId,guildId,userId,symbol,side,quantityText,units,priceEcy,priceTickId,grossEcy,feeEcy,marketFeeEcy,treasuryFeeEcy,burnFeeEcy,costBasisDeltaEcy,realizedProfitEcy,transactionId,status,createdAt) "
            "VALUES ('trade','request','1','2','ETHR','BUY','1',100000000,10000,'phase6-initial',10000,200,100,60,40,10200,0,'tx','PENDING','2026')"
        )
        connection.commit()
        connection.close()
        result = await recover_phase6_runtime(self.database.path)
        self.assertEqual(result["review_required"], 1)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT status FROM CryptoTrade").fetchone()[0], "REVIEW_REQUIRED")
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM CryptoRecoveryReview").fetchone()[0], 1)
        connection.close()

    async def test_news_outbox_lease_and_review_transition(self):
        connection = sqlite3.connect(self.database.path)
        connection.execute(
            "INSERT INTO CryptoNewsEvent "
            "(newsId,eventKey,symbol,previousPriceEcy,currentPriceEcy,changeBps,newsType,comparisonStartedAt,occurredAt) "
            "VALUES ('news','event','ETHR',10000,12000,2000,'ALERT','2026','2026')"
        )
        connection.execute(
            "INSERT INTO CryptoNewsOutbox (outboxId,newsId,guildId,status,createdAt) "
            "VALUES ('out','news','1','PENDING','2026')"
        )
        connection.commit()
        connection.close()
        rows = await claim_crypto_news_outbox(self.database.path, lease_owner="worker")
        self.assertEqual(rows[0]["eventKey"], "event")
        updated = await finalize_crypto_news_outbox(
            self.database.path, outbox_id="out", lease_owner="worker", sent=False,
            error_code="adoption_scan_failed", review_required=True,
        )
        self.assertTrue(updated)
        connection = sqlite3.connect(self.database.path)
        self.assertEqual(connection.execute("SELECT status FROM CryptoNewsOutbox").fetchone()[0], "REVIEW_REQUIRED")
        connection.close()
