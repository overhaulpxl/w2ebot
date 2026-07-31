import discord
import random


def _casino_receipt_text(result):
    receipt = result.receipt or {}
    if not result.ok:
        return result.message
    if result.code == "active":
        hands = receipt.get("playerHands", [])
        cards = " | ".join(", ".join(hand) for hand in hands) or "-"
        actions = ", ".join(receipt.get("allowedActions", [])) or "menunggu settlement"
        return (f"**Blackjack Casino V1**\nKartu kamu: **{cards}**\n"
                f"Dealer: **{receipt.get('dealerUpCard', '-')}**\nAksi: **{actions}**")
    game = receipt.get("game", "Casino")
    stake = int(receipt.get("stakeEcy", 0))
    payout = int(receipt.get("grossPayoutEcy", 0))
    detail = receipt.get("result", {})
    if game == "SLOT":
        extra = " | ".join(detail.get("reels", []))
    elif game == "COINFLIP":
        extra = f"Hasil: {detail.get('result', '-')}"
    elif game == "RPS":
        extra = f"Lawan: {detail.get('opponent', '-')}"
    elif game == "NUMBER":
        extra = f"Angka: {detail.get('result', '-')}"
    elif game == "GACHA":
        extra = str(detail.get("label", "-"))
    elif game == "BOX":
        extra = "Loot Box selesai dibuka."
    else:
        extra = "Blackjack selesai."
    return f"**{game} Casino V1**\n{extra}\nStake: **{stake:,} ECY**\nPayout: **{payout:,} ECY**"


class CasinoBlackjackView(discord.ui.View):
    def __init__(self, user, session_id):
        super().__init__(timeout=600)
        self.user = user
        self.session_id = str(session_id)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Sesi Blackjack ini bukan milik kamu.", ephemeral=True)
            return False
        return True

    async def _act(self, interaction, action):
        from core import DB_PATH
        from economy.casino import blackjack_action
        await interaction.response.defer(ephemeral=True)
        result = await blackjack_action(
            DB_PATH, session_id=self.session_id, user_id=interaction.user.id,
            action=action, action_request_id=str(interaction.id),
        )
        if result.code == "committed":
            for child in self.children:
                child.disabled = True
        await interaction.edit_original_response(content=_casino_receipt_text(result), view=self)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction, button):
        await self._act(interaction, "HIT")

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction, button):
        await self._act(interaction, "STAND")

    @discord.ui.button(label="Double", style=discord.ButtonStyle.success)
    async def double(self, interaction, button):
        await self._act(interaction, "DOUBLE")

    @discord.ui.button(label="Split", style=discord.ButtonStyle.success)
    async def split(self, interaction, button):
        await self._act(interaction, "SPLIT")


class CasinoConfirmationView(discord.ui.View):
    def __init__(self, user, *, request_id, game, stake, payload):
        super().__init__(timeout=90)
        self.user = user
        self.request_id = str(request_id)
        self.game = str(game)
        self.stake = int(stake)
        self.payload = dict(payload)
        self.completed = False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Konfirmasi ini hanya untuk pemohon.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Konfirmasi", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        from core import DB_PATH
        from economy.casino import reserve_session
        await interaction.response.defer(ephemeral=True)
        if self.completed:
            result_text = "Konfirmasi ini sudah diproses."
            await interaction.edit_original_response(content=result_text, view=self)
            return
        self.completed = True
        for child in self.children:
            child.disabled = True
        result = await reserve_session(
            DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
            request_id=self.request_id, game=self.game, stake=self.stake, payload=self.payload,
        )
        if result.ok and result.code == "active" and self.game == "BLACKJACK":
            view = CasinoBlackjackView(self.user, result.session_id)
            await interaction.edit_original_response(content=_casino_receipt_text(result), view=view)
            return
        await interaction.edit_original_response(content=_casino_receipt_text(result), view=self)

    @discord.ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self.completed = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Permintaan Casino dibatalkan sebelum reservasi.", view=self)


async def _dispatch(interaction, command_name, *args):
    # `client` is a plain discord.Client; the CommandTree lives as a module
    # global in core, so resolve commands through it directly.
    from core import tree
    cmd = tree.get_command(command_name)
    if cmd is None:
        await interaction.response.send_message(
            f"❌ Perintah `{command_name}` tidak tersedia.", ephemeral=True)
        return
    await cmd.callback(interaction, *args)

class ShopView(discord.ui.View):
    def __init__(self, user, premium_since):
        super().__init__(timeout=90)
        self.user = user
        self.premium_since = premium_since
        self.update_buttons()

    def update_buttons(self):
        from core import SHOP_ITEMS
        for item_id, item_data in SHOP_ITEMS.items():
            price = item_data['price']
            if self.premium_since:
                price = int(price * 0.8)
            
            # Simple emoji extract or fallback
            emoji = item_data['name'].split()[0] if item_data['name'].split() else "📦"
            label = f"Beli {item_data['name'].replace(emoji, '').strip()} ({price} Koin)"
            
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.success,
                emoji=emoji,
                custom_id=f"shop_buy_{item_id}"
            )
            button.callback = self.make_buy_callback(item_id, price, item_data['name'])
            self.add_item(button)

    def make_buy_callback(self, item_id, price, item_name):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user.id:
                await interaction.response.send_message("❌ Ini bukan menu shop Anda.", ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            from core import try_spend, load_json, save_json

            uid = str(interaction.user.id)
            # Debit atomik dulu (anti double-spend via klik beruntun / prefix+slash).
            if not await try_spend(uid, price, interaction.user.display_name):
                embed = discord.Embed(description=f"❌ Koin kamu tidak cukup! Harga {item_name} adalah {price} Koin.", color=discord.Color.red())
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            users = await load_json('users.json')
            if uid not in users: users[uid] = {'items': {}}
            if 'items' not in users[uid]: users[uid]['items'] = {}

            users[uid]['items'][item_id] = users[uid]['items'].get(item_id, 0) + 1
            await save_json('users.json', users)

            embed = discord.Embed(description=f"🛍️ Berhasil membeli **{item_name}** seharga {price} Koin! (Cek `/inventory`)", color=discord.Color.green())
            await interaction.followup.send(embed=embed, ephemeral=True)
        return callback

class ProfileView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=120)
        self.user = user

    @discord.ui.button(label="🎒 Inventory", style=discord.ButtonStyle.primary, emoji="🎒")
    async def view_inventory(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan profile Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "inventory")

    @discord.ui.button(label="⛏️ Miner Rigs", style=discord.ButtonStyle.success, emoji="⛏️")
    async def view_miner(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan profile Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "miner")

    @discord.ui.button(label="👪 Silsilah Keluarga", style=discord.ButtonStyle.secondary, emoji="👪")
    async def view_family(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan profile Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "family")

    @discord.ui.button(label="🛒 Buka Toko", style=discord.ButtonStyle.danger, emoji="🛒")
    async def open_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan profile Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "shop")

class BlackjackView(discord.ui.View):
    def __init__(self, user, bet):
        super().__init__(timeout=90)
        self.user = user
        self.bet = bet

    @discord.ui.button(label="Main Lagi 🃏", style=discord.ButtonStyle.success)
    async def play_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan game Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "blackjack", self.bet)

class SlotView(discord.ui.View):
    def __init__(self, user, bet):
        super().__init__(timeout=90)
        self.user = user
        self.bet = bet

    @discord.ui.button(label="Putar Lagi 🎰", style=discord.ButtonStyle.success)
    async def spin_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan game Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "slot", self.bet)

class GachaView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=90)
        self.user = user

    @discord.ui.button(label="Gacha Lagi 💫", style=discord.ButtonStyle.success)
    async def roll_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan gacha Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "gacha")

class BoxView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=90)
        self.user = user

    @discord.ui.button(label="Buka Lagi 📦", style=discord.ButtonStyle.success)
    async def open_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan loot box Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "box")

class MarketView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=90)
        self.user = user

    @discord.ui.button(label="🔄 Refresh Harga", style=discord.ButtonStyle.secondary)
    async def refresh_market(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan menu market Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "market")

    @discord.ui.button(label="💼 Cek Portfolio", style=discord.ButtonStyle.primary)
    async def check_portfolio(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan menu market Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "portfolio")

class MinerView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=90)
        self.user = user

    @discord.ui.button(label="Beli Rig T1 ETHR (10k)", style=discord.ButtonStyle.primary, custom_id="buy_rig_1")
    async def buy_rig_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan miner Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "buyrig", 1, "ETHR")

    @discord.ui.button(label="Beli Rig T2 ETHR (30k)", style=discord.ButtonStyle.success, custom_id="buy_rig_2")
    async def buy_rig_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan miner Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "buyrig", 2, "ETHR")

    @discord.ui.button(label="Beli Rig T3 ETHR (80k)", style=discord.ButtonStyle.danger, custom_id="buy_rig_3")
    async def buy_rig_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan miner Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "buyrig", 3, "ETHR")
