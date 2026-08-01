import asyncio
import os
import sys

# Tambahkan path root ke sys.path agar bisa import modul
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from economy.treasury import system_seed

DB_PATH = 'w2ebot.db'
GUILD_ID = 790479858081071134 # Dari .env ALLOWED_SERVER_ID

async def main():
    print("Seeding Casino Bankroll...")
    res = await system_seed(
        DB_PATH, guild_id=GUILD_ID, account_code="ECY_CASINO", amount=25_000_000,
        seed_key=f"phase5-casino-initial:{GUILD_ID}", reason="Initial seed Casino Phase 5",
        idempotency_key=f"casino:seed:{GUILD_ID}",
    )
    print("Casino:", res.success if hasattr(res, 'success') else res)
    
    print("Seeding Market Reserve...")
    res2 = await system_seed(
        DB_PATH, guild_id=GUILD_ID, account_code="ECY_MARKET", amount=25_000_000,
        seed_key=f"phase6-crypto-reserve:{GUILD_ID}", reason="Seed reserve market Crypto Phase 6",
        idempotency_key=f"crypto:reserve:{GUILD_ID}",
    )
    print("Market:", res2.success if hasattr(res2, 'success') else res2)
    
    print("Seeding selesai.")

if __name__ == "__main__":
    asyncio.run(main())
