"""Adapter Discord untuk Eternal Marketplace Phase 4."""

import aiosqlite
import discord
from discord import app_commands

from core import DB_PATH, register_prefix_command_handler
from economy.amounts import AmountParseError, parse_economy_amount
from economy.constants import (
    ECONOMY_PHASE2_ENABLED, ECONOMY_PHASE3_ENABLED, ECONOMY_PHASE4_ENABLED,
    ECONOMY_V1_ENABLED,
)
from economy.marketplace import (
    browse_listings, cancel_listing, claim_returns, create_listing, create_report,
    get_listing_details, list_history, list_watchlist, marketplace_status,
    moderate_listing, price_check, reserve_purchase, resolve_report,
    set_marketplace_pause, set_marketplace_user_state, set_watch, settle_purchase,
    issue_discord_staff_authorization, issue_member_authorization,
    require_authorization,
)
from economy.phase4_recovery import recover_phase4_runtime
from economy.phase4_schema import phase4_schema_capability


def marketplace_enabled():
    return all((ECONOMY_V1_ENABLED, ECONOMY_PHASE2_ENABLED,
                ECONOMY_PHASE3_ENABLED, ECONOMY_PHASE4_ENABLED))


async def _reply(interaction, text, *, ephemeral=False):
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(text, ephemeral=ephemeral)


async def _require_marketplace(interaction):
    if not marketplace_enabled():
        await _reply(interaction, "Marketplace Phase 4 belum diaktifkan.", ephemeral=True)
        return False
    try:
        async with _pool.acquire() as db:
            if not await phase4_schema_capability(db):
                await _reply(interaction, "Marketplace Phase 4 belum dimigrasikan.", ephemeral=True)
                return False
    except aiosqlite.Error:
        await _reply(interaction, "Marketplace tidak dapat membaca database.", ephemeral=True)
        return False
    return True


async def _staff_allowed(interaction, client):
    if bool(getattr(getattr(interaction.user, "guild_permissions", None), "administrator", False)):
        return True
    try:
        return bool(await client.is_owner(interaction.user))
    except Exception:
        return False


def _request_id(interaction, prefix):
    return f"{prefix}:{getattr(interaction, 'id', 'unknown')}"


def _member_authorization(interaction, prefix="discord"):
    return issue_member_authorization(
        actor_id=interaction.user.id, guild_id=interaction.guild_id,
        request_id=_request_id(interaction, prefix),
    )


async def _staff_authorization(interaction, client, prefix="discord-staff"):
    administrator = bool(getattr(getattr(interaction.user, "guild_permissions", None), "administrator", False))
    try:
        bot_owner = bool(await client.is_owner(interaction.user))
    except Exception:
        bot_owner = False
    if not (administrator or bot_owner):
        return None
    return issue_discord_staff_authorization(
        actor_id=interaction.user.id, guild_id=interaction.guild_id,
        request_id=_request_id(interaction, prefix),
        verified_administrator=administrator, verified_bot_owner=bot_owner,
    )


async def _listing_choices(interaction, current, *, seller_only=False, include_terminal=False):
    if not marketplace_enabled() or not interaction.guild_id or not getattr(interaction, "user", None):
        return []
    try:
        async with _pool.acquire() as db:
            if not await phase4_schema_capability(db):
                return []
            clauses = ["guildId=$1"]
            params = [str(interaction.guild_id)]
            if seller_only:
                clauses.extend(("sellerId=$1", "status IN ('ACTIVE','PARTIALLY_FILLED')"))
                params.append(str(interaction.user.id))
            elif not include_terminal:
                clauses.append("status IN ('ACTIVE','PARTIALLY_FILLED')")
            rows = await db.fetch(
                "SELECT listingId,assetType,equipmentInstanceId,stackItemId,remainingQuantity "
                "FROM MarketplaceListing WHERE " + " AND ".join(clauses) + " ORDER BY createdAt DESC LIMIT 25",
                tuple(params),
            )
        needle = str(current or "").lower()
        choices = []
        for listing_id, asset_type, equipment_id, item_id, quantity in rows:
            asset = equipment_id or item_id
            name = f"{asset_type} {asset} x{quantity} ({listing_id[:8]})"
            if needle in name.lower() or needle in listing_id.lower():
                choices.append(app_commands.Choice(name=name[:100], value=listing_id))
        return choices[:25]
    except (aiosqlite.Error, OSError, ValueError):
        return []


async def _catalog_version_choices(interaction, current):
    if not marketplace_enabled() or not interaction.guild_id:
        return []
    try:
        async with _pool.acquire() as db:
            if not await phase4_schema_capability(db):
                return []
            async with db.execute(
                "SELECT DISTINCT catalogVersion FROM MarketplaceListing "
                "WHERE guildId=$1 ORDER BY catalogVersion LIMIT 25", str(interaction.guild_id),),
                versions = [row[0] for row in await cursor.fetchall()]
        needle = str(current or "").lower()
        return [
            app_commands.Choice(name=str(version)[:100], value=str(version)[:100])
            for version in versions if needle in str(version).lower()
        ][:25]
    except (aiosqlite.Error, OSError, ValueError):
        return []


def _listing_lines(rows):
    if not rows:
        return "Tidak ada listing marketplace."
    lines = []
    for row in rows:
        asset = row.get("equipmentInstanceId") or row.get("stackItemId") or "unknown"
        lines.append(
            f"`{row['listingId']}` | `{asset}` | {row['remainingQuantity']} x "
            f"{int(row['unitPriceEtm']):,} ETM | {row['status']}"
    return "\n".join(lines)


class MarketGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="rpg-market", description="Eternal Marketplace Phase 4")

    @app_commands.command(name="browse", description="Lihat listing marketplace")
    async def browse(self, interaction: discord.Interaction, page: int = 1):
        if not await _require_marketplace(interaction): return
        await interaction.response.defer(ephemeral=True)
        rows = await browse_listings(DB_PATH, interaction.guild_id, offset=(max(1, page)-1)*20)
        await _reply(interaction, _listing_lines(rows), ephemeral=True)

    @app_commands.command(name="search", description="Cari listing marketplace")
    async def search(self, interaction: discord.Interaction, query: str, page: int = 1):
        if not await _require_marketplace(interaction): return
        await interaction.response.defer(ephemeral=True)
        rows = await browse_listings(DB_PATH, interaction.guild_id, query=query, offset=(max(1, page)-1)*20)
        await _reply(interaction, _listing_lines(rows), ephemeral=True)

    @app_commands.command(name="details", description="Lihat detail listing")
    async def details(self, interaction: discord.Interaction, listing: str):
        if not await _require_marketplace(interaction): return
        row = await get_listing_details(DB_PATH, interaction.guild_id, listing)
        await _reply(interaction, _listing_lines([row] if row else []), ephemeral=True)

    @details.autocomplete("listing")
    async def details_autocomplete(self, interaction: discord.Interaction, current: str):
        return await _listing_choices(interaction, current, include_terminal=True)

    @app_commands.command(name="sell", description="Jual equipment atau stack tradeable")
    async def sell(self, interaction: discord.Interaction, item: str, quantity: int, unit_price: str):
        if not await _require_marketplace(interaction): return
        await interaction.response.defer(ephemeral=True)
        try:
            price = parse_economy_amount(unit_price)
            if item.startswith("equipment:"):
                asset_type, asset_id, catalog, binding = "EQUIPMENT", item.split(":",1)[1], None, "UNBOUND"
            elif item.startswith("stack:"):
                _, asset_id, catalog, binding = item.split("|", 3)
                asset_type = "STACK"
            else:
                raise ValueError("Pilihan inventory tidak valid.")
            result = await create_listing(
                DB_PATH, guild_id=interaction.guild_id, seller_id=interaction.user.id,
                asset_type=asset_type, asset_id=asset_id, quantity=quantity,
                unit_price_etm=price, idempotency_key=f"discord:list:{interaction.id}",
                catalog_version=catalog, binding_status=binding,
                authorization=_member_authorization(interaction, "discord-list"),
            )
            await _reply(interaction, result.message, ephemeral=True)
        except (AmountParseError, ValueError) as exc:
            await _reply(interaction, str(exc), ephemeral=True)

    @sell.autocomplete("item")
    async def sell_autocomplete(self, interaction: discord.Interaction, current: str):
        if not marketplace_enabled() or not interaction.guild_id:
            return []
        try:
            async with _pool.acquire() as db:
                if not await phase4_schema_capability(db): return []
                rows = []
                async with db.execute(
                    "SELECT equipmentInstanceId,itemId FROM RpgEquipmentInstance "
                    "WHERE guildId=$1 AND ownerId=$2 AND status='OWNED' LIMIT 25", str(interaction.guild_id), str(interaction.user.id),
                    rows.extend((f"{row[1]} ({row[0][:8]})", f"equipment:{row[0]}") for row in await cursor.fetchall())
                async with db.execute(
                    "SELECT itemId,catalogVersion,bindingStatus,quantity FROM RpgInventoryStack "
                    "WHERE guildId=$1 AND userId=$2 AND bindingStatus='UNBOUND' AND status='ACTIVE' AND quantity>0 LIMIT 25", str(interaction.guild_id), str(interaction.user.id),
                    rows.extend((f"{row[0]} x{row[3]}", f"stack:|{row[0]}|{row[1]}|{row[2]}") for row in await cursor.fetchall())
            needle = str(current).lower()
            return [app_commands.Choice(name=name[:100], value=value[:100]) for name, value in rows
                    if needle in name.lower()][:25]
        except (aiosqlite.Error, OSError):
            return []

    @app_commands.command(name="buy", description="Beli listing marketplace")
    async def buy(self, interaction: discord.Interaction, listing: str, quantity: int = 1):
        if not await _require_marketplace(interaction): return
        await interaction.response.defer(ephemeral=True)
        reserved = await reserve_purchase(
            DB_PATH, guild_id=interaction.guild_id, buyer_id=interaction.user.id,
            listing_id=listing, quantity=quantity, idempotency_key=f"discord:buy:{interaction.id}",
            authorization=_member_authorization(interaction, "discord-buy"),
        )
        if not reserved.ok:
            await _reply(interaction, reserved.message, ephemeral=True); return
        settled = await settle_purchase(DB_PATH, guild_id=interaction.guild_id, sale_id=reserved.sale_id)
        await _reply(interaction, settled.message, ephemeral=True)

    @buy.autocomplete("listing")
    async def buy_autocomplete(self, interaction: discord.Interaction, current: str):
        return await _listing_choices(interaction, current)

    @app_commands.command(name="cancel", description="Batalkan listing milik sendiri")
    async def cancel(self, interaction: discord.Interaction, listing: str):
        if not await _require_marketplace(interaction): return
        await interaction.response.defer(ephemeral=True)
        result = await cancel_listing(
            DB_PATH, guild_id=interaction.guild_id, listing_id=listing,
            authorization=_member_authorization(interaction, "discord-cancel"),
        )
        await _reply(interaction, result.message, ephemeral=True)

    @cancel.autocomplete("listing")
    async def cancel_autocomplete(self, interaction: discord.Interaction, current: str):
        return await _listing_choices(interaction, current, seller_only=True)

    @app_commands.command(name="my-listings", description="Lihat listing milik sendiri")
    async def my_listings(self, interaction: discord.Interaction, page: int = 1):
        if not await _require_marketplace(interaction): return
        rows = await browse_listings(DB_PATH, interaction.guild_id, seller_id=interaction.user.id,
                                     offset=(max(1,page)-1)*20)
        await _reply(interaction, _listing_lines(rows), ephemeral=True)

    @app_commands.command(name="history", description="Lihat history purchase atau sales")
    async def history(self, interaction: discord.Interaction, kind: str = "purchases", page: int = 1):
        if not await _require_marketplace(interaction): return
        rows = await list_history(DB_PATH, interaction.guild_id, interaction.user.id, kind=kind,
                                  offset=(max(1,page)-1)*20)
        text = "\n".join(f"`{r['saleId']}` | {r['quantity']} x {r['unitPriceEtm']:,} ETM | {r['status']}" for r in rows)
        await _reply(interaction, text or "History marketplace kosong.", ephemeral=True)

    @app_commands.command(name="price-check", description="Lihat harga sale 30 hari")
    async def price(self, interaction: discord.Interaction, item: str, catalog_version: str):
        if not await _require_marketplace(interaction): return
        data = await price_check(DB_PATH, interaction.guild_id, item_id=item, catalog_version=catalog_version)
        await _reply(interaction, f"Count {data['count']} | Min {data['minimum']} | Median {data['median']} | Max {data['maximum']}", ephemeral=True)

    @price.autocomplete("item")
    async def price_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = await _listing_choices(interaction, current, include_terminal=True)
        results = []
        for choice in choices:
            row = await get_listing_details(DB_PATH, interaction.guild_id, choice.value)
            if row:
                item_id = row.get("stackItemId")
                if not item_id:
                    try:
                        import json
                        item_id = json.loads(row["assetSnapshotJson"])["item_id"]
                    except (KeyError, TypeError, ValueError):
                        continue
                if all(existing.value != item_id for existing in results):
                    results.append(app_commands.Choice(name=str(item_id)[:100], value=str(item_id)[:100]))
        return results[:25]

    @price.autocomplete("catalog_version")
    async def price_catalog_autocomplete(self, interaction: discord.Interaction, current: str):
        return await _catalog_version_choices(interaction, current)

    @app_commands.command(name="watch", description="Tambahkan listing ke watchlist")
    async def watch(self, interaction: discord.Interaction, listing: str):
        if not await _require_marketplace(interaction): return
        result = await set_watch(DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
                                 listing_id=listing, active=True,
                                 authorization=_member_authorization(interaction, "discord-watch"))
        await _reply(interaction, result.message, ephemeral=True)

    @watch.autocomplete("listing")
    async def watch_autocomplete(self, interaction: discord.Interaction, current: str):
        return await _listing_choices(interaction, current)

    @app_commands.command(name="watchlist", description="Lihat watchlist")
    async def watchlist(self, interaction: discord.Interaction):
        if not await _require_marketplace(interaction): return
        rows = await list_watchlist(DB_PATH, interaction.guild_id, interaction.user.id)
        await _reply(interaction, _listing_lines(rows) if rows else "Watchlist kosong.", ephemeral=True)

    @app_commands.command(name="unwatch", description="Hapus listing dari watchlist")
    async def unwatch(self, interaction: discord.Interaction, listing: str):
        if not await _require_marketplace(interaction): return
        result = await set_watch(DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
                                 listing_id=listing, active=False,
                                 authorization=_member_authorization(interaction, "discord-unwatch"))
        await _reply(interaction, result.message, ephemeral=True)

    @unwatch.autocomplete("listing")
    async def unwatch_autocomplete(self, interaction: discord.Interaction, current: str):
        if not marketplace_enabled() or not interaction.guild_id:
            return []
        try:
            rows = await list_watchlist(DB_PATH, interaction.guild_id, interaction.user.id)
            needle = str(current or "").lower()
            return [app_commands.Choice(name=f"{row['listingId']} | {row['status']}"[:100], value=row["listingId"])
                    for row in rows if needle in row["listingId"].lower()][:25]
        except (ValueError, aiosqlite.Error):
            return []

    @app_commands.command(name="claim-returns", description="Periksa return marketplace")
    async def claim_returns(self, interaction: discord.Interaction):
        if not await _require_marketplace(interaction): return
        await interaction.response.defer(ephemeral=True)
        result = await claim_returns(
            DB_PATH, guild_id=interaction.guild_id, recipient_id=interaction.user.id,
            authorization=_member_authorization(interaction, "discord-claim-returns"),
        )
        await _reply(interaction, f"Return diproses: **{result['settled']}** dari **{result['scanned']}**.", ephemeral=True)

    @app_commands.command(name="report", description="Laporkan listing marketplace")
    async def report(self, interaction: discord.Interaction, listing: str, category: str, details: str = ""):
        if not await _require_marketplace(interaction): return
        result = await create_report(DB_PATH, guild_id=interaction.guild_id,
                                     reporter_id=interaction.user.id, listing_id=listing,
                                     category=category, details=details,
                                     authorization=_member_authorization(interaction, "discord-report"))
        await _reply(interaction, result.message, ephemeral=True)

    @report.autocomplete("listing")
    async def report_autocomplete(self, interaction: discord.Interaction, current: str):
        return await _listing_choices(interaction, current)

    @app_commands.command(name="status", description="Lihat status marketplace")
    async def status(self, interaction: discord.Interaction):
        if not await _require_marketplace(interaction): return
        data = await marketplace_status(DB_PATH, interaction.guild_id)
        await _reply(interaction, f"Paused: **{'Ya' if data['paused'] else 'Tidak'}** | Unresolved: **{data['unresolved']}** | Review: **{data['purchase_reviews']}**", ephemeral=True)


class MarketAdminGroup(app_commands.Group):
    def __init__(self, client):
        super().__init__(name="rpg-market-admin", description="Moderasi Eternal Marketplace")
        self.client = client

    async def interaction_check(self, interaction: discord.Interaction):
        context = await _staff_authorization(interaction, self.client)
        if not context: await _reply(interaction, "Kamu tidak punya permission marketplace staff.", ephemeral=True)
        return context is not None

    @app_commands.command(name="inspect", description="Inspect listing dan escrow")
    async def inspect(self, interaction: discord.Interaction, listing: str):
        if not await _staff_allowed(interaction, self.client) or not await _require_marketplace(interaction): return
        row = await get_listing_details(DB_PATH, interaction.guild_id, listing)
        await _reply(interaction, _listing_lines([row] if row else []), ephemeral=True)

    @app_commands.command(name="pause", description="Pause marketplace global")
    async def pause(self, interaction: discord.Interaction, reason: str):
        context = await _staff_authorization(interaction, self.client, "discord-pause")
        if not context or not await _require_marketplace(interaction): return
        await set_marketplace_pause(DB_PATH, guild_id=interaction.guild_id, paused=True,
                                    reason=reason, authorization=context)
        await _reply(interaction, "Marketplace dijeda.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume marketplace global")
    async def resume(self, interaction: discord.Interaction, reason: str):
        context = await _staff_authorization(interaction, self.client, "discord-resume")
        if not context or not await _require_marketplace(interaction): return
        await set_marketplace_pause(DB_PATH, guild_id=interaction.guild_id, paused=False,
                                    reason=reason, authorization=context)
        await _reply(interaction, "Marketplace dilanjutkan.", ephemeral=True)

    async def _moderate(self, interaction, listing, action, reason):
        context = await _staff_authorization(interaction, self.client, "discord-moderate")
        if not context or not await _require_marketplace(interaction): return
        try: result = await moderate_listing(DB_PATH, guild_id=interaction.guild_id, listing_id=listing,
                                             authorization=context, action=action, reason_code=reason)
        except ValueError as exc: await _reply(interaction, str(exc), ephemeral=True); return
        await _reply(interaction, result.message, ephemeral=True)

    @app_commands.command(name="pause-listing", description="Tahan listing")
    async def pause_listing(self, interaction: discord.Interaction, listing: str, reason: str):
        await self._moderate(interaction, listing, "PAUSE", reason)

    @app_commands.command(name="review", description="Masukkan listing ke review")
    async def review(self, interaction: discord.Interaction, listing: str, reason: str):
        await self._moderate(interaction, listing, "REVIEW", reason)

    @app_commands.command(name="cancel", description="Cancel dan return listing")
    async def cancel(self, interaction: discord.Interaction, listing: str, reason: str):
        context = await _staff_authorization(interaction, self.client, "discord-staff-cancel")
        if not context or not await _require_marketplace(interaction): return
        result = await cancel_listing(DB_PATH, guild_id=interaction.guild_id,
                                      listing_id=listing, authorization=context, reason_code=reason)
        await _reply(interaction, result.message, ephemeral=True)

    @app_commands.command(name="return", description="Audited return listing")
    async def return_asset(self, interaction: discord.Interaction, listing: str, reason: str):
        context = await _staff_authorization(interaction, self.client, "discord-staff-return")
        if not context or not await _require_marketplace(interaction): return
        result = await cancel_listing(
            DB_PATH, guild_id=interaction.guild_id, listing_id=listing,
            authorization=context, reason_code=reason,
        )
        await _reply(interaction, result.message, ephemeral=True)

    @app_commands.command(name="freeze-user", description="Bekukan user marketplace")
    async def freeze(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        context = await _staff_authorization(interaction, self.client, "discord-freeze")
        if not context or not await _require_marketplace(interaction): return
        result = await set_marketplace_user_state(DB_PATH, guild_id=interaction.guild_id, user_id=user.id,
                                                  status="FROZEN", authorization=context, reason_code=reason)
        await _reply(interaction, result.message, ephemeral=True)

    @app_commands.command(name="unfreeze-user", description="Aktifkan user marketplace")
    async def unfreeze(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        context = await _staff_authorization(interaction, self.client, "discord-unfreeze")
        if not context or not await _require_marketplace(interaction): return
        result = await set_marketplace_user_state(DB_PATH, guild_id=interaction.guild_id, user_id=user.id,
                                                  status="ACTIVE", authorization=context, reason_code=reason)
        await _reply(interaction, result.message, ephemeral=True)

    @app_commands.command(name="reports", description="Lihat report marketplace")
    async def reports(self, interaction: discord.Interaction):
        if not await _staff_allowed(interaction, self.client) or not await _require_marketplace(interaction): return
        async with _pool.acquire() as db:
            async with db.execute("SELECT reportId,listingId,reasonCategory,status FROM MarketplaceReport WHERE guildId=$1 ORDER BY createdAt DESC LIMIT 20", str(interaction.guild_id) as cursor: rows=await cursor.fetchall()
        await _reply(interaction, "\n".join(f"`{r[0]}` | `{r[1]}` | {r[2]} | {r[3]}" for r in rows) or "Tidak ada report.", ephemeral=True)

    @app_commands.command(name="resolve-report", description="Selesaikan report")
    async def resolve(self, interaction: discord.Interaction, report: str, resolution: str):
        context = await _staff_authorization(interaction, self.client, "discord-report-resolve")
        if not context or not await _require_marketplace(interaction): return
        result = await resolve_report(DB_PATH, guild_id=interaction.guild_id, report_id=report,
                                      authorization=context, resolution_code=resolution)
        await _reply(interaction, result.message, ephemeral=True)

    @app_commands.command(name="reconcile", description="Jalankan rekonsiliasi marketplace")
    async def reconcile(self, interaction: discord.Interaction):
        context = await _staff_authorization(interaction, self.client, "discord-reconcile")
        if not context or not await _require_marketplace(interaction): return
        require_authorization(context, guild_id=interaction.guild_id, staff=True)
        await interaction.response.defer(ephemeral=True)
        result = await recover_phase4_runtime(DB_PATH)
        await _reply(interaction, f"Rekonsiliasi: {result}", ephemeral=True)


def setup(tree, client):
    tree.add_command(MarketGroup())
    tree.add_command(MarketAdminGroup(client))

    async def prefix_market(message, args):
        if not marketplace_enabled():
            await message.reply("Marketplace Phase 4 belum diaktifkan."); return
        action = args[0].lower() if args else "browse"
        authorization = issue_member_authorization(
            actor_id=message.author.id, guild_id=message.guild.id,
            request_id=f"prefix-market:{message.id}",
        )
        try:
            if action == "sell":
                await message.reply("Use /rpg-market sell to select an item from your inventory."); return
            if action in ("browse", "search", "my-listings"):
                rows = await browse_listings(DB_PATH, message.guild.id,
                    query=" ".join(args[1:]) if action == "search" else None,
                    seller_id=message.author.id if action == "my-listings" else None)
                await message.reply(_listing_lines(rows)); return
            if action == "details" and len(args) >= 2:
                row = await get_listing_details(DB_PATH, message.guild.id, args[1])
                await message.reply(_listing_lines([row] if row else [])); return
            if action == "buy" and len(args) >= 2:
                quantity = int(args[2]) if len(args) >= 3 else 1
                reserved = await reserve_purchase(DB_PATH, guild_id=message.guild.id,
                    buyer_id=message.author.id, listing_id=args[1], quantity=quantity,
                    idempotency_key=f"prefix:buy:{message.id}", authorization=authorization)
                result = reserved if not reserved.ok else await settle_purchase(DB_PATH, guild_id=message.guild.id, sale_id=reserved.sale_id)
                await message.reply(result.message); return
            if action == "cancel" and len(args) >= 2:
                result = await cancel_listing(DB_PATH, guild_id=message.guild.id,
                    listing_id=args[1], authorization=authorization); await message.reply(result.message); return
            if action in ("watch", "unwatch") and len(args) >= 2:
                result = await set_watch(DB_PATH, guild_id=message.guild.id, user_id=message.author.id,
                    listing_id=args[1], active=action == "watch", authorization=authorization); await message.reply(result.message); return
            if action == "watchlist":
                rows = await list_watchlist(DB_PATH, message.guild.id, message.author.id)
                await message.reply(_listing_lines(rows) if rows else "Watchlist kosong."); return
            if action == "history":
                kind = args[1] if len(args) >= 2 else "purchases"
                rows = await list_history(DB_PATH, message.guild.id, message.author.id, kind=kind)
                await message.reply("\n".join(f"`{r['saleId']}` | {r['status']}" for r in rows) or "History marketplace kosong."); return
            if action == "price-check" and len(args) >= 3:
                data = await price_check(DB_PATH, message.guild.id, item_id=args[1], catalog_version=args[2])
                await message.reply(f"Count {data['count']} | Min {data['minimum']} | Median {data['median']} | Max {data['maximum']}"); return
            if action == "claim-returns":
                result = await claim_returns(DB_PATH, guild_id=message.guild.id, recipient_id=message.author.id,
                    authorization=authorization)
                await message.reply(f"Return diproses: {result['settled']} dari {result['scanned']}."); return
            if action == "report" and len(args) >= 3:
                result = await create_report(DB_PATH, guild_id=message.guild.id, reporter_id=message.author.id,
                    listing_id=args[1], category=args[2], details=" ".join(args[3:]), authorization=authorization)
                await message.reply(result.message); return
            if action == "status":
                data = await marketplace_status(DB_PATH, message.guild.id); await message.reply(str(data)); return
            await message.reply("Gunakan `w!rpg-market browse|search|details|buy|cancel|my-listings|history|price-check|watch|watchlist|unwatch|claim-returns|report|status`.")
        except ValueError as exc:
            await message.reply(str(exc))
        except aiosqlite.Error:
            await message.reply("Marketplace gagal membaca data. Silakan coba lagi.")

    register_prefix_command_handler("rpg-market", prefix_market)
