"""Adapter Discord Phase 8 Giveaway dan Eternal Options."""

from datetime import datetime, timezone
import asyncio
import json
import secrets
import uuid

import aiosqlite
import discord
from discord import app_commands

from core import (
    DB_PATH, FakeInteraction, register_prefix_command_handler, register_ready_startup_task,
    register_voice_state_callback, send_embed,
)
from economy.constants import (
    CRYPTO_ASSETS, ECONOMY_PHASE2_ENABLED, ECONOMY_PHASE5_ENABLED, ECONOMY_PHASE6_ENABLED,
    ECONOMY_PHASE8_ENABLED, ECONOMY_V1_ENABLED,
)
from economy.database import configure_connection
from economy.eternal_options import list_positions, open_option, option_details, options_status, settle_option
from economy.giveaways import (
    build_eligibility_evidence, cancel_giveaway, claim_giveaway, create_giveaway,
    draw_giveaway, enter_giveaway, list_giveaways, record_winner_review,
    redraw_giveaway, set_giveaway_message,
)
from economy.phase8_recovery import claim_phase8_outbox, finalize_phase8_outbox, recover_phase8
from economy.phase8_schema import phase8_capability
from economy.phase8_voice import reconcile_voice_snapshot


def phase8_enabled():
    return (ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE5_ENABLED
            and ECONOMY_PHASE6_ENABLED and ECONOMY_PHASE8_ENABLED)


def _request_id():
    return secrets.token_urlsafe(24)


def _is_admin(interaction):
    permissions = getattr(getattr(interaction, "user", None), "guild_permissions", None)
    return bool(permissions and permissions.administrator)


async def _blacklisted(guild_id, user_id):
    try:
        async with _pool.acquire() as db:
            await configure_connection(db)
            row = await db.fetchrow(
                "SELECT status FROM trustModerationStatus WHERE guildId=$1 AND userId=$2", str(guild_id), str(user_id)),
            )
            return bool(row and str(row[0]).lower() == "blacklisted")
    except aiosqlite.Error:
        return True


async def _member_evidence(guild, member, *, now=None):
    if not guild or not member:
        return {"eligible": False, "evidenceHash": "missing"}
    created = getattr(member, "created_at", None) or datetime.now(timezone.utc)
    joined = getattr(member, "joined_at", None) or datetime.now(timezone.utc)
    async with _pool.acquire() as db:
        await configure_connection(db)
        return await build_eligibility_evidence(
            db, guild_id=guild.id, user_id=member.id, account_created_at=created,
            guild_joined_at=joined, present=guild.get_member(member.id) is not None,
            is_bot=member.bot, blacklisted=await _blacklisted(guild.id, member.id), as_of=now,
        )


async def _eligible_pool(guild, giveaway_id):
    async with _pool.acquire() as db:
        await configure_connection(db)
        row = await db.fetchrow("SELECT userId FROM GiveawayTicket WHERE giveawayId=$1 AND status IN ('PAID','ALLOCATED')", str(giveaway_id) as cursor:
            user_ids = [row[0] for row in await cursor.fetchall()]
    evidence = {}
    for user_id in user_ids:
        member = guild.get_member(int(user_id))
        evidence[user_id] = await _member_evidence(guild, member)
    return [uid for uid, value in evidence.items() if value.get("eligible")], evidence


class OptionConfirmationView(discord.ui.View):
    def __init__(self, actor_id, callback, request_id):
        super().__init__(timeout=90)
        self.actor_id = int(actor_id)
        self.callback = callback
        self.request_id = request_id
        self.completed = False

    async def interaction_check(self, interaction):
        if int(interaction.user.id) != self.actor_id:
            await interaction.response.send_message("Konfirmasi ini bukan milik kamu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Konfirmasi", style=discord.ButtonStyle.green)
    async def confirm(self, interaction, button):
        if self.completed:
            await interaction.response.send_message("Request ini sudah diproses.", ephemeral=True)
            return
        self.completed = True
        button.disabled = True
        await interaction.response.defer()
        result = await self.callback(self.request_id)
        await send_embed(interaction, result.message)
        self.stop()

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self.completed = True
        await interaction.response.edit_message(content="Pembukaan Options dibatalkan tanpa posisi atau debit.", view=None)
        self.stop()


class GiveawayClaimView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Akui Kemenangan", style=discord.ButtonStyle.green,
                       custom_id="phase8:giveaway:claim")
    async def claim(self, interaction, button):
        if not phase8_enabled():
            await interaction.response.send_message("Giveaway tidak aktif.", ephemeral=True)
            return
        async with _pool.acquire() as db:
            await configure_connection(db)
            async with db.execute(
                "SELECT giveawayId FROM GiveawayV1 WHERE guildId=$1 AND messageId=$2 AND status='AWAITING_CLAIM'", str(interaction.guild_id), str(interaction.message.id),
            )
        if not row:
            await interaction.response.send_message("Giveaway tidak lagi menunggu klaim.", ephemeral=True)
            return
        result = await claim_giveaway(DB_PATH, giveaway_id=row[0], user_id=interaction.user.id)
        await interaction.response.send_message(result.message, ephemeral=True)


def _voice_snapshot(guild):
    snapshot = {}
    for channel in guild.voice_channels:
        eligible = [member for member in channel.members if not member.bot and member.voice
                    and not member.voice.self_deaf and not member.voice.deaf]
        if len(eligible) >= 2:
            snapshot.update({str(member.id): str(channel.id) for member in eligible})
    return snapshot


async def _voice_changed(member, before, after):
    if phase8_enabled():
        await reconcile_voice_snapshot(DB_PATH, member.guild.id, _voice_snapshot(member.guild))


async def _deliver_phase8_outbox(client, *, limit=100):
    async def find_existing(channel, marker):
        async for previous in channel.history(limit=20):
            if marker in str(getattr(previous, "content", "")):
                return previous
        return None

    lease_owner = f"phase8-discord:{uuid.uuid4()}"
    rows = await claim_phase8_outbox(DB_PATH, lease_owner=lease_owner, limit=limit)
    delivered = failed = 0
    for row in rows:
        marker = f"W2E-PHASE8-EVENT:{row['eventKey']}"
        try:
            payload = json.loads(row["payloadJson"])
            if row["entityType"] == "GIVEAWAY_DRAW":
                guild = client.get_guild(int(row["guildId"]))
                giveaway_id = payload.get("giveawayId")
                async with _pool.acquire() as db:
                    await configure_connection(db)
                    channel_row = await db.fetchrow(
                        "SELECT channelId FROM GiveawayV1 WHERE giveawayId=$1 AND guildId=$2", str(giveaway_id), str(row["guildId"]),
                    )
                channel = guild.get_channel(int(channel_row[0])) if guild and channel_row else None
                if channel is None:
                    raise ValueError("giveaway_channel_missing")
                winner = payload.get("winnerId")
                content = (f"Giveaway selesai. Pemenang: <@{winner}>." if winner
                           else "Giveaway selesai tanpa peserta yang memenuhi syarat.")
                view = GiveawayClaimView() if winner else None
            elif row["entityType"] == "OPTIONS_SETTLEMENT":
                user = client.get_user(int(row["userId"])) or await asyncio.wait_for(
                    client.fetch_user(int(row["userId"])), timeout=8,
                )
                channel = await asyncio.wait_for(user.create_dm(), timeout=8)
                content = ("Settlement Eternal Options selesai. "
                           f"Hasil: **{payload.get('resultCode', '-')}**, "
                           f"payout: **{int(payload.get('payoutEcy', 0)):,} ECY**.")
                view = None
            else:
                raise ValueError("unsupported_phase8_outbox_type")
            message = await asyncio.wait_for(find_existing(channel, marker), timeout=8)
            if message is None:
                message = await asyncio.wait_for(
                    channel.send(f"{content}\n-# `{marker}`", view=view), timeout=8,
                )
            await finalize_phase8_outbox(
                DB_PATH, outbox_id=row["outboxId"], lease_owner=lease_owner,
                sent=True, message_id=getattr(message, "id", None),
            )
            delivered += 1
        except (ValueError, json.JSONDecodeError, discord.HTTPException, asyncio.TimeoutError):
            await finalize_phase8_outbox(
                DB_PATH, outbox_id=row["outboxId"], lease_owner=lease_owner,
                sent=False, error_code="discord_delivery_failed",
            )
            failed += 1
        except Exception:
            await finalize_phase8_outbox(
                DB_PATH, outbox_id=row["outboxId"], lease_owner=lease_owner,
                sent=False, error_code="unexpected_delivery_error",
            )
            failed += 1
    return {"scanned": len(rows), "delivered": delivered, "failed": failed}


def setup(tree, client):
    if not ECONOMY_PHASE8_ENABLED:
        return
    giveaway = app_commands.Group(name="giveaway", description="Giveaway ECY Phase 8")
    options = app_commands.Group(name="eternal-options", description="Eternal Options ECY")

    @giveaway.command(name="create", description="Buat Giveaway")
    async def giveaway_create(interaction: discord.Interaction, prize: str, duration_minutes: int):
        if not _is_admin(interaction):
            await send_embed(interaction, "Khusus Administrator.")
            return
        result = await create_giveaway(
            DB_PATH, guild_id=interaction.guild_id, channel_id=interaction.channel_id,
            host_id=interaction.user.id, request_id=str(interaction.id), prize=prize,
            duration_minutes=duration_minutes,
        )
        if not result.ok:
            await send_embed(interaction, result.message)
            return
        view = GiveawayClaimView()
        await send_embed(interaction, f"Giveaway **{prize}** aktif.\n-# ID: `{result.entity_id}`", view=view)
        try:
            message = await interaction.original_response()
            await set_giveaway_message(DB_PATH, result.entity_id, message.id)
        except (discord.HTTPException, AttributeError):
            pass

    @giveaway.command(name="enter", description="Beli satu tiket Giveaway")
    async def giveaway_enter(interaction: discord.Interaction, giveaway_id: str):
        if not phase8_enabled():
            await send_embed(interaction, "Giveaway Phase 8 belum siap.")
            return
        evidence = await _member_evidence(interaction.guild, interaction.user)
        result = await enter_giveaway(
            DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
            giveaway_id=giveaway_id, request_id=str(interaction.id), evidence=evidence,
        )
        await send_embed(interaction, result.message)

    @giveaway.command(name="end", description="Akhiri dan draw Giveaway")
    async def giveaway_end(interaction: discord.Interaction, giveaway_id: str):
        if not _is_admin(interaction):
            await send_embed(interaction, "Khusus Administrator.")
            return
        pool, evidence = await _eligible_pool(interaction.guild, giveaway_id)
        result = await draw_giveaway(
            DB_PATH, guild_id=interaction.guild_id, giveaway_id=giveaway_id,
            request_id=str(interaction.id), eligible_user_ids=pool, participant_evidence=evidence,
        )
        await send_embed(interaction, result.message)

    @giveaway.command(name="cancel", description="Batalkan Giveaway dan refund tiket")
    async def giveaway_cancel(interaction: discord.Interaction, giveaway_id: str, reason: str):
        if not _is_admin(interaction):
            await send_embed(interaction, "Khusus Administrator.")
            return
        result = await cancel_giveaway(
            DB_PATH, guild_id=interaction.guild_id, giveaway_id=giveaway_id,
            actor_id=interaction.user.id, request_id=str(interaction.id), reason=reason,
        )
        await send_embed(interaction, result.message)

    @giveaway.command(name="redraw", description="Redraw dengan bukti terstruktur")
    async def giveaway_redraw(interaction: discord.Interaction, giveaway_id: str, reason_code: str,
                              evidence_reference: str = ""):
        if not _is_admin(interaction):
            await send_embed(interaction, "Khusus Administrator.")
            return
        reason = reason_code.upper()
        metadata, evidence_type = {}, "AUTHORITATIVE_STATE"
        if reason == "RULE_VIOLATION":
            try:
                parts = evidence_reference.strip().split("/")
                channel_id, message_id = int(parts[-2]), int(parts[-1])
                channel = interaction.guild.get_channel(channel_id)
                message = await channel.fetch_message(message_id)
                metadata = {"channelId": str(channel_id), "messageId": str(message_id),
                            "authorId": str(message.author.id),
                            "attachmentIds": [str(item.id) for item in message.attachments],
                            "contentHash": __import__('hashlib').sha256(message.content.encode('utf-8')).hexdigest()}
                evidence_type = "DISCORD_MESSAGE"
            except (ValueError, IndexError, AttributeError, discord.HTTPException):
                await send_embed(interaction, "Referensi bukti Discord tidak dapat diverifikasi.")
                return
        async with _pool.acquire() as db:
            await configure_connection(db)
            prior = await db.fetchrow(
                "SELECT w.winnerId,w.userId,w.status,w.claimDeadline,w.eligibilityEvidenceJson FROM GiveawayV1 g "
                "JOIN GiveawayWinner w ON w.giveawayId=g.giveawayId AND w.userId=g.currentWinnerId "
                "WHERE g.giveawayId=$1", giveaway_id,),
            )
        if not prior:
            await send_embed(interaction, "Pemenang aktif tidak ditemukan.")
            return
        current_winner = interaction.guild.get_member(int(prior[1])
        if reason == "WINNER_DEPARTED":
            if current_winner is not None:
                await send_embed(interaction, "Pemenang masih berada di guild.")
                return
            metadata = {"memberLookupFound": False, "winnerId": prior[0], "userId": prior[1]}
            evidence_type = "GUILD_MEMBER_LOOKUP"
        elif reason == "WINNER_INVALID":
            current_evidence = await _member_evidence(interaction.guild, current_winner)
            if current_evidence.get("eligible"):
                await send_embed(interaction, "Pemenang masih eligible.")
                return
            metadata = {"eligible": False, "winnerId": prior[0], "userId": prior[1],
                        "eligibilityEvidenceHash": current_evidence.get("evidenceHash")}
            evidence_type = "CURRENT_ELIGIBILITY"
        review = await record_winner_review(
            DB_PATH, guild_id=interaction.guild_id, giveaway_id=giveaway_id,
            reviewer_id=interaction.user.id, reason_code=reason,
            evidence_reference=evidence_reference or f"state:{giveaway_id}:{reason}",
            evidence_type=evidence_type,
            prior_winner_state={"winnerId": prior[0], "userId": prior[1], "status": prior[2],
                                "claimDeadline": prior[3], "eligibility": prior[4]}, metadata=metadata,
        )
        if not review.ok:
            await send_embed(interaction, review.message)
            return
        pool, evidence = await _eligible_pool(interaction.guild, giveaway_id)
        result = await redraw_giveaway(
            DB_PATH, guild_id=interaction.guild_id, giveaway_id=giveaway_id,
            reviewer_id=interaction.user.id, review_id=review.entity_id,
            request_id=str(interaction.id), eligible_user_ids=pool, participant_evidence=evidence,
        )
        await send_embed(interaction, result.message)

    async def _show_giveaways(interaction, admin=False):
        if admin and not _is_admin(interaction):
            await send_embed(interaction, "Khusus Administrator.")
            return
        rows = await list_giveaways(DB_PATH, interaction.guild_id)
        text = "\n".join(f"`{row[0]}` | {row[1]} | {row[2]} | {row[3]}" for row in rows) or "Belum ada Giveaway."
        await send_embed(interaction, text)

    @giveaway.command(name="list", description="Daftar Giveaway")
    async def giveaway_list(interaction: discord.Interaction, page: int = 1):
        await _show_giveaways(interaction)

    @giveaway.command(name="history", description="Riwayat Giveaway administratif")
    async def giveaway_history(interaction: discord.Interaction, page: int = 1):
        await _show_giveaways(interaction, admin=True)

    @giveaway.command(name="info", description="Detail Giveaway")
    async def giveaway_info(interaction: discord.Interaction, giveaway_id: str):
        rows = await list_giveaways(DB_PATH, interaction.guild_id, limit=100)
        row = next((item for item in rows if item[0] == giveaway_id), None)
        await send_embed(interaction, "Giveaway tidak ditemukan." if not row else
                         f"`{row[0]}` | {row[1]} | {row[2]} | berakhir {row[3]} | pemenang {row[4] or '-'}")

    @giveaway.command(name="status", description="Status Giveaway")
    async def giveaway_status(interaction: discord.Interaction, giveaway_id: str = ""):
        if giveaway_id:
            await giveaway_info.callback(interaction, giveaway_id)
        else:
            await _show_giveaways(interaction)

    @options.command(name="open", description="Buka Eternal Options")
    async def option_open(interaction: discord.Interaction, asset: str, direction: str,
                          stake: int, duration: int):
        if not phase8_enabled():
            await send_embed(interaction, "Eternal Options belum siap.")
            return
        request_id = _request_id()
        async def settle(request):
            return await open_option(
                DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
                request_id=request, symbol=asset, direction=direction, stake_ecy=stake,
                duration_minutes=duration,
            )
        view = OptionConfirmationView(interaction.user.id, settle, request_id)
        await send_embed(interaction, f"Konfirmasi Options {asset.upper()} {direction.upper()} {stake:,} ECY.", view=view)

    async def _show_positions(interaction, history=False):
        rows = await list_positions(DB_PATH, interaction.guild_id, interaction.user.id, history=history)
        text = "\n".join(f"`{row[0]}` | {row[1]} {row[2]} | {row[3]:,} | {row[4]}" for row in rows) or "Tidak ada posisi."
        await send_embed(interaction, text)

    @options.command(name="positions", description="Posisi Eternal Options aktif")
    async def option_positions(interaction: discord.Interaction):
        await _show_positions(interaction)

    @options.command(name="history", description="Riwayat Eternal Options")
    async def option_history(interaction: discord.Interaction, page: int = 1):
        await _show_positions(interaction, history=True)

    @options.command(name="details", description="Detail posisi Eternal Options")
    async def option_detail(interaction: discord.Interaction, position_id: str):
        row = await option_details(DB_PATH, interaction.guild_id, interaction.user.id, position_id)
        await send_embed(interaction, "Posisi tidak ditemukan." if not row else str(row))

    async def giveaway_autocomplete(interaction, current):
        if not phase8_enabled() or not interaction.guild_id:
            return []
        rows = await list_giveaways(DB_PATH, interaction.guild_id)
        query = current.lower()
        return [app_commands.Choice(name=f"{row[1]} - {row[2]}", value=row[0]) for row in rows
                if not query or query in row[0].lower() or query in row[1].lower()][:25]

    async def symbol_autocomplete(interaction, current):
        if not phase8_enabled() or not interaction.guild_id:
            return []
        async with _pool.acquire() as db:
            await configure_connection(db)
            if not await phase8_capability(db):
                return []
        query = current.lower()
        return [app_commands.Choice(name=f"{symbol} - {value[0]}", value=symbol)
                for symbol, value in CRYPTO_ASSETS.items() if not query or query in symbol.lower() or query in value[0].lower()][:25]

    for command in (giveaway_enter, giveaway_end, giveaway_cancel, giveaway_redraw,
                    giveaway_info, giveaway_status):
        command.autocomplete("giveaway_id")(giveaway_autocomplete)
    option_open.autocomplete("asset")(symbol_autocomplete)
    if tree.get_command("giveaway") is not None or tree.get_command("eternal-options") is not None:
        raise RuntimeError("Duplikasi command Phase 8 terdeteksi sebelum sinkronisasi.")
    tree.add_command(giveaway)
    tree.add_command(options)

    async def giveaway_prefix(message, args):
        interaction = FakeInteraction(message)
        if len(args) == 2 and args[1].isdigit():
            await giveaway_create.callback(interaction, args[0], int(args[1]))
            return
        if not args:
            await message.reply("Gunakan w!giveaway create|enter|end|cancel|redraw|history|list|info|status")
            return
        action, values = args[0].lower(), args[1:]
        callbacks = {"list": giveaway_list.callback, "history": giveaway_history.callback}
        if action in callbacks:
            await callbacks[action](interaction, 1)
        elif action == "create" and len(values) >= 2 and values[-1].isdigit():
            await giveaway_create.callback(interaction, " ".join(values[:-1]), int(values[-1]))
        elif action in {"enter", "end", "info", "status"} and values:
            await {"enter": giveaway_enter.callback, "end": giveaway_end.callback,
                   "info": giveaway_info.callback, "status": giveaway_status.callback}[action](interaction, values[0])
        elif action == "cancel" and len(values) >= 2:
            await giveaway_cancel.callback(interaction, values[0], " ".join(values[1:]))
        elif action == "redraw" and len(values) >= 2:
            await giveaway_redraw.callback(interaction, values[0], values[1], values[2] if len(values) > 2 else "")
        else:
            await message.reply("Argumen Giveaway tidak valid.")

    async def options_prefix(message, args):
        interaction = FakeInteraction(message)
        if not args:
            await message.reply("Gunakan w!eternal-options open|positions|history|details")
            return
        action, values = args[0].lower(), args[1:]
        if action == "open" and len(values) == 4 and values[2].isdigit() and values[3].isdigit():
            await option_open.callback(interaction, values[0], values[1], int(values[2]), int(values[3]))
        elif action == "positions":
            await option_positions.callback(interaction)
        elif action == "history":
            await option_history.callback(interaction, 1)
        elif action == "details" and values:
            await option_detail.callback(interaction, values[0])
        else:
            await message.reply("Argumen Eternal Options tidak valid.")

    register_prefix_command_handler("giveaway", giveaway_prefix)
    register_prefix_command_handler("eternal-options", options_prefix)
    register_voice_state_callback(_voice_changed)

    async def _startup():
        if not phase8_enabled():
            return
        client.add_view(GiveawayClaimView())
        await recover_phase8(DB_PATH)
        await _deliver_phase8_outbox(client)
        for guild in client.guilds:
            await reconcile_voice_snapshot(DB_PATH, guild.id, _voice_snapshot(guild))
        async def worker():
            while not client.is_closed():
                await asyncio.sleep(60)
                now = datetime.now(timezone.utc).isoformat()
                async with _pool.acquire() as db:
                    await configure_connection(db)
                    async with db.execute(
                        "SELECT positionId FROM EternalOptionPosition WHERE status IN ('ACTIVE','SETTLEMENT_PENDING') AND expiresAt<=$1", now,),
                        expired_positions = [row[0] for row in await cursor.fetchall()]
                for position_id in expired_positions:
                    await settle_option(DB_PATH, position_id, now=now)
                for guild in client.guilds:
                    await reconcile_voice_snapshot(DB_PATH, guild.id, _voice_snapshot(guild)
                    async with _pool.acquire() as db:
                        await configure_connection(db)
                        async with db.execute(
                            "SELECT giveawayId FROM GiveawayV1 WHERE guildId=$1 AND status='ACTIVE' AND endsAt<=$2",
                            (str(guild.id), now),
                            ended = [row[0] for row in await cursor.fetchall()]
                    for giveaway_id in ended:
                        pool, evidence = await _eligible_pool(guild, giveaway_id)
                        await draw_giveaway(
                            DB_PATH, guild_id=guild.id, giveaway_id=giveaway_id,
                            request_id=f"scheduler:{giveaway_id}:1", eligible_user_ids=pool,
                            participant_evidence=evidence,
                        )
                await _deliver_phase8_outbox(client)
        asyncio.create_task(worker(), name="phase8-worker")

    register_ready_startup_task(_startup)
