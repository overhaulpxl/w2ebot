import discord
from core import *
import logging
import random, asyncio, sqlite3
from datetime import datetime

def setup(tree, client):
    try:
        from w2e_help import W2EHelpExpiredView
        client.add_view(W2EHelpExpiredView())
        logging.info("Registered persistent view: W2EHelpExpiredView")
    except Exception as e:
        logging.error("Failed to register W2EHelpExpiredView exception=%s", type(e).__name__)

    @tree.command(name="find", description="Cari tahu member sedang berada di Voice Channel mana")
    async def slash_find(interaction: discord.Interaction, target: discord.Member):
        await interaction.response.defer()
        if target.voice and target.voice.channel:
            channel = target.voice.channel
            link = f"https://discord.com/channels/{interaction.guild.id}/{channel.id}"
            duration_str = "Tidak diketahui"
            if target.id in voice_join_times:
                delta = datetime.now() - voice_join_times[target.id]
                minutes = int(delta.total_seconds() // 60)
                duration_str = f"{minutes} menit"
            await send_embed(interaction, f"{target.display_name} sedang berada di voice channel **{channel.name}** selama {duration_str}.\nJoin link: {link}")
        else:
            await send_embed(interaction, f"{target.display_name} tidak sedang berada di voice channel mana pun.")
    
    @tree.command(name="about", description="Menampilkan informasi tentang bot ini.")
    async def slash_about(interaction: discord.Interaction):
        embed = discord.Embed(
            title="Tentang Way 2 Eternal Bot",
            description="Bot Discord serbaguna dengan AI Gemini, RPG, Economy, dan Web Dashboard terintegrasi.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Developer", value="W2E Dev Team", inline=True)
        embed.add_field(name="Library", value="discord.py, asyncpg", inline=True)
        embed.add_field(name="Database", value="PostgreSQL (Supabase)", inline=True)
        embed.add_field(name="Versi", value="Phase 9C", inline=True)
        embed.set_footer(text="Ditenagai oleh Google Gemini & Next.js")
        await interaction.response.send_message(embed=embed)

    @tree.command(name="checkbots", description="Pantau aktivitas bot musik di server")
    async def slash_radar(interaction: discord.Interaction):
        await interaction.response.defer()
        active_bots = []
        idle_bots = []
        
        def is_music_bot(m):
            for r in m.roles:
                if "+ music bot" in r.name.lower():
                    return True
            return False
            
        for member in interaction.guild.members:
            if member.bot and is_music_bot(member):
                if member.voice and member.voice.channel:
                    active_bots.append(f"🤖 **{member.display_name}** sedang di 🔊 **{member.voice.channel.name}**")
                else:
                    idle_bots.append(member.display_name)
                    
        res = "📡 **RADAR BOT MUSIK & SISTEM** 📡\n\n"
        if active_bots:
            res += "**🟢 Sedang Aktif (Di Dalam Voice):**\n" + "\n".join(active_bots) + "\n\n"
        else:
            res += "**🟢 Sedang Aktif (Di Dalam Voice):**\n- Tidak ada bot yang aktif di Voice Channel.\n\n"
            
        if idle_bots:
            if len(idle_bots) > 15:
                idle_str = ", ".join(idle_bots[:15]) + f" ... dan {len(idle_bots)-15} lainnya."
            else:
                idle_str = ", ".join(idle_bots)
            res += f"**💤 Idle (Tidur):**\n{idle_str}"
            
        await send_embed(interaction, res)
    
    @tree.command(name="ping", description="Cek latency bot")
    async def slash_ping(interaction: discord.Interaction):
        latency = round(client.latency * 1000)
        await send_embed(interaction, f'🏓 Pong! Latency: {latency}ms')
    
    @tree.command(name="marry", description="Ajak member lain menikah")
    async def slash_marry(interaction: discord.Interaction, target: discord.Member):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        tid = str(target.id)
        
        if uid == tid:
            await send_embed(interaction, "❌ Gak bisa nikah sama diri sendiri.")
            return
            
        marriages = await load_json('marriages.json')
        if uid in marriages or tid in marriages:
            await send_embed(interaction, "❌ Salah satu dari kalian sudah menikah! Dilarang poligami/poliandri di server ini.")
            return
            
        # We will just force marry for simplicity in slash command, or ask for confirmation using View
        class ConfirmMarriage(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.value = None
                
            @discord.ui.button(label="Terima", style=discord.ButtonStyle.green)
            async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if str(button_interaction.user.id) != tid:
                    await button_interaction.response.send_message("❌ Ini bukan untukmu!", ephemeral=True)
                    return
                self.value = True
                self.stop()
                
            @discord.ui.button(label="Tolak", style=discord.ButtonStyle.red)
            async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if str(button_interaction.user.id) != tid:
                    await button_interaction.response.send_message("❌ Ini bukan untukmu!", ephemeral=True)
                    return
                self.value = False
                self.stop()
                
        view = ConfirmMarriage()
        msg = await send_embed(interaction, f"💍 {target.mention}, apakah kamu mau menikah dengan {interaction.user.display_name}?", view=view)
        await view.wait()
        
        if view.value is None:
            await msg.edit(embed=discord.Embed(description="⏳ Waktu habis. Lamaran dibatalkan otomatis.", color=discord.Color.blurple()).set_footer(text="W2E Official Bot"), view=None)
        elif view.value:
            marriages[uid] = tid
            marriages[tid] = uid
            await save_json('marriages.json', marriages)
            await msg.edit(embed=discord.Embed(description=f"🎉 **Resmi!** 🎉\n{interaction.user.mention} dan {target.mention} sekarang menikah! Selamat!", color=discord.Color.blurple()).set_footer(text="W2E Official Bot"), view=None)
        else:
            await msg.edit(embed=discord.Embed(description=f"💔 {target.display_name} menolak lamaran dari {interaction.user.display_name}.", color=discord.Color.blurple()).set_footer(text="W2E Official Bot"), view=None)
    
    @tree.command(name="divorce", description="Ceraikan pasanganmu")
    async def slash_divorce(interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        marriages = await load_json('marriages.json')
        
        if uid not in marriages:
            await send_embed(interaction, "❌ Kamu saja belum menikah, mau cerai dari mana?")
            return
            
        tid = marriages[uid]
        del marriages[uid]
        if tid in marriages:
            del marriages[tid]
            
        await save_json('marriages.json', marriages)
        await send_embed(interaction, f"💔 Kamu telah resmi **Bercerai** dengan <@{tid}>.")
    
    @tree.command(name="family", description="Lihat status keluarga kamu")
    async def slash_family(interaction: discord.Interaction, target: discord.Member = None):
        await interaction.response.defer()
        target_user = target if target else interaction.user
        uid = str(target_user.id)
        marriages = await load_json('marriages.json')
        
        embed = discord.Embed(title=f"👨‍👩‍👦 Keluarga: {target_user.display_name}", color=discord.Color.magenta())
        if uid in marriages:
            embed.add_field(name="💍 Pasangan", value=f"<@{marriages[uid]}>", inline=False)
        else:
            embed.add_field(name="💍 Pasangan", value="Belum menikah", inline=False)
            
        await interaction.followup.send(embed=embed)
    
    @tree.command(name="adopt", description="Adopsi member lain sebagai anakmu")
    async def slash_adopt(interaction: discord.Interaction, target: discord.Member):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        tid = str(target.id)
        
        if uid == tid:
            await send_embed(interaction, "❌ Gak bisa mengadopsi diri sendiri.")
            return
            
        class ConfirmAdopt(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.value = None
                
            @discord.ui.button(label="Terima Adopsi", style=discord.ButtonStyle.green)
            async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if str(button_interaction.user.id) != tid:
                    await button_interaction.response.send_message("❌ Ini bukan untukmu!", ephemeral=True)
                    return
                self.value = True
                self.stop()
                
            @discord.ui.button(label="Tolak", style=discord.ButtonStyle.red)
            async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if str(button_interaction.user.id) != tid:
                    await button_interaction.response.send_message("❌ Ini bukan untukmu!", ephemeral=True)
                    return
                self.value = False
                self.stop()
                
        view = ConfirmAdopt()
        msg = await send_embed(interaction, f"👶 {target.mention}, apakah kamu mau diadopsi oleh {interaction.user.display_name}?", view=view)
        await view.wait()
        
        if view.value is None:
            await msg.edit(embed=discord.Embed(description="⏳ Waktu habis. Adopsi batal.", color=discord.Color.blurple()).set_footer(text="W2E Official Bot"), view=None)
        elif view.value:
            users = await load_json('users.json')
            family = users.setdefault(uid, {}).setdefault('children', [])
            if tid not in family:
                family.append(tid)
                await save_json('users.json', users)
                await msg.edit(embed=discord.Embed(description=f"🎉 Selamat! {interaction.user.mention} telah resmi menjadi orang tua dari {target.mention}!", color=discord.Color.blurple()).set_footer(text="W2E Official Bot"), view=None)
            else:
                await msg.edit(embed=discord.Embed(description="❌ Dia sudah menjadi anakmu.", color=discord.Color.blurple()).set_footer(text="W2E Official Bot"), view=None)
        else:
            await msg.edit(embed=discord.Embed(description=f"💔 {target.display_name} menolak diadopsi oleh {interaction.user.display_name}.", color=discord.Color.blurple()).set_footer(text="W2E Official Bot"), view=None)
    
    @tree.command(name="poll", description="Buat sistem voting (Poll)")
    async def slash_poll(interaction: discord.Interaction, pertanyaan: str, opsi1: str, opsi2: str, opsi3: str = None, opsi4: str = None):
        await interaction.response.defer()
        embed = discord.Embed(title="📊 W2E Polling", description=pertanyaan, color=discord.Color.teal())
        
        options = [opsi1, opsi2]
        if opsi3: options.append(opsi3)
        if opsi4: options.append(opsi4)
        
        emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣']
        desc = ""
        for i, opt in enumerate(options):
            desc += f"{emojis[i]} {opt}\n\n"
            
        embed.add_field(name="Pilihan:", value=desc, inline=False)
        embed.set_footer(text=f"Dibuat oleh {interaction.user.display_name}")
        
        msg = await interaction.followup.send(embed=embed, wait=True)
        for i in range(len(options)):
            await msg.add_reaction(emojis[i])
    
    if not ECONOMY_PHASE8_ENABLED:
        @tree.command(name="giveaway", description="Buat Giveaway (Khusus Admin)")
        async def slash_giveaway(interaction: discord.Interaction, hadiah: str, durasi_menit: int):
            await interaction.response.defer()
            if not interaction.user.guild_permissions.administrator:
                await send_embed(interaction, "❌ Kamu bukan Admin!")
                return

            if durasi_menit < 1 or durasi_menit > 1440:
                await send_embed(interaction, "❌ Durasi harus antara 1 dan 1440 menit (24 jam).")
                return

            embed = discord.Embed(title="🎉 **GIVEAWAY!** 🎉", description=f"**Hadiah:** {hadiah}\n**Waktu:** {durasi_menit} Menit\n\nReact dengan 🎉 untuk ikutan!", color=discord.Color.purple())
            embed.set_footer(text=f"Diselenggarakan oleh {interaction.user.display_name}")

            msg = await interaction.followup.send(embed=embed, wait=True)
            await msg.add_reaction("🎉")

            from datetime import timedelta
            end_at = datetime.utcnow() + timedelta(minutes=durasi_menit)
            gid = await add_giveaway(interaction.channel.id, msg.id, hadiah, interaction.user.id, end_at)
            if gid:
                schedule_giveaway(gid, str(interaction.channel.id), str(msg.id), hadiah, end_at)
    
    @tree.command(name="birthday", description="Atur tanggal ulang tahun kamu")
    async def slash_birthday(interaction: discord.Interaction, tanggal_bulan: str):
        if not interaction.response.is_done():
            await interaction.response.defer()
        # Format HH-BB
        if len(tanggal_bulan) != 5 or tanggal_bulan[2] != '-':
            await send_embed(interaction, "❌ Format salah! Gunakan: DD-MM (Contoh: 25-12 untuk 25 Desember)")
            return
            
        uid = str(interaction.user.id)
        users = await load_json('users.json')
        users.setdefault(uid, {})['birthday'] = tanggal_bulan
        await save_json('users.json', users)
        
        # Save to birthdays.json for automated alerts compatibility
        bdays = await load_json('birthdays.json')
        bdays[uid] = tanggal_bulan
        await save_json('birthdays.json', bdays)
        
        await send_embed(interaction, f"🎂 Ulang tahun kamu berhasil diatur ke **{tanggal_bulan}**!")
    
    @tree.command(name="valo", description="Ajak orang main Valorant")
    async def slash_valo(interaction: discord.Interaction, target: discord.Role = None):
        await interaction.response.defer()
        mention = target.mention if target else "@here"
        await send_embed(interaction, f"🎮 {mention} **Main Valorant yuk!**\nAda yang mau join? Ping dari {interaction.user.mention}.")
    
    @tree.command(name="remindme", description="Buat pengingat/alarm")
    async def slash_remindme(interaction: discord.Interaction, menit: int, pesan: str):
        await interaction.response.defer()
        if menit <= 0 or menit > 1440:
            await send_embed(interaction, "❌ Durasi harus antara 1 sampai 1440 menit.")
            return

        await send_embed(interaction, f"⏰ Siap! Aku akan mengingatkanmu tentang **'{pesan}'** dalam {menit} menit.")

        # Persist ke DB lalu jadwalkan; tahan banting terhadap restart bot.
        from datetime import timedelta
        fire_at = datetime.utcnow() + timedelta(minutes=menit)
        rid = await add_reminder(interaction.user.id, interaction.channel.id, pesan, fire_at)
        if rid:
            schedule_reminder(rid, str(interaction.user.id), str(interaction.channel.id), pesan, fire_at)
    
    @tree.command(name="bg", description="Set URL background untuk profile card kamu")
    async def slash_bg(interaction: discord.Interaction, url: str):
        await interaction.response.defer()
        # Validasi + proteksi SSRF: tolak URL non-publik / bukan gambar sebelum disimpan.
        if not url.lower().startswith(('http://', 'https://')):
            await send_embed(interaction, "❌ URL tidak valid. Harus diawali http:// atau https://.")
            return
        if not await asyncio.to_thread(is_safe_remote_url, url):
            await send_embed(interaction, "❌ URL ditolak (host internal/privat tidak diizinkan).")
            return
        # Pastikan benar-benar bisa di-fetch sebagai gambar (sekalian validasi).
        test_img = await fetch_remote_image(url)
        if test_img is None:
            await send_embed(interaction, "❌ URL tidak mengarah ke gambar yang valid / terlalu besar.")
            return

        uid = str(interaction.user.id)
        items_data = await load_json('items.json')
        items_data.setdefault(uid, {})['bg_url'] = url
        await save_json('items.json', items_data)
        
        await send_embed(interaction, "🖼️ Background Profile Card kamu berhasil diubah! Cek dengan `/profile`.")
    
    @tree.command(name="help", description="Lihat daftar prefix bot dan panduan command")
    async def slash_help(interaction):
        from w2e_help import send_w2e_help
        await send_w2e_help(interaction)
    
    
