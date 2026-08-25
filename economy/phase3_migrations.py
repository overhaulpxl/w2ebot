"""Migrasi Phase 3 staging-only dan laporan rekonsiliasi aman."""

import hashlib
import json
import os
import uuid
from pathlib import Path


from .catalog import catalog_hash, seed_catalog, validate_catalog
from .constants import ECONOMY_PHASE3_MIGRATION_VERSION
from .database import configure_connection
from .phase3_schema import migrate_phase3_schema
from .time_policy import utc_iso


def _resolved(path):
    return Path(path).expanduser().resolve()


def assert_not_production(target_db, production_db):
    if _resolved(target_db) == _resolved(production_db):
        raise ValueError("Migrasi Phase 3 menolak database production.")


async def phase3_dry_run(db_path):
    digest = validate_catalog()
    async with _pool.acquire() as db:
        
        marker = await db.fetchrow("SELECT COUNT(*) FROM RpgProfile") as cursor:
            profile_count = int((await cursor.fetchone())[0])
        blobs = await db.fetch(
            "SELECT COUNT(*) FROM RpgProfile WHERE level=100 AND xp>0"
        ) as cursor:
            level_cap_reviews = int((await cursor.fetchone())[0])
    return {
        "migration_version": ECONOMY_PHASE3_MIGRATION_VERSION,
        "mode": "DRY_RUN", "profile_count": profile_count,
        "level_100_xp_review_count": level_cap_reviews,
        "catalog_hash": digest, "can_apply": True,
        "legacy_source_modified": False,
    }


async def apply_phase3_staging(target_db, *, production_db, seed=True):
    assert_not_production(target_db, production_db)
    await migrate_phase3_schema(target_db, rebuild_profile=True)
    async with aiosqlite.connect(target_db) as db:
        
        async with db.transaction():
        try:
            digest = await seed_catalog(db) if seed else catalog_hash()
            async with db.execute(
                "SELECT checksum,status FROM EconomySchemaMigration WHERE version=$1",
                (ECONOMY_PHASE3_MIGRATION_VERSION,),
            )
            now = utc_iso()
            if marker and tuple(marker) != (digest, "COMPLETED"):
                raise ValueError("Checksum migration Phase 3 tidak cocok.")
            if not marker:
                await db.execute(
                    "INSERT INTO EconomySchemaMigration "
                    "(version,name,checksum,status,startedAt,completedAt,detailsJson) "
                    "VALUES ($1,$2,$3,'COMPLETED',$1,$2,$3)",
                    (ECONOMY_PHASE3_MIGRATION_VERSION, "phase3-rpg", digest, now, now,
                     json.dumps({"catalogVersion": "rpg-v1.0.0"}, separators=(",", ":"))),
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    quarantine = await quarantine_legacy_assets(target_db)
    return {"migration_version": ECONOMY_PHASE3_MIGRATION_VERSION,
            "catalog_hash": digest, "target": str(_resolved(target_db)),
            "production_cutover": False, "legacy_quarantine": quarantine}


def _safe_source_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


async def quarantine_legacy_assets(target_db, *, guild_id="legacy"):
    """Simpan ownership legacy sebagai non-power LEGACY_BOUND tanpa mengubah sumber."""
    report = {"quarantined_items": 0, "quarantined_pets": 0,
              "cosmetic_achievements_copied": 0, "malformed_records": 0,
              "duplicate_sources": 0, "changed_hashes": 0, "replayed_records": 0}
    async with aiosqlite.connect(target_db) as db:
        
        has_json_store = await db.fetchrow(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='json_store'"
        ) is not None
        if has_json_store:
            existing = await db.fetchrow(
                "SELECT filename,content FROM json_store WHERE filename IN "
                "('users.json','quests.json','boss.json') ORDER BY filename"
            )
        else:
            blobs = []
        decoded = {}
        for filename, content in blobs:
            try:
                decoded[filename] = json.loads(content)
            except (TypeError, ValueError):
                report["malformed_records"] += 1
        records = []
        users = decoded.get("users.json", {})
        if isinstance(users, dict):
            for user_id, user in users.items():
                if not isinstance(user, dict):
                    report["malformed_records"] += 1
                    continue
                items = user.get("items", {})
                if isinstance(items, dict):
                    for item_id, quantity in items.items():
                        try:
                            amount = int(quantity)
                            if amount < 0:
                                raise ValueError
                        except (TypeError, ValueError, OverflowError):
                            report["malformed_records"] += 1
                            continue
                        records.append((str(user_id), "ITEM", str(item_id), amount,
                                        {"legacy_kind": "item"},
                                        {"item_id": str(item_id), "quantity": quantity}))
                elif items not in (None, []):
                    report["malformed_records"] += 1
                for field in ("pet", "pets"):
                    pet_value = user.get(field)
                    if pet_value in (None, "", [], {}):
                        continue
                    if isinstance(pet_value, dict):
                        pet_rows = sorted(pet_value.items())
                    elif isinstance(pet_value, list):
                        pet_rows = [(str(index), value) for index, value in enumerate(pet_value)]
                    else:
                        pet_rows = [(field, pet_value)]
                    for source_key, value in pet_rows:
                        records.append((str(user_id), "PET", f"{field}:{source_key}", 1,
                                        {"legacy_kind": "pet", "legacy_label": str(value)[:100]},
                                        value))
        for filename, source_type in (("quests.json", "QUEST_STATE"), ("boss.json", "BOSS_STATE")):
            value = decoded.get(filename)
            if value is not None:
                records.append(("0", source_type, filename, 1,
                                {"legacy_kind": source_type.lower()}, value))

        async with db.transaction():
        try:
            for user_id, source_type, source_key, quantity, metadata, source_value in records:
                source_hash = _safe_source_hash(source_value)
                async with db.execute(
                    "SELECT sourceHash FROM RpgLegacyAsset WHERE guildId=$1 AND userId=$2 "
                    "AND sourceType=$1 AND sourceKey=$2",
                    (str(guild_id), user_id, source_type, source_key),
                )
                if existing:
                    if existing[0] == source_hash:
                        report["replayed_records"] += 1
                    else:
                        report["changed_hashes"] += 1
                        await db.execute(
                            "UPDATE RpgLegacyAsset SET migrationStatus='REVIEW_REQUIRED' "
                            "WHERE guildId=$1 AND userId=$2 AND sourceType=$3 AND sourceKey=$4",
                            (str(guild_id), user_id, source_type, source_key),
                        )
                    continue
                await db.execute(
                    "INSERT INTO RpgLegacyAsset "
                    "(assetId,guildId,userId,sourceType,sourceKey,sourceHash,quantity,bindingStatus,"
                    "migrationStatus,metadataJson,migratedAt) "
                    "VALUES ($5,$6,$7,$8,$9,$10,$11,'LEGACY_BOUND','QUARANTINED',?,?)",
                    (str(uuid.uuid4()), str(guild_id), user_id, source_type, source_key,
                     source_hash, quantity, json.dumps(metadata, sort_keys=True), utc_iso()),
                )
                if source_type == "ITEM":
                    report["quarantined_items"] += 1
                elif source_type == "PET":
                    report["quarantined_pets"] += 1
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return report
