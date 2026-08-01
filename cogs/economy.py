import asyncio
import discord
import logging
import uuid
import json
import aiosqlite
from discord import app_commands

from core import ALLOWED_SERVER_ID, DB_PATH, get_announce_channel, register_ready_startup_task
from economy.amounts import AmountParseError, format_economy_amount, parse_economy_amount
from economy.constants import (
    CURRENCIES,
    ECONOMY_CONFIRM_TIMEOUT_SECONDS,
    ECONOMY_PHASE2_ENABLED,
    ECONOMY_PHASE3_ENABLED,
    ECONOMY_PHASE4_ENABLED,
    ECONOMY_PHASE5_ENABLED,
    ECONOMY_PHASE6_ENABLED,
    ECONOMY_PHASE7_ENABLED,
    ECONOMY_PHASE8_ENABLED,
    ECONOMY_V1_ENABLED,
    EMERGENCY_FEATURES,
    configured_large_threshold,
)
from economy.controls import (
    bootstrap_whitelist,
    feature_states,
    is_whitelisted,
    list_whitelist,
    set_feature_paused,
    set_whitelist,
)
from economy.treasury import get_supply_report, treasury_grant
from economy.wallets import admin_mint, admin_remove
from economy.recovery import recover_phase2_runtime
from economy.phase3_recovery import recover_phase3_operations
from economy.phase4_recovery import recover_phase4_runtime
from economy.marketplace import claim_notification_events, finalize_notification_event
from economy.casino import (
    adjust_casino_bankroll, casino_status, distribute_casino_excess,
    is_casino_authorized, list_casino_authorizations, seed_casino_bankroll,
    set_casino_authorization, set_casino_paused, record_owner_recovery_override,
    resolve_review_session,
)
from economy.phase5_recovery import (
    claim_casino_outbox, finalize_casino_outbox, recover_phase5_runtime,
)
from economy.crypto import (
    crypto_readiness, is_crypto_authorized, list_crypto_authorizations,
    seed_market_reserve, set_crypto_authorization,
)
from economy.crypto_market import run_market_tick
from economy.phase6_recovery import (
    claim_crypto_news_outbox, finalize_crypto_news_outbox, recover_phase6_runtime,
)
from economy.mining import (
    is_mining_authorized, list_mining_authorizations, mining_readiness,
    set_mining_authorization,
)
from economy.phase7_recovery import recover_phase7
from economy.constants import MINING_RIG_CATALOG
from economy.database import configure_connection
from economy.phase9b_schema import phase9b_capability
from economy.notification_delivery import (
    claim_deliveries, finalize_delivery, reserve_crypto_news_outbox,
)


logger = logging.getLogger(__name__)


STAGING_MESSAGE = "Economy Phase 1 belum diaktifkan. Tidak ada saldo production yang diubah."


async def _deliver_phase5_notifications(client, *, limit=100):
    async def find_existing(channel, marker):
        async for previous in channel.history(limit=20):
            if marker in str(getattr(previous, "content", "")):
                return previous
        return None

    lease_owner = f"casino-discord:{uuid.uuid4()}"
    rows = await claim_casino_outbox(DB_PATH, lease_owner=lease_owner, limit=limit)
    delivered = failed = 0
    for row in rows:
        marker = f"W2E-CASINO-EVENT:{row['eventKey']}"
        try:
            user = client.get_user(int(row["userId"])) or await asyncio.wait_for(
                client.fetch_user(int(row["userId"])), timeout=8,
            )
            channel = await asyncio.wait_for(user.create_dm(), timeout=8)
            payload = __import__("json").loads(row["payloadJson"])
            message = await asyncio.wait_for(find_existing(channel, marker), timeout=8)
            if message is None:
                message = await asyncio.wait_for(channel.send(
                    "Settlement Casino selesai. "
                    f"Game: **{payload.get('game', '-')}**, stake: **{int(payload.get('stakeEcy', 0)):,} ECY**, "
                    f"payout: **{int(payload.get('grossPayoutEcy', 0)):,} ECY**.\n-# `{marker}`"
                ), timeout=8)
            await finalize_casino_outbox(
                DB_PATH, event_id=row["eventId"], lease_owner=lease_owner,
                sent=True, message_id=getattr(message, "id", None),
            )
            delivered += 1
        except (ValueError, discord.HTTPException, asyncio.TimeoutError):
            await finalize_casino_outbox(
                DB_PATH, event_id=row["eventId"], lease_owner=lease_owner,
                sent=False, error_code="discord_delivery_failed",
            )
            failed += 1
        except Exception:
            logger.exception("Phase 5 notification delivery failed event=%s", row.get("eventId"))
            failed += 1
    return {"scanned": len(rows), "delivered": delivered, "failed": failed}


async def _deliver_phase6_news(client, *, limit=100):
    async with aiosqlite.connect(DB_PATH) as phase9b_db:
        await configure_connection(phase9b_db)
        if await phase9b_capability(phase9b_db):
            return await _deliver_phase9b_notifications(client, limit=limit)

    async def find_existing(channel, marker):
        async for previous in channel.history(limit=20):
            if marker in str(getattr(previous, "content", "")):
                return previous
        return None

    lease_owner = f"crypto-discord:{uuid.uuid4()}"
    rows = await claim_crypto_news_outbox(DB_PATH, lease_owner=lease_owner, limit=limit)
    delivered = failed = 0
    for row in rows:
        try:
            guild = client.get_guild(int(row["guildId"]))
            channel = get_announce_channel(guild, "market") if guild else None
            if channel is None:
                raise ValueError("market_announcement_channel_missing")
            marker = f"W2E-CRYPTO-NEWS:{row['eventKey']}"
            change = row["changeBps"] / 100
            try:
                message = await asyncio.wait_for(find_existing(channel, marker), timeout=8)
            except (discord.Forbidden, discord.HTTPException, asyncio.TimeoutError):
                await finalize_crypto_news_outbox(
                    DB_PATH, outbox_id=row["outboxId"], lease_owner=lease_owner,
                    sent=False, error_code="adoption_scan_failed", review_required=True,
                )
                failed += 1
                continue
            if message is None:
                message = await asyncio.wait_for(channel.send(
                    f"**{row['newsType']} CRYPTO** - {row['symbol']} berubah **{change:+.2f}%** "
                    f"menjadi **{row['currentPriceEcy']:,} ECY**.\n-# `{marker}`"
                ), timeout=8)
            await finalize_crypto_news_outbox(
                DB_PATH, outbox_id=row["outboxId"], lease_owner=lease_owner,
                sent=True, message_id=getattr(message, "id", None),
            )
            delivered += 1
        except (ValueError, discord.HTTPException, asyncio.TimeoutError):
            await finalize_crypto_news_outbox(
                DB_PATH, outbox_id=row["outboxId"], lease_owner=lease_owner,
                sent=False, error_code="discord_delivery_failed",
            )
            failed += 1
        except Exception:
            logger.exception("Phase 6 news delivery failed outbox=%s", row.get("outboxId"))
            failed += 1
    return {"scanned": len(rows), "delivered": delivered, "failed": failed}


async def _deliver_phase9b_notifications(client, *, limit=100):
    lease_owner = f"phase9b-discord:{uuid.uuid4()}"
    async with aiosqlite.connect(DB_PATH) as db:
        await configure_connection(db)
        await db.execute("BEGIN IMMEDIATE")
        if not await phase9b_capability(db):
            await db.rollback()
            return {"scanned": 0, "delivered": 0, "failed": 0, "reviewRequired": 0}
        await reserve_crypto_news_outbox(db, limit=limit)
        rows = await claim_deliveries(db, lease_owner=lease_owner, limit=limit)
        await db.commit()

    delivered = failed = review = 0
    for row in rows:
        outcome = None; message_id = None; failure_code = None; marker_inspected = False
        try:
            guild = client.get_guild(int(row["guildId"]))
            channel = guild.get_channel(int(row["channelId"])) if guild else None
            if channel is None or not hasattr(channel, "history") or not hasattr(channel, "send"):
                outcome, failure_code, marker_inspected = "FAILED", "destination_unavailable", True
            else:
                try:
                    adopted = None
                    async for previous in channel.history(limit=50):
                        if row["marker"] in str(getattr(previous, "content", "")):
                            adopted = previous
                            break
                    marker_inspected = True
                except (discord.Forbidden, discord.HTTPException, asyncio.TimeoutError):
                    outcome, failure_code = "REVIEW_REQUIRED", "marker_inspection_uncertain"
                    adopted = None
                if outcome is None and adopted is not None:
                    outcome, message_id = "SENT", str(adopted.id)
                elif outcome is None:
                    payload = json.loads(row["payloadJson"])
                    if row["sourceType"] == "CRYPTO_NEWS_OUTBOX":
                        change = int(payload["changeBps"]) / 100
                        body = (f"**{payload['newsType']} CRYPTO** - {payload['symbol']} berubah "
                                f"**{change:+.2f}%** menjadi **{int(payload['currentPriceEcy']):,} ECY**.")
                    else:
                        body = str(payload.get("content", "Notifikasi dashboard"))
                    role = row.get("roleMentionId") if row["deliveryKind"] == "EVENT" else None
                    content = f"<@&{role}> {body}" if role else body
                    reserved_role = guild.get_role(int(role)) if role else None
                    allowed = (discord.AllowedMentions(roles=[reserved_role], users=False, everyone=False)
                               if reserved_role else discord.AllowedMentions.none())
                    try:
                        message = await asyncio.wait_for(
                            channel.send(f"{content}\n-# `{row['marker']}`", allowed_mentions=allowed), timeout=8,
                        )
                        outcome, message_id = "SENT", str(message.id)
                    except discord.Forbidden:
                        outcome, failure_code = "FAILED", "discord_forbidden"
                    except (discord.HTTPException, asyncio.TimeoutError):
                        outcome, failure_code = "REVIEW_REQUIRED", "send_acceptance_uncertain"
        except Exception:
            logger.exception("Phase 9B delivery worker failed delivery=%s", row.get("deliveryId"))
            outcome, failure_code = "REVIEW_REQUIRED", "unexpected_delivery_state"
        async with aiosqlite.connect(DB_PATH) as db:
            await configure_connection(db); await db.execute("BEGIN IMMEDIATE")
            try:
                await finalize_delivery(
                    db, delivery_id=row["deliveryId"], lease_owner=lease_owner, outcome=outcome,
                    message_id=message_id, failure_code=failure_code, marker_inspected=marker_inspected,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("Phase 9B finalization failed delivery=%s", row.get("deliveryId"))
                review += 1
                continue
        if outcome == "SENT": delivered += 1
        elif outcome == "FAILED": failed += 1
        else: review += 1
    return {"scanned": len(rows), "delivered": delivered, "failed": failed, "reviewRequired": review}


async def _deliver_phase4_watch_notifications(client, *, limit=100):
    async def find_existing(channel, marker):
        async for previous in channel.history(limit=20):
            if marker in str(getattr(previous, "content", "")):
                return previous
        return None

    lease_owner = f"discord-worker:{uuid.uuid4()}"
    rows = await claim_notification_events(DB_PATH, lease_owner=lease_owner, limit=limit)
    delivered = failed = 0
    for row in rows:
        marker = f"W2E-MARKET-EVENT:{row['eventKey']}"
        try:
            user = client.get_user(int(row["userId"]))
            if user is None:
                user = await asyncio.wait_for(client.fetch_user(int(row["userId"])), timeout=8)
            channel = await asyncio.wait_for(user.create_dm(), timeout=8)
            try:
                adopted = await asyncio.wait_for(find_existing(channel, marker), timeout=8)
            except (discord.Forbidden, discord.HTTPException, asyncio.TimeoutError):
                await finalize_notification_event(
                    DB_PATH, event_id=row["eventId"], lease_owner=lease_owner,
                    ambiguous=True, error_code="adoption_scan_failed",
                )
                failed += 1
                continue
            message = adopted
            if message is None:
                message = await asyncio.wait_for(
                    channel.send(
                        "Listing marketplace yang kamu pantau telah diperbarui. "
                        f"Listing ID: `{row['listingId']}`.\n-# `{marker}`"
                    ),
                    timeout=8,
                )
            updated = await finalize_notification_event(
                DB_PATH, event_id=row["eventId"], lease_owner=lease_owner,
                sent=True, message_id=getattr(message, "id", None),
            )
            delivered += int(updated)
        except (ValueError, discord.HTTPException, asyncio.TimeoutError):
            updated = await finalize_notification_event(
                DB_PATH, event_id=row["eventId"], lease_owner=lease_owner,
                sent=False, error_code="discord_delivery_failed",
            )
            if updated:
                failed += 1
        except Exception:
            logger.exception("phase4 notification delivery failed event=%s", row.get("eventId"))
            failed += 1
    return {"scanned": len(rows), "delivered": delivered, "failed": failed}


async def _reply(interaction, content, *, ephemeral=True):
    if interaction.response.is_done():
        try:
            return await interaction.edit_original_response(content=content)
        except (discord.NotFound, discord.HTTPException):
            return await interaction.followup.send(content, ephemeral=ephemeral)
    return await interaction.response.send_message(content, ephemeral=ephemeral)


class EconomyConfirmationView(discord.ui.View):
    def __init__(self, *, requester_id, request_id, action, payload, large):
        super().__init__(timeout=ECONOMY_CONFIRM_TIMEOUT_SECONDS)
        self.requester_id = int(requester_id)
        self.request_id = str(request_id)
        self.action = action
        self.payload = payload
        self.large = bool(large)
        self.second_stage = False
        self.completed = False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("Konfirmasi ini hanya dapat digunakan oleh pemohon.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Konfirmasi", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.completed:
            await interaction.response.send_message("Permintaan ini sudah diproses.", ephemeral=True)
            return
        if self.large and not self.second_stage:
            self.second_stage = True
            button.label = "Konfirmasi Besar Sekali Lagi"
            await interaction.response.edit_message(
                content="Operasi ini melewati threshold besar. Konfirmasi sekali lagi untuk memproses.",
                view=self,
            )
            return
        self.completed = True
        for item in self.children:
            item.disabled = True
        await interaction.response.defer(ephemeral=True)
        key = f"discord:{self.request_id}:{self.action}"
        common = dict(
            db_path=DB_PATH,
            guild_id=self.payload["guild_id"],
            actor_id=self.requester_id,
            target_user_id=self.payload["target_user_id"],
            currency=self.payload["currency"],
            amount=self.payload["amount"],
            reason=self.payload["reason"],
            idempotency_key=key,
        )
        if self.action == "mint":
            result = await admin_mint(**common)
        elif self.action == "remove":
            result = await admin_remove(**common)
        else:
            result = await treasury_grant(account_code=self.payload["account_code"], **common)
        await interaction.edit_original_response(content=result.message, view=self)

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.completed = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Operasi ekonomi dibatalkan.", view=self)


def setup(tree, client):
    economy_group = app_commands.Group(name="economy", description="Fondasi Economy")
    whitelist_group = app_commands.Group(name="whitelist", description="Whitelist mutasi ekonomi")
    casino_auth_group = app_commands.Group(name="casino-auth", description="Otorisasi least-privilege Casino")
    crypto_auth_group = app_commands.Group(name="crypto-auth", description="Otorisasi least-privilege Crypto")
    mining_auth_group = app_commands.Group(name="mining-auth", description="Otorisasi least-privilege Mining")

    async def _is_owner(interaction):
        try:
            return await client.is_owner(interaction.user)
        except Exception:
            return False

    async def _can_control(interaction):
        return await _is_owner(interaction) or await is_whitelisted(DB_PATH, interaction.guild_id, interaction.user.id)

    async def _can_control_feature(interaction, feature):
        if str(feature).lower() == "casino" and ECONOMY_PHASE5_ENABLED:
            return await is_casino_authorized(DB_PATH, interaction.guild_id, interaction.user.id, "CASINO_CONTROL")
        if str(feature).lower() == "mining" and ECONOMY_PHASE7_ENABLED:
            return await is_mining_authorized(DB_PATH, interaction.guild_id, interaction.user.id, "MINING_CONTROL")
        return await _can_control(interaction)

    async def _active_member_count(interaction):
        from datetime import datetime, timedelta, timezone
        import aiosqlite
        eligible_members = {str(member.id) for member in interaction.guild.members if not member.bot}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT DISTINCT userId FROM EconomyActivityEvent WHERE guildId=? AND occurredAt>=? "
                "AND transactionId IS NOT NULL AND eventType IN "
                "('DAILY_CLAIM','WEEKLY_CLAIM','WORK_SUCCESS','HUNT_COMPLETED','DUNGEON_COMPLETED',"
                "'BOSS_ATTACK','BOSS_PARTICIPATION','DAILY_QUEST_COMPLETED','WEEKLY_QUEST_COMPLETED')",
                (str(interaction.guild_id), cutoff),
            ) as cursor:
                active = {str(row[0]) for row in await cursor.fetchall()}
        return len(active & eligible_members)

    async def _stage(interaction, action, target, currency, amount, reason, account_code=None):
        if not ECONOMY_V1_ENABLED:
            await _reply(interaction, STAGING_MESSAGE)
            return
        await interaction.response.defer(ephemeral=True)
        if not await is_whitelisted(DB_PATH, interaction.guild_id, interaction.user.id):
            await _reply(interaction, "User ID kamu tidak terdaftar di whitelist ekonomi.")
            return
        currency = str(currency).upper()
        if currency not in CURRENCIES:
            await _reply(interaction, "Currency harus ETM atau ECY.")
            return
        try:
            parsed = parse_economy_amount(amount)
        except AmountParseError as exc:
            await _reply(interaction, str(exc))
            return
        threshold = configured_large_threshold(action if action != "treasury-grant" else "grant", currency)
        if threshold is None:
            await _reply(interaction, "Threshold operasi besar belum dikonfigurasi; mutasi dinonaktifkan.")
            return
        reason = str(reason or "").strip()
        if not reason:
            await _reply(interaction, "Alasan wajib diisi.")
            return
        payload = {
            "guild_id": interaction.guild_id,
            "target_user_id": target.id,
            "currency": currency,
            "amount": parsed,
            "reason": reason,
            "account_code": account_code,
        }
        view = EconomyConfirmationView(
            requester_id=interaction.user.id,
            request_id=interaction.id,
            action=action,
            payload=payload,
            large=parsed >= threshold,
        )
        await _reply(
            interaction,
            f"Konfirmasi `{action}` {format_economy_amount(parsed, currency)} untuk {target.mention}.",
        )
        await interaction.edit_original_response(view=view)

    @economy_group.command(name="mint", description="Mint ETM/ECY (whitelist only)")
    async def mint(interaction: discord.Interaction, target: discord.Member, currency: str, amount: str, reason: str):
        await _stage(interaction, "mint", target, currency, amount, reason)

    @economy_group.command(name="remove", description="Hapus saldo ke burn account (whitelist only)")
    async def remove(interaction: discord.Interaction, target: discord.Member, currency: str, amount: str, reason: str):
        await _stage(interaction, "remove", target, currency, amount, reason)

    @economy_group.command(name="treasury-grant", description="Grant dari operational treasury (whitelist only)")
    async def grant(interaction: discord.Interaction, target: discord.Member, currency: str, amount: str, account: str, reason: str):
        await _stage(interaction, "treasury-grant", target, currency, amount, reason, account)

    @economy_group.command(name="pause", description="Jeda fitur ekonomi")
    async def pause(interaction: discord.Interaction, feature: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        if str(feature).lower() == "casino" and ECONOMY_PHASE5_ENABLED:
            result = await set_casino_paused(
                DB_PATH, guild_id=interaction.guild_id, actor_id=interaction.user.id,
                paused=True, reason=reason,
            )
            await _reply(interaction, result.message)
            return
        if str(feature).lower() == "crypto" and ECONOMY_PHASE6_ENABLED:
            if not await is_crypto_authorized(
                DB_PATH, interaction.guild_id, interaction.user.id, "CRYPTO_CONTROL"
            ):
                await _reply(interaction, "Kamu tidak memiliki CRYPTO_CONTROL.")
                return
            await set_feature_paused(
                DB_PATH, guild_id=interaction.guild_id, feature="crypto", paused=True,
                actor_id=interaction.user.id, reason=reason,
            )
            await _reply(interaction, "Fitur `crypto` berhasil dijeda.")
            return
        if str(feature).lower() == "mining" and ECONOMY_PHASE7_ENABLED:
            if not await is_mining_authorized(
                DB_PATH, interaction.guild_id, interaction.user.id, "MINING_CONTROL"
            ):
                await _reply(interaction, "Kamu tidak memiliki MINING_CONTROL.")
                return
            await set_feature_paused(
                DB_PATH, guild_id=interaction.guild_id, feature="mining", paused=True,
                actor_id=interaction.user.id, reason=reason,
            )
            await _reply(interaction, "Fitur `mining` berhasil dijeda.")
            return
        if not await _can_control_feature(interaction, feature):
            await _reply(interaction, "Kamu tidak punya permission untuk mengubah emergency control.")
            return
        try:
            await set_feature_paused(DB_PATH, guild_id=interaction.guild_id, feature=feature,
                                     paused=True, actor_id=interaction.user.id, reason=reason)
        except ValueError as exc:
            await _reply(interaction, str(exc))
            return
        await _reply(interaction, f"Fitur `{feature}` berhasil dijeda.")

    @economy_group.command(name="resume", description="Aktifkan kembali fitur ekonomi")
    async def resume(interaction: discord.Interaction, feature: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        if str(feature).lower() == "casino" and ECONOMY_PHASE5_ENABLED:
            result = await set_casino_paused(
                DB_PATH, guild_id=interaction.guild_id, actor_id=interaction.user.id,
                paused=False, reason=reason,
            )
            await _reply(interaction, result.message)
            return
        if str(feature).lower() == "mining" and ECONOMY_PHASE7_ENABLED:
            if not await is_mining_authorized(
                DB_PATH, interaction.guild_id, interaction.user.id, "MINING_CONTROL"
            ):
                await _reply(interaction, "Kamu tidak memiliki MINING_CONTROL.")
                return
            await set_feature_paused(
                DB_PATH, guild_id=interaction.guild_id, feature="mining", paused=False,
                actor_id=interaction.user.id, reason=reason,
            )
            await _reply(interaction, "Fitur `mining` berhasil dilanjutkan.")
            return
        if str(feature).lower() == "crypto" and ECONOMY_PHASE6_ENABLED:
            if not await is_crypto_authorized(
                DB_PATH, interaction.guild_id, interaction.user.id, "CRYPTO_CONTROL"
            ):
                await _reply(interaction, "Kamu tidak memiliki CRYPTO_CONTROL.")
                return
            await set_feature_paused(
                DB_PATH, guild_id=interaction.guild_id, feature="crypto", paused=False,
                actor_id=interaction.user.id, reason=reason,
            )
            await _reply(interaction, "Fitur `crypto` berhasil dilanjutkan.")
            return
        if not await _can_control_feature(interaction, feature):
            await _reply(interaction, "Kamu tidak punya permission untuk mengubah emergency control.")
            return
        try:
            await set_feature_paused(DB_PATH, guild_id=interaction.guild_id, feature=feature,
                                     paused=False, actor_id=interaction.user.id, reason=reason)
        except ValueError as exc:
            await _reply(interaction, str(exc))
            return
        await _reply(interaction, f"Fitur `{feature}` berhasil dilanjutkan.")

    @economy_group.command(name="status", description="Lihat status dan supply Economy")
    async def status(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await _can_control(interaction):
            await _reply(interaction, "Kamu tidak punya permission untuk melihat status ekonomi.")
            return
        supply = await get_supply_report(DB_PATH, interaction.guild_id)
        states = await feature_states(DB_PATH, interaction.guild_id)
        state_text = ", ".join(f"{row[0]}={'pause' if row[1] else 'aktif'}" for row in states)
        lines = [
            f"Economy enabled: **{'Ya' if ECONOMY_V1_ENABLED else 'Tidak'}**",
            f"Economy Phase 2 enabled: **{'Ya' if ECONOMY_PHASE2_ENABLED else 'Tidak'}**",
            f"Economy Phase 3 enabled: **{'Ya' if ECONOMY_PHASE3_ENABLED else 'Tidak'}**",
            f"Economy Phase 4 enabled: **{'Ya' if ECONOMY_PHASE4_ENABLED else 'Tidak'}**",
            f"Economy Phase 5 enabled: **{'Ya' if ECONOMY_PHASE5_ENABLED else 'Tidak'}**",
            f"Economy Phase 6 enabled: **{'Ya' if ECONOMY_PHASE6_ENABLED else 'Tidak'}**",
            f"Economy Phase 7 enabled: **{'Ya' if ECONOMY_PHASE7_ENABLED else 'Tidak'}**",
            f"Economy Phase 8 enabled: **{'Ya' if ECONOMY_PHASE8_ENABLED else 'Tidak'}**",
            state_text,
        ]
        for currency in CURRENCIES:
            data = supply[currency]
            lines.append(
                f"**{currency}** net={data['net_issued_supply']:,} circulating={data['circulating_supply']:,} "
                f"reserve={data['non_circulating_supply']:,} burned={data['burned_supply']:,}"
            )
        await _reply(interaction, "\n".join(lines))

    @whitelist_group.command(name="add", description="Tambah whitelist ekonomi (bot owner only)")
    async def whitelist_add(interaction: discord.Interaction, user: discord.User, reason: str):
        await interaction.response.defer(ephemeral=True)
        if not await _is_owner(interaction):
            await _reply(interaction, "Hanya bot owner yang dapat mengubah whitelist.")
            return
        await set_whitelist(DB_PATH, guild_id=interaction.guild_id, user_id=user.id, enabled=True,
                            actor_id=interaction.user.id, reason=reason)
        await _reply(interaction, "Whitelist ekonomi berhasil diperbarui.")

    @whitelist_group.command(name="remove", description="Nonaktifkan whitelist ekonomi (bot owner only)")
    async def whitelist_remove(interaction: discord.Interaction, user: discord.User, reason: str):
        await interaction.response.defer(ephemeral=True)
        if not await _is_owner(interaction):
            await _reply(interaction, "Hanya bot owner yang dapat mengubah whitelist.")
            return
        await set_whitelist(DB_PATH, guild_id=interaction.guild_id, user_id=user.id, enabled=False,
                            actor_id=interaction.user.id, reason=reason)
        await _reply(interaction, "Whitelist ekonomi berhasil dinonaktifkan.")

    @whitelist_group.command(name="list", description="Lihat whitelist ekonomi (bot owner only)")
    async def whitelist_list(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await _is_owner(interaction):
            await _reply(interaction, "Hanya bot owner yang dapat melihat whitelist.")
            return
        rows = await list_whitelist(DB_PATH, interaction.guild_id)
        text = "\n".join(f"<@{row[0]}> — {'enabled' if row[1] else 'disabled'}" for row in rows) or "Whitelist kosong."
        await _reply(interaction, text)

    @casino_auth_group.command(name="add", description="Tambah kelas otorisasi Casino (bot owner only)")
    async def casino_auth_add(interaction: discord.Interaction, user: discord.User, permission_class: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        if not await _is_owner(interaction):
            await _reply(interaction, "Hanya bot owner yang dapat mengelola otorisasi Casino.")
            return
        try:
            await set_casino_authorization(
                DB_PATH, guild_id=interaction.guild_id, user_id=user.id,
                permission_class=permission_class.upper(), enabled=True,
                actor_id=interaction.user.id, reason=reason,
            )
        except ValueError as exc:
            await _reply(interaction, str(exc))
            return
        await _reply(interaction, "Otorisasi Casino berhasil ditambahkan.")

    @casino_auth_group.command(name="remove", description="Cabut kelas otorisasi Casino (bot owner only)")
    async def casino_auth_remove(interaction: discord.Interaction, user: discord.User, permission_class: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        if not await _is_owner(interaction):
            await _reply(interaction, "Hanya bot owner yang dapat mengelola otorisasi Casino.")
            return
        try:
            await set_casino_authorization(
                DB_PATH, guild_id=interaction.guild_id, user_id=user.id,
                permission_class=permission_class.upper(), enabled=False,
                actor_id=interaction.user.id, reason=reason,
            )
        except ValueError as exc:
            await _reply(interaction, str(exc))
            return
        await _reply(interaction, "Otorisasi Casino berhasil dicabut.")

    @casino_auth_group.command(name="list", description="Lihat otorisasi Casino (bot owner only)")
    async def casino_auth_list(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await _is_owner(interaction):
            await _reply(interaction, "Hanya bot owner yang dapat melihat otorisasi Casino.")
            return
        rows = await list_casino_authorizations(DB_PATH, interaction.guild_id)
        text = "\n".join(f"<@{row[0]}> `{row[1]}`: {'aktif' if row[2] else 'nonaktif'}" for row in rows) or "Otorisasi Casino kosong."
        await _reply(interaction, text)

    @economy_group.command(name="casino-status", description="Lihat bankroll dan exposure Casino")
    async def casino_status_command(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await is_casino_authorized(DB_PATH, interaction.guild_id, interaction.user.id, "CASINO_CONTROL"):
            await _reply(interaction, "Kamu tidak memiliki CASINO_CONTROL.")
            return
        data = await casino_status(DB_PATH, interaction.guild_id)
        await _reply(interaction, "\n".join((
            f"Schema siap: **{'Ya' if data['schemaCapable'] else 'Tidak'}**",
            f"Seeded: **{'Ya' if data['seeded'] else 'Tidak'}**",
            f"Paused: **{'Ya' if data['paused'] else 'Tidak'}**",
            f"Bankroll: **{data['bankrollEcy']:,} ECY**",
            f"Reserved: **{data['reservedLiabilityEcy']:,} ECY**",
            f"Available: **{data['availableBankrollEcy']:,} ECY**",
            f"Exposure cap: **{data['exposureCapEcy']:,} ECY**",
            f"Unresolved/review: **{data['unresolvedSessions']}/{data['reviewRequired']}**",
        )))

    @economy_group.command(name="casino-seed", description="Seed awal Casino staging")
    async def casino_seed_command(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await is_casino_authorized(DB_PATH, interaction.guild_id, interaction.user.id, "CASINO_FINANCIAL"):
            await _reply(interaction, "Kamu tidak memiliki CASINO_FINANCIAL.")
            return
        active = await _active_member_count(interaction)
        result = await seed_casino_bankroll(
            DB_PATH, guild_id=interaction.guild_id, actor_id=interaction.user.id, active_members=active,
        )
        await _reply(interaction, f"{result.message}\nActive member terverifikasi: **{active}**.")

    @economy_group.command(name="casino-adjust", description="Transfer bankroll Casino dari/ke ECY_GENERAL")
    async def casino_adjust_command(interaction: discord.Interaction, direction: str, amount: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        if not await is_casino_authorized(DB_PATH, interaction.guild_id, interaction.user.id, "CASINO_FINANCIAL"):
            await _reply(interaction, "Kamu tidak memiliki CASINO_FINANCIAL.")
            return
        try:
            parsed = parse_economy_amount(amount)
        except AmountParseError as exc:
            await _reply(interaction, str(exc))
            return
        result = await adjust_casino_bankroll(
            DB_PATH, guild_id=interaction.guild_id, actor_id=interaction.user.id,
            amount=parsed, direction=direction, request_id=str(interaction.id), reason=reason,
        )
        await _reply(interaction, result.message)

    @economy_group.command(name="casino-distribute", description="Distribusikan excess bankroll saat pause")
    async def casino_distribute_command(interaction: discord.Interaction, reason: str):
        await interaction.response.defer(ephemeral=True)
        if not await is_casino_authorized(DB_PATH, interaction.guild_id, interaction.user.id, "CASINO_FINANCIAL"):
            await _reply(interaction, "Kamu tidak memiliki CASINO_FINANCIAL.")
            return
        active = await _active_member_count(interaction)
        result = await distribute_casino_excess(
            DB_PATH, guild_id=interaction.guild_id, actor_id=interaction.user.id,
            active_members=active, request_id=str(interaction.id), reason=reason,
        )
        await _reply(interaction, result.message)

    @economy_group.command(name="casino-recover", description="Jalankan recovery Casino terotorisasi")
    async def casino_recover_command(interaction: discord.Interaction, session_id: str = "", resolution: str = "inspect",
                                     owner_override: bool = False, reason: str = ""):
        await interaction.response.defer(ephemeral=True)
        authorized = await is_casino_authorized(DB_PATH, interaction.guild_id, interaction.user.id, "CASINO_RECOVERY")
        override_used = False
        if not authorized:
            owner = await _is_owner(interaction)
            if not (owner and owner_override):
                await _reply(interaction, "Kamu tidak memiliki CASINO_RECOVERY. Owner override harus eksplisit.")
                return
            try:
                await record_owner_recovery_override(
                    DB_PATH, guild_id=interaction.guild_id, actor_id=interaction.user.id, reason=reason,
                )
            except ValueError as exc:
                await _reply(interaction, str(exc))
                return
            logger.warning("Audited Casino owner recovery override actor_id=%s guild_id=%s", interaction.user.id, interaction.guild_id)
            override_used = True
        if str(session_id).strip():
            result = await resolve_review_session(
                DB_PATH, guild_id=interaction.guild_id, actor_id=interaction.user.id,
                session_id=session_id.strip(), resolution=resolution, request_id=str(interaction.id),
                reason=reason or "Casino reviewed recovery", authorization_override=override_used,
            )
            await _reply(interaction, result.message)
            return
        result = await recover_phase5_runtime(DB_PATH, guild_id=interaction.guild_id)
        await _reply(interaction, f"Recovery Casino selesai: `{result}`")

    @crypto_auth_group.command(name="add", description="Tambah kelas otorisasi Crypto (bot owner only)")
    async def crypto_auth_add(interaction: discord.Interaction, user: discord.User,
                              permission_class: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        if not await _is_owner(interaction):
            await _reply(interaction, "Hanya bot owner yang dapat mengelola otorisasi Crypto.")
            return
        try:
            await set_crypto_authorization(
                DB_PATH, guild_id=interaction.guild_id, user_id=user.id,
                permission_class=permission_class, enabled=True,
                actor_id=interaction.user.id, reason=reason,
            )
        except ValueError as exc:
            await _reply(interaction, str(exc))
            return
        await _reply(interaction, "Otorisasi Crypto berhasil ditambahkan.")

    @crypto_auth_group.command(name="remove", description="Cabut kelas otorisasi Crypto (bot owner only)")
    async def crypto_auth_remove(interaction: discord.Interaction, user: discord.User,
                                 permission_class: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        if not await _is_owner(interaction):
            await _reply(interaction, "Hanya bot owner yang dapat mengelola otorisasi Crypto.")
            return
        try:
            await set_crypto_authorization(
                DB_PATH, guild_id=interaction.guild_id, user_id=user.id,
                permission_class=permission_class, enabled=False,
                actor_id=interaction.user.id, reason=reason,
            )
        except ValueError as exc:
            await _reply(interaction, str(exc))
            return
        await _reply(interaction, "Otorisasi Crypto berhasil dicabut.")

    @crypto_auth_group.command(name="list", description="Lihat otorisasi Crypto (bot owner only)")
    async def crypto_auth_list(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await _is_owner(interaction):
            await _reply(interaction, "Hanya bot owner yang dapat melihat otorisasi Crypto.")
            return
        rows = await list_crypto_authorizations(DB_PATH, interaction.guild_id)
        text = "\n".join(
            f"<@{row[0]}> `{row[1]}`: {'aktif' if row[2] else 'nonaktif'}"
            for row in rows
        ) or "Otorisasi Crypto kosong."
        await _reply(interaction, text)

    @economy_group.command(name="crypto-status", description="Lihat kesiapan Market Reserve Crypto")
    async def crypto_status_command(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await is_crypto_authorized(
            DB_PATH, interaction.guild_id, interaction.user.id, "CRYPTO_CONTROL"
        ):
            await _reply(interaction, "Kamu tidak memiliki CRYPTO_CONTROL.")
            return
        data = await crypto_readiness(DB_PATH, interaction.guild_id)
        await _reply(interaction, "\n".join((
            f"Schema siap: **{'Ya' if data.get('code') != 'schema_unavailable' else 'Tidak'}**",
            f"Reserve seeded: **{'Ya' if data.get('code') != 'market_unseeded' else 'Tidak'}**",
            f"Status: **{data.get('code', 'unknown')}**",
            f"Market Reserve: **{int(data.get('marketReserveEcy', 0)):,} ECY**",
        )))

    @economy_group.command(name="crypto-seed", description="Seed Market Reserve Crypto staging")
    async def crypto_seed_command(interaction: discord.Interaction, amount: str):
        await interaction.response.defer(ephemeral=True)
        if not await is_crypto_authorized(
            DB_PATH, interaction.guild_id, interaction.user.id, "CRYPTO_FINANCIAL"
        ):
            await _reply(interaction, "Kamu tidak memiliki CRYPTO_FINANCIAL.")
            return
        try:
            parsed = parse_economy_amount(amount)
            result = await seed_market_reserve(
                DB_PATH, guild_id=interaction.guild_id, amount=parsed,
                actor_id=interaction.user.id,
            )
        except (AmountParseError, PermissionError, ValueError) as exc:
            await _reply(interaction, str(exc))
            return
        await _reply(interaction, result.message)

    @economy_group.command(name="crypto-recover", description="Jalankan recovery Crypto terotorisasi")
    async def crypto_recover_command(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await is_crypto_authorized(
            DB_PATH, interaction.guild_id, interaction.user.id, "CRYPTO_RECOVERY"
        ):
            await _reply(interaction, "Kamu tidak memiliki CRYPTO_RECOVERY.")
            return
        result = await recover_phase6_runtime(DB_PATH)
        await _reply(interaction, f"Recovery Crypto selesai: `{result}`")

    @mining_auth_group.command(name="add", description="Tambah kelas otorisasi Mining (bot owner only)")
    async def mining_auth_add(interaction: discord.Interaction, user: discord.User,
                              permission_class: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        if not await _is_owner(interaction):
            await _reply(interaction, "Hanya bot owner yang dapat mengelola otorisasi Mining.")
            return
        try:
            await set_mining_authorization(
                DB_PATH, guild_id=interaction.guild_id, user_id=user.id,
                permission_class=permission_class, enabled=True,
                actor_id=interaction.user.id, reason=reason,
            )
        except ValueError as exc:
            await _reply(interaction, str(exc))
            return
        await _reply(interaction, "Otorisasi Mining berhasil ditambahkan.")

    @mining_auth_group.command(name="remove", description="Cabut kelas otorisasi Mining (bot owner only)")
    async def mining_auth_remove(interaction: discord.Interaction, user: discord.User,
                                 permission_class: str, reason: str):
        await interaction.response.defer(ephemeral=True)
        if not await _is_owner(interaction):
            await _reply(interaction, "Hanya bot owner yang dapat mengelola otorisasi Mining.")
            return
        try:
            await set_mining_authorization(
                DB_PATH, guild_id=interaction.guild_id, user_id=user.id,
                permission_class=permission_class, enabled=False,
                actor_id=interaction.user.id, reason=reason,
            )
        except ValueError as exc:
            await _reply(interaction, str(exc))
            return
        await _reply(interaction, "Otorisasi Mining berhasil dicabut.")

    @mining_auth_group.command(name="list", description="Lihat otorisasi Mining (bot owner only)")
    async def mining_auth_list(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await _is_owner(interaction):
            await _reply(interaction, "Hanya bot owner yang dapat melihat otorisasi Mining.")
            return
        rows = await list_mining_authorizations(DB_PATH, interaction.guild_id)
        text = "\n".join(f"<@{row[0]}> `{row[1]}`: {'aktif' if row[2] else 'nonaktif'}" for row in rows)
        await _reply(interaction, text or "Otorisasi Mining kosong.")

    @economy_group.command(name="mining-status", description="Lihat kesiapan Mining Phase 7")
    async def mining_status_command(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await is_mining_authorized(
            DB_PATH, interaction.guild_id, interaction.user.id, "MINING_CONTROL"
        ):
            await _reply(interaction, "Kamu tidak memiliki MINING_CONTROL.")
            return
        data = await mining_readiness(DB_PATH, interaction.guild_id)
        await _reply(interaction, f"Status Mining: **{data.get('code', 'unknown')}**")

    @economy_group.command(name="mining-config", description="Lihat konfigurasi ekonomi rig Mining")
    async def mining_config_command(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await is_mining_authorized(
            DB_PATH, interaction.guild_id, interaction.user.id, "MINING_CONTROL"
        ):
            await _reply(interaction, "Kamu tidak memiliki MINING_CONTROL.")
            return
        await _reply(interaction, "\n".join(
            f"{key}: purchase={value[1]:,}, gross/day={value[2]:,}, maintenance={value[3]:,}"
            for key, value in MINING_RIG_CATALOG.items()
        ))

    @economy_group.command(name="mining-recover", description="Jalankan recovery Mining terotorisasi")
    async def mining_recover_command(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await is_mining_authorized(
            DB_PATH, interaction.guild_id, interaction.user.id, "MINING_RECOVERY"
        ):
            await _reply(interaction, "Kamu tidak memiliki MINING_RECOVERY.")
            return
        result = await recover_phase7(DB_PATH)
        await _reply(interaction, f"Recovery Mining selesai: `{result}`")

    economy_group.add_command(whitelist_group)
    economy_group.add_command(casino_auth_group)
    economy_group.add_command(crypto_auth_group)
    economy_group.add_command(mining_auth_group)
    tree.add_command(economy_group)

    async def _bootstrap():
        await bootstrap_whitelist(DB_PATH, ALLOWED_SERVER_ID)

    async def _recover_phase2():
        await recover_phase2_runtime(DB_PATH)

    register_ready_startup_task(_bootstrap)
    register_ready_startup_task(_recover_phase2)

    async def _recover_phase3():
        if not (ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE3_ENABLED):
            return
        try:
            counts = await recover_phase3_operations(DB_PATH)
            logger.info("Phase 3 recovery result counts=%s", counts)
        except Exception as exc:
            logger.warning("Phase 3 recovery inspection failed type=%s", type(exc).__name__)

    register_ready_startup_task(_recover_phase3)

    async def _recover_phase4():
        if not (ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and
                ECONOMY_PHASE3_ENABLED and ECONOMY_PHASE4_ENABLED):
            return
        try:
            counts = await recover_phase4_runtime(DB_PATH)
            counts["watch_notifications"] = await _deliver_phase4_watch_notifications(client)
            logger.info("Phase 4 recovery result counts=%s", counts)
        except Exception as exc:
            logger.warning("Phase 4 recovery inspection failed type=%s", type(exc).__name__)

    register_ready_startup_task(_recover_phase4)

    async def _recover_phase5():
        if not (ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE5_ENABLED):
            return
        try:
            counts = await recover_phase5_runtime(DB_PATH)
            counts["notifications"] = await _deliver_phase5_notifications(client)
            logger.info("Phase 5 recovery result counts=%s", counts)
        except Exception as exc:
            logger.warning("Phase 5 recovery failed type=%s", type(exc).__name__)

    register_ready_startup_task(_recover_phase5)

    async def _phase6_worker_loop():
        while not client.is_closed():
            try:
                recovery = await recover_phase6_runtime(DB_PATH)
                if recovery.get("schema_ready"):
                    await run_market_tick(DB_PATH)
                    recovery["news"] = await _deliver_phase6_news(client)
                logger.info("Phase 6 worker result=%s", recovery)
            except Exception as exc:
                logger.warning("Phase 6 worker failed type=%s", type(exc).__name__)
            await asyncio.sleep(60)

    async def _start_phase6_worker():
        if not (ECONOMY_V1_ENABLED and ECONOMY_PHASE6_ENABLED):
            return
        existing = getattr(client, "_phase6_crypto_worker", None)
        if existing is None or existing.done():
            client._phase6_crypto_worker = asyncio.create_task(_phase6_worker_loop())

    register_ready_startup_task(_start_phase6_worker)

    async def _recover_phase7():
        if not (ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE7_ENABLED):
            return
        try:
            result = await recover_phase7(DB_PATH)
            logger.info("Phase 7 recovery result=%s", result)
        except Exception as exc:
            logger.warning("Phase 7 recovery failed type=%s", type(exc).__name__)

    register_ready_startup_task(_recover_phase7)

    async def _phase9b_delivery_loop():
        while not client.is_closed():
            try:
                result = await _deliver_phase9b_notifications(client)
                if result["scanned"]:
                    logger.info("Phase 9B notification delivery result=%s", result)
            except Exception as exc:
                logger.warning("Phase 9B delivery worker failed type=%s", type(exc).__name__)
            await asyncio.sleep(30)

    async def _start_phase9b_delivery_worker():
        async with aiosqlite.connect(DB_PATH) as db:
            await configure_connection(db)
            if not await phase9b_capability(db):
                return
        existing = getattr(client, "_phase9b_delivery_worker", None)
        if existing is None or existing.done():
            client._phase9b_delivery_worker = asyncio.create_task(_phase9b_delivery_loop())

    register_ready_startup_task(_start_phase9b_delivery_worker)
