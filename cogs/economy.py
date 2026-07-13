import asyncio
import discord
import logging
import uuid
from discord import app_commands

from core import ALLOWED_SERVER_ID, DB_PATH, register_ready_startup_task
from economy.amounts import AmountParseError, format_economy_amount, parse_economy_amount
from economy.constants import (
    CURRENCIES,
    ECONOMY_CONFIRM_TIMEOUT_SECONDS,
    ECONOMY_PHASE2_ENABLED,
    ECONOMY_PHASE3_ENABLED,
    ECONOMY_PHASE4_ENABLED,
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


logger = logging.getLogger(__name__)


STAGING_MESSAGE = "Economy V1 Phase 1 belum diaktifkan. Tidak ada saldo production yang diubah."


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
    economy_group = app_commands.Group(name="economy", description="Fondasi Economy V1")
    whitelist_group = app_commands.Group(name="whitelist", description="Whitelist mutasi ekonomi")

    async def _is_owner(interaction):
        try:
            return await client.is_owner(interaction.user)
        except Exception:
            return False

    async def _can_control(interaction):
        return await _is_owner(interaction) or await is_whitelisted(DB_PATH, interaction.guild_id, interaction.user.id)

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
        if not await _can_control(interaction):
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
        if not await _can_control(interaction):
            await _reply(interaction, "Kamu tidak punya permission untuk mengubah emergency control.")
            return
        try:
            await set_feature_paused(DB_PATH, guild_id=interaction.guild_id, feature=feature,
                                     paused=False, actor_id=interaction.user.id, reason=reason)
        except ValueError as exc:
            await _reply(interaction, str(exc))
            return
        await _reply(interaction, f"Fitur `{feature}` berhasil dilanjutkan.")

    @economy_group.command(name="status", description="Lihat status dan supply Economy V1")
    async def status(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await _can_control(interaction):
            await _reply(interaction, "Kamu tidak punya permission untuk melihat status ekonomi.")
            return
        supply = await get_supply_report(DB_PATH, interaction.guild_id)
        states = await feature_states(DB_PATH, interaction.guild_id)
        state_text = ", ".join(f"{row[0]}={'pause' if row[1] else 'aktif'}" for row in states)
        lines = [
            f"Economy V1 enabled: **{'Ya' if ECONOMY_V1_ENABLED else 'Tidak'}**",
            f"Economy Phase 2 enabled: **{'Ya' if ECONOMY_PHASE2_ENABLED else 'Tidak'}**",
            f"Economy Phase 3 enabled: **{'Ya' if ECONOMY_PHASE3_ENABLED else 'Tidak'}**",
            f"Economy Phase 4 enabled: **{'Ya' if ECONOMY_PHASE4_ENABLED else 'Tidak'}**",
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

    economy_group.add_command(whitelist_group)
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
