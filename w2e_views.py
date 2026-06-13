import discord
import random


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
            from core import get_discord_stat, update_discord_stat, load_json, save_json, DB_PATH
            import sqlite3
            
            uid = str(interaction.user.id)
            stat = await get_discord_stat(uid)
            if stat['coins'] < price:
                embed = discord.Embed(description=f"❌ Koin kamu tidak cukup! Harga {item_name} adalah {price} Koin.", color=discord.Color.red())
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
                
            stat['coins'] -= price
            users = await load_json('users.json')
            if uid not in users: users[uid] = {'balance': 0, 'items': {}}
            if 'items' not in users[uid]: users[uid]['items'] = {}
            
            users[uid]['items'][item_id] = users[uid]['items'].get(item_id, 0) + 1
            await save_json('users.json', users)
            await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            
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

    @discord.ui.button(label="Beli Rig Tier 1 (10k)", style=discord.ButtonStyle.primary, custom_id="buy_rig_1")
    async def buy_rig_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan miner Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "buyrig", 1)

    @discord.ui.button(label="Beli Rig Tier 2 (30k)", style=discord.ButtonStyle.success, custom_id="buy_rig_2")
    async def buy_rig_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan miner Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "buyrig", 2)

    @discord.ui.button(label="Beli Rig Tier 3 (80k)", style=discord.ButtonStyle.danger, custom_id="buy_rig_3")
    async def buy_rig_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ini bukan miner Anda.", ephemeral=True)
            return
        await _dispatch(interaction, "buyrig", 3)
