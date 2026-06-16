import discord
import logging
import os

BOT_PREFIX = os.getenv('BOT_PREFIX', 'w!')

def get_help_embed(category: str, guild=None) -> discord.Embed:
    guild_name = guild.name if guild else "W2E Server"
    
    if category == "main":
        embed = discord.Embed(
            title="📚 Panduan Utama W2E Bot Ecosystem",
            description=(
                "Selamat datang di **Way 2 Eternal (W2E)**! Di sini kamu bisa bermain RPG seru, "
                "mengumpulkan koin, membangun mining rig tambang kripto fiktif, memelihara pet, menikah virtual, "
                "hingga mengobrol santai bareng Gemini AI.\n\n"
                "**Pilih kategori di menu dropdown di bawah untuk melihat daftar command lengkapnya!**"
            ),
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="🤖 W2E Bot (Utama & RPG)",
            value=f"Gunakan prefix `{BOT_PREFIX}` (contoh: `{BOT_PREFIX}daily`, `{BOT_PREFIX}shop`, `{BOT_PREFIX}work`).",
            inline=False
        )
        embed.add_field(
            name="🔗 Link Cepat",
            value=(
                "• **Web Dashboard:** [Klik di sini](http://localhost:8081)\n"
                "• **Support Server:** [Discord Support](https://discord.gg/way2eternal)"
            ),
            inline=False
        )
        embed.set_footer(text=f"Panduan W2E • Server: {guild_name}")
        return embed

    elif category == "rpg":
        embed = discord.Embed(
            title="🎮 Kategori: RPG & Ekonomi",
            description="Kumpulkan koin, bangun mining rig, beli pet, dan lawan Raid Boss bareng.",
            color=discord.Color.gold()
        )
        commands = [
            (f"`{BOT_PREFIX}daily`", "Klaim koin harian (Booster dapat bonus +50%)."),
            (f"`{BOT_PREFIX}weekly`", "Klaim koin mingguan."),
            (f"`{BOT_PREFIX}work`", "Kerja untuk dapat koin."),
            (f"`{BOT_PREFIX}rob @user`", "Coba merampok koin member lain (33% peluang berhasil)."),
            (f"`{BOT_PREFIX}transfer @user <jumlah>`", "Kirim koin ke member lain (pajak 5%)."),
            (f"`{BOT_PREFIX}shop`", "Buka toko item."),
            (f"`{BOT_PREFIX}buy <item>`", "Beli item dari toko."),
            (f"`{BOT_PREFIX}inventory`", "Lihat isi inventory kamu."),
            (f"`{BOT_PREFIX}sell <item>`", "Jual item dengan harga 50%."),
            (f"`{BOT_PREFIX}buyrig <tier> <koin>`", "Beli mining rig untuk koin tertentu (cth: `/buyrig 1 ETHR`)."),
            (f"`{BOT_PREFIX}moverig <tier> <dari> <ke>`", "Pindahkan rig ke koin lain, gratis (cth: `/moverig 2 ETHR LUNA`)."),
            (f"`{BOT_PREFIX}miner`", "Lihat status mining rig kamu."),
            (f"`{BOT_PREFIX}market`", "Lihat harga kripto saat ini."),
            (f"`{BOT_PREFIX}portfolio`", "Lihat kepemilikan dan nilai kripto kamu."),
            (f"`{BOT_PREFIX}buycoin <symbol> <jumlah>`", "Beli kripto pakai koin (fee 2%, dukung `all`)."),
            (f"`{BOT_PREFIX}sellcoin <symbol> <jumlah>`", "Jual kripto jadi koin (fee 2%, dukung `all`)."),
            (f"`{BOT_PREFIX}tebak <1-10>`", "Tebak angka, benar dapat 100 koin."),
            (f"`{BOT_PREFIX}cf <head/tail> <bet>`", "Coinflip — tebak sisi koin."),
            (f"`{BOT_PREFIX}blackjack <bet>`", "Main blackjack lawan bandar."),
            (f"`{BOT_PREFIX}crash <bet>`", "Judi grafik crash."),
            (f"`{BOT_PREFIX}attack`", "Serang Boss Raid yang sedang aktif."),
            (f"`{BOT_PREFIX}buypet <slime/wolf/dragon>`", "Beli pet untuk bonus damage Boss Raid."),
            (f"`{BOT_PREFIX}gacha` & `{BOT_PREFIX}box`", "Gacha item acak atau buka loot box.")
        ]
        for cmd, desc in commands:
            embed.add_field(name=cmd, value=desc, inline=False)
        embed.set_footer(text=f"Gunakan prefix '{BOT_PREFIX}' sebelum menulis command.")
        return embed

    elif category == "ai":
        embed = discord.Embed(
            title="🤖 Kategori: AI & Sosial",
            description="Chat sama AI, kuis, nikah virtual, dan bikin family tree.",
            color=discord.Color.green()
        )
        commands = [
            (f"`{BOT_PREFIX}ai <pesan>`", "Chat dengan AI."),
            (f"`{BOT_PREFIX}listen`", "Panggil bot ke voice channel untuk transkripsi suara."),
            (f"`{BOT_PREFIX}setpersona <sifat>`", "Ubah kepribadian bot AI."),
            (f"`{BOT_PREFIX}chat <pesan>`", "Chat tanpa prefix (mode percakapan)."),
            (f"`{BOT_PREFIX}roast @user`", "Minta AI nge-roast member lain."),
            (f"`{BOT_PREFIX}rate @user`", "Minta AI kasih rating 1-10 buat seseorang beserta alasannya."),
            (f"`{BOT_PREFIX}shipper @user1 @user2`", "Cek persentase kecocokan dua orang."),
            (f"`{BOT_PREFIX}marry @user`", "Ajak member untuk menikah virtual."),
            (f"`{BOT_PREFIX}divorce`", "Ceraikan pasangan virtual kamu."),
            (f"`{BOT_PREFIX}adopt @user`", "Adopsi member sebagai anak."),
            (f"`{BOT_PREFIX}family`", "Lihat family tree kamu (gambar PNG)."),
            (f"`{BOT_PREFIX}quiz`", "Kuis trivia dari AI.")
        ]
        for cmd, desc in commands:
            embed.add_field(name=cmd, value=desc, inline=False)
        embed.set_footer(text="Ditenagai oleh Google Gemini AI.")
        return embed

    elif category == "utils":
        embed = discord.Embed(
            title="⚙️ Kategori: Utilitas",
            description="Tools dan fitur tambahan server.",
            color=discord.Color.light_grey()
        )
        commands = [
            (f"`{BOT_PREFIX}checkbots`", "Lihat bot yang aktif atau idle di server."),
            (f"`{BOT_PREFIX}find @user`", "Cari member di voice channel mana + berapa lama."),
            (f"`{BOT_PREFIX}ping`", "Cek latency bot."),
            (f"`{BOT_PREFIX}poll`", "Buat voting untuk komunitas."),
            (f"`{BOT_PREFIX}giveaway`", "Buat giveaway dengan timer (Admin only)."),
            (f"`{BOT_PREFIX}remindme <menit> <pesan>`", "Set reminder/alarm."),
            (f"`{BOT_PREFIX}birthday <DD-MM>`", "Daftarkan ulang tahun kamu (dapat 1000 Koin saat hari H)."),
            (f"`{BOT_PREFIX}bg <url>`", "Ganti background profile card kamu."),
            (f"`{BOT_PREFIX}kas`", "Cek saldo treasury server (Admin only)."),
            (f"`{BOT_PREFIX}valo`", "Ajak orang main Valorant."),
            ("👑 **Booster Perks**", "Custom role otomatis via channel #custom-role.")
        ]
        for cmd, desc in commands:
            embed.add_field(name=cmd, value=desc, inline=False)
        return embed

class HelpSelect(discord.ui.Select):
    def __init__(self, current_user_id=None):
        self.current_user_id = current_user_id
        options = [
            discord.SelectOption(label="Halaman Utama", description="Menu utama & panduan ekosistem W2E", emoji="🏠", value="main"),
            discord.SelectOption(label="RPG & Ekonomi", description="Mining, blackjack, market, pet, raid boss, dsb", emoji="🎮", value="rpg"),
            discord.SelectOption(label="Gemini AI & Sosial", description="Chatbot, voice listener, quiz, jodoh, persona", emoji="🤖", value="ai"),
            discord.SelectOption(label="Utilitas & Admin", description="Booster custom role, bot tracker, radar", emoji="⚙️", value="utils")
        ]
        super().__init__(placeholder="Pilih kategori panduan...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.current_user_id and interaction.user.id != self.current_user_id:
            await interaction.response.send_message("❌ Hanya pengirim command awal yang bisa berinteraksi dengan menu ini.", ephemeral=True)
            return

        value = self.values[0]
        embed = get_help_embed(value, interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self.view)

class W2EHelpView(discord.ui.View):
    def __init__(self, current_user_id=None):
        super().__init__(timeout=180)
        self.current_user_id = current_user_id
        self.message = None

        # Add the dropdown select menu
        self.add_item(HelpSelect(current_user_id))

        # Add quick link buttons
        self.add_item(discord.ui.Button(label="Support Server", url="https://discord.gg/way2eternal", style=discord.ButtonStyle.link, emoji="💬"))
        self.add_item(discord.ui.Button(label="Dashboard", url="http://localhost:8081", style=discord.ButtonStyle.link, emoji="📊"))

    async def on_timeout(self):
        # Disable select menu on timeout and push the change to Discord
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

async def send_w2e_help(target, current_user_id=None):
    """
    Kirim menu bantuan W2E interaktif menggunakan Dropdown dan Button.
    Mendukung target berupa:
      - discord.Interaction (Slash Command)
      - discord.ext.commands.Context (Prefix Command di commands.Bot)
      - discord.Message (on_message di discord.Client)
    """
    guild = None
    user_id = current_user_id
    
    if isinstance(target, discord.Interaction):
        guild = target.guild
        if not user_id:
            user_id = target.user.id
    elif hasattr(target, 'guild'):
        guild = target.guild
        if not user_id and hasattr(target, 'author'):
            user_id = target.author.id

    embed = get_help_embed("main", guild)
    view = W2EHelpView(user_id)
    
    if isinstance(target, discord.Interaction):
        if target.response.is_done():
            view.message = await target.followup.send(embed=embed, view=view, wait=True)
        else:
            await target.response.send_message(embed=embed, view=view)
            view.message = await target.original_response()
    elif hasattr(target, 'send'): # commands.Context or channel
        view.message = await target.send(embed=embed, view=view)
    elif isinstance(target, discord.Message):
        view.message = await target.channel.send(embed=embed, view=view)
    else:
        logging.error("Target tidak didukung oleh send_w2e_help.")
