"""Service Eternal Marketplace Phase 4 yang atomic dan fail-closed."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import uuid

import aiosqlite

from .constants import (
    ECONOMY_MAX_AMOUNT, MARKETPLACE_FEE_BPS, MARKETPLACE_MAX_PRICE_ETM,
    MARKETPLACE_MAX_UNRESOLVED_LISTINGS, MARKETPLACE_MAX_WATCHES,
    MARKETPLACE_MIN_PRICE_ETM, MARKETPLACE_REPORT_COOLDOWN_SECONDS,
    SQLITE_MAX_INTEGER,
)
from .database import configure_connection
from .controls import set_feature_paused
from .inventory import adjust_stack, inventory_quantity
from .ledger import AccountDelta, EconomyMutationError, settle_pending_transaction
from .phase4_schema import phase4_schema_capability


UNRESOLVED_LISTING_STATES = (
    "ACTIVE", "PARTIALLY_FILLED", "PAUSED", "REVIEW_REQUIRED", "CANCELLED", "EXPIRED",
)

_LISTING_ESCROW_COLUMNS = (
    "l.listingId,l.guildId,l.sellerId,l.assetType,l.equipmentInstanceId,l.stackItemId,"
    "l.catalogVersion,l.stackBindingStatus,l.originalQuantity,l.remainingQuantity,"
    "l.unitPriceEtm,l.totalListingValue,l.assetSnapshotJson,l.status,l.escrowId,"
    "l.idempotencyKey,l.version,l.createdAt,l.expiresAt,l.cancelledAt,l.completedAt,"
    "l.moderationCode,l.moderationActorId,l.moderationReasonCode,l.moderatedAt,"
    "e.authoritativeOwnerId,e.status AS escrowStatus,"
    "e.remainingQuantity AS escrowRemaining,e.version AS escrowVersion"


@dataclass(frozen=True)
class MarketplaceResult:
    ok: bool
    code: str
    message: str
    listing_id: str | None = None
    sale_id: str | None = None
    transaction_id: str | None = None
    replayed: bool = False
    data: dict | None = None


_AUTHORIZATION_PROOF = object()


@dataclass(frozen=True)
class MarketplaceAuthorizationContext:
    actor_id: str
    guild_id: str
    source: str
    verified_administrator: bool
    verified_bot_owner: bool
    verified_api_principal: bool
    verified_at: str
    request_id: str
    _proof: object = field(repr=False, compare=False, default=None)

    @property
    def is_staff(self):
        return bool(
            self.verified_administrator or self.verified_bot_owner
            or self.verified_api_principal


def issue_member_authorization(*, actor_id, guild_id, request_id):
    return MarketplaceAuthorizationContext(
        str(actor_id), str(guild_id), "DISCORD", False, False, False,
        utc_now(), str(request_id), _AUTHORIZATION_PROOF,
    )


def issue_discord_staff_authorization(*, actor_id, guild_id, request_id,
                                      verified_administrator=False,
                                      verified_bot_owner=False):
    if not (verified_administrator or verified_bot_owner):
        raise PermissionError("Otorisasi staff Discord belum terverifikasi.")
    return MarketplaceAuthorizationContext(
        str(actor_id), str(guild_id), "BOT_OWNER" if verified_bot_owner else "DISCORD",
        bool(verified_administrator), bool(verified_bot_owner), False,
        utc_now(), str(request_id), _AUTHORIZATION_PROOF,
    )


def issue_internal_api_authorization(*, actor_id, guild_id, request_id,
                                     verified_api_principal=False):
    if not verified_api_principal:
        raise PermissionError("Principal internal API belum terverifikasi.")
    return MarketplaceAuthorizationContext(
        str(actor_id), str(guild_id), "INTERNAL_API", False, False, True,
        utc_now(), str(request_id), _AUTHORIZATION_PROOF,
    )


def require_authorization(context, *, guild_id, actor_id=None, staff=False):
    if not isinstance(context, MarketplaceAuthorizationContext) or context._proof is not _AUTHORIZATION_PROOF:
        raise PermissionError("Konteks otorisasi marketplace tidak valid.")
    if context.guild_id != str(guild_id):
        raise PermissionError("Konteks otorisasi marketplace berbeda guild.")
    if actor_id is not None and context.actor_id != str(actor_id):
        raise PermissionError("Actor marketplace tidak cocok dengan konteks terverifikasi.")
    if context.source not in ("DISCORD", "BOT_OWNER", "INTERNAL_API"):
        raise PermissionError("Sumber otorisasi marketplace tidak valid.")
    if staff and not context.is_staff:
        raise PermissionError("Otorisasi staff marketplace diperlukan.")
    return context


def _authorization_source(context):
    return require_authorization(context, guild_id=context.guild_id).source


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def _checked_product(left, right, *, label):
    if isinstance(left, bool) or isinstance(right, bool) or not isinstance(left, int) or not isinstance(right, int):
        raise ValueError(f"{label} wajib berupa integer.")
    if left <= 0 or right <= 0:
        raise ValueError(f"{label} wajib lebih dari nol.")
    limit = min(ECONOMY_MAX_AMOUNT, SQLITE_MAX_INTEGER)
    if left > limit // right:
        raise ValueError(f"{label} melewati batas ekonomi.")
    value = left * right
    if value <= 0 or value > limit:
        raise ValueError(f"{label} melewati batas ekonomi.")
    return value


def _positive_integer(value, *, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} wajib berupa integer positif.")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.isdigit():
        parsed = int(value)
    else:
        raise ValueError(f"{label} wajib berupa integer positif.")
    if parsed <= 0 or parsed > SQLITE_MAX_INTEGER:
        raise ValueError(f"{label} melewati batas yang didukung.")
    return parsed


def _listing_escrow_consistent(listing):
    if int(listing["remainingQuantity"]) != int(listing["escrowRemaining"]):
        return False
    expected = {
        "ACTIVE": "HELD", "PARTIALLY_FILLED": "PARTIAL", "PAUSED": "HELD",
        "REVIEW_REQUIRED": "REVIEW_REQUIRED", "CANCELLED": "HELD", "EXPIRED": "HELD",
        "SOLD": "SOLD", "RETURNED": "RETURNED",
    }.get(listing["status"])
    if expected != listing["escrowStatus"]:
        return False
    quantity = int(listing["remainingQuantity"])
    return quantity == 0 if listing["status"] in ("SOLD", "RETURNED") else quantity > 0


def calculate_marketplace_amounts(unit_price, quantity):
    if isinstance(unit_price, bool) or not isinstance(unit_price, int):
        raise ValueError("Harga marketplace wajib berupa integer.")
    if not MARKETPLACE_MIN_PRICE_ETM <= unit_price <= MARKETPLACE_MAX_PRICE_ETM:
        raise ValueError("Harga marketplace harus 10.000 sampai 2.000.000.000 ETM.")
    gross = _checked_product(unit_price, quantity, label="Nilai marketplace")
    fee = gross * MARKETPLACE_FEE_BPS // 10_000
    proceeds = gross - fee
    treasury = fee * 80 // 100
    reserve = fee * 10 // 100
    burn = fee - treasury - reserve
    values = (gross, fee, proceeds, treasury, reserve, burn)
    if any(value < 0 or value > min(ECONOMY_MAX_AMOUNT, SQLITE_MAX_INTEGER) for value in values):
        raise ValueError("Alokasi marketplace melewati batas ekonomi.")
    if proceeds + treasury + reserve + burn != gross:
        raise ValueError("Alokasi marketplace tidak seimbang.")
    return {"gross": gross, "fee": fee, "proceeds": proceeds,
            "treasury": treasury, "reserve": reserve, "burn": burn}


def _sale_receipts(sale):
    asset_id = sale["equipmentInstanceId"] or sale["stackItemId"]
    common = {
        "sale_id": sale["saleId"], "listing_id": sale["listingId"],
        "asset_id": asset_id, "catalog_version": sale["catalogVersion"],
        "quantity": int(sale["quantity"]), "transaction_id": sale["transactionId"],
    }
    return (
        json.dumps({**common, "gross_etm": int(sale["grossEtm"])}, sort_keys=True, separators=(",", ":")),
        json.dumps({**common, "proceeds_etm": int(sale["sellerProceedsEtm"])}, sort_keys=True, separators=(",", ":")),
    )


async def require_marketplace_schema(db):
    if not await phase4_schema_capability(db):
        raise ValueError("Marketplace Phase 4 belum dimigrasikan pada database ini.")


async def _apply_quantity_mutation(
    db, *, listing, operation_type, new_quantity, new_listing_status,
    new_escrow_status, now, sale_id=None, return_id=None,
    actor_id=None, authorization_source=None, mutation_id=None,
):
    mutation_id = mutation_id or str(uuid.uuid4())
    cursor = await db.execute(
        "INSERT INTO MarketplaceQuantityMutation "
        "(mutationId,listingId,escrowId,operationType,expectedListingVersion,expectedEscrowVersion,"
        "expectedOldQuantity,newQuantity,expectedListingStatus,expectedEscrowStatus,newListingStatus,"
        "newEscrowStatus,saleId,returnId,actorId,authorizationSource,createdAt) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)", mutation_id, listing["listingId"], listing["escrowId"], operation_type,
            int(listing["version"]), int(listing["escrowVersion"]),
            int(listing["remainingQuantity"]), int(new_quantity), listing["status"],
            listing["escrowStatus"], new_listing_status, new_escrow_status,
            sale_id, return_id, str(actor_id) if actor_id is not None else None,
            str(authorization_source) if authorization_source else None, now,
        ),
    )
    if cursor.rowcount != 1:
        raise EconomyMutationError("stale", "Mutasi quantity marketplace gagal dibuat.")
    applied = await db.fetchrow(
        "SELECT applied FROM MarketplaceQuantityMutation WHERE mutationId=$1", mutation_id,),
    )
    if not applied or int(applied[0]) != 1:
        raise EconomyMutationError("stale", "Mutasi quantity marketplace tidak diterapkan.")
    return mutation_id


async def _enqueue_watch_events(db, *, guild_id, listing_id, listing_version,
                                event_type, now):
    row = await db.fetchrow(
        "SELECT userId FROM MarketplaceWatch WHERE guildId=$1 AND listingId=$2 AND active=1", str(guild_id), str(listing_id),
        users = [str(row[0]) for row in await cursor.fetchall()]
    payload = json.dumps(
        {"listing_id": str(listing_id), "listing_version": int(listing_version),
         "event_type": str(event_type)},
        sort_keys=True, separators=(",", ":"),
    )
    for user_id in users:
        event_key = f"market:{guild_id}:{listing_id}:{listing_version}:{event_type}:{user_id}"
        await db.execute(
            "INSERT OR IGNORE INTO MarketplaceNotificationOutbox "
            "(eventId,eventKey,guildId,userId,listingId,listingVersion,eventType,sanitizedPayloadJson,status,createdAt) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8, 'PENDING',$9)", str(uuid.uuid4(), event_key, str(guild_id), user_id, str(listing_id),
             int(listing_version), str(event_type), payload, now),
        )


async def record_recovery_review(db, *, guild_id, entity_type, entity_id,
                                 listing_id, error_code, now, metadata=None):
    review_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"marketplace-review:{guild_id}:{entity_type}:{entity_id}:{error_code}")
    sanitized = json.dumps(metadata or {}, sort_keys=True, separators=(",", ":")
    await db.execute(
        "INSERT INTO MarketplaceRecoveryReview "
        "(reviewId,guildId,entityType,entityId,listingId,errorCode,status,retryCount,"
        "firstDetectedAt,lastAttemptedAt,sanitizedMetadataJson) "
        "VALUES ($1,$2,$3,$4,$5,$6,'OPEN',1,$7,$8,$9) ON CONFLICT(guildId,entityType,entityId,errorCode) "
        "DO UPDATE SET retryCount=MarketplaceRecoveryReview.retryCount+1,"
        "lastAttemptedAt=excluded.lastAttemptedAt,sanitizedMetadataJson=excluded.sanitizedMetadataJson", review_id, str(guild_id), str(entity_type), str(entity_id),
         str(listing_id) if listing_id else None, str(error_code)[:100], now, now, sanitized),
    )


async def _user_state(db, guild_id, user_id):
    row = await db.fetchrow(
        "SELECT status FROM MarketplaceUserState WHERE guildId=$1 AND userId=$2", str(guild_id), str(user_id),
    )
    return row[0] if row else "ACTIVE"


async def _is_paused(db, guild_id):
    row = await db.fetchrow(
        "SELECT 1 FROM EconomyFeatureState WHERE guildId=$1 AND feature IN ('marketplace','economy') "
        "AND paused=1 LIMIT 1", str(guild_id),),
        return await cursor.fetchone() is not None


async def _catalog_item(db, catalog_version, item_id):
    async with db.execute(
        "SELECT itemType,name,rarity,slot,requiredLevel,tradeable,definitionJson "
        "FROM RpgCatalogItem WHERE catalogVersion=$1 AND itemId=$2", str(catalog_version), str(item_id),
    )
    if not row:
        raise ValueError("Definisi catalog historis asset tidak ditemukan.")
    manifest = await db.fetchrow(
        "SELECT catalogHash FROM RpgCatalogManifest WHERE catalogVersion=$1", (str(catalog_version),),
    )
    if not manifest:
        raise ValueError("Manifest catalog historis asset tidak ditemukan.")
    try:
        definition = json.loads(row[6])
    except (TypeError, ValueError) as exc:
        raise ValueError("Definisi catalog historis asset rusak.") from exc
    return {"item_type": row[0], "name": row[1], "rarity": row[2], "slot": row[3],
            "required_level": row[4], "tradeable": bool(row[5]), "definition": definition,
            "catalog_hash": manifest[0], "item_id": str(item_id), "catalog_version": str(catalog_version)}


async def _resolve_listing_asset(db, guild_id, seller_id, *, asset_type, asset_id,
                                 catalog_version=None, binding_status="UNBOUND"):
    asset_type = str(asset_type).upper()
    if asset_type == "EQUIPMENT":
        row = await db.fetchrow(
            "SELECT itemId,catalogVersion,slot,enhancementLevel,pityBps,bindingStatus,status,acquiredSource "
            "FROM RpgEquipmentInstance WHERE equipmentInstanceId=$1 AND guildId=$2 AND ownerId=$3",
            (str(asset_id), str(guild_id), str(seller_id),
        )
        if not row or row[6] != "OWNED":
            raise ValueError("Equipment tidak tersedia untuk marketplace.")
        if row[5] != "BOUND_ON_EQUIP":
            raise ValueError("Binding equipment tidak memenuhi syarat marketplace.")
        row = await db.fetchrow(
            "SELECT 1 FROM RpgProfile WHERE guildId=$1 AND userId=$2 AND $3 IN "
            "(activeWeaponInstanceId,activeArmorInstanceId,activeAccessoryInstanceId) LIMIT 1", str(guild_id), str(seller_id), str(asset_id),
        )
                        if row:
                raise ValueError("Equipment yang sedang dipakai tidak dapat dijual.")
        catalog = await _catalog_item(db, row[1], row[0])
        if not catalog["tradeable"] or catalog["rarity"] == "ETERNAL":
            raise ValueError("Equipment ini tidak tradeable.")
        snapshot = {**catalog, "enhancement_level": int(row[3]), "pity_bps": int(row[4]),
                    "binding_status": row[5], "slot": row[2], "acquired_source": row[7]}
        return {"asset_type": "EQUIPMENT", "equipment_id": str(asset_id), "stack_item_id": None,
                "catalog_version": row[1], "binding_status": None, "snapshot": snapshot,
                "available": 1}
    if asset_type != "STACK":
        raise ValueError("Jenis asset marketplace tidak valid.")
    if not catalog_version:
        raise ValueError("Versi catalog stack wajib dipilih.")
    row = await db.fetchrow(
        "SELECT quantity,status FROM RpgInventoryStack WHERE guildId=$1 AND userId=$2 AND itemId=$3 "
        "AND catalogVersion=$1 AND bindingStatus=$2", str(guild_id), str(seller_id), str(asset_id), str(catalog_version), str(binding_status),
    )
    if not row or row[1] != "ACTIVE" or int(row[0]) <= 0 or binding_status != "UNBOUND":
        raise ValueError("Stack tidak tersedia atau tidak tradeable.")
    catalog = await _catalog_item(db, catalog_version, asset_id)
    if not catalog["tradeable"]:
        raise ValueError("Item ini tidak tradeable.")
    return {"asset_type": "STACK", "equipment_id": None, "stack_item_id": str(asset_id),
            "catalog_version": str(catalog_version), "binding_status": str(binding_status),
            "snapshot": catalog, "available": int(row[0])}


async def create_listing(db_path, *, guild_id, seller_id, asset_type, asset_id,
                         quantity, unit_price_etm, idempotency_key,
                         authorization,
                         catalog_version=None, binding_status="UNBOUND", now=None,
                         failure_stage=None):
    try:
        require_authorization(authorization, guild_id=guild_id, actor_id=seller_id)
    except PermissionError as exc:
        return MarketplaceResult(False, "unauthorized", str(exc))
    try:
        quantity = _positive_integer(quantity, label="Quantity listing")
        unit_price_etm = _positive_integer(unit_price_etm, label="Harga listing")
        amounts = calculate_marketplace_amounts(unit_price_etm, quantity)
    except (TypeError, ValueError, OverflowError) as exc:
        return MarketplaceResult(False, "invalid_amount", str(exc))
    listing_id, escrow_id = str(uuid.uuid4()), str(uuid.uuid4())
    timestamp = now or utc_now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            await require_marketplace_schema(db)
            existing = await db.fetchrow(
                "SELECT listingId FROM MarketplaceListing WHERE guildId=$1 AND idempotencyKey=$2", str(guild_id), str(idempotency_key),
            )
            if existing:
                await db.rollback()
                return MarketplaceResult(True, "already_created", "Listing ini sudah dibuat.",
                                         listing_id=existing[0], replayed=True)
            if await _is_paused(db, guild_id):
                raise ValueError("Marketplace sedang dijeda.")
            if await _user_state(db, guild_id, seller_id) != "ACTIVE":
                raise ValueError("Akun marketplace tidak dapat membuat listing.")
            placeholders = ",".join("$1" for _ in UNRESOLVED_LISTING_STATES)
            existing = await db.fetchrow(
                f"SELECT COUNT(*) FROM MarketplaceListing WHERE guildId=$1 AND sellerId=$2 AND status IN ({placeholders})", str(guild_id), str(seller_id), *UNRESOLVED_LISTING_STATES),
                if int((await cursor.fetchone()[0]) >= MARKETPLACE_MAX_UNRESOLVED_LISTINGS:
                    raise ValueError("Batas listing marketplace aktif sudah tercapai.")
            asset = await _resolve_listing_asset(
                db, guild_id, seller_id, asset_type=asset_type, asset_id=asset_id,
                catalog_version=catalog_version, binding_status=binding_status,
            )
            if quantity < 1 or quantity > asset["available"] or (asset["asset_type"] == "EQUIPMENT" and quantity != 1):
                raise ValueError("Quantity listing tidak valid.")
            amounts = calculate_marketplace_amounts(unit_price_etm, quantity)
            snapshot = json.dumps(asset["snapshot"], sort_keys=True, separators=(",", ":"))
            await db.execute(
                "INSERT INTO MarketplaceListing "
                "(listingId,guildId,sellerId,assetType,equipmentInstanceId,stackItemId,catalogVersion,"
                "stackBindingStatus,originalQuantity,remainingQuantity,unitPriceEtm,totalListingValue,"
                "assetSnapshotJson,status,escrowId,idempotencyKey,createdAt) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,'ACTIVE',$14,$15,$16)", listing_id, str(guild_id), str(seller_id), asset["asset_type"], asset["equipment_id"],
                 asset["stack_item_id"], asset["catalog_version"], asset["binding_status"], quantity,
                 quantity, unit_price_etm, amounts["gross"], snapshot, escrow_id,
                 str(idempotency_key), timestamp),
            )
            if failure_stage == "after_listing_insert":
                raise RuntimeError("Injected marketplace listing failure")
            await db.execute(
                "INSERT INTO MarketplaceEscrow "
                "(escrowId,listingId,guildId,authoritativeOwnerId,assetType,equipmentInstanceId,stackItemId,"
                "catalogVersion,stackBindingStatus,originalQuantity,remainingQuantity,assetSnapshotJson,status,createdAt,updatedAt) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12, 'HELD',$13,$14)",
                (escrow_id, listing_id, str(guild_id), str(seller_id), asset["asset_type"],
                 asset["equipment_id"], asset["stack_item_id"], asset["catalog_version"],
                 asset["binding_status"], quantity, quantity, snapshot, timestamp, timestamp),
            )
            if failure_stage == "after_escrow_insert":
                raise RuntimeError("Injected marketplace escrow failure")
            if asset["asset_type"] == "EQUIPMENT":
                cursor = await db.execute(
                    "UPDATE RpgEquipmentInstance SET status='ESCROWED',updatedAt=$1 "
                    "WHERE equipmentInstanceId=$1 AND guildId=$2 AND ownerId=$3 AND status='OWNED'",
                    (timestamp, asset["equipment_id"], str(guild_id), str(seller_id),
                )
                if cursor.rowcount != 1:
                    raise ValueError("Equipment berubah saat listing diproses.")
            else:
                await adjust_stack(db, guild_id, seller_id, asset["stack_item_id"], -quantity, timestamp,
                                   catalog_version=asset["catalog_version"],
                                   binding_status=asset["binding_status"])
            if failure_stage == "before_listing_commit":
                raise RuntimeError("Injected marketplace listing commit failure")
            await db.commit()
            return MarketplaceResult(True, "listing_created", "Listing marketplace berhasil dibuat.",
                                     listing_id=listing_id)
        except (ValueError, aiosqlite.IntegrityError) as exc:
            await db.rollback()
            return MarketplaceResult(False, "listing_rejected", str(exc))
        except Exception:
            await db.rollback()
            raise


async def reserve_purchase(db_path, *, guild_id, buyer_id, listing_id, quantity,
                           idempotency_key, authorization, now=None, failure_stage=None):
    try:
        require_authorization(authorization, guild_id=guild_id, actor_id=buyer_id)
    except PermissionError as exc:
        return MarketplaceResult(False, "unauthorized", str(exc), listing_id=str(listing_id))
    timestamp = now or utc_now()
    try:
        quantity = _positive_integer(quantity, label="Quantity purchase")
    except (TypeError, ValueError, OverflowError) as exc:
        return MarketplaceResult(False, "invalid_quantity", str(exc))
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        try:
            await require_marketplace_schema(db)
            async with db.execute(
                "SELECT saleId,transactionId,status FROM MarketplaceSale WHERE guildId=$1 AND buyerId=$2 "
                "AND listingId=$1 AND status IN ('PENDING','REVIEW_REQUIRED')", str(guild_id), str(buyer_id), str(listing_id),
            )
            if existing:
                await db.rollback()
                return MarketplaceResult(existing[2] == "PENDING", existing[2].lower(),
                                         "Purchase sebelumnya masih diproses." if existing[2] == "PENDING"
                                         else "Purchase memerlukan review staff.",
                                         listing_id=str(listing_id), sale_id=existing[0],
                                         transaction_id=existing[1], replayed=True)
            if await _is_paused(db, guild_id):
                raise ValueError("Marketplace sedang dijeda.")
            if await _user_state(db, guild_id, buyer_id) != "ACTIVE":
                raise ValueError("Akun marketplace tidak dapat membeli listing.")
            db.row_factory = aiosqlite.Row
            listing = await db.fetchrow(
                "SELECT " + _LISTING_ESCROW_COLUMNS + " "
                "FROM MarketplaceListing l JOIN MarketplaceEscrow e ON e.escrowId=l.escrowId "
                "WHERE l.listingId=$1 AND l.guildId=$2", str(listing_id), str(guild_id),
            )
            if not listing or listing["status"] not in ("ACTIVE", "PARTIALLY_FILLED"):
                raise ValueError("Listing tidak tersedia.")
            if not _listing_escrow_consistent(listing):
                raise ValueError("Listing memerlukan rekonsiliasi marketplace.")
            if listing["sellerId"] == str(buyer_id):
                raise ValueError("Seller tidak dapat membeli listing sendiri.")
            if await _user_state(db, guild_id, listing["sellerId"]) != "ACTIVE":
                raise ValueError("Akun seller marketplace tidak dapat menerima purchase.")
            if quantity > int(listing["remainingQuantity"]) or quantity > int(listing["escrowRemaining"]):
                raise ValueError("Quantity listing tidak mencukupi.")
            amounts = calculate_marketplace_amounts(int(listing["unitPriceEtm"]), quantity)
            sale_id, transaction_id = str(uuid.uuid4()), str(uuid.uuid4())
            envelope = json.dumps({"sale_id": sale_id, "listing_id": str(listing_id),
                                   "escrow_id": listing["escrowId"], "quantity": quantity},
                                  sort_keys=True, separators=(",", ":"))
            await db.execute(
                "INSERT INTO EconomyTransaction "
                "(transactionId,guildId,idempotencyKey,operation,source,referenceId,actorId,reasonCode,"
                "reasonText,metadataJson,status,createdAt) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'PENDING',$11)", transaction_id, str(guild_id), str(idempotency_key), "MARKETPLACE_PURCHASE",
                 "marketplace", str(listing_id), str(buyer_id), "marketplace_purchase",
                 "marketplace purchase", envelope, timestamp),
            )
            if failure_stage == "after_transaction_header":
                raise RuntimeError("Injected marketplace purchase header failure")
            await db.execute(
                "INSERT INTO MarketplaceSale "
                "(saleId,transactionId,guildId,listingId,escrowId,sellerId,buyerId,assetType,equipmentInstanceId,"
                "stackItemId,catalogVersion,stackBindingStatus,quantity,unitPriceEtm,grossEtm,feeEtm,sellerProceedsEtm,"
                "treasuryEtm,reserveEtm,burnEtm,expectedListingVersion,expectedEscrowVersion,idempotencyKey,authorizationSource,status,createdAt) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,'PENDING',$25)",
                (sale_id, transaction_id, str(guild_id), str(listing_id), listing["escrowId"],
                 listing["sellerId"], str(buyer_id), listing["assetType"], listing["equipmentInstanceId"],
                 listing["stackItemId"], listing["catalogVersion"], listing["stackBindingStatus"], quantity,
                 listing["unitPriceEtm"], amounts["gross"], amounts["fee"], amounts["proceeds"],
                 amounts["treasury"], amounts["reserve"], amounts["burn"], listing["version"],
                 listing["escrowVersion"], str(idempotency_key), authorization.source, timestamp),
            )
            if failure_stage == "after_sale_envelope":
                raise RuntimeError("Injected marketplace sale envelope failure")
            if failure_stage == "before_reservation_commit":
                raise RuntimeError("Injected marketplace reservation commit failure")
            await db.commit()
            return MarketplaceResult(True, "purchase_reserved", "Purchase marketplace direservasi.",
                                     listing_id=str(listing_id), sale_id=sale_id,
                                     transaction_id=transaction_id)
        except (ValueError, aiosqlite.IntegrityError) as exc:
            await db.rollback()
            return MarketplaceResult(False, "purchase_rejected", str(exc)
        except Exception:
            await db.rollback()
            raise


async def settle_purchase(db_path, *, guild_id, sale_id, failure_stage=None):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        sale = await db.fetchrow(
            "SELECT saleId,transactionId,guildId,listingId,escrowId,sellerId,buyerId,assetType,"
            "equipmentInstanceId,stackItemId,catalogVersion,stackBindingStatus,quantity,unitPriceEtm,"
            "grossEtm,feeEtm,sellerProceedsEtm,treasuryEtm,reserveEtm,burnEtm,expectedListingVersion,"
            "expectedEscrowVersion,idempotencyKey,authorizationSource,status,buyerReceiptJson,sellerReceiptJson,"
            "voidReasonCode,reviewReasonCode,createdAt,completedAt "
            "FROM MarketplaceSale WHERE saleId=$1 AND guildId=$2", str(sale_id), str(guild_id),
        )
    if not sale:
        return MarketplaceResult(False, "not_found", "Reservasi purchase tidak ditemukan.")
    if sale["status"] == "COMMITTED":
        return MarketplaceResult(True, "already_committed", "Purchase ini sudah diproses.",
                                 listing_id=sale["listingId"], sale_id=sale["saleId"],
                                 transaction_id=sale["transactionId"], replayed=True,
                                 data=json.loads(sale["buyerReceiptJson"]))
    if sale["status"] != "PENDING":
        return MarketplaceResult(False, sale["status"].lower(), "Purchase tidak dapat dilanjutkan.",
                                 listing_id=sale["listingId"], sale_id=sale["saleId"])
    deltas = (
        AccountDelta("USER", str(sale["buyerId"]), "ETM", -int(sale["grossEtm"]), str(sale["buyerId"])),
        AccountDelta("USER", str(sale["sellerId"]), "ETM", int(sale["sellerProceedsEtm"]), str(sale["sellerId"])),
        AccountDelta("SYSTEM", "ETM_GENERAL", "ETM", int(sale["treasuryEtm"])),
        AccountDelta("SYSTEM", "ETM_RESERVE", "ETM", int(sale["reserveEtm"])),
        AccountDelta("SYSTEM", "ETM_BURN", "ETM", int(sale["burnEtm"])),
    )

    async def finalize(db, context):
        db.row_factory = aiosqlite.Row
        listing = await db.fetchrow(
            "SELECT " + _LISTING_ESCROW_COLUMNS + " "
            "FROM MarketplaceListing l JOIN MarketplaceEscrow e ON e.escrowId=l.escrowId "
            "WHERE l.listingId=$1 AND l.guildId=$2", sale["listingId"], str(guild_id),
        )
        if not listing or listing["status"] not in ("ACTIVE", "PARTIALLY_FILLED"):
            raise EconomyMutationError("stale", "Listing berubah sebelum settlement.")
        if not _listing_escrow_consistent(listing):
            raise EconomyMutationError("review_required", "Listing memerlukan rekonsiliasi marketplace.")
        if await _user_state(db, guild_id, sale["buyerId"]) != "ACTIVE":
            raise EconomyMutationError("buyer_restricted", "Akun buyer tidak dapat menyelesaikan purchase.")
        if await _user_state(db, guild_id, sale["sellerId"]) != "ACTIVE":
            raise EconomyMutationError("seller_restricted", "Akun seller tidak dapat menerima purchase.")
        if int(listing["version"]) != int(sale["expectedListingVersion"]) or int(listing["escrowVersion"]) != int(sale["expectedEscrowVersion"]):
            raise EconomyMutationError("stale", "Versi listing berubah sebelum settlement.")
        quantity = int(sale["quantity"])
        remaining = int(listing["remainingQuantity"]) - quantity
        if remaining < 0 or int(listing["escrowRemaining"]) < quantity:
            raise EconomyMutationError("stale", "Escrow quantity tidak mencukupi.")
        final_status = "SOLD" if remaining == 0 else "PARTIALLY_FILLED"
        escrow_status = "SOLD" if remaining == 0 else "PARTIAL"
        mutation_id = await _apply_quantity_mutation(
            db, listing=listing, operation_type="SALE", new_quantity=remaining,
            new_listing_status=final_status, new_escrow_status=escrow_status,
            now=context.now, sale_id=sale["saleId"], actor_id=sale["buyerId"],
            authorization_source=sale["authorizationSource"],
        )
        if failure_stage == "after_quantity_mutation":
            raise RuntimeError("Injected marketplace quantity mutation failure")
        buyer_stack_before = buyer_stack_after = None
        if sale["assetType"] == "EQUIPMENT":
            cursor = await db.execute(
                "UPDATE RpgEquipmentInstance SET ownerId=$1,status='OWNED',updatedAt=$2 "
                "WHERE equipmentInstanceId=$1 AND guildId=$2 AND ownerId=$3 AND status='ESCROWED'", sale["buyerId"], context.now, sale["equipmentInstanceId"], str(guild_id), sale["sellerId"]),
            )
            if cursor.rowcount != 1:
                raise EconomyMutationError("stale", "Equipment escrow tidak dapat ditransfer.")
        else:
            buyer_stack_before = await inventory_quantity(
                db, guild_id, sale["buyerId"], sale["stackItemId"],
                catalog_version=sale["catalogVersion"],
                binding_status=sale["stackBindingStatus"],
            )
            await adjust_stack(db, guild_id, sale["buyerId"], sale["stackItemId"], quantity, context.now,
                               catalog_version=sale["catalogVersion"],
                               binding_status=sale["stackBindingStatus"])
            buyer_stack_after = buyer_stack_before + quantity
        await db.execute(
            "INSERT INTO MarketplaceSettlementEvidence "
            "(saleId,transactionId,guildId,listingId,escrowId,assetType,equipmentInstanceId,stackItemId,"
            "catalogVersion,stackBindingStatus,quantity,buyerId,sellerId,buyerStackBefore,buyerStackAfter,"
            "quantityMutationId,createdAt) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)",
            (sale["saleId"], sale["transactionId"], str(guild_id), sale["listingId"], sale["escrowId"],
             sale["assetType"], sale["equipmentInstanceId"], sale["stackItemId"], sale["catalogVersion"],
             sale["stackBindingStatus"], quantity, sale["buyerId"], sale["sellerId"],
             buyer_stack_before, buyer_stack_after, mutation_id, context.now),
        )
        if final_status == "SOLD":
            await db.execute(
                "UPDATE MarketplaceListing SET completedAt=$1 WHERE listingId=$2",
                (context.now, sale["listingId"]),
            )
        buyer_receipt, seller_receipt = _sale_receipts(sale)
        cursor = await db.execute(
            "UPDATE MarketplaceSale SET status='COMMITTED',buyerReceiptJson=$1,sellerReceiptJson=$2,completedAt=$3 "
            "WHERE saleId=$1 AND status='PENDING'",
            (buyer_receipt, seller_receipt, context.now, sale["saleId"]),
        )
        if cursor.rowcount != 1:
            raise EconomyMutationError("stale", "Sale berubah saat settlement.")
        await _enqueue_watch_events(
            db, guild_id=guild_id, listing_id=sale["listingId"],
            listing_version=int(listing["version"]) + 1,
            event_type="SALE_COMMITTED", now=context.now,
        )
        return {"sale_id": sale["saleId"], "listing_id": sale["listingId"]}

    result = await settle_pending_transaction(
        db_path, transaction_id=sale["transactionId"], guild_id=guild_id, deltas=deltas,
        feature="marketplace", success_code="marketplace_purchase_committed",
        success_message="Purchase marketplace berhasil diproses.", before_commit=finalize,
    )
    return MarketplaceResult(result.ok, result.code, result.message, listing_id=sale["listingId"],
                             sale_id=sale["saleId"], transaction_id=sale["transactionId"],
                             replayed=result.replayed)


async def cancel_listing(db_path, *, guild_id, listing_id, authorization,
                         reason_code="seller_cancel", now=None):
    try:
        context = require_authorization(authorization, guild_id=guild_id)
    except PermissionError as exc:
        return MarketplaceResult(False, "unauthorized", str(exc), listing_id=str(listing_id)
    actor_id = context.actor_id
    staff = context.is_staff
    authorization_source = context.source
    timestamp = now or utc_now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            await require_marketplace_schema(db)
            listing = await db.fetchrow(
                "SELECT " + _LISTING_ESCROW_COLUMNS + " FROM MarketplaceListing l "
                "JOIN MarketplaceEscrow e ON e.escrowId=l.escrowId "
                "WHERE l.listingId=$1 AND l.guildId=$2", str(listing_id), str(guild_id),
            )
            if not listing:
                raise ValueError("Listing tidak ditemukan.")
            if not _listing_escrow_consistent(listing):
                raise ValueError("Listing memerlukan rekonsiliasi marketplace.")
            owner = listing["authoritativeOwnerId"]
            state = await _user_state(db, guild_id, owner)
            if not staff:
                if str(actor_id) != owner:
                    raise ValueError("Kamu bukan seller listing ini.")
                if listing["status"] not in ("ACTIVE", "PARTIALLY_FILLED"):
                    raise ValueError("Listing ini memerlukan staff atau recovery.")
                if state == "FROZEN":
                    raise ValueError("Akun marketplace sedang dibekukan.")
            elif listing["status"] not in ("ACTIVE", "PARTIALLY_FILLED", "PAUSED", "REVIEW_REQUIRED", "CANCELLED", "EXPIRED"):
                raise ValueError("Listing tidak dapat dikembalikan.")
            quantity = int(listing["escrowRemaining"])
            if quantity <= 0:
                raise ValueError("Tidak ada sisa escrow untuk dikembalikan.")
            return_id = str(uuid.uuid4())
            receipt = json.dumps({"return_id": return_id, "listing_id": str(listing_id),
                                  "recipient_id": owner, "quantity": quantity,
                                  "reason_code": reason_code}, sort_keys=True, separators=(",", ":"))
            await db.execute(
                "INSERT INTO MarketplaceReturn "
                "(returnId,listingId,escrowId,guildId,recipientId,assetType,equipmentInstanceId,stackItemId,"
                "catalogVersion,stackBindingStatus,quantity,reasonCode,initiatedById,authorizationSource,status,"
                "idempotencyKey,receiptJson,createdAt,completedAt) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,'COMMITTED',$15,$16,$17,$18)", return_id, str(listing_id), listing["escrowId"], str(guild_id), owner,
                 listing["assetType"], listing["equipmentInstanceId"], listing["stackItemId"],
                 listing["catalogVersion"], listing["stackBindingStatus"], quantity, str(reason_code),
                 str(actor_id), str(authorization_source), f"return:{listing['escrowId']}:{listing['escrowVersion']}",
                 receipt, timestamp, timestamp),
            )
            await _apply_quantity_mutation(
                db, listing=listing, operation_type="RETURN", new_quantity=0,
                new_listing_status="RETURNED", new_escrow_status="RETURNED",
                now=timestamp, return_id=return_id, actor_id=actor_id,
                authorization_source=authorization_source,
            )
            if listing["assetType"] == "EQUIPMENT":
                cursor = await db.execute(
                    "UPDATE RpgEquipmentInstance SET status='OWNED',updatedAt=$1 WHERE equipmentInstanceId=$2 "
                    "AND guildId=$1 AND ownerId=$2 AND status='ESCROWED'", timestamp, listing["equipmentInstanceId"], str(guild_id), owner),
                )
                if cursor.rowcount != 1:
                    raise ValueError("Equipment escrow tidak dapat dikembalikan.")
            else:
                await adjust_stack(db, guild_id, owner, listing["stackItemId"], quantity, timestamp,
                                   catalog_version=listing["catalogVersion"],
                                   binding_status=listing["stackBindingStatus"])
            await db.execute(
                "UPDATE MarketplaceListing SET cancelledAt=$1,completedAt=$2 WHERE listingId=$3",
                (timestamp, timestamp, str(listing_id),
            )
            await _enqueue_watch_events(
                db, guild_id=guild_id, listing_id=listing_id,
                listing_version=int(listing["version"]) + 1,
                event_type="LISTING_RETURNED", now=timestamp,
            )
            await db.commit()
            return MarketplaceResult(True, "listing_returned", "Sisa escrow berhasil dikembalikan.",
                                     listing_id=str(listing_id), data=json.loads(receipt)
        except (ValueError, aiosqlite.IntegrityError) as exc:
            await db.rollback()
            return MarketplaceResult(False, "cancel_rejected", str(exc), listing_id=str(listing_id))
        except Exception:
            await db.rollback()
            raise


async def browse_listings(db_path, guild_id, *, query=None, seller_id=None, limit=20, offset=0):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await require_marketplace_schema(db)
        db.row_factory = aiosqlite.Row
        clauses = ["l.guildId=$1"]
        params = [str(guild_id)]
        if seller_id:
            clauses.append("l.sellerId=$1")
            params.append(str(seller_id))
        else:
            clauses.append("l.status IN ('ACTIVE','PARTIALLY_FILLED')")
        if query:
            clauses.append("(l.stackItemId LIKE $1 OR l.assetSnapshotJson LIKE $2)")
            params.extend((f"%{str(query)[:80]}%", f"%{str(query)[:80]}%"))
        state_pairs = (
            "((l.status='ACTIVE' AND e.status='HELD') OR "
            "(l.status='PARTIALLY_FILLED' AND e.status='PARTIAL') OR "
            "(l.status='PAUSED' AND e.status='HELD') OR "
            "(l.status='REVIEW_REQUIRED' AND e.status='REVIEW_REQUIRED') OR "
            "(l.status IN ('CANCELLED','EXPIRED') AND e.status='HELD') OR "
            "(l.status='SOLD' AND e.status='SOLD') OR "
            "(l.status='RETURNED' AND e.status='RETURNED'))"
            if seller_id else
            "((l.status='ACTIVE' AND e.status='HELD') OR "
            "(l.status='PARTIALLY_FILLED' AND e.status='PARTIAL'))"
        review_filter = "" if seller_id else (
            "AND NOT EXISTS (SELECT 1 FROM MarketplaceRecoveryReview rr WHERE rr.guildId=l.guildId "
            "AND rr.listingId=l.listingId AND rr.status='OPEN') "
        params.extend((max(1, min(int(limit), 25)), max(0, int(offset))))
        row = await db.fetchrow(
            "SELECT l.listingId,l.sellerId,l.assetType,l.equipmentInstanceId,l.stackItemId,l.catalogVersion,"
            "l.stackBindingStatus,l.remainingQuantity,l.unitPriceEtm,l.status,l.createdAt "
            "FROM MarketplaceListing l JOIN MarketplaceEscrow e ON e.escrowId=l.escrowId WHERE "
            + " AND ".join(clauses)
            + " AND l.remainingQuantity=e.remainingQuantity AND " + state_pairs + " "
            + review_filter + "ORDER BY l.createdAt DESC LIMIT $1 OFFSET $2", tuple(params),
            return [dict(row) for row in await cursor.fetchall()]


async def get_listing_details(db_path, guild_id, listing_id):
    """Baca listing terminal maupun aktif tanpa membuat state baru."""
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await require_marketplace_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT l.listingId,l.sellerId,l.assetType,l.equipmentInstanceId,l.stackItemId,"
            "l.catalogVersion,l.stackBindingStatus,l.originalQuantity,l.remainingQuantity,l.unitPriceEtm,"
            "l.assetSnapshotJson,l.status,l.createdAt,l.completedAt,e.status AS escrowStatus,"
            "e.remainingQuantity AS escrowRemaining FROM MarketplaceListing l "
            "JOIN MarketplaceEscrow e ON e.escrowId=l.escrowId "
            "WHERE l.guildId=$1 AND l.listingId=$2", str(guild_id), str(listing_id),
        )
    return dict(row) if row else None


async def list_watchlist(db_path, guild_id, user_id, *, limit=50):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await require_marketplace_schema(db)
        db.row_factory = aiosqlite.Row
        existing = await db.fetchrow(
            "SELECT w.listingId,l.assetType,l.equipmentInstanceId,l.stackItemId,l.catalogVersion,"
            "l.remainingQuantity,l.unitPriceEtm,l.status,w.notificationStatus "
            "FROM MarketplaceWatch w JOIN MarketplaceListing l ON l.listingId=w.listingId "
            "WHERE w.guildId=$1 AND w.userId=$2 AND w.active=1 ORDER BY w.updatedAt DESC LIMIT $3", str(guild_id), str(user_id), max(1, min(int(limit), MARKETPLACE_MAX_WATCHES)),
            return [dict(row) for row in await cursor.fetchall()]


async def set_watch(db_path, *, guild_id, user_id, listing_id, authorization, active=True, now=None):
    try:
        require_authorization(authorization, guild_id=guild_id, actor_id=user_id)
    except PermissionError as exc:
        return MarketplaceResult(False, "unauthorized", str(exc), listing_id=str(listing_id))
    timestamp = now or utc_now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        try:
            await require_marketplace_schema(db)
            if active and await _is_paused(db, guild_id):
                raise ValueError("Marketplace sedang dijeda.")
            async with db.execute(
                "SELECT active FROM MarketplaceWatch WHERE guildId=$1 AND userId=$2 AND listingId=$3", str(guild_id), str(user_id), str(listing_id),
            )
            if existing and bool(existing[0]) == bool(active):
                await db.rollback()
                return MarketplaceResult(
                    True, "watch_replayed", "Watchlist sudah berada pada status yang diminta.",
                    replayed=True,
                )
            if active:
                existing = await db.fetchrow(
                    "SELECT COUNT(*) FROM MarketplaceWatch WHERE guildId=$1 AND userId=$2 AND active=1", str(guild_id), str(user_id),
                    if int((await cursor.fetchone())[0]) >= MARKETPLACE_MAX_WATCHES:
                        await db.rollback()
                        return MarketplaceResult(
                            False, "watch_limit", "Batas watchlist sudah tercapai."
            await db.execute(
                "INSERT INTO MarketplaceWatch (guildId,userId,listingId,active,createdAt,removedAt,updatedAt) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT(guildId,userId,listingId) DO UPDATE SET "
                "active=excluded.active,removedAt=excluded.removedAt,updatedAt=excluded.updatedAt", str(guild_id), str(user_id), str(listing_id), int(bool(active), timestamp,
                 None if active else timestamp, timestamp),
            )
            await db.commit()
            return MarketplaceResult(True, "watch_updated", "Watchlist berhasil diperbarui.")
        except (ValueError, aiosqlite.IntegrityError) as exc:
            await db.rollback()
            return MarketplaceResult(False, "watch_rejected", str(exc))


async def create_report(db_path, *, guild_id, reporter_id, listing_id, category, authorization,
                        details="", now=None):
    try:
        require_authorization(authorization, guild_id=guild_id, actor_id=reporter_id)
    except PermissionError as exc:
        return MarketplaceResult(False, "unauthorized", str(exc), listing_id=str(listing_id))
    timestamp = now or utc_now()
    cutoff = (datetime.fromisoformat(timestamp) - timedelta(seconds=MARKETPLACE_REPORT_COOLDOWN_SECONDS)).isoformat()
    clean = " ".join(str(details or "").replace("\r", " ").replace("\n", " ").split())[:500]
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        try:
            await require_marketplace_schema(db)
            if await _is_paused(db, guild_id):
                raise ValueError("Marketplace sedang dijeda.")
            async with db.execute(
                "SELECT reportId,status FROM MarketplaceReport WHERE guildId=$1 AND reporterId=$2 "
                "AND listingId=$1 AND status IN ('OPEN','IN_REVIEW') LIMIT 1", str(guild_id), str(reporter_id), str(listing_id),
            )
            if existing:
                await db.rollback()
                return MarketplaceResult(
                    True, "report_existing", "Report marketplace yang sama masih diproses.",
                    listing_id=str(listing_id), replayed=True,
                    data={"report_id": existing[0], "status": existing[1]},
                )
            existing = await db.fetchrow(
                "SELECT 1 FROM MarketplaceReport WHERE guildId=$1 AND reporterId=$2 AND listingId=$3 "
                "AND status IN ('RESOLVED','DISMISSED') AND createdAt>=$1 LIMIT 1", str(guild_id), str(reporter_id), str(listing_id), cutoff),
            )
                        if row:
                    raise ValueError("Report untuk listing ini masih dalam cooldown.")
            report_id = str(uuid.uuid4()
            await db.execute(
                "INSERT INTO MarketplaceReport "
                "(reportId,guildId,listingId,reporterId,reasonCategory,sanitizedDetails,status,createdAt) "
                "VALUES ($1,$2,$3,$4,$5,$6,'OPEN',$7)", report_id, str(guild_id), str(listing_id), str(reporter_id), str(category)[:50], clean, timestamp),
            )
            await db.commit()
            return MarketplaceResult(True, "report_created", "Report marketplace berhasil dikirim.", data={"report_id": report_id})
        except aiosqlite.IntegrityError:
            await db.rollback()
            async with aiosqlite.connect(db_path) as lookup:
                async with lookup.execute(
                    "SELECT reportId,status FROM MarketplaceReport WHERE guildId=$1 AND reporterId=$2 "
                    "AND listingId=$1 AND status IN ('OPEN','IN_REVIEW')",
                    (str(guild_id), str(reporter_id), str(listing_id),
                )
            if existing:
                return MarketplaceResult(
                    True, "report_existing", "Report marketplace yang sama masih diproses.",
                    listing_id=str(listing_id), replayed=True,
                    data={"report_id": existing[0], "status": existing[1]},
                )
            return MarketplaceResult(False, "report_rejected", "Report marketplace gagal disimpan.")
        except ValueError as exc:
            await db.rollback()
            return MarketplaceResult(False, "report_rejected", str(exc))


async def marketplace_status(db_path, guild_id):
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await require_marketplace_schema(db)
        paused = await _is_paused(db, guild_id)
        placeholders = ",".join("$1" for _ in UNRESOLVED_LISTING_STATES)
        version_row = await db.fetchrow(
            f"SELECT COUNT(*) FROM MarketplaceListing WHERE guildId=$1 AND status IN ({placeholders})", str(guild_id), *UNRESOLVED_LISTING_STATES),
            unresolved = int((await cursor.fetchone()[0])
        async with db.execute(
            "SELECT COUNT(*) FROM MarketplaceSale WHERE guildId=$1 AND status='REVIEW_REQUIRED'", str(guild_id),),
            reviews = int((await cursor.fetchone()[0])
    return {"paused": paused, "unresolved": unresolved, "purchase_reviews": reviews}


async def set_marketplace_pause(db_path, *, guild_id, paused, reason, authorization):
    context = require_authorization(authorization, guild_id=guild_id, staff=True)
    await set_feature_paused(
        db_path, guild_id=guild_id, feature="marketplace", paused=bool(paused),
        actor_id=context.actor_id, reason=reason,
    )
    return MarketplaceResult(
        True, "marketplace_paused" if paused else "marketplace_resumed",
        "Marketplace dijeda." if paused else "Marketplace dilanjutkan.",
    )


async def list_history(db_path, guild_id, user_id, *, kind="purchases", limit=20, offset=0):
    column = "buyerId" if str(kind).lower() != "sales" else "sellerId"
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await require_marketplace_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT saleId,listingId,assetType,equipmentInstanceId,stackItemId,catalogVersion,quantity,"
            f"unitPriceEtm,grossEtm,sellerProceedsEtm,status,completedAt FROM MarketplaceSale "
            f"WHERE guildId=$1 AND {column}=$2 ORDER BY createdAt DESC LIMIT $3 OFFSET $4", str(guild_id), str(user_id), max(1, min(int(limit), 25), max(0, int(offset))),
            return [dict(row) for row in await cursor.fetchall()]


async def price_check(db_path, guild_id, *, item_id, catalog_version, days=30):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await require_marketplace_schema(db)
        async with db.execute(
            "SELECT s.unitPriceEtm FROM MarketplaceSale s "
            "JOIN MarketplaceListing l ON l.listingId=s.listingId "
            "WHERE s.guildId=$1 AND s.status='COMMITTED' AND s.catalogVersion=$2 "
            "AND (s.stackItemId=$1 OR json_extract(l.assetSnapshotJson,'$.item_id')=$2) "
            "AND s.completedAt>=$1 ORDER BY s.unitPriceEtm", str(guild_id), str(catalog_version), str(item_id), str(item_id), cutoff),
            prices = [int(row[0]) for row in await cursor.fetchall()]
    if not prices:
        return {"count": 0, "minimum": None, "median": None, "maximum": None}
    middle = len(prices) // 2
    median = prices[middle] if len(prices) % 2 else (prices[middle - 1] + prices[middle]) // 2
    return {"count": len(prices), "minimum": prices[0], "median": median, "maximum": prices[-1]}


async def set_marketplace_user_state(db_path, *, guild_id, user_id, status, authorization,
                                     reason_code, expected_version=None, now=None):
    context = require_authorization(authorization, guild_id=guild_id, staff=True)
    actor_id = context.actor_id
    authorization_source = context.source
    status = str(status).upper()
    if status not in ("ACTIVE", "RESTRICTED", "FROZEN"):
        raise ValueError("Status user marketplace tidak valid.")
    timestamp = now or utc_now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await require_marketplace_schema(db)
        if expected_version is not None:
            async with db.execute(
                "SELECT version FROM MarketplaceUserState WHERE guildId=$1 AND userId=$2",
                (str(guild_id), str(user_id),
            )
            actual = int(version_row[0]) if version_row else None
            if actual != int(expected_version):
                raise ValueError("Versi state user marketplace sudah berubah.")
        await db.execute(
            "INSERT INTO MarketplaceUserState "
            "(guildId,userId,status,reasonCode,staffActorId,authorizationSource,version,createdAt,updatedAt) "
            "VALUES ($1,$2,$3,$4,$5,$6,0,$7,$8) ON CONFLICT(guildId,userId) DO UPDATE SET "
            "status=excluded.status,reasonCode=excluded.reasonCode,staffActorId=excluded.staffActorId,"
            "authorizationSource=excluded.authorizationSource,version=MarketplaceUserState.version+1,"
            "updatedAt=excluded.updatedAt", str(guild_id), str(user_id), status, str(reason_code)[:100], str(actor_id),
             str(authorization_source), timestamp, timestamp),
        )
        await db.commit()
    return MarketplaceResult(True, "user_state_updated", "Status user marketplace diperbarui.")


async def moderate_listing(db_path, *, guild_id, listing_id, authorization, action,
                           reason_code, now=None):
    context = require_authorization(authorization, guild_id=guild_id, staff=True)
    actor_id = context.actor_id
    action = str(action).upper()
    target = {"PAUSE": "PAUSED", "REVIEW": "REVIEW_REQUIRED", "RESUME": None}.get(action)
    if action not in ("PAUSE", "REVIEW", "RESUME"):
        raise ValueError("Aksi moderasi tidak valid.")
    timestamp = now or utc_now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            await require_marketplace_schema(db)
            row = await db.fetchrow(
                "SELECT " + _LISTING_ESCROW_COLUMNS + " FROM MarketplaceListing l "
                "JOIN MarketplaceEscrow e ON e.escrowId=l.escrowId "
                "WHERE l.listingId=$1 AND l.guildId=$2", str(listing_id), str(guild_id),
            )
            if not row or row["status"] in ("SOLD", "RETURNED", "CANCELLED", "EXPIRED"):
                raise ValueError("Listing tidak dapat dimoderasi.")
            if not _listing_escrow_consistent(row):
                raise ValueError("Listing memerlukan rekonsiliasi marketplace.")
            if action == "RESUME":
                if row["status"] not in ("PAUSED", "REVIEW_REQUIRED"):
                    raise ValueError("Listing tidak sedang ditahan.")
                target = "ACTIVE" if int(row["remainingQuantity"]) == int(row["originalQuantity"]) else "PARTIALLY_FILLED"
            escrow_target = "REVIEW_REQUIRED" if target == "REVIEW_REQUIRED" else (
                "HELD" if int(row["remainingQuantity"]) == int(row["originalQuantity"]) else "PARTIAL"
            await _apply_quantity_mutation(
                db, listing=row, operation_type="MODERATION",
                new_quantity=int(row["remainingQuantity"]), new_listing_status=target,
                new_escrow_status=escrow_target, now=timestamp, actor_id=actor_id,
                authorization_source=context.source,
            )
            await db.execute(
                "UPDATE MarketplaceListing SET moderationCode=$1,moderationActorId=$2,"
                "moderationReasonCode=$1,moderatedAt=$2 WHERE listingId=$3", action, str(actor_id), str(reason_code)[:100], timestamp, str(listing_id),
            )
            await _enqueue_watch_events(
                db, guild_id=guild_id, listing_id=listing_id,
                listing_version=int(row["version"]) + 1,
                event_type=f"LISTING_{target}", now=timestamp,
            )
            await db.commit()
            return MarketplaceResult(True, "listing_moderated", "Status listing diperbarui.", listing_id=str(listing_id)
        except Exception:
            await db.rollback()
            raise


async def resolve_report(db_path, *, guild_id, report_id, authorization, resolution_code, now=None):
    context = require_authorization(authorization, guild_id=guild_id, staff=True)
    actor_id = context.actor_id
    timestamp = now or utc_now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await require_marketplace_schema(db)
        cursor = await db.execute(
            "UPDATE MarketplaceReport SET status='RESOLVED',staffActorId=$1,resolutionCode=$2,"
            "resolutionMetadataJson='{}',reviewedAt=COALESCE(reviewedAt,$1),resolvedAt=$2 "
            "WHERE reportId=$1 AND guildId=$2 AND status IN ('OPEN','IN_REVIEW')", str(actor_id), str(resolution_code)[:100], timestamp, timestamp,
             str(report_id), str(guild_id),
        )
        await db.commit()
        if cursor.rowcount != 1:
            return MarketplaceResult(False, "report_not_found", "Report tidak ditemukan atau sudah selesai.")
    return MarketplaceResult(True, "report_resolved", "Report marketplace diselesaikan.")


async def mark_purchase_review(db_path, *, guild_id, sale_id, reason_code):
    """Pertahankan identity purchase yang ambigu dan blok request pengganti."""
    clean_reason = str(reason_code or "ambiguous_state")[:100]
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            sale = await db.fetchrow(
                "SELECT s.listingId,s.status AS saleStatus," + _LISTING_ESCROW_COLUMNS + " "
                "FROM MarketplaceSale s JOIN MarketplaceListing l ON l.listingId=s.listingId "
                "JOIN MarketplaceEscrow e ON e.escrowId=s.escrowId "
                "WHERE s.guildId=$1 AND s.saleId=$2", str(guild_id), str(sale_id),
            )
            if not sale:
                raise ValueError("Purchase tidak ditemukan.")
            if sale["saleStatus"] == "COMMITTED":
                await db.rollback()
                return MarketplaceResult(True, "already_committed", "Purchase sudah diselesaikan.", sale_id=str(sale_id))
            if sale["saleStatus"] == "VOID":
                await db.rollback()
                return MarketplaceResult(False, "void", "Purchase sudah dibatalkan secara aman.", sale_id=str(sale_id))
            await db.execute(
                "UPDATE MarketplaceSale SET status='REVIEW_REQUIRED',reviewReasonCode=$1 "
                "WHERE saleId=$1 AND status IN ('PENDING','REVIEW_REQUIRED')", clean_reason, str(sale_id),
            )
            timestamp = utc_now()
            if sale["status"] not in ("SOLD", "RETURNED"):
                await _apply_quantity_mutation(
                    db, listing=sale, operation_type="RECOVERY",
                    new_quantity=int(sale["remainingQuantity"]),
                    new_listing_status="REVIEW_REQUIRED", new_escrow_status="REVIEW_REQUIRED",
                    now=timestamp, actor_id="phase4-recovery", authorization_source="INTERNAL_API",
                )
                await db.execute(
                    "UPDATE MarketplaceListing SET moderationCode='PURCHASE_RECOVERY_REVIEW',"
                    "moderationReasonCode=$1,moderatedAt=$2 WHERE listingId=$3", clean_reason, timestamp, sale["listingId"]),
                )
            await record_recovery_review(
                db, guild_id=guild_id, entity_type="SALE", entity_id=sale_id,
                listing_id=sale["listingId"], error_code=clean_reason, now=timestamp,
            )
            await db.commit()
            return MarketplaceResult(False, "review_required", "Purchase memerlukan rekonsiliasi staff.",
                                     listing_id=sale["listingId"], sale_id=str(sale_id)
        except Exception:
            await db.rollback()
            raise


async def void_purchase(db_path, *, guild_id, sale_id, reason_code="mutation_free"):
    """VOID hanya bila pasangan reservasi terbukti belum memutasi ledger atau asset."""
    timestamp = utc_now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            sale = await db.fetchrow(
                "SELECT s.saleId,s.transactionId,s.listingId,s.expectedListingVersion,"
                "s.expectedEscrowVersion,s.status,t.status AS transactionStatus "
                "FROM MarketplaceSale s "
                "JOIN EconomyTransaction t ON t.transactionId=s.transactionId "
                "WHERE s.guildId=$1 AND s.saleId=$2", str(guild_id), str(sale_id),
            )
            if not sale or sale["status"] not in ("PENDING", "REVIEW_REQUIRED") or sale["transactionStatus"] != "PENDING":
                raise ValueError("Purchase tidak dapat di-VOID.")
            state = await db.fetchrow("SELECT COUNT(*) FROM EconomyLedger WHERE transactionId=$1", sale["transactionId"]) as cursor:
                if int((await cursor.fetchone()[0]):
                    raise ValueError("Purchase memiliki ledger dan wajib direview.")
            async with db.execute(
                "SELECT l.version,e.version,l.remainingQuantity,e.remainingQuantity FROM MarketplaceListing l "
                "JOIN MarketplaceEscrow e ON e.escrowId=l.escrowId WHERE l.listingId=$1", sale["listingId"],),
            )
            if not state or int(state[0]) != int(sale["expectedListingVersion"]) or int(state[1]) != int(sale["expectedEscrowVersion"]):
                raise ValueError("State purchase ambigu dan wajib direview.")
            cursor = await db.execute(
                "UPDATE MarketplaceSale SET status='VOID',voidReasonCode=$1,completedAt=$2 "
                "WHERE saleId=$1 AND status IN ('PENDING','REVIEW_REQUIRED')",
                (str(reason_code)[:100], timestamp, str(sale_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Purchase berubah sebelum VOID.")
            cursor = await db.execute(
                "UPDATE EconomyTransaction SET status='REVERSED',metadataJson=$1,committedAt=$2 "
                "WHERE transactionId=$1 AND status='PENDING'", json.dumps({"result_code": "void", "reason_code": str(reason_code)[:100]}, separators=(",", ":"),
                 timestamp, sale["transactionId"]),
            )
            if cursor.rowcount != 1:
                raise ValueError("Header purchase berubah sebelum VOID.")
            await db.commit()
            return MarketplaceResult(True, "void", "Purchase dibatalkan tanpa mutasi ekonomi.",
                                     listing_id=sale["listingId"], sale_id=str(sale_id),
                                     transaction_id=sale["transactionId"])
        except Exception:
            await db.rollback()
            raise


async def claim_returns(db_path, *, guild_id, recipient_id, authorization, limit=20):
    """Retry return tertunda tanpa mengubah penerima authoritative escrow."""
    require_authorization(authorization, guild_id=guild_id, actor_id=recipient_id)
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await require_marketplace_schema(db)
        row = await db.fetchrow(
            "SELECT returnId,listingId FROM MarketplaceReturn WHERE guildId=$1 AND recipientId=$2 "
            "AND status IN ('PENDING','REVIEW_REQUIRED') ORDER BY createdAt LIMIT $1", str(guild_id), str(recipient_id), max(1, min(int(limit), 100)),
            pending_returns = [(row[0], row[1]) for row in await cursor.fetchall()]
    settled = 0
    for return_id, _listing_id in pending_returns:
        result = await settle_pending_return(
            db_path, guild_id=guild_id, recipient_id=recipient_id, return_id=return_id,
        )
        settled += int(result.ok)
    scanned = len(pending_returns)
    return {"scanned": scanned, "settled": settled, "remaining": scanned - settled}


async def settle_pending_return(db_path, *, guild_id, recipient_id, return_id):
    """Selesaikan envelope return yang sudah ada tanpa mengganti identity atau recipient."""
    timestamp = utc_now()
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                "SELECT r.returnId,r.listingId,r.escrowId,r.guildId,r.recipientId,r.assetType,"
                "r.equipmentInstanceId,r.stackItemId,r.catalogVersion,r.stackBindingStatus,r.quantity,"
                "r.reasonCode,r.status,r.receiptJson,e.authoritativeOwnerId,e.status AS escrowStatus,"
                "e.remainingQuantity AS escrowRemaining,e.version AS escrowVersion,"
                "l.remainingQuantity AS listingRemaining,l.status AS listingStatus,l.version AS listingVersion "
                "FROM MarketplaceReturn r JOIN MarketplaceEscrow e ON e.escrowId=r.escrowId "
                "JOIN MarketplaceListing l ON l.listingId=r.listingId WHERE r.returnId=$1 AND r.guildId=$2", str(return_id), str(guild_id),
            )
            if not row:
                raise ValueError("Return tidak ditemukan.")
            if row["status"] == "COMMITTED":
                await db.rollback()
                return MarketplaceResult(True, "return_replayed", "Return sudah diproses.",
                                         listing_id=row["listingId"], replayed=True,
                                         data=json.loads(row["receiptJson"]))
            if row["recipientId"] != row["authoritativeOwnerId"] or row["recipientId"] != str(recipient_id):
                raise ValueError("Recipient return tidak cocok dengan escrow authoritative.")
            if (int(row["escrowRemaining"]) != int(row["quantity"])
                    or int(row["listingRemaining"]) != int(row["quantity"])):
                raise ValueError("Quantity return tidak cocok dengan escrow.")
            listing_state = {
                "listingId": row["listingId"], "escrowId": row["escrowId"],
                "version": row["listingVersion"], "escrowVersion": row["escrowVersion"],
                "remainingQuantity": row["listingRemaining"], "status": row["listingStatus"],
                "escrowStatus": row["escrowStatus"], "escrowRemaining": row["escrowRemaining"],
            }
            if not _listing_escrow_consistent(listing_state):
                raise ValueError("Return memerlukan rekonsiliasi marketplace.")
            await _apply_quantity_mutation(
                db, listing=listing_state, operation_type="RETURN", new_quantity=0,
                new_listing_status="RETURNED", new_escrow_status="RETURNED",
                now=timestamp, return_id=row["returnId"], actor_id="phase4-recovery",
                authorization_source="INTERNAL_API",
            )
            if row["assetType"] == "EQUIPMENT":
                cursor = await db.execute(
                    "UPDATE RpgEquipmentInstance SET status='OWNED',updatedAt=$1 WHERE equipmentInstanceId=$2 "
                    "AND guildId=$1 AND ownerId=$2 AND status='ESCROWED'", timestamp, row["equipmentInstanceId"], str(guild_id), row["recipientId"]),
                )
                if cursor.rowcount != 1:
                    raise ValueError("Equipment return tidak dapat dipulihkan.")
            else:
                await adjust_stack(
                    db, guild_id, row["recipientId"], row["stackItemId"], int(row["quantity"]), timestamp,
                    catalog_version=row["catalogVersion"], binding_status=row["stackBindingStatus"],
                )
            await db.execute(
                "UPDATE MarketplaceListing SET cancelledAt=COALESCE(cancelledAt,$1),completedAt=$2 WHERE listingId=$3",
                (timestamp, timestamp, row["listingId"]),
            )
            receipt = json.dumps(
                {"return_id": row["returnId"], "listing_id": row["listingId"],
                 "recipient_id": row["recipientId"], "quantity": int(row["quantity"]),
                 "reason_code": row["reasonCode"]},
                sort_keys=True, separators=(",", ":"),
            )
            cursor = await db.execute(
                "UPDATE MarketplaceReturn SET status='COMMITTED',receiptJson=$1,completedAt=$2,lastAttemptedAt=$3,"
                "lastErrorCode=NULL WHERE returnId=$1 AND status IN ('PENDING','REVIEW_REQUIRED')",
                (receipt, timestamp, timestamp, row["returnId"]),
            )
            if cursor.rowcount != 1:
                raise ValueError("Return berubah saat dipulihkan.")
            await db.commit()
            return MarketplaceResult(True, "return_committed", "Return marketplace berhasil dipulihkan.",
                                     listing_id=row["listingId"], data=json.loads(receipt)
        except Exception:
            await db.rollback()
            raise


async def pending_watch_notifications(db_path, *, limit=100):
    """Read-only compatibility view over the append-only outbox."""
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        await require_marketplace_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT o.eventId,o.eventKey,o.guildId,o.userId,o.listingId,o.listingVersion,"
            "o.eventType,o.sanitizedPayloadJson,o.status,o.messageId "
            "FROM MarketplaceNotificationOutbox o JOIN MarketplaceWatch w "
            "ON w.guildId=o.guildId AND w.userId=o.userId AND w.listingId=o.listingId "
            "WHERE w.active=1 AND o.status='PENDING' ORDER BY o.createdAt LIMIT $1", max(1, min(int(limit), 500),),
            return [dict(row) for row in await cursor.fetchall()]


async def mark_watch_notification(db_path, *, guild_id, user_id, listing_id, event_key,
                                  sent, message_id=None):
    """Compatibility finalizer; event identity, not watch row, is authoritative."""
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        cursor = await db.execute(
            "UPDATE MarketplaceNotificationOutbox SET status=$1,messageId=$2,sentAt=$3,lastAttemptedAt=$4,"
            "leaseOwner=NULL,leaseExpiresAt=NULL,lastErrorCode=$1 WHERE guildId=$2 AND userId=$3 "
            "AND listingId=$1 AND eventKey=$2 AND status IN ('PENDING','SENDING')", "SENT" if sent else "PENDING", str(message_id) if message_id else None,
             utc_now() if sent else None, utc_now(), None if sent else "delivery_failed",
             str(guild_id), str(user_id), str(listing_id), str(event_key),
        )
        await db.commit()
        return cursor.rowcount == 1


async def claim_notification_events(db_path, *, lease_owner, limit=100, lease_seconds=60, now=None):
    timestamp = now or utc_now()
    expiry = (datetime.fromisoformat(timestamp) + timedelta(seconds=max(10, int(lease_seconds)))).isoformat()
    claimed = []
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            await require_marketplace_schema(db)
            async with db.execute(
                "SELECT o.eventId FROM MarketplaceNotificationOutbox o JOIN MarketplaceWatch w "
                "ON w.guildId=o.guildId AND w.userId=o.userId AND w.listingId=o.listingId "
                "WHERE w.active=1 AND (o.status='PENDING' OR (o.status='SENDING' AND o.leaseExpiresAt<$1)) "
                "ORDER BY o.createdAt LIMIT $1", timestamp, max(1, min(int(limit), 500)),
                event_ids = [row[0] for row in await cursor.fetchall()]
            for event_id in event_ids:
                cursor = await db.execute(
                    "UPDATE MarketplaceNotificationOutbox SET status='SENDING',leaseOwner=$1,leaseExpiresAt=$2,"
                    "attemptCount=attemptCount+1,lastAttemptedAt=$1,lastErrorCode=NULL "
                    "WHERE eventId=$1 AND (status='PENDING' OR (status='SENDING' AND leaseExpiresAt<$2))", str(lease_owner), expiry, timestamp, event_id, timestamp),
                )
                if cursor.rowcount == 1:
                    async with db.execute(
                        "SELECT eventId,eventKey,guildId,userId,listingId,listingVersion,eventType,"
                        "sanitizedPayloadJson,attemptCount,messageId FROM MarketplaceNotificationOutbox WHERE eventId=$1",
                        (event_id,),
                    ) as row_cursor:
                        claimed.append(dict(await row_cursor.fetchone())
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return claimed


async def finalize_notification_event(db_path, *, event_id, lease_owner, sent=False,
                                      message_id=None, error_code=None, ambiguous=False, now=None):
    timestamp = now or utc_now()
    status = "SENT" if sent else ("REVIEW_REQUIRED" if ambiguous else "PENDING")
    async with aiosqlite.connect(db_path) as db:
        await configure_connection(db)
        cursor = await db.execute(
            "UPDATE MarketplaceNotificationOutbox SET status=$1,messageId=COALESCE($2,messageId),"
            "sentAt=CASE WHEN $1='SENT' THEN $2 ELSE sentAt END,leaseOwner=NULL,leaseExpiresAt=NULL,"
            "lastAttemptedAt=$1,lastErrorCode=$2 WHERE eventId=$3 AND status='SENDING' AND leaseOwner=$4", status, str(message_id) if message_id else None, status, timestamp, timestamp,
             str(error_code)[:100] if error_code else None, str(event_id), str(lease_owner),
        )
        await db.commit()
        return cursor.rowcount == 1
