import discord
import logging
import os

BOT_PREFIX = os.getenv("BOT_PREFIX", "w!")


def get_help_embed(category: str, guild=None) -> discord.Embed:
    guild_name = guild.name if guild else "W2E Server"

    if category == "main":
        embed = discord.Embed(
            title="Panduan Utama W2E Bot Ecosystem",
            description=(
                "Selamat datang di **Way 2 Eternal (W2E)**. Di sini kamu bisa bermain RPG, "
                "mengumpulkan koin, membangun mining rig kripto fiktif, memakai fitur sosial, "
                "dan menjalankan sistem middleman deal.\n\n"
                "**Pilih kategori di menu dropdown di bawah untuk melihat daftar command.**"
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="W2E Bot (Utama & RPG)",
            value=f"Gunakan prefix `{BOT_PREFIX}`. Contoh: `{BOT_PREFIX}daily`, `{BOT_PREFIX}shop`, `{BOT_PREFIX}work`.",
            inline=False,
        )
        embed.add_field(
            name="Link Cepat",
            value=(
                "- **Web Dashboard:** [Klik di sini](http://localhost:8081)\n"
                "- **Support Server:** [Discord Support](https://discord.gg/way2eternal)"
            ),
            inline=False,
        )
        embed.add_field(
            name="Kategori Panduan",
            value=(
                "**Halaman Utama** - Menu utama & panduan ekosistem W2E\n"
                "**RPG & Ekonomi** - Mining, blackjack, market, pet, raid boss, dsb\n"
                "**Gemini AI & Sosial** - Chatbot, voice listener, quiz, jodoh, persona\n"
                "🛡️ **Middleman & Vouch** - Deal, payment proof, dispute, vouch, trust profile, reports, panels\n"
                "**Utilitas & Admin** - Booster custom role, bot tracker, radar"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Panduan W2E - Server: {guild_name}")
        return embed

    if category == "rpg":
        embed = discord.Embed(
            title="Kategori: RPG & Ekonomi",
            description="Kumpulkan koin, bangun mining rig, beli pet, dan lawan Raid Boss bareng.",
            color=discord.Color.gold(),
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
            (f"`{BOT_PREFIX}buyrig <tier> <koin>`", "Beli mining rig untuk koin tertentu."),
            (f"`{BOT_PREFIX}moverig <tier> <dari> <ke>`", "Pindahkan rig ke koin lain."),
            (f"`{BOT_PREFIX}miner`", "Lihat status mining rig kamu."),
            (f"`{BOT_PREFIX}market`", "Lihat harga kripto saat ini."),
            (f"`{BOT_PREFIX}portfolio`", "Lihat kepemilikan dan nilai kripto kamu."),
            (f"`{BOT_PREFIX}buycoin <symbol> <jumlah>`", "Beli kripto pakai koin (fee 2%, dukung `all`)."),
            (f"`{BOT_PREFIX}sellcoin <symbol> <jumlah>`", "Jual kripto jadi koin (fee 2%, dukung `all`)."),
            (f"`{BOT_PREFIX}tebak <1-10>`", "Tebak angka, benar dapat 100 koin."),
            (f"`{BOT_PREFIX}cf <head/tail> <bet>`", "Coinflip - tebak sisi koin."),
            (f"`{BOT_PREFIX}blackjack <bet>`", "Main blackjack lawan bandar."),
            (f"`{BOT_PREFIX}crash <bet>`", "Judi grafik crash."),
            (f"`{BOT_PREFIX}attack`", "Serang Boss Raid yang sedang aktif."),
            (f"`{BOT_PREFIX}buypet <slime/wolf/dragon>`", "Beli pet untuk bonus damage Boss Raid."),
            (f"`{BOT_PREFIX}gacha` & `{BOT_PREFIX}box`", "Gacha item acak atau buka loot box."),
        ]
        for cmd, desc in commands:
            embed.add_field(name=cmd, value=desc, inline=False)
        embed.add_field(
            name="Economy V1 Phase 1-4",
            value=(
                "Fondasi wallet ETM/ECY, ledger, treasury, dan migration dry-run telah tersedia "
                "namun **belum diaktifkan untuk production**. Phase 2 menyiapkan profile RPG, "
                "Daily/Weekly, Work, transfer ETM, dan Eternal Exchange. Phase 3 menyiapkan starter, "
                "equipment, enhancement, pet, Hunt, Dungeon, Boss, dan Quest. Phase 4 menyiapkan "
                "Eternal Marketplace dengan escrow dan settlement ETM. Command legacy tetap berjalan "
                "selama feature flag nonaktif; seluruh flag Economy default-nya `false`."
            ),
            inline=False,
        )
        embed.set_footer(text=f"Gunakan prefix `{BOT_PREFIX}` sebelum menulis command.")
        return embed

    if category == "ai":
        embed = discord.Embed(
            title="Kategori: AI & Sosial",
            description="Chat sama AI, kuis, nikah virtual, dan bikin family tree.",
            color=discord.Color.green(),
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
            (f"`{BOT_PREFIX}quiz`", "Kuis trivia dari AI."),
        ]
        for cmd, desc in commands:
            embed.add_field(name=cmd, value=desc, inline=False)
        embed.set_footer(text="Ditenagai oleh Google Gemini AI.")
        return embed

    if category == "middleman":
        embed = discord.Embed(
            title="🛡️ Middleman & Vouch",
            description="Deal, payment proof, dispute, vouch, trust profile, reports, dan panels.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Deal Basics",
            value=(
                "`/deal start buyer:@buyer seller:@seller`\n"
                f"`{BOT_PREFIX}deal start @buyer @seller`\n"
                "`/deal info deal_id:<id>`\n"
                f"`{BOT_PREFIX}deal info <deal_id>`\n\n"
                "Start middleman deal di channel saat ini. Executor menjadi middleman."
            ),
            inline=False,
        )
        embed.add_field(
            name="Deal Flow",
            value=(
                "Form -> Payment Instruction -> Kirim Bukti Payment -> Dana Masuk -> "
                "Buyer Confirm -> Kirim Data Pencairan -> Done & Transfer Sukses\n\n"
                "Tahap Item Sent sudah dihapus. Buyer Confirm dapat diproses oleh buyer atau middleman/staff. "
                "Gunakan tombol seperti biasa. Jika tombol error atau tidak bisa ditekan, gunakan `/deal status` "
                "untuk melihat posisi transaksi, lalu gunakan `/deal next` atau `/deal action`."
            ),
            inline=False,
        )
        embed.add_field(
            name="Button Fallback",
            value=(
                "`/deal status` | `/deal next` | `/deal action`\n"
                "`/deal refresh` | `/deal recover`\n"
                f"`{BOT_PREFIX}deal status` | `{BOT_PREFIX}deal next` | `{BOT_PREFIX}deal action <action>`\n\n"
                "`refresh` memperbaiki tampilan deal. `recover` melakukan targeted recovery tanpa membocorkan data sensitif."
            ),
            inline=False,
        )
        embed.add_field(
            name="Payment Profile",
            value=(
                "`/deal payment-config set` | `/deal payment-config image`\n"
                "`/deal payment-config show` | `/deal payment-config enable`\n"
                "`/deal payment-config disable` | `/deal payment-config clear-image`\n\n"
                "Profile payment bersifat per admin/middleman user. `set` membuka modal, payment text bisa satu atau banyak akun, dan image QRIS/payment bersifat opsional. `w!deal payment-config set` akan mengarahkan ke slash command. Instruksi otomatis muncul setelah form selesai, dan detail payment hanya tampil di private deal channel atau response config staff-only/ephemeral/DM."
            ),
            inline=False,
        )
        embed.add_field(
            name="Dispute",
            value=(
                "`/deal action action:dispute deal_id:<id> reason:<reason>`\n"
                "`/deal action action:resolve-dispute deal_id:<id>`\n"
                f"`{BOT_PREFIX}deal action dispute <deal_id> <reason>`\n"
                f"`{BOT_PREFIX}deal action resolve-dispute <deal_id>`\n"
                f"`{BOT_PREFIX}deal resolve-dispute <deal_id> <resolution>`\n\n"
                "Dispute hanya dibuka oleh middleman/staff. Buyer/seller jelaskan kendala di ticket."
            ),
            inline=False,
        )
        embed.add_field(
            name="Verified Deal Vouch",
            value=(
                "`/vouch`\n"
                f"`{BOT_PREFIX}deal vouch <deal_id> @user <rating> <review>`\n\n"
                "Verified vouch berasal dari deal yang sudah Completed."
            ),
            inline=False,
        )
        embed.add_field(
            name="Manual Vouch",
            value=(
                "`/deal vouch-panel setup channel:#channel`\n"
                "`/deal vouch-review-channel set channel:#channel`\n"
                f"`{BOT_PREFIX}deal vouch-panel setup #channel`\n"
                f"`{BOT_PREFIX}deal vouch-review-channel set #channel`\n\n"
                "Member pakai tombol Submit Vouch. Staff approve/reject dari review channel."
            ),
            inline=False,
        )
        embed.add_field(
            name="Reputation",
            value=(
                "`/vouchleaderboard`\n"
                f"`{BOT_PREFIX}deal leaderboard`\n"
                f"`{BOT_PREFIX}deal rep @user`\n"
                f"`{BOT_PREFIX}deal rank @user`\n"
                f"`{BOT_PREFIX}deal vouches @user`\n\n"
                "Lihat leaderboard trusted vouch, trust profile, rank, dan riwayat vouch."
            ),
            inline=False,
        )
        embed.add_field(
            name="Scammer Report & Trust",
            value=(
                "`/deal scam-report-panel setup channel:#channel`\n"
                "`/deal scam-report-review-channel set channel:#channel`\n"
                "`/deal trust-status view user:@user`\n"
                "`/deal trust-status set user:@user status:<clear|under_review|blacklisted> reason:<reason>`\n"
                "`/deal trust-status clear user:@user reason:<reason>`\n\n"
                "Member pakai tombol Report Scammer. Staff review dan update status trust."
            ),
            inline=False,
        )
        embed.add_field(
            name="Audit & Archive",
            value=(
                "`/deal audit-log set channel:#channel` | `/deal audit-log status` | `/deal audit-log disable`\n"
                "`/deal archive info deal_id:<id>` | `/deal archive search user:@user`\n"
                "`/deal archive recent` | `/deal archive backfill`\n"
                "`/deal recover-buttons scope:<all|active-deals|panels|reviews> scan_limit:<angka>`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Public Trust Panels",
            value=(
                "`/deal panel leaderboard action:set channel:#channel`\n"
                "`/deal panel leaderboard action:refresh|disable|status`\n"
                "`/deal panel stats action:set channel:#channel`\n"
                "`/deal panel stats action:refresh|disable|status`\n"
                "`/deal panel recent-vouches action:set channel:#channel`\n"
                "`/deal panel recent-vouches action:disable|status`\n"
                "`/deal panel completed-deals action:set channel:#channel`\n"
                "`/deal panel completed-deals action:disable|status`\n"
                "Flat slash lama tetap tersedia: `leaderboard-set`, `stats-set`, `refresh`, `disable`."
            ),
            inline=False,
        )
        embed.add_field(
            name="Staff Operation Panels",
            value=(
                "`/deal panel middleman-status-set channel:#channel` | `/deal panel middleman-status-status`\n"
                "`/deal panel active-deals-set channel:#channel` | `/deal panel active-deals-status`\n"
                "`/deal panel dispute-board-set channel:#channel` | `/deal panel dispute-board-status`\n"
                "`/deal panel trust-warning-set channel:#channel` | `/deal panel trust-warning-status`\n"
                "`/deal panel refresh panel:<panel>` | `/deal panel disable panel:<panel>`\n"
                "`/deal mm-status set status:<available|busy|offline|unavailable> note:<opsional>`\n"
                "`/deal mm-status clear`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Command Ownership",
            value=(
                "`/leaderboard` dan "
                f"`{BOT_PREFIX}leaderboard` = RPG leaderboard\n"
                "`/vouchleaderboard` dan "
                f"`{BOT_PREFIX}deal leaderboard` = Trusted Vouch leaderboard\n"
                f"`{BOT_PREFIX}rank` = RPG rank\n"
                f"`{BOT_PREFIX}deal rank` = Trust/Vouch rank"
            ),
            inline=False,
        )
        embed.add_field(
            name="Prefix Reminder",
            value=(
                f"Sebagian besar command staff juga mendukung format `{BOT_PREFIX}deal ...`. "
                "Gunakan slash command untuk melihat nama opsi yang lengkap."
            ),
            inline=False,
        )
        embed.set_footer(text="Data sensitif seperti proof, payout, dan evidence tidak ditampilkan di panel publik.")
        return embed

    if category == "utils":
        embed = discord.Embed(
            title="Kategori: Utilitas",
            description="Tools dan fitur tambahan server.",
            color=discord.Color.light_grey(),
        )
        commands = [
            (f"`{BOT_PREFIX}checkbots`", "Lihat bot yang aktif atau idle di server."),
            (f"`{BOT_PREFIX}find @user`", "Cari member di voice channel mana + berapa lama."),
            (f"`{BOT_PREFIX}ping`", "Cek latency bot."),
            (f"`{BOT_PREFIX}poll`", "Buat voting untuk komunitas."),
            (f"`{BOT_PREFIX}giveaway`", "Buat giveaway dengan timer (Admin only)."),
            (f"`{BOT_PREFIX}remindme <menit> <pesan>`", "Set reminder/alarm."),
            (f"`{BOT_PREFIX}birthday <DD-MM>`", "Daftarkan ulang tahun kamu."),
            (f"`{BOT_PREFIX}bg <url>`", "Ganti background profile card kamu."),
            (f"`{BOT_PREFIX}kas`", "Cek saldo treasury server (Admin only)."),
            (f"`{BOT_PREFIX}valo`", "Ajak orang main Valorant."),
            ("**Booster Perks**", "Custom role otomatis via channel #custom-role."),
        ]
        for cmd, desc in commands:
            embed.add_field(name=cmd, value=desc, inline=False)
        return embed

    return get_help_embed("main", guild)


class HelpSelect(discord.ui.Select):
    def __init__(self, current_user_id=None):
        self.current_user_id = current_user_id
        options = [
            discord.SelectOption(label="Halaman Utama", description="Menu utama & panduan ekosistem W2E", value="main"),
            discord.SelectOption(label="RPG & Ekonomi", description="Mining, blackjack, market, pet, raid boss, dsb", value="rpg"),
            discord.SelectOption(label="Gemini AI & Sosial", description="Chatbot, voice listener, quiz, jodoh, persona", value="ai"),
            discord.SelectOption(label="Middleman & Vouch", description="Deal, vouch, trust profile, reports, panels", emoji="🛡️", value="middleman"),
            discord.SelectOption(label="Utilitas & Admin", description="Booster custom role, bot tracker, radar", value="utils"),
        ]
        super().__init__(
            placeholder="Pilih kategori panduan...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="w2e_help_select",
        )

    async def callback(self, interaction: discord.Interaction):
        if self.current_user_id and interaction.user.id != self.current_user_id:
            await interaction.response.send_message("Hanya pengirim command awal yang bisa berinteraksi dengan menu ini.", ephemeral=True)
            return

        value = self.values[0]
        embed = get_help_embed(value, interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self.view)


class W2EHelpView(discord.ui.View):
    def __init__(self, current_user_id=None):
        super().__init__(timeout=180)
        self.current_user_id = current_user_id
        self.message = None

        self.add_item(HelpSelect(current_user_id))
        self.add_item(discord.ui.Button(label="Support Server", url="https://discord.gg/way2eternal", style=discord.ButtonStyle.link))
        self.add_item(discord.ui.Button(label="Dashboard", url="http://localhost:8081", style=discord.ButtonStyle.link))

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class ExpiredHelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Menu kadaluarsa", description="Jalankan /help atau w!help lagi.", value="expired")
        ]
        super().__init__(
            placeholder="Menu help sudah kadaluarsa...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="w2e_help_expired_select",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Menu help sudah kadaluarsa. Jalankan `/help` atau `w!help` lagi.", ephemeral=True)


class W2EHelpExpiredView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ExpiredHelpSelect())


async def send_w2e_help(target, current_user_id=None):
    """
    Kirim menu bantuan W2E interaktif menggunakan dropdown dan button.
    Mendukung discord.Interaction, Context/channel-like target, dan discord.Message.
    """
    guild = None
    user_id = current_user_id

    if isinstance(target, discord.Interaction):
        guild = target.guild
        if not user_id:
            user_id = target.user.id
    elif hasattr(target, "guild"):
        guild = target.guild
        if not user_id and hasattr(target, "author"):
            user_id = target.author.id

    embed = get_help_embed("main", guild)
    view = W2EHelpView(user_id)

    if isinstance(target, discord.Interaction):
        if target.response.is_done():
            view.message = await target.followup.send(embed=embed, view=view, wait=True)
        else:
            await target.response.send_message(embed=embed, view=view)
            view.message = await target.original_response()
    elif hasattr(target, "send"):
        view.message = await target.send(embed=embed, view=view)
    elif isinstance(target, discord.Message):
        view.message = await target.channel.send(embed=embed, view=view)
    else:
        logging.error("Target tidak didukung oleh send_w2e_help.")
