import sqlite3, datetime, uuid
def fix_6():
    conn = sqlite3.connect('w2ebot.db')
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    from economy.constants import CRYPTO_ASSETS
    initial_tick = "phase6-initial"
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
        conn.commit()
if __name__ == '__main__': fix_6()
