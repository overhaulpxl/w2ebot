import discord
from core import *
import random, asyncio, sqlite3
from datetime import datetime

def setup(tree, client):
    @tree.command(name="profile", description="Lihat profil RPG kamu")
    async def slash_profile(interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        stat = await get_discord_stat(uid)
        users = await load_json('users.json')
        achievements = users.get(uid, {}).get('achievements', [])
        
        items_dict = await load_json(ITEMS_FILE)
        items_data = items_dict.get(uid, {})
        bg_url = items_data.get('bg_url')
        
        from w2e_views import ProfileView
        view = ProfileView(interaction.user)
        
        if PILLOW_AVAILABLE:
            img_buf = await generate_profile_image(interaction.user, stat, bg_url)
            if img_buf:
                file = discord.File(fp=img_buf, filename="profile.png")
                await interaction.followup.send(file=file, view=view)
                return
    
        # Fallback if Pillow fails or isn't available
        embed = discord.Embed(title=f"Profile: {interaction.user.display_name}", color=discord.Color.blue())
        embed.add_field(name="Level", value=str(stat['level']), inline=True)
        embed.add_field(name="XP", value=str(stat['xp']), inline=True)
        embed.add_field(name="Koin", value=str(stat['coins']), inline=True)
        
        if achievements:
            ach_emojis = {
                'gambler_king': '👑 Sang Raja Judi',
                'no_lifer': '🧟‍♂️ No-Lifer',
                'hitman': '🔪 Hitman',
                'boss_slayer': '🛡️ Boss Slayer'
            }
            ach_text = "\n".join([f"- {ach_emojis.get(a, a)}" for a in achievements])
            embed.add_field(name="🏆 Achievements", value=ach_text, inline=False)
            
        await interaction.followup.send(embed=embed, view=view)
    
    @tree.command(name="market", description="Lihat harga kripto (Market 3.0)")
    async def slash_market(interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        market = await load_json(MARKET_FILE)
        if not market or 'coins' not in market:
            await send_embed(interaction, "Market belum diinisialisasi.")
            return
            
        coins_data = market['coins']
        embed = discord.Embed(title="📈 W2E Crypto Market", color=discord.Color.gold())
        for coin, data in coins_data.items():
            price = data['price']
            history = data.get('history', [price])
            
            blocks = [' ', '▂', '▃', '▄', '▅', '▆', '▇', '█']
            if len(history) > 1:
                h_min, h_max = min(history), max(history)
                if h_max == h_min:
                    sparkline = blocks[0] * len(history)
                else:
                    sparkline = "".join([blocks[int((v - h_min) / (h_max - h_min) * 7)] for v in history])
            else:
                sparkline = blocks[0]
                
            trend = "🟩" if history[-1] >= history[max(0, len(history)-2)] else "🟥"
            # We can extract the emoji or use a fallback
            emoji = data.get('emoji', '🪙')
            embed.add_field(name=f"{emoji} {coin} ({data.get('name', '')})", value=f"Harga: **{price} Koin** {trend}\nTrend: `{sparkline}`", inline=False)
            
        from w2e_views import MarketView
        await interaction.followup.send(embed=embed, view=MarketView(interaction.user))
    
    @tree.command(name="attack", description="Serang Boss Raid")
    async def slash_attack(interaction: discord.Interaction):
        await interaction.response.defer()
        boss_data = await load_json(BOSS_FILE)
        if not boss_data.get('active', False):
            await send_embed(interaction, "❌ Tidak ada Boss yang sedang aktif saat ini.")
            return
            
        uid = str(interaction.user.id)
        if uid in boss_cooldowns:
            delta = datetime.now() - boss_cooldowns[uid]
            if delta.total_seconds() < 30:
                await send_embed(interaction, f"⏳ Senjatamu masih *cooldown*! Tunggu {int(30 - delta.total_seconds())} detik lagi.")
                return
                
        boss_cooldowns[uid] = datetime.now()
        damage = random.randint(50, 300)
        
        users = await load_json('users.json')
        pet_name = users.get(uid, {}).get('pet')
        PETS = {
            'slime': {'price': 5000, 'damage': 500, 'emoji': '💧'},
            'wolf':  {'price': 15000, 'damage': 1500, 'emoji': '🐺'},
            'dragon':{'price': 50000, 'damage': 5000, 'emoji': '🐉'}
        }
        pet_dmg = PETS.get(pet_name, {}).get('damage', 0) if pet_name else 0
        damage += pet_dmg
        pet_msg = f" (+{pet_dmg} dari {pet_name.capitalize()})" if pet_dmg > 0 else ""
        
        boss_data['hp'] -= damage
        
        if boss_data['hp'] <= 0:
            boss_data['active'] = False
            await save_json(BOSS_FILE, boss_data)
            reward = 5000
            
            stat = await get_discord_stat(uid)
            stat['coins'] += reward
            await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            
            await send_embed(interaction, f"💥 **FATAL BLOW!** 💥\n{interaction.user.mention} berhasil memberikan serangan terakhir sebesar **{damage} DMG**{pet_msg} dan membunuh **{boss_data['name']}**!\n🎉 Hadiah: **{reward} Koin!**")
        else:
            await save_json(BOSS_FILE, boss_data)
            await send_embed(interaction, f"⚔️ {interaction.user.mention} menyerang **{boss_data['name']}** sebesar **{damage} DMG**!{pet_msg} (Sisa HP: {boss_data['hp']}/{boss_data['max_hp']})")
    
    @tree.command(name="buypet", description="Beli peliharaan untuk nambah Damage Raid")
    async def slash_buypet(interaction: discord.Interaction, pet_name: str = None):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        users = await load_json('users.json')
        if uid not in users: users[uid] = {'balance': 0}
        
        PETS = {
            'slime': {'price': 5000, 'damage': 500, 'emoji': '💧'},
            'wolf':  {'price': 15000, 'damage': 1500, 'emoji': '🐺'},
            'dragon':{'price': 50000, 'damage': 5000, 'emoji': '🐉'}
        }
        
        if not pet_name or pet_name.lower() not in PETS:
            msg = "Tersedia peliharaan:\n"
            for p, info in PETS.items():
                msg += f"- **{p.capitalize()}** {info['emoji']} (Harga: {info['price']} Koin, Bonus DMG: +{info['damage']})\n"
            await send_embed(interaction, msg)
            return
            
        pet_name = pet_name.lower()
        pet_info = PETS[pet_name]
        
        if users[uid].get('balance', 0) < pet_info['price']:
            await send_embed(interaction, "❌ Koin nggak cukup!")
            return
            
        users[uid]['balance'] -= pet_info['price']
        users[uid]['pet'] = pet_name
        await save_json('users.json', users)
        await send_embed(interaction, f"🎉 Selamat! Kamu telah mengadopsi {pet_info['emoji']} **{pet_name.capitalize()}**!")
    
    @tree.command(name="blackjack", description="Main judi Blackjack melawan bandar")
    async def slash_blackjack(interaction: discord.Interaction, bet: int):
        if not interaction.response.is_done():
            await interaction.response.defer()
        if bet < 50:
            await send_embed(interaction, "❌ Taruhan minimal 50 Koin.")
            return
        uid = str(interaction.user.id)
        stat = await get_discord_stat(uid)
        if stat['coins'] < bet:
            await send_embed(interaction, "❌ Koin tidak cukup!")
            return
            
        stat['coins'] -= bet
        
        player_score = random.randint(15, 25)
        dealer_score = random.randint(17, 23)
        
        if player_score > 21:
            msg = f"🃏 Nilai kamu {player_score}. **BUSTED!** Uang {bet} hangus."
        elif dealer_score > 21 or player_score > dealer_score:
            win = bet * 2
            stat['coins'] += win
            msg = f"🃏 Kamu {player_score}, Bandar {dealer_score}. **MENANG!** Dapat {win} Koin!"
            
            # Trophy check
            if win >= 1000000:
                users = await load_json('users.json')
                if 'gambler_king' not in users.get(uid, {}).get('achievements', []):
                    if uid not in users: users[uid] = {}
                    if 'achievements' not in users[uid]: users[uid]['achievements'] = []
                    users[uid]['achievements'].append('gambler_king')
                    await save_json('users.json', users)
                    msg += "\n🏆 **ACHIEVEMENT UNLOCKED: 👑 Sang Raja Judi!**"
        elif player_score == dealer_score:
            stat['coins'] += bet
            msg = f"🃏 Sama-sama {player_score}. **DRAW!** Uang dikembalikan."
        else:
            msg = f"🃏 Kamu {player_score}, Bandar {dealer_score}. **BANDAR MENANG!** Uang {bet} hangus."
            
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        from w2e_views import BlackjackView
        await send_embed(interaction, msg, view=BlackjackView(interaction.user, bet))
    
    @tree.command(name="hunt", description="Buru member yang memiliki harga buronan (Bounty)")
    async def slash_hunt(interaction: discord.Interaction, target: discord.Member):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        tid = str(target.id)
        if uid == tid: 
            await send_embed(interaction, "❌ Jangan bunuh diri.")
            return
        
        bounties = await load_json('bounties.json')
        if tid not in bounties or bounties[tid] <= 0:
            await send_embed(interaction, "❌ Orang ini nggak punya harga buronan.")
            return
            
        reward = bounties[tid]
        success = random.random() > 0.5
        
        if success:
            stat = await get_discord_stat(uid)
            stat['coins'] += reward
            bounties[tid] = 0
            await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            await save_json('bounties.json', bounties)
            msg = f"🔪 **HUNT BERHASIL!** Kamu membunuh {target.display_name} dan merampas **{reward} Koin**!"
            
            users = await load_json('users.json')
            if uid not in users: users[uid] = {}
            users[uid]['hunt_success'] = users[uid].get('hunt_success', 0) + 1
            if users[uid]['hunt_success'] >= 5 and 'hitman' not in users.get(uid, {}).get('achievements', []):
                if 'achievements' not in users[uid]: users[uid]['achievements'] = []
                users[uid]['achievements'].append('hitman')
                msg += "\n🏆 **ACHIEVEMENT UNLOCKED: 🔪 Hitman!**"
            await save_json('users.json', users)
        else:
            stat = await get_discord_stat(uid)
            denda = int(reward / 2)
            if stat['coins'] > denda:
                stat['coins'] -= denda
                msg = f"❌ **HUNT GAGAL!** Kamu dikalahkan. Didenda **{denda} Koin**."
            else:
                msg = "❌ **HUNT GAGAL!** Kamu dikalahkan hingga sekarat."
            await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            
        await send_embed(interaction, msg)
    
    
    
    @tree.command(name="shop", description="Lihat toko W2E Sultan Shop")
    async def slash_shop(interaction: discord.Interaction):
        await interaction.response.defer()
        from w2e_views import ShopView
        booster_msg = " (👑 Diskon 20% khusus Server Booster!)" if interaction.user.premium_since else ""
        res = f"🛒 **W2E SULTAN SHOP** 🛒{booster_msg}\n*Beli item langsung menggunakan tombol di bawah ini atau gunakan `/buy <item_id>`.*\n\n"
        for i_id, i_data in SHOP_ITEMS.items():
            price = i_data['price']
            if interaction.user.premium_since:
                price = int(price * 0.8)
            res += f"**[{i_id}]** {i_data['name']} - 💰 {price} Koin\n"
            res += f"↳ *{i_data['desc']}*\n\n"
        await send_embed(interaction, res, view=ShopView(interaction.user, interaction.user.premium_since))
    
    @tree.command(name="buy", description="Beli item dari Shop")
    async def slash_buy(interaction: discord.Interaction, item_id: str):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        if item_id not in SHOP_ITEMS:
            await send_embed(interaction, "❌ Item tidak ditemukan. Cek `/shop`.")
            return
            
        stat = await get_discord_stat(uid)
        item = SHOP_ITEMS[item_id]
        price = item['price']
        
        if interaction.user.premium_since:
            price = int(price * 0.8)
            
        if stat['coins'] < price:
            await send_embed(interaction, f"❌ Koin kamu tidak cukup! Harga {item['name']} adalah {price} Koin.")
            return
            
        stat['coins'] -= price
        users = await load_json('users.json')
        if uid not in users: users[uid] = {'balance': 0, 'items': {}}
        if 'items' not in users[uid]: users[uid]['items'] = {}
        
        users[uid]['items'][item_id] = users[uid]['items'].get(item_id, 0) + 1
        await save_json('users.json', users)
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        await send_embed(interaction, f"🛍️ Berhasil membeli **{item['name']}** seharga {price} Koin! (Cek `/inventory`)")
    
    @tree.command(name="inventory", description="Lihat isi tas kamu")
    async def slash_inventory(interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        users = await load_json('users.json')
        items = users.get(uid, {}).get('items', {})
        
        if not items:
            await send_embed(interaction, "🎒 Tas kamu kosong melompong.")
            return
            
        res = f"🎒 **Inventory {interaction.user.display_name}** 🎒\n\n"
        for i_id, count in items.items():
            name = SHOP_ITEMS.get(i_id, {}).get('name', i_id)
            res += f"- **{name}** (x{count})\n"
            
        await send_embed(interaction, res)
    
    @tree.command(name="daily", description="Ambil jatah koin dan XP harian")
    async def slash_daily(interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        stat = await get_discord_stat(uid)
        now = datetime.now()
        
        if stat['lastDaily']:
            last_daily = datetime.fromisoformat(stat['lastDaily'])
            if (now - last_daily).total_seconds() < 86400:
                sisa = 86400 - (now - last_daily).total_seconds()
                hours, remainder = divmod(int(sisa), 3600)
                minutes, seconds = divmod(remainder, 60)
                await send_embed(interaction, f"⏳ Kamu sudah mengambil daily. Tunggu {hours}j {minutes}m {seconds}s lagi.")
                return
                
        reward_coins = random.randint(500, 1500)
        reward_xp = random.randint(100, 300)
        
        # Booster bonus
        if interaction.user.premium_since:
            reward_coins *= 2
            reward_xp *= 2
            
        stat['coins'] += reward_coins
        stat['xp'] += reward_xp
        stat['lastDaily'] = now.isoformat()
        
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        booster_msg = "\n👑 *Server Booster Bonus 2x Lipat diterapkan!*" if interaction.user.premium_since else ""
        await send_embed(interaction, f"🎁 **DAILY CLAIMED!**\nKamu mendapatkan **{reward_coins} Koin** dan **{reward_xp} XP**!{booster_msg}")
    
    @tree.command(name="slot", description="Main judi mesin slot")
    async def slash_slot(interaction: discord.Interaction, bet: int):
        if not interaction.response.is_done():
            await interaction.response.defer()
        if bet < 50:
            await send_embed(interaction, "❌ Minimal taruhan 50 Koin.")
            return
            
        uid = str(interaction.user.id)
        stat = await get_discord_stat(uid)
        
        if stat['coins'] < bet:
            await send_embed(interaction, "❌ Koin tidak cukup!")
            return
            
        stat['coins'] -= bet
        
        emojis = ["🍒", "🍋", "🔔", "⭐", "💎", "7️⃣"]
        slots = [random.choice(emojis) for _ in range(3)]
        result = " | ".join(slots)
        
        win = 0
        msg = f"🎰 **W2E SLOT MACHINE** 🎰\n\n[ {result} ]\n\n"
        
        if slots[0] == slots[1] == slots[2]:
            if slots[0] == "7️⃣":
                win = bet * 10
                msg += f"🔥 **JACKPOT!** 🔥 Kamu menang **{win} Koin** (10x lipat)!"
            else:
                win = bet * 5
                msg += f"🎉 **SUPER WIN!** Kamu menang **{win} Koin** (5x lipat)!"
        elif slots[0] == slots[1] or slots[1] == slots[2] or slots[0] == slots[2]:
            win = int(bet * 1.5)
            msg += f"👍 **MINI WIN!** Kamu menang **{win} Koin** (1.5x lipat)!"
        else:
            msg += f"😢 Zonk! Uang taruhan **{bet} Koin** hangus dimakan mesin."
            
        stat['coins'] += win
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        from w2e_views import SlotView
        await send_embed(interaction, msg, view=SlotView(interaction.user, bet))
    
    
    
    @tree.command(name="kas", description="Cek brankas pajak komunitas (Khusus Admin)")
    async def slash_kas(interaction: discord.Interaction):
        await interaction.response.defer()
        if not interaction.user.guild_permissions.administrator:
            await send_embed(interaction, "❌ Hati-hati! Brankas Kas hanya bisa dibuka oleh Admin/Sultan server ini.")
            return
            
        treasury = await load_json(TREASURY_FILE)
        balance = treasury.get('balance', 0) if treasury else 0
        await send_embed(interaction, f"🏦 **Brankas Komunitas (W2E Treasury)**\nUang pajak yang terkumpul: **{balance} Koin RPG**\n*(Uang ini akan digunakan untuk membayar hadiah Boss Raid!)*")
    
    
    
    @tree.command(name="work", description="Bekerja untuk mendapatkan koin")
    async def slash_work(interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        stat = await get_discord_stat(uid)
        users = await load_json('users.json')
        now = datetime.now()
        last_work = users.get(uid, {}).get('lastWork')
        
        if last_work:
            last = datetime.fromisoformat(last_work)
            delta = (now - last).total_seconds()
            if delta < 3600:
                await send_embed(interaction, f"⏳ Bosmu menyuruhmu istirahat. Kerja lagi dalam {int((3600-delta)//60)} menit.")
                return
    
        reward = random.randint(50, 200)
        users.setdefault(uid, {})['lastWork'] = now.isoformat()
        await save_json('users.json', users)
        
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'] + reward, stat['xp'] + 10, stat['level'], stat['lastDaily'])
        
        jobs = ["nguli bangunan", "jaga lilin babi ngepet", "jadi admin slot", "joki ML", "jualan seblak", "nambal ban", "driver gojek", "ngetik captcha"]
        job = random.choice(jobs)
        await send_embed(interaction, f"💼 Kamu {job} dan mendapatkan **{reward} Koin RPG**! (+10 XP)")
    
    @tree.command(name="rob", description="Mencuri koin dari member lain (Hati-hati ketahuan!)")
    async def slash_rob(interaction: discord.Interaction, target: discord.Member):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        tid = str(target.id)
        
        if uid == tid:
            await send_embed(interaction, "❌ Masa merampok diri sendiri?")
            return
            
        stat_robber = await get_discord_stat(uid)
        stat_target = await get_discord_stat(tid)
        
        if stat_target['coins'] < 100:
            await send_embed(interaction, f"❌ {target.display_name} terlalu miskin untuk dirampok.")
            return
            
        users = await load_json('users.json')
        now = datetime.now()
        last_rob = users.get(uid, {}).get('lastRob')
        
        if last_rob:
            last = datetime.fromisoformat(last_rob)
            delta = (now - last).total_seconds()
            if delta < 7200: # 2 hours
                await send_embed(interaction, f"⏳ Polisi masih patroli! Tunggu {int((7200-delta)//60)} menit lagi sebelum merampok.")
                return
    
        users.setdefault(uid, {})['lastRob'] = now.isoformat()
        await save_json('users.json', users)
    
        success = random.choice([True, False, False]) # 33% win rate
        if success:
            stolen = random.randint(10, int(stat_target['coins'] * 0.2)) # Max 20%
            await update_discord_stat(uid, interaction.user.display_name, stat_robber['coins'] + stolen, stat_robber['xp'], stat_robber['level'], stat_robber['lastDaily'])
            await update_discord_stat(tid, target.display_name, stat_target['coins'] - stolen, stat_target['xp'], stat_target['level'], stat_target['lastDaily'])
            await send_embed(interaction, f"🥷 **BERHASIL!** Kamu merampok **{stolen} Koin** dari {target.mention}!")
        else:
            fine = random.randint(10, 100)
            actual_fine = min(fine, stat_robber['coins'])
            await update_discord_stat(uid, interaction.user.display_name, stat_robber['coins'] - actual_fine, stat_robber['xp'], stat_robber['level'], stat_robber['lastDaily'])
            await send_embed(interaction, f"🚓 **Terciduk Polisi!** Kamu gagal merampok {target.display_name} dan didenda **{actual_fine} Koin**!")
    
    @tree.command(name="top", description="Lihat peringkat member terkaya dan tertinggi")
    async def slash_top(interaction: discord.Interaction):
        await interaction.response.defer()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, displayName, coins, level FROM DiscordStat ORDER BY level DESC, coins DESC LIMIT 10")
        rows = c.fetchall()
        conn.close()
        
        embed = discord.Embed(title="🏆 W2E Leaderboard 🏆", color=discord.Color.gold())
        for i, row in enumerate(rows):
            embed.add_field(name=f"#{i+1} {row[1]}", value=f"Level: {row[3]} | Koin: {row[2]}", inline=False)
        await interaction.followup.send(embed=embed)
    
    @tree.command(name="weekly", description="Ambil jatah koin mingguan")
    async def slash_weekly(interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        stat = await get_discord_stat(uid)
        weekly_data = await load_json('weekly.json')
        
        today = datetime.now()
        last_weekly_str = weekly_data.get(uid)
        
        if last_weekly_str:
            last_weekly = datetime.strptime(last_weekly_str, '%Y-%m-%d')
            if (today - last_weekly).days < 7:
                days_left = 7 - (today - last_weekly).days
                await send_embed(interaction, f"⏳ Sabar ya! Kamu baru bisa ambil weekly lagi dalam {days_left} hari.")
                return
    
        reward = 5000
        stat['coins'] += reward
        weekly_data[uid] = today.strftime('%Y-%m-%d')
        await save_json('weekly.json', weekly_data)
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        await send_embed(interaction, f"📅 **WEEKLY CLAIMED!**\nKamu mendapatkan **{reward} Koin RPG** mingguan!")
    
    @tree.command(name="transfer", description="Kirim koin ke member lain")
    async def slash_transfer(interaction: discord.Interaction, target: discord.Member, amount: int):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        tid = str(target.id)
        
        if amount <= 0:
            await send_embed(interaction, "❌ Jumlah koin harus lebih dari 0!")
            return
        if uid == tid:
            await send_embed(interaction, "❌ Kamu tidak bisa transfer ke diri sendiri!")
            return
            
        stat_sender = await get_discord_stat(uid)
        if stat_sender['coins'] < amount:
            await send_embed(interaction, "❌ Koin kamu tidak cukup!")
            return
            
        stat_target = await get_discord_stat(tid)
        stat_sender['coins'] -= amount
        stat_target['coins'] += amount
        
        await update_discord_stat(uid, interaction.user.display_name, stat_sender['coins'], stat_sender['xp'], stat_sender['level'], stat_sender['lastDaily'])
        await update_discord_stat(tid, target.display_name, stat_target['coins'], stat_target['xp'], stat_target['level'], stat_target['lastDaily'])
        
        await send_embed(interaction, f"💸 **Transfer Berhasil!**\nKamu telah mengirim **{amount} Koin** ke {target.mention}.")
    
    @tree.command(name="cf", description="Main Coinflip (Judi tebak koin)")
    async def slash_cf(interaction: discord.Interaction, tebakan: str, bet: int):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        tebakan = tebakan.lower()
        if tebakan not in ['head', 'tail']:
            await send_embed(interaction, "❌ Pilihan hanya 'head' atau 'tail'.")
            return
        if bet < 10:
            await send_embed(interaction, "❌ Taruhan minimal 10 Koin.")
            return
            
        stat = await get_discord_stat(uid)
        if stat['coins'] < bet:
            await send_embed(interaction, "❌ Koin kamu tidak cukup!")
            return
            
        result = random.choice(['head', 'tail'])
        if tebakan == result:
            stat['coins'] += bet
            msg = f"🪙 Koin dilempar dan hasilnya: **{result.upper()}**\n🎉 Tebakanmu benar! Kamu menang **{bet} Koin**."
        else:
            stat['coins'] -= bet
            msg = f"🪙 Koin dilempar dan hasilnya: **{result.upper()}**\n💀 Tebakanmu salah! Kamu kalah **{bet} Koin**."
            
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await send_embed(interaction, msg)
    
    @tree.command(name="flip", description="Flip koin (Head/Tail)")
    async def slash_flip(interaction: discord.Interaction):
        result = random.choice(['Head', 'Tail'])
        await send_embed(interaction, f"🪙 Koin mendarat pada: **{result}**")
    
    @tree.command(name="rps", description="Main Batu Gunting Kertas")
    async def slash_rps(interaction: discord.Interaction, pilihan: str, bet: int):
        await interaction.response.defer()
        pilihan = pilihan.lower()
        valid = ['batu', 'gunting', 'kertas']
        if pilihan not in valid:
            await send_embed(interaction, "❌ Pilihan hanya: batu, gunting, kertas.")
            return
            
        if bet < 10:
            await send_embed(interaction, "❌ Taruhan minimal 10 Koin.")
            return
            
        uid = str(interaction.user.id)
        stat = await get_discord_stat(uid)
        if stat['coins'] < bet:
            await send_embed(interaction, "❌ Koin kamu tidak cukup!")
            return
            
        bot_choice = random.choice(valid)
        if pilihan == bot_choice:
            msg = f"🤖 Bot memilih **{bot_choice.upper()}**.\nSERI! Koin dikembalikan."
        elif (pilihan == 'batu' and bot_choice == 'gunting') or \
             (pilihan == 'gunting' and bot_choice == 'kertas') or \
             (pilihan == 'kertas' and bot_choice == 'batu'):
            stat['coins'] += bet
            msg = f"🤖 Bot memilih **{bot_choice.upper()}**.\n🎉 Kamu MENANG **{bet} Koin**!"
        else:
            stat['coins'] -= bet
            msg = f"🤖 Bot memilih **{bot_choice.upper()}**.\n💀 Kamu KALAH **{bet} Koin**!"
            
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await send_embed(interaction, msg)
    
    @tree.command(name="gacha", description="Gacha Waifu/Item (Biaya 500 Koin)")
    async def slash_gacha(interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        uid = str(interaction.user.id)
        stat = await get_discord_stat(uid)
        cost = 500
        if stat['coins'] < cost:
            await send_embed(interaction, f"❌ Koin tidak cukup! Butuh {cost} Koin.")
            return
            
        stat['coins'] -= cost
        pool = ["Ampas (Zonk)", "Nasi Bungkus", "Panci Bolong", "Kunci Jawaban UN", "Waifu Wangi", "Pedang Excalibur", "Gundam Bekas", "Sertifikat Rumah"]
        result = random.choice(pool)
        
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        from w2e_views import GachaView
        await send_embed(interaction, f"🎰 Kamu memutar Gacha seharga {cost} Koin...\n✨ Kamu mendapatkan: **{result}**!", view=GachaView(interaction.user))
    
    @tree.command(name="tebak", description="Game tebak angka 1-10")
    async def slash_tebak(interaction: discord.Interaction, tebakan: int):
        await interaction.response.defer()
        jawaban = random.randint(1, 10)
        if tebakan == jawaban:
            uid = str(interaction.user.id)
            stat = await get_discord_stat(uid)
            stat['coins'] += 100
            await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            await send_embed(interaction, f"🎯 BENAR! Angkanya adalah {jawaban}. Kamu dapat 100 Koin!")
        else:
            await send_embed(interaction, f"❌ SALAH! Angkanya adalah {jawaban}.")
    
    @tree.command(name="sell", description="Jual item dari inventory kamu")
    async def slash_sell(interaction: discord.Interaction, item_name: str):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        items_data = await load_json('items.json')
        user_inventory = items_data.get(uid, {}).get('inventory', {})
        
        # Simple search
        item_key = next((k for k in user_inventory if k.lower() == item_name.lower()), None)
        if not item_key or user_inventory[item_key] <= 0:
            await send_embed(interaction, f"❌ Kamu tidak punya item **{item_name}** di tas.")
            return
            
        shop_data = await load_json('shop.json')
        item_info = next((i for i in shop_data if i['id'] == item_key), None)
        if not item_info:
            await send_embed(interaction, "❌ Item ini tidak bisa dijual.")
            return
            
        sell_price = int(item_info['price'] * 0.5) # Sell for 50% price
        user_inventory[item_key] -= 1
        if user_inventory[item_key] == 0:
            del user_inventory[item_key]
            
        items_data[uid]['inventory'] = user_inventory
        await save_json('items.json', items_data)
        
        stat = await get_discord_stat(uid)
        stat['coins'] += sell_price
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        await send_embed(interaction, f"🛍️ Berhasil menjual **{item_info['name']}** seharga {sell_price} Koin!")
    
    @tree.command(name="crash", description="Main judi grafik Crash")
    async def slash_crash(interaction: discord.Interaction, bet: int):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        if bet < 10:
            await send_embed(interaction, "❌ Taruhan minimal 10 Koin.")
            return
            
        stat = await get_discord_stat(uid)
        if stat['coins'] < bet:
            await send_embed(interaction, "❌ Koin kamu tidak cukup!")
            return
    
        # Crash logic (1.00x to 10.00x)
        multiplier = 1.00
        while random.random() > 0.15: # 85% chance to increase
            multiplier += random.uniform(0.1, 0.5)
            if multiplier > 10.0:
                break
                
        multiplier = round(min(multiplier, 10.0), 2)
        win_amount = int(bet * multiplier)
        
        if multiplier > 1.2:
            stat['coins'] += (win_amount - bet)
            msg = f"📈 Grafik Crash berhenti di **{multiplier}x**!\n🎉 Kamu MENANG dan saldo bertambah **{win_amount - bet} Koin**!"
        else:
            stat['coins'] -= bet
            msg = f"📉 Grafik langsung CRASH di **{multiplier}x**!\n💀 Kamu KALAH dan kehilangan **{bet} Koin**!"
            
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await send_embed(interaction, msg)
    
    @tree.command(name="box", description="Buka Loot Box (Biaya: 1000 Koin)")
    async def slash_box(interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        uid = str(interaction.user.id)
        stat = await get_discord_stat(uid)
        cost = 1000
        if stat['coins'] < cost:
            await send_embed(interaction, f"❌ Butuh {cost} Koin untuk membuka Loot Box.")
            return
            
        stat['coins'] -= cost
        # Loot pool
        rand = random.random()
        if rand < 0.05:
            reward = 5000
            item = "🪙 JACKPOT! 5000 Koin"
        elif rand < 0.2:
            reward = 2000
            item = "💰 Pouch of Coins (2000 Koin)"
        elif rand < 0.5:
            reward = 500
            item = "🥈 Silver Coin (500 Koin)"
        else:
            reward = 10
            item = "🗑️ Sampah (10 Koin)"
            
        stat['coins'] += reward
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        from w2e_views import BoxView
        await send_embed(interaction, f"📦 Kamu membuka Loot Box...\nIsinya adalah: **{item}**!", view=BoxView(interaction.user))
    
    @tree.command(name="portfolio", description="Lihat aset kripto kamu")
    async def slash_portfolio(interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        uid = str(interaction.user.id)
        market_data = await load_json('market.json')
        users = await load_json('users.json')
        portfolio = users.get(uid, {}).get('crypto', {})
        
        if not portfolio:
            await send_embed(interaction, "💼 Portfolio kamu kosong. Beli koin kripto di `/market`.")
            return
            
        embed = discord.Embed(title=f"💼 Crypto Portfolio: {interaction.user.display_name}", color=discord.Color.green())
        total_value = 0
        coins_data = market_data.get('coins', {})
        for coin, amount in portfolio.items():
            if coin in coins_data:
                value = amount * coins_data[coin]['price']
                total_value += value
                emoji = coins_data[coin].get('emoji', '🪙')
                embed.add_field(name=f"{emoji} {coin}", value=f"Jumlah: {amount}\nNilai: {value:.2f} Koin", inline=False)
                
        embed.add_field(name="Total Estimasi Nilai", value=f"**{total_value:.2f} Koin RPG**", inline=False)
        await interaction.followup.send(embed=embed)
    
    @tree.command(name="buyrig", description="Beli mesin Miner Kripto (Harga bervariasi)")
    async def slash_buyrig(interaction: discord.Interaction, tier: int):
        if not interaction.response.is_done():
            await interaction.response.defer()
        uid = str(interaction.user.id)
        stat = await get_discord_stat(uid)
        users = await load_json('users.json')
        
        prices = {1: 10000, 2: 30000, 3: 80000}
        if tier not in prices:
            await send_embed(interaction, "❌ Pilihan tier: 1 (Basic), 2 (Pro), 3 (Quantum).")
            return
            
        cost = prices[tier]
        if stat['coins'] < cost:
            await send_embed(interaction, f"❌ Koin tidak cukup! Harga Rig Tier {tier} adalah {cost} Koin.")
            return
            
        stat['coins'] -= cost
        rigs = users.setdefault(uid, {}).setdefault('rigs', {})
        rigs[str(tier)] = rigs.get(str(tier), 0) + 1
        
        await save_json('users.json', users)
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        await send_embed(interaction, f"🖥️ Berhasil membeli **Mining Rig Tier {tier}** seharga {cost} Koin!\nRig akan otomatis menambang kripto setiap jam.")
    
    @tree.command(name="miner", description="Cek status mesin Miner kamu")
    async def slash_miner(interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        uid = str(interaction.user.id)
        users = await load_json('users.json')
        rigs = users.get(uid, {}).get('rigs', {})
        
        from w2e_views import MinerView
        view = MinerView(interaction.user)
        
        if not rigs:
            await send_embed(interaction, "🖥️ Kamu belum memiliki Mining Rig. Beli menggunakan tombol di bawah ini atau ketik `/buyrig <tier>`.", view=view)
            return
            
        rates = {'1': '1-5 Koin/jam', '2': '10-20 Koin/jam', '3': '50-100 Koin/jam'}
        embed = discord.Embed(title=f"⛏️ Mining Farm: {interaction.user.display_name}", color=discord.Color.dark_grey())
        
        for tier, count in rigs.items():
            embed.add_field(name=f"Rig Tier {tier}", value=f"Jumlah: {count} Unit\nEst. Hashrate: {rates.get(tier)}", inline=False)
            
        await interaction.followup.send(embed=embed, view=view)
    
    @tree.command(name="pray", description="Berdoa agar mendapatkan berkah Koin")
    async def slash_pray(interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        stat = await get_discord_stat(uid)
        users = await load_json('users.json')
        now = datetime.now()
        last_pray = users.get(uid, {}).get('lastPray')
        
        if last_pray:
            last = datetime.fromisoformat(last_pray)
            delta = (now - last).total_seconds()
            if delta < 3600:
                await send_embed(interaction, f"⏳ Tuhan menyuruhmu bersabar. Berdoa lagi dalam {int((3600-delta)//60)} menit.")
                return
    
        users.setdefault(uid, {})['lastPray'] = now.isoformat()
        await save_json('users.json', users)
        
        rand = random.random()
        if rand < 0.1:
            stat['coins'] += 1000
            msg = "✨ **MUKJIZAT!** Doamu didengar! Kamu mendapatkan **1000 Koin** dari langit!"
        elif rand < 0.6:
            stat['coins'] += 50
            msg = "🙏 Doamu dikabulkan. Kamu mendapatkan berkah **50 Koin**."
        else:
            msg = "💨 Doamu kurang khusyuk. Coba lagi nanti."
            
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await send_embed(interaction, msg)
    
    @tree.command(name="curse", description="Mengutuk orang agar koinnya hilang")
    async def slash_curse(interaction: discord.Interaction, target: discord.Member):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        tid = str(target.id)
        
        if uid == tid:
            await send_embed(interaction, "❌ Masa mengutuk diri sendiri?")
            return
            
        stat = await get_discord_stat(uid)
        if stat['coins'] < 100:
            await send_embed(interaction, "❌ Mengutuk butuh persembahan 100 Koin. Kamu terlalu miskin.")
            return
            
        stat['coins'] -= 100 # Cost of cursing
        
        users = await load_json('users.json')
        now = datetime.now()
        last_curse = users.get(uid, {}).get('lastCurse')
        
        if last_curse:
            last = datetime.fromisoformat(last_curse)
            delta = (now - last).total_seconds()
            if delta < 14400: # 4 hours
                await send_embed(interaction, f"⏳ Energi gelapmu habis. Tunggu {int((14400-delta)//3600)} jam lagi.")
                await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
                return
    
        users.setdefault(uid, {})['lastCurse'] = now.isoformat()
        await save_json('users.json', users)
        
        target_stat = await get_discord_stat(tid)
        rand = random.random()
        
        if rand < 0.4:
            loss = random.randint(50, 500)
            actual_loss = min(loss, target_stat['coins'])
            target_stat['coins'] -= actual_loss
            await update_discord_stat(tid, target.display_name, target_stat['coins'], target_stat['xp'], target_stat['level'], target_stat['lastDaily'])
            msg = f"😈 **Kutukan Berhasil!** {target.mention} terkena santet dan kehilangan **{actual_loss} Koin**!"
        else:
            # Karma
            stat['coins'] -= 200
            msg = f"🛡️ **KUTUKAN BERBALIK!** {target.display_name} dilindungi kekuatan suci. Kamu terkena karma dan kehilangan ekstra **200 Koin**!"
    
        await update_discord_stat(uid, interaction.user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await send_embed(interaction, msg)
    
    @tree.command(name="quest", description="Lihat Misi Harian/Mingguan kamu")
    async def slash_quest(interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        quests = await get_user_quests(uid)
        
        if not quests:
            await send_embed(interaction, "📜 Tidak ada quest yang aktif.")
            return
            
        embed = discord.Embed(title=f"📜 Quest Log: {interaction.user.display_name}", color=discord.Color.dark_purple())
        for q_id, q_data in quests.items():
            status = "✅ Selesai" if q_data['progress'] >= q_data['target'] else f"⏳ {q_data['progress']}/{q_data['target']}"
            embed.add_field(name=q_data['name'], value=f"{q_data['desc']}\nProgress: {status}\nReward: {q_data['reward']} Koin", inline=False)
            
        await interaction.followup.send(embed=embed)
    
