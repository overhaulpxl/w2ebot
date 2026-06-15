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
            title="🎮 Kategori: RPG & Ekonomi Sultan",
            description="Yuk kumpulkan koin harian, bangun rig tambang kripto fiktif, adopsi pet pembantu, sampai bertarung mengalahkan Raid Boss bersama-sama!",
            color=discord.Color.gold()
        )
        commands = [
            (f"`{BOT_PREFIX}daily`", "Ambil jatah koin harian gratis (Server Booster mendapatkan koin 2x lipat!)."),
            (f"`{BOT_PREFIX}weekly`", "Ambil jatah koin mingguan gratis."),
            (f"`{BOT_PREFIX}work`", "Bekerja di server untuk menghasilkan pundi-pundi koin."),
            (f"`{BOT_PREFIX}rob @user`", "Mencuri koin dari member lain (Hati-hati, awas tertangkap polisi server!)."),
            (f"`{BOT_PREFIX}transfer @user <jumlah>`", "Kirim koin secara aman ke member lain."),
            (f"`{BOT_PREFIX}shop`", "Buka menu toko Sultan Shop untuk membeli item menggunakan tombol interaktif."),
            (f"`{BOT_PREFIX}buy <item>`", "Beli item incaranmu langsung dari toko."),
            (f"`{BOT_PREFIX}inventory`", "Cek isi tas inventory milikmu saat ini."),
            (f"`{BOT_PREFIX}sell <item>`", "Jual kembali item milikmu ke pasar dengan harga setengah koin."),
            (f"`{BOT_PREFIX}buyrig <tier>`", "Beli mesin mining rig pasif untuk mendapatkan koin ETHR otomatis."),
            (f"`{BOT_PREFIX}miner`", "Pantau status farm mining rig pasif milikmu."),
            (f"`{BOT_PREFIX}market`", "Pantau tren naik-turun bursa kripto fiktif terupdate."),
            (f"`{BOT_PREFIX}portfolio`", "Cek kepemilikan dan nilai aset kripto fiktif milikmu."),
            (f"`{BOT_PREFIX}buycoin <symbol> <jumlah>`", "Beli kripto pakai Koin (fee 2%, dukung `all`)."),
            (f"`{BOT_PREFIX}sellcoin <symbol> <jumlah>`", "Jual kripto jadi Koin (fee 2%, dukung `all`)."),
            (f"`{BOT_PREFIX}tebak <1-10>`", "Bermain tebak angka berhadiah 100 koin."),
            (f"`{BOT_PREFIX}cf <head/tail> <bet>`", "Judi lempar koin (Coinflip) menggunakan taruhan koin."),
            (f"`{BOT_PREFIX}blackjack <bet>`", "Bermain blackjack melawan bandar dealer AI."),
            (f"`{BOT_PREFIX}crash <bet>`", "Judi grafik crash untuk melipatgandakan taruhan koinmu."),
            (f"`{BOT_PREFIX}attack`", "Ikut menyerang Boss Raid aktif di server secara ramai-ramai."),
            (f"`{BOT_PREFIX}buypet <slime/wolf/dragon>`", "Adopsi pet agar damage serangan Raid Boss semakin besar."),
            (f"`{BOT_PREFIX}gacha` & `{BOT_PREFIX}box`", "Lakukan gacha waifu impianmu atau buka Box misterius.")
        ]
        for cmd, desc in commands:
            embed.add_field(name=cmd, value=desc, inline=False)
        embed.set_footer(text=f"Gunakan prefix '{BOT_PREFIX}' sebelum menulis command.")
        return embed

    elif category == "ai":
        embed = discord.Embed(
            title="🤖 Kategori: Gemini AI & Sosial",
            description="Tempat mengobrol bareng Gemini AI, bermain kuis trivia, menikah virtual, hingga membuat silsilah keluarga digital.",
            color=discord.Color.green()
        )
        commands = [
            (f"`{BOT_PREFIX}ai <pesan>`", "Tanya apa saja atau mengobrol santai bareng Gemini AI secara instan."),
            (f"`{BOT_PREFIX}listen`", "Panggil bot ke voice channel untuk mengobrol langsung menggunakan suara."),
            (f"`{BOT_PREFIX}setpersona <sifat>`", "Ubah kepribadian / sifat bot AI agar gaya responsnya berbeda."),
            (f"`{BOT_PREFIX}chat <pesan>`", "Aktifkan fitur mengobrol santai tanpa perlu menggunakan prefix."),
            (f"`{BOT_PREFIX}roast @user`", "Minta AI me-roast member lain secara kocak."),
            (f"`{BOT_PREFIX}rate @user`", "Minta AI memberikan rating pesona seseorang (skala 1-10) beserta alasan kocak."),
            (f"`{BOT_PREFIX}shipper @user1 @user2`", "Cek persentase kecocokan jodoh antara dua orang."),
            (f"`{BOT_PREFIX}marry @user`", "Ajak member idamanmu untuk menikah secara resmi di server."),
            (f"`{BOT_PREFIX}divorce`", "Ceraikan pasangan nikah virtualmu saat ini."),
            (f"`{BOT_PREFIX}adopt @user`", "Adopsi member lain untuk dijadikan sebagai anak angkat di silsilah keluarga."),
            (f"`{BOT_PREFIX}family`", "Membuat gambar bagan silsilah keluarga digitalmu berformat PNG."),
            (f"`{BOT_PREFIX}quiz`", "Main kuis trivia interaktif dari AI berhadiah koin.")
        ]
        for cmd, desc in commands:
            embed.add_field(name=cmd, value=desc, inline=False)
        embed.set_footer(text="Ditenagai oleh Google Gemini AI.")
        return embed

    elif category == "utils":
        embed = discord.Embed(
            title="⚙️ Kategori: Utilitas & Keamanan",
            description="Pantau status bot, voice radar, serta fitur khusus server booster.",
            color=discord.Color.light_grey()
        )
        commands = [
            (f"`{BOT_PREFIX}checkbots`", "Pantau bot yang sedang aktif atau idle di server."),
            (f"`{BOT_PREFIX}find @user` atau `{BOT_PREFIX}radar`", "Lacak durasi member lain nongkrong di Voice Channel secara real-time."),
            (f"`{BOT_PREFIX}ping`", "Periksa latensi kecepatan respons bot saat ini."),
            (f"`{BOT_PREFIX}poll`", "Buat voting/polling interaktif untuk komunitas."),
            (f"`{BOT_PREFIX}giveaway`", "Selenggarakan giveaway koin dengan penarikan otomatis (Khusus Admin)."),
            (f"`{BOT_PREFIX}birthday`", "Daftarkan tanggal lahirmu untuk mendapatkan hadiah 1000 Koin saat hari H."),
            (f"`{BOT_PREFIX}kas`", "Cek saldo brankas pajak server (Khusus Admin/Owner)."),
            ("👑 **Booster Perks**", "Kirim gambar ke channel `#custom-role` dengan menyertakan teks Nama Role: [Nama] dan Role Color: [Hex] untuk membuat Custom Role otomatis.")
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
