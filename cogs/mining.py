"""Adapter Discord untuk Mining Phase 7."""

import secrets

import discord
from discord import app_commands

from core import DB_PATH, register_prefix_command_handler, send_embed
from economy.constants import (
    CRYPTO_ASSETS, ECONOMY_PHASE2_ENABLED, ECONOMY_PHASE7_ENABLED,
    ECONOMY_V1_ENABLED, MINING_RIG_CATALOG,
)
from economy.mining import (
    change_target, claim_rig, list_rigs, mining_history, mining_readiness,
    pay_maintenance, purchase_rig, rig_details,
)


def phase7_enabled():
    return ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE7_ENABLED


def new_request_id():
    return secrets.token_urlsafe(24)


class MiningConfirmationView(discord.ui.View):
    def __init__(self, actor, callback, *, request_id):
        super().__init__(timeout=90)
        self.actor_id = int(actor.id)
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
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Operasi Mining dibatalkan tanpa reservasi atau debit.", view=self)
        self.stop()


async def _confirm(interaction, description, callback):
    request_id = new_request_id()
    view = MiningConfirmationView(interaction.user, callback, request_id=request_id)
    await send_embed(interaction, f"{description}\nKonfirmasi berlaku 90 detik.", view=view)


def _format_rigs(rows):
    if not rows:
        return "Belum ada rig Mining."
    return "\n".join(
        f"`{row[0]}` | {row[1]} | {row[2]} | {row[3]} | maintenance: {row[4] or '-'}"
        for row in rows
    )


def setup(tree, client):
    group = app_commands.Group(name="mining", description="Mining Crypto berbasis ECY")

    @group.command(name="status", description="Lihat kesiapan Mining")
    async def status(interaction: discord.Interaction):
        state = await mining_readiness(DB_PATH, interaction.guild_id, interaction.user.id)
        await send_embed(interaction, f"Status Mining: **{state['code']}**")

    @group.command(name="catalog", description="Lihat katalog rig Mining")
    async def catalog(interaction: discord.Interaction):
        lines = [f"**{name}** (`{key}`): {price:,} ECY | gross {gross:,}/hari | maintenance {maintenance:,} ECY"
                 for key, (name, price, gross, maintenance) in MINING_RIG_CATALOG.items()]
        await send_embed(interaction, "\n".join(lines))

    @group.command(name="buy", description="Beli rig Mining")
    async def buy(interaction: discord.Interaction, rig: str, target: str = "ETHR"):
        if not phase7_enabled():
            await send_embed(interaction, "Mining Phase 7 belum diaktifkan.")
            return
        rig, target = rig.lower(), target.upper()
        readiness = await mining_readiness(DB_PATH, interaction.guild_id, interaction.user.id)
        if not readiness.get("ready"):
            await send_embed(interaction, f"Pembelian Mining ditolak: **{readiness.get('code')}**.")
            return
        async def callback(request_id):
            return await purchase_rig(DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
                                      request_id=request_id, rig_definition_id=rig, target_symbol=target)
        await _confirm(interaction, f"Konfirmasi pembelian **{rig}** untuk **{target}**.", callback)

    @group.command(name="rigs", description="Lihat rig Mining yang dimiliki")
    async def rigs(interaction: discord.Interaction):
        if not phase7_enabled():
            await send_embed(interaction, "Mining Phase 7 belum diaktifkan.")
            return
        rows = await list_rigs(DB_PATH, interaction.guild_id, interaction.user.id)
        await send_embed(interaction, _format_rigs(rows))

    @group.command(name="target", description="Ganti target rig berdasarkan instance ID")
    async def target(interaction: discord.Interaction, rig_id: str, symbol: str):
        if not phase7_enabled():
            await send_embed(interaction, "Mining Phase 7 belum diaktifkan.")
            return
        symbol = symbol.upper()
        async def callback(request_id):
            return await change_target(DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
                                       request_id=request_id, rig_instance_id=rig_id, target_symbol=symbol)
        await _confirm(interaction, f"Konfirmasi target rig `{rig_id}` menjadi **{symbol}**.", callback)

    @group.command(name="maintenance", description="Bayar maintenance rig selama 24 jam")
    async def maintenance(interaction: discord.Interaction, rig_id: str):
        if not phase7_enabled():
            await send_embed(interaction, "Mining Phase 7 belum diaktifkan.")
            return
        async def callback(request_id):
            return await pay_maintenance(DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
                                         request_id=request_id, rig_instance_id=rig_id)
        await _confirm(interaction, f"Konfirmasi maintenance rig `{rig_id}`.", callback)

    @group.command(name="claim", description="Klaim hasil asset Mining")
    async def claim(interaction: discord.Interaction, rig_id: str):
        if not phase7_enabled():
            await send_embed(interaction, "Mining Phase 7 belum diaktifkan.")
            return
        async def callback(request_id):
            return await claim_rig(DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
                                   request_id=request_id, rig_instance_id=rig_id)
        await _confirm(interaction, f"Konfirmasi klaim rig `{rig_id}`.", callback)

    @group.command(name="details", description="Lihat detail satu rig")
    async def details(interaction: discord.Interaction, rig_id: str):
        if not phase7_enabled():
            await send_embed(interaction, "Mining Phase 7 belum diaktifkan.")
            return
        value = await rig_details(DB_PATH, interaction.guild_id, interaction.user.id, rig_id)
        await send_embed(interaction, "Rig tidak ditemukan." if not value else f"Rig: `{value['rig']}`\nPending: `{value['pending']}`")

    @group.command(name="history", description="Lihat riwayat operasi Mining")
    async def history(interaction: discord.Interaction):
        if not phase7_enabled():
            await send_embed(interaction, "Mining Phase 7 belum diaktifkan.")
            return
        rows = await mining_history(DB_PATH, interaction.guild_id, interaction.user.id)
        text = "\n".join(f"{row[0]} | {row[1]} | {row[3]}" for row in rows) or "Belum ada riwayat Mining."
        await send_embed(interaction, text)

    async def rig_autocomplete(interaction, current):
        if not phase7_enabled() or not interaction.guild_id:
            return []
        rows = await list_rigs(DB_PATH, interaction.guild_id, interaction.user.id)
        query = current.lower()
        return [app_commands.Choice(name=f"{row[1]} {row[2]} - {row[0]}", value=row[0])
                for row in rows if not query or query in row[0].lower() or query in row[1].lower()][:25]

    async def definition_autocomplete(interaction, current):
        if not phase7_enabled() or not interaction.guild_id:
            return []
        ready = await mining_readiness(DB_PATH, interaction.guild_id, interaction.user.id)
        if not ready.get("ready"):
            return []
        query = current.lower()
        return [app_commands.Choice(name=value[0], value=key)
                for key, value in MINING_RIG_CATALOG.items() if not query or query in key or query in value[0].lower()][:25]

    async def symbol_autocomplete(interaction, current):
        if not phase7_enabled() or not interaction.guild_id:
            return []
        query = current.lower()
        return [app_commands.Choice(name=f"{symbol} - {value[0]}", value=symbol)
                for symbol, value in CRYPTO_ASSETS.items() if not query or query in symbol.lower() or query in value[0].lower()][:25]

    buy.autocomplete("rig")(definition_autocomplete)
    buy.autocomplete("target")(symbol_autocomplete)
    target.autocomplete("rig_id")(rig_autocomplete)
    target.autocomplete("symbol")(symbol_autocomplete)
    maintenance.autocomplete("rig_id")(rig_autocomplete)
    claim.autocomplete("rig_id")(rig_autocomplete)
    details.autocomplete("rig_id")(rig_autocomplete)
    tree.add_command(group)

    async def prefix_dispatcher(message, args):
        if not args:
            await message.reply("Gunakan: w!mining status|catalog|buy|rigs|target|maintenance|claim|details|history")
            return
        interaction = __import__("core").FakeInteraction(message)
        action = args[0].lower()
        callbacks = {"status": status.callback, "catalog": catalog.callback, "rigs": rigs.callback,
                     "history": history.callback}
        if action in callbacks:
            await callbacks[action](interaction)
        elif action == "buy" and len(args) >= 2:
            await buy.callback(interaction, args[1], args[2] if len(args) > 2 else "ETHR")
        elif action == "target" and len(args) >= 3:
            await target.callback(interaction, args[1], args[2])
        elif action in ("maintenance", "claim", "details") and len(args) >= 2:
            await {"maintenance": maintenance.callback, "claim": claim.callback,
                   "details": details.callback}[action](interaction, args[1])
        else:
            await message.reply("Argumen Mining tidak valid.")

    register_prefix_command_handler("mining", prefix_dispatcher)
