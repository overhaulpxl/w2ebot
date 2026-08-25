"""Global Crypto V1 market, integer pricing, news, and deterministic simulation."""

from datetime import datetime, timedelta, timezone
import json
import secrets
import uuid


from .constants import (
    CRYPTO_ASSETS, CRYPTO_MAJOR_EVENT_PER_100000, CRYPTO_MEAN_REVERSION_BPS,
    CRYPTO_NEWS_COOLDOWN_SECONDS, CRYPTO_NORMAL_EVENT_PER_100000,
)
from .database import configure_connection
from .phase6_schema import phase6_capability


def utc_now(value=None):
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat()


def minute_key(value=None):
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()


class SecureRng:
    @staticmethod
    def randbelow(upper):
        return secrets.randbelow(upper)


class DeterministicRng:
    def __init__(self, seed):
        import random
        self._random = random.Random(seed)

    def randbelow(self, upper):
        return self._random.randrange(upper)


def _signed_divide(value, divisor):
    return value // divisor if value >= 0 else -((-value) // divisor)


def _clamp(value, lower, upper):
    return max(lower, min(upper, value))


def plan_tick(states, rng=None):
    """Return a complete immutable plan for all seven global prices."""
    rng = rng or SecureRng()
    symbols = tuple(CRYPTO_ASSETS)
    event_draw = rng.randbelow(100_000)
    event_type = None
    if event_draw < CRYPTO_MAJOR_EVENT_PER_100000:
        event_type = "MAJOR_EVENT"
    elif event_draw < CRYPTO_MAJOR_EVENT_PER_100000 + CRYPTO_NORMAL_EVENT_PER_100000:
        event_type = "NORMAL_EVENT"
    selected = symbols[rng.randbelow(len(symbols))] if event_type else None
    direction = 1 if event_type and rng.randbelow(2) else -1
    if event_type == "MAJOR_EVENT":
        event_bps = 2_500 + rng.randbelow(501)
    elif event_type == "NORMAL_EVENT":
        event_bps = 800 + rng.randbelow(1_201)
    else:
        event_bps = 0
    assets = {}
    for symbol in symbols:
        name, base, maximum_bps, _ = CRYPTO_ASSETS[symbol]
        current = int(states[symbol]["currentPriceEcy"])
        minimum, maximum = base * 20 // 100, base * 500 // 100
        if symbol == selected:
            raw_delta = _signed_divide(current * event_bps * direction, 10_000)
            new_price = _clamp(current + raw_delta, minimum, maximum)
            movement_type = event_type
        else:
            sampled_bps = rng.randbelow(maximum_bps * 2 + 1) - maximum_bps
            random_delta = _signed_divide(current * sampled_bps, 10_000)
            reversion = _signed_divide((base - current) * CRYPTO_MEAN_REVERSION_BPS, 10_000)
            limit = max(1, current * maximum_bps // 10_000)
            delta = _clamp(random_delta + reversion, -limit, limit)
            new_price = _clamp(current + delta, minimum, maximum)
            movement_type = "NORMAL"
        actual_bps = _signed_divide((new_price - current) * 10_000, current)
        assets[symbol] = {
            "name": name, "previousPriceEcy": current, "currentPriceEcy": new_price,
            "movementBps": actual_bps, "movementType": movement_type,
            "expectedVersion": int(states[symbol].get("version", 0)),
        }
    return {"eventType": event_type, "eventSymbol": selected,
            "eventDirection": direction if event_type else None,
            "eventMagnitudeBps": event_bps, "assets": assets}


async def _states(db):
    existing = await db.fetchrow(
        "SELECT symbol,currentPriceEcy,lastTickId,version,updatedAt FROM CryptoMarketState ORDER BY symbol"
    ) as cursor:
        rows = await cursor.fetchall()
    return {row[0]: {"currentPriceEcy": int(row[1]), "lastTickId": row[2],
                     "version": int(row[3]), "updatedAt": row[4]} for row in rows}


async def reserve_market_tick(db_path, *, scheduled_at=None, rng=None):
    scheduled = minute_key(scheduled_at)
    async with _pool.acquire() as db:
        
        async with db.transaction():
        if not await phase6_capability(db):
            await db.rollback()
            raise RuntimeError("Schema Crypto Phase 6 belum siap.")
        rows = await db.fetch(
            "SELECT tickId,outcomeJson,status FROM CryptoMarketTick WHERE scheduledAt=$1", (scheduled,),
        )
        if existing:
            await db.rollback()
            return existing[0], json.loads(existing[1]), existing[2], True
        states = await _states(db)
        if set(states) != set(CRYPTO_ASSETS):
            await db.rollback()
            raise RuntimeError("Global market state tidak lengkap.")
        outcome = plan_tick(states, rng=rng)
        tick_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO CryptoMarketTick (tickId,scheduledAt,outcomeJson,status,createdAt) VALUES ($1,$2,$3,'RESERVED',$4)",
            (tick_id, scheduled, json.dumps(outcome, sort_keys=True, separators=(",", ":")), utc_now()),
        )
        await db.commit()
        return tick_id, outcome, "RESERVED", False


async def _create_news(db, *, tick_id, symbol, current_price, occurred_at):
    cutoff = (datetime.fromisoformat(occurred_at) - timedelta(minutes=30)).isoformat()
    previous = await db.fetchrow(
        "SELECT currentPriceEcy,occurredAt FROM CryptoPriceHistory WHERE symbol=$1 AND occurredAt<=$2 "
        "ORDER BY occurredAt DESC LIMIT 1", (symbol, cutoff),
    )
    if not previous or int(previous[0]) <= 0:
        return None
    change_bps = _signed_divide((current_price - int(previous[0])) * 10_000, int(previous[0]))
    absolute = abs(change_bps)
    if absolute < 1_000:
        return None
    row = await db.fetchrow(
        "SELECT 1 FROM CryptoNewsEvent WHERE symbol=$1 AND occurredAt>$2 LIMIT 1", (symbol, cutoff),
    ) as cursor:
        if await cursor.fetchone():
            return None
    news_type = "ALERT" if absolute < 2_500 else ("SURGE" if change_bps > 0 else "CRASH")
    news_id = str(uuid.uuid4())
    event_key = f"crypto-news:{symbol}:{tick_id}"
    await db.execute(
        "INSERT INTO CryptoNewsEvent "
        "(newsId,eventKey,symbol,previousPriceEcy,currentPriceEcy,changeBps,newsType,comparisonStartedAt,occurredAt) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        (news_id, event_key, symbol, int(previous[0]), current_price, change_bps,
         news_type, previous[1], occurred_at),
    )
    async with db.execute(
        "SELECT DISTINCT guildId FROM EconomySeedMarker WHERE accountCode='ECY_MARKET'"
    ) as cursor:
        guilds = [str(row[0]) for row in await cursor.fetchall()]
    for guild_id in guilds:
        await db.execute(
            "INSERT INTO CryptoNewsOutbox (outboxId,newsId,guildId,status,createdAt) VALUES ($1, $2, $3, 'PENDING', $4)",
            (str(uuid.uuid4()), news_id, guild_id, occurred_at),
        )
    return news_id


async def commit_market_tick(db_path, tick_id):
    async with _pool.acquire() as db:
        
        async with db.transaction():
        async with db.execute(
            "SELECT outcomeJson,status,scheduledAt,resultJson FROM CryptoMarketTick WHERE tickId=$1", (str(tick_id),),
        )
        if not row:
            await db.rollback()
            raise ValueError("Tick Crypto tidak ditemukan.")
        if row[1] == "COMMITTED":
            await db.rollback()
            return json.loads(row[3]), True
        if row[1] not in ("RESERVED", "REVIEW_REQUIRED"):
            await db.rollback()
            raise RuntimeError("Status tick Crypto tidak dapat diselesaikan.")
        outcome = json.loads(row[0])
        occurred_at = row[2]
        news_ids = []
        for symbol, planned in sorted(outcome["assets"].items()):
            cursor = await db.execute(
                "UPDATE CryptoMarketState SET currentPriceEcy=$1,lastTickId=$2,version=version+1,updatedAt=$3 "
                "WHERE symbol=$1 AND currentPriceEcy=$2 AND version=$3",
                (planned["currentPriceEcy"], str(tick_id), occurred_at, symbol,
                 planned["previousPriceEcy"], planned["expectedVersion"]),
            )
            if cursor.rowcount != 1:
                await db.rollback()
                raise RuntimeError("Global market berubah saat tick diproses.")
            await db.execute(
                "INSERT INTO CryptoPriceHistory "
                "(historyId,tickId,symbol,previousPriceEcy,currentPriceEcy,movementBps,movementType,occurredAt) "
                "VALUES ($4,$5,$6,$7,$8,$9,$10,$11)",
                (str(uuid.uuid4()), str(tick_id), symbol, planned["previousPriceEcy"],
                 planned["currentPriceEcy"], planned["movementBps"], planned["movementType"], occurred_at),
            )
            news_id = await _create_news(
                db, tick_id=str(tick_id), symbol=symbol,
                current_price=int(planned["currentPriceEcy"]), occurred_at=occurred_at,
            )
            if news_id:
                news_ids.append(news_id)
        result = {"tickId": str(tick_id), "scheduledAt": occurred_at,
                  "eventType": outcome.get("eventType"), "eventSymbol": outcome.get("eventSymbol"),
                  "newsIds": news_ids}
        result_json = json.dumps(result, sort_keys=True, separators=(",", ":"))
        cursor = await db.execute(
            "UPDATE CryptoMarketTick SET status='COMMITTED',resultJson=$1,committedAt=$2 "
            "WHERE tickId=? AND status IN ('RESERVED','REVIEW_REQUIRED')",
            (result_json, utc_now(), str(tick_id)),
        )
        if cursor.rowcount != 1:
            await db.rollback()
            raise RuntimeError("Tick Crypto gagal commit.")
        await db.commit()
        return result, False


async def run_market_tick(db_path, *, scheduled_at=None, rng=None):
    tick_id, _, status, replayed = await reserve_market_tick(
        db_path, scheduled_at=scheduled_at, rng=rng,
    )
    if status == "COMMITTED":
        async with _pool.acquire() as db:
            async with db.execute("SELECT resultJson FROM CryptoMarketTick WHERE tickId=$1", tick_id) as cursor:
                result = json.loads((await cursor.fetchone())[0])
        return result, True
    result, committed_replay = await commit_market_tick(db_path, tick_id)
    return result, replayed or committed_replay


async def market_snapshot(db_path, *, history_limit=10):
    async with _pool.acquire() as db:
        
        if not await phase6_capability(db):
            return {"available": False, "coins": {}}
        async with db.execute(
            "SELECT a.symbol,a.name,s.currentPriceEcy,a.basePriceEcy,a.maximumNormalChangeBps,a.volatilityLevel,s.updatedAt "
            "FROM CryptoAssetDefinition a JOIN CryptoMarketState s ON s.symbol=a.symbol ORDER BY a.symbol"
        )
        coins = {}
        for symbol, name, price, base, bps, level, updated in rows:
            async with db.execute(
                "SELECT currentPriceEcy FROM CryptoPriceHistory WHERE symbol=$1 ORDER BY occurredAt DESC LIMIT $2",
                (symbol, int(history_limit)),
            ) as cursor:
                history = [int(row[0]) for row in reversed(await cursor.fetchall())]
            coins[symbol] = {"name": name, "price": int(price), "basePriceEcy": int(base),
                             "maximumNormalChangeBps": int(bps), "volatilityLevel": level,
                             "history": history, "updatedAt": updated}
        return {"available": True, "currency": "ECY", "global": True,
                "last_updated": max((value["updatedAt"] for value in coins.values()), default=None),
                "coins": coins}
