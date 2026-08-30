import sqlite3
import datetime
import uuid

def fix_db():
    conn = sqlite3.connect('w2ebot.db')
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # 1. Drop RpgProfile and let Phase 3 recreate it to get the correct CHECK constraints
    # Wait, Phase 3 SCHEMA_SQL is in phase3_schema.py. We can just execute it.
    from economy.phase3_schema import PHASE3_SCHEMA_SQL
    
    # First drop it
    try:
        conn.execute('DROP TABLE IF EXISTS RpgProfile')
    except Exception as e:
        print('Drop RpgProfile error:', e)
        
    # Then recreate using Phase 3 sql
    # PHASE3_SCHEMA_SQL contains CREATE TABLE IF NOT EXISTS for all Phase 3 tables
    conn.executescript(PHASE3_SCHEMA_SQL)
    
    # 2. Seed Phase 6 Crypto
    from economy.constants import CRYPTO_ASSETS
    
    initial_tick = "phase6-initial"
    # Check if already seeded
    if not conn.execute("SELECT 1 FROM CryptoAssetDefinition LIMIT 1").fetchone():
        conn.execute(
            "INSERT INTO CryptoMarketTick (tickId,scheduledAt,outcomeJson,status,resultJson,createdAt,committedAt) "
            "VALUES (?,?,?,'COMMITTED',?,?,?)",
            (initial_tick, now, '{"type":"INITIAL"}', '{"initialized":true}', now, now),
        )
        for symbol, (name, price, maximum_bps, level) in CRYPTO_ASSETS.items():
            conn.execute(
                "INSERT INTO CryptoAssetDefinition "
                "(symbol,name,basePriceEcy,minimumPriceEcy,maximumPriceEcy,maximumNormalChangeBps,volatilityLevel,catalogVersion,createdAt) "
                "VALUES (?,?,?,?,?,?,?,'crypto-v1.0.0',?)",
                (symbol, name, price, price * 20 // 100, price * 500 // 100, maximum_bps, level, now),
            )
            conn.execute(
                "INSERT INTO CryptoMarketState (symbol,currentPriceEcy,lastTickId,version,updatedAt) VALUES (?,?,?,0,?)",
                (symbol, price, initial_tick, now),
            )
            conn.execute(
                "INSERT INTO CryptoPriceHistory "
                "(historyId,tickId,symbol,previousPriceEcy,currentPriceEcy,movementBps,movementType,occurredAt) "
                "VALUES (?,?,?,?,?,0,'INITIAL',?)",
                (str(uuid.uuid4()), initial_tick, symbol, price, price, now),
            )
        print("Phase 6 seeded.")
        
    # 3. Seed Phase 7 Mining
    from economy.constants import MINING_RIG_CATALOG
    if not conn.execute("SELECT 1 FROM MiningRigCatalog LIMIT 1").fetchone():
        for tier, details in MINING_RIG_CATALOG.items():
            conn.execute(
                "INSERT INTO MiningRigCatalog "
                "(tier,name,description,priceEcy,dailyPowerCostEcy,baseHashRate,maxDurability,imagePath,catalogVersion,createdAt) "
                "VALUES (?,?,?,?,?,?,?,?,'mining-v1.0.0',?)",
                (tier, details["name"], details["name"], details["price"], details.get("power_cost", 0),
                 details["hash_rate"], details["durability"], details.get("image_path", ""), now),
            )
        print("Phase 7 seeded.")

    conn.commit()
    print("DB Fixed!")

if __name__ == '__main__':
    fix_db()
