import asyncio
import os
import sys

# Tambahkan path root ke sys.path agar bisa import modul
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from economy.casino import seed_casino_bankroll
from economy.crypto import seed_market_reserve

DB_PATH = 'w2ebot.db'
GUILD_ID = 790479858081071134 # Dari .env ALLOWED_SERVER_ID

async def main():
    print("Seeding Casino Bankroll...")
    await seed_casino_bankroll(DB_PATH, guild_id=GUILD_ID, actor_id="0", active_members=250)
    
    print("Seeding Market Reserve...")
    await seed_market_reserve(DB_PATH, guild_id=GUILD_ID, amount=25_000_000, actor_id="0", staging_override=True)
    
    print("Seeding selesai.")

if __name__ == "__main__":
    asyncio.run(main())
