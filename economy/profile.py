from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta


from .activity import rolling_activity_score
from .constants import (
    RPG_DEFAULT_ATTACK,
    RPG_DEFAULT_CRIT_BPS,
    RPG_DEFAULT_DEFENSE,
    RPG_DEFAULT_MAX_HP,
    RPG_ENERGY_REGEN_SECONDS,
    RPG_MAX_CRIT_BPS,
    RPG_MAX_ENERGY,
    RPG_MAX_LEVEL,
)
from .database import configure_connection
from .time_policy import utc_datetime, utc_iso


@dataclass(frozen=True)
class ProfileSnapshot:
    guild_id: str
    user_id: str
    level: int
    xp: int
    max_hp: int
    current_hp: int
    attack: int
    defense: int
    crit_bps: int
    energy: int
    power_score: int
    activity_score_30d: int
    etm_balance: int
    ecy_balance: int
    active_weapon_instance_id: str | None
    active_armor_instance_id: str | None
    active_accessory_instance_id: str | None
    active_pet_instance_id: str | None


def validate_profile_stats(*, level, xp, max_hp, current_hp, attack, defense, crit_bps, energy):
    values = (level, xp, max_hp, current_hp, attack, defense, crit_bps, energy)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError("Stat profile wajib berupa integer.")
    if not 1 <= level <= RPG_MAX_LEVEL or xp < 0:
        raise ValueError("Level atau XP tidak valid.")
    if max_hp <= 0 or not 0 <= current_hp <= max_hp:
        raise ValueError("HP tidak valid.")
    if attack < 0 or defense < 0 or not 0 <= crit_bps <= RPG_MAX_CRIT_BPS:
        raise ValueError("Stat combat tidak valid.")
    if not 0 <= energy <= RPG_MAX_ENERGY:
        raise ValueError("Energy tidak valid.")


def calculate_power_score(*, attack, defense, max_hp, crit_bps):
    validate_profile_stats(
        level=1, xp=0, max_hp=max_hp, current_hp=max_hp,
        attack=attack, defense=defense, crit_bps=crit_bps, energy=RPG_MAX_ENERGY,
    )
    return attack * 4 + defense * 3 + max_hp // 5 + crit_bps // 100


async def ensure_profile(db_path, guild_id, user_id, *, now=None):
    timestamp = utc_iso(now)
    async with _pool.acquire() as db:
        await configure_connection(db)
        await db.execute(
            "INSERT OR IGNORE INTO RpgProfile "
            "(guildId,userId,level,xp,maxHp,currentHp,attack,defense,critBps,energy,energyUpdatedAt,version,createdAt,updatedAt) "
            "VALUES ($1,$2,1,0,$3,$4,$5,$6,$7,100,$8,0,$9,$10)", str(guild_id), str(user_id), RPG_DEFAULT_MAX_HP, RPG_DEFAULT_MAX_HP,
                RPG_DEFAULT_ATTACK, RPG_DEFAULT_DEFENSE, RPG_DEFAULT_CRIT_BPS,
                timestamp, timestamp, timestamp,
            ),
        )
        await db.execute('COMMIT')


async def materialize_energy(db_path, guild_id, user_id, *, now=None):
    current_time = utc_datetime(now)
    await ensure_profile(db_path, guild_id, user_id, now=current_time)
    async with _pool.acquire() as db:
        await configure_connection(db)
        await db.execute('BEGIN')
        try:
            row = await db.fetchrow(
                "SELECT energy,energyUpdatedAt,version FROM RpgProfile WHERE guildId=$1 AND userId=$2", str(guild_id), str(user_id),
            )
            energy, updated_raw, version = int(row[0]), row[1], int(row[2])
            if energy >= RPG_MAX_ENERGY:
                await db.execute('ROLLBACK')
                return RPG_MAX_ENERGY
            try:
                updated = utc_datetime(updated_raw)
            except (TypeError, ValueError):
                updated = current_time
            elapsed = max(0, int((current_time - updated).total_seconds())
            ticks = elapsed // RPG_ENERGY_REGEN_SECONDS
            if ticks <= 0:
                await db.execute('ROLLBACK')
                return energy
            gained = min(ticks, RPG_MAX_ENERGY - energy)
            next_energy = energy + gained
            next_updated = utc_iso(updated + timedelta(seconds=gained * RPG_ENERGY_REGEN_SECONDS))
            cursor = await db.execute(
                "UPDATE RpgProfile SET energy=$1,energyUpdatedAt=$2,version=version+1,updatedAt=$3 "
                "WHERE guildId=$1 AND userId=$2 AND version=$3", next_energy, next_updated, utc_iso(current_time), str(guild_id), str(user_id), version),
            )
            if cursor.rowcount != 1:
                await db.execute('ROLLBACK')
                return await materialize_energy(db_path, guild_id, user_id, now=current_time)
            await db.execute('COMMIT')
            return next_energy
        except Exception:
            await db.execute('ROLLBACK')
            raise


async def get_profile_snapshot(db_path, guild_id, user_id, *, now=None, create=True):
    if create:
        await ensure_profile(db_path, guild_id, user_id, now=now)
        await materialize_energy(db_path, guild_id, user_id, now=now)
    async with _pool.acquire() as db:
        await configure_connection(db)
        row = await db.fetchrow(
            "SELECT level,xp,maxHp,currentHp,attack,defense,critBps,energy,energyUpdatedAt,"
            "activeWeaponInstanceId,activeArmorInstanceId,activeAccessoryInstanceId,activePetInstanceId "
            "FROM RpgProfile WHERE guildId=$1 AND userId=$2", str(guild_id), str(user_id),
        )
        wallet = await db.fetchrow(
            "SELECT etmBalance,ecyBalance FROM EconomyWallet WHERE guildId=$1 AND userId=$2",
            (str(guild_id), str(user_id),
        )
    if not row:
        return None
    level, xp, max_hp, current_hp, attack, defense, crit_bps, energy, energy_updated_at, *instances = row
    if not create and int(energy) < RPG_MAX_ENERGY:
        try:
            elapsed = max(0, int((utc_datetime(now) - utc_datetime(energy_updated_at)).total_seconds()))
            energy = min(RPG_MAX_ENERGY, int(energy) + elapsed // RPG_ENERGY_REGEN_SECONDS)
        except (TypeError, ValueError, OverflowError):
            energy = int(energy)
    activity = await rolling_activity_score(db_path, guild_id, user_id, now=now)
    return ProfileSnapshot(
        str(guild_id), str(user_id), int(level), int(xp), int(max_hp), int(current_hp),
        int(attack), int(defense), int(crit_bps), int(energy),
        calculate_power_score(attack=int(attack), defense=int(defense), max_hp=int(max_hp), crit_bps=int(crit_bps)),
        activity, int(wallet[0]) if wallet else 0, int(wallet[1]) if wallet else 0,
        *instances,
    )
