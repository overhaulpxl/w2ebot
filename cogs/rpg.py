import discord
from core import *
import random, asyncio, sqlite3
from datetime import datetime

from economy.amounts import AmountParseError, parse_economy_amount
from economy.constants import ECONOMY_PHASE2_ENABLED, ECONOMY_PHASE3_ENABLED, ECONOMY_V1_ENABLED
from economy.exchange import exchange_etm_to_ecy, get_exchange_info
from economy.profile import get_profile_snapshot
from economy.rewards import claim_reward, reserve_work_roll, settle_work_roll
from economy.transfers import transfer_etm


def _phase2_enabled():
    return ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED


def _phase3_enabled():
    return _phase2_enabled() and ECONOMY_PHASE3_ENABLED


def _economy_request_id(interaction):
    interaction_id = getattr(interaction, "id", None)
    if interaction_id is not None:
        return str(interaction_id)
    message_id = getattr(getattr(interaction, "message", None), "id", None)
    return str(message_id) if message_id is not None else f"actor:{interaction.user.id}"


def normalize_user_id(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("<@") and text.endswith(">"):
        text = text[2:-1].strip()
        if text.startswith("!"):
            text = text[1:].strip()
    if not text.isdigit():
        return None
    user_id = int(text)
    return user_id if user_id > 0 else None


def setup(tree, client):
    async def format_leaderboard_user(bot, guild, user_id):
        normalized_id = normalize_user_id(user_id)
        if normalized_id is None:
            return "Unknown User"

        member = guild.get_member(normalized_id) if guild else None
        if not member and guild:
            try:
                member = await guild.fetch_member(normalized_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                member = None
        if member:
            return f"@{member.display_name}"

        user = bot.get_user(normalized_id) if bot else None
        if not user and bot:
            try:
                user = await bot.fetch_user(normalized_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                user = None
        if user:
            display_name = getattr(user, "global_name", None) or getattr(user, "name", None)
            return f"@{display_name}" if display_name is not None else "Unknown User"
        return "Unknown User"

    async def _prefix_rank_member(guild, token):
        user_id = normalize_user_id(token)
        if user_id is None or not guild:
            return None
        member = guild.get_member(user_id)
        if member:
            return member
        try:
            return await guild.fetch_member(user_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def rpg_rank_prefix_dispatcher(message, args):
        target = message.author
        if args:
            parsed = await _prefix_rank_member(message.guild, args[0])
            if not parsed:
                await message.reply("User tidak valid.", delete_after=10)
                return
            target = parsed
        stat = await get_discord_stat(str(target.id))
        rank = await get_user_rank(target.id)
        embed = discord.Embed(title=f"🏅 RPG Rank — {target.display_name}", color=discord.Color.gold())
        embed.add_field(name="Rank", value=f"#{rank}" if rank else "-", inline=True)
        embed.add_field(name="Level", value=str(stat.get("level", 1)), inline=True)
        embed.add_field(name="XP", value=f"{int(stat.get('xp', 0) or 0):,}", inline=True)
        embed.add_field(name="Koin", value=f"{int(stat.get('coins', 0) or 0):,}", inline=True)
        await message.reply(embed=embed)

    register_prefix_command_handler("rank", rpg_rank_prefix_dispatcher)

    async def _rpg_level_leaderboard_embed(guild):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, xp, level FROM DiscordStat ORDER BY level DESC, xp DESC LIMIT 10"
            ) as cursor:
                rows = await cursor.fetchall()
        embed = discord.Embed(
            title="🏆 RPG Level Leaderboard",
            description="Top users ranked by level and experience." if rows else "No RPG level data yet.\nStart chatting or using RPG features to appear on the leaderboard.",
            color=discord.Color.gold(),
        )
        medals = ["🥇", "🥈", "🥉"]
        for idx, (uid, xp, level) in enumerate(rows, start=1):
            name = await format_leaderboard_user(client, guild, uid)
            current_xp = int(xp or 0)
            current_level = int(level or 1)
            needed = max(100, current_level * 100)
            prefix = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
            if idx <= 3:
                value = (
                    f"> 🧬 **Level:** {current_level}\n"
                    f"> ✨ **XP:** {current_xp:,}\n"
                    f"> 📈 **Progress:** {current_xp:,}/{needed:,} XP"
                )
            else:
                value = (
                    f"> 🧬 Level: {current_level}\n"
                    f"> ✨ XP: {current_xp:,}\n"
                    f"> 📈 Progress: {current_xp:,}/{needed:,} XP"
                )
            embed.add_field(name=f"{prefix} **{name}**", value=value, inline=False)
        return embed

    @tree.command(name="profile", description="Lihat profil RPG kamu")
    async def slash_profile(interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        if _phase3_enabled():
            from economy.equipment import get_active_loadout, get_effective_stats, initialize_phase3_profile
            await initialize_phase3_profile(DB_PATH, interaction.guild_id, uid)
            profile = await get_profile_snapshot(DB_PATH, interaction.guild_id, uid)
            effective = await get_effective_stats(DB_PATH, interaction.guild_id, uid)
            loadout = await get_active_loadout(DB_PATH, interaction.guild_id, uid)
            embed = discord.Embed(title=f"RPG Profile: {interaction.user.display_name}", color=0x5865F2)
            embed.add_field(name="Level / XP", value=f"{profile.level} / {profile.xp:,}", inline=True)
            embed.add_field(name="ETM / ECY", value=f"{profile.etm_balance:,} / {profile.ecy_balance:,}", inline=True)
            embed.add_field(name="HP", value=f"{profile.current_hp:,}/{effective.max_hp:,}", inline=True)
            embed.add_field(name="Attack", value=f"{effective.attack:,}", inline=True)
            embed.add_field(name="Defense", value=f"{effective.defense:,}", inline=True)
            embed.add_field(name="Critical Chance", value=f"{effective.crit_bps / 100:.2f}%", inline=True)
            embed.add_field(name="Energy", value=f"{profile.energy}/100", inline=True)
            embed.add_field(name="Power Score", value=f"{effective.power_score:,}", inline=True)
            embed.add_field(name="Activity 30 Hari", value=f"{profile.activity_score_30d:,}", inline=True)
            embed.add_field(
                name="Equipment / Pet Aktif",
                value="\n".join(
                    (f"{slot.title()}: {data['name']} (`{data['instance_id']}`)" if slot == "pet"
                     else f"{slot.title()}: {data['name']} +{data['enhancement_level']} (`{data['instance_id']}`)")
                    if data else f"{slot.title()}: -" for slot, data in loadout.items()
                ), inline=False,
            )
            await interaction.followup.send(embed=embed)
            return
        if _phase2_enabled():
            profile = await get_profile_snapshot(DB_PATH, interaction.guild_id, uid)
            embed = discord.Embed(title=f"RPG Profile: {interaction.user.display_name}", color=0x5865F2)
            embed.add_field(name="Level", value=str(profile.level), inline=True)
            embed.add_field(name="XP", value=f"{profile.xp:,}", inline=True)
            embed.add_field(name="Power Score", value=f"{profile.power_score:,}", inline=True)
            embed.add_field(name="ETM", value=f"{profile.etm_balance:,}", inline=True)
            embed.add_field(name="ECY", value=f"{profile.ecy_balance:,}", inline=True)
            embed.add_field(name="Activity 30 Hari", value=f"{profile.activity_score_30d:,}", inline=True)
            embed.add_field(name="HP", value=f"{profile.current_hp:,}/{profile.max_hp:,}", inline=True)
            embed.add_field(name="Attack", value=f"{profile.attack:,}", inline=True)
            embed.add_field(name="Defense", value=f"{profile.defense:,}", inline=True)
            crit_text = f"{profile.crit_bps // 100}.{profile.crit_bps % 100:02d}%"
            embed.add_field(name="Critical Chance", value=crit_text, inline=True)
            embed.add_field(name="Energy", value=f"{profile.energy}/100", inline=True)
            embed.add_field(
                name="Equipment / Pet",
                value=(
                    f"Weapon: `{profile.active_weapon_instance_id or '-'}`\n"
                    f"Armor: `{profile.active_armor_instance_id or '-'}`\n"
                    f"Accessory: `{profile.active_accessory_instance_id or '-'}`\n"
                    f"Pet: `{profile.active_pet_instance_id or '-'}`"
                ),
                inline=False,
            )
            await interaction.followup.send(embed=embed)
            return
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
                'gambler_king': '👑 High Roller',
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

        embed.set_footer(text="Beli: /buycoin <symbol> <jumlah>  •  Jual: /sellcoin <symbol> <jumlah>  •  fee 2%")
        from w2e_views import MarketView
        await interaction.followup.send(embed=embed, view=MarketView(interaction.user))
    
    @tree.command(name="attack", description="Serang Boss Raid")
    async def slash_attack(interaction: discord.Interaction):
        await interaction.response.defer()
        if _phase3_enabled():
            from economy.bosses import commit_boss_attack, reserve_boss_attack
            try:
                operation_id, _, _ = await reserve_boss_attack(
                    DB_PATH, guild_id=interaction.guild_id, user_id=str(interaction.user.id),
                )
                result, _ = await commit_boss_attack(
                    DB_PATH, guild_id=interaction.guild_id, user_id=str(interaction.user.id),
                    operation_id=operation_id,
                )
                await send_embed(interaction, f"Boss menerima **{result['damage']:,} damage**. Sisa HP: **{result['boss_hp']:,}**.")
            except (ValueError, PermissionError) as exc:
                await send_embed(interaction, str(exc))
            return
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
            reward = await apply_soft_cap(uid, ECON_BOSS_REWARD)
            
            await add_coins(uid, reward, interaction.user.display_name)
            
            await send_embed(interaction, f"💥 **FATAL BLOW!** 💥\n{interaction.user.mention} berhasil memberikan serangan terakhir sebesar **{damage} DMG**{pet_msg} dan membunuh **{boss_data['name']}**!\n🎉 Hadiah: **{reward} Koin!**")
        else:
            await save_json(BOSS_FILE, boss_data)
            await send_embed(interaction, f"⚔️ {interaction.user.mention} menyerang **{boss_data['name']}** sebesar **{damage} DMG**!{pet_msg} (Sisa HP: {boss_data['hp']}/{boss_data['max_hp']})")
    
    @tree.command(name="buypet", description="Beli peliharaan untuk nambah Damage Raid")
    async def slash_buypet(interaction: discord.Interaction, pet_name: str = None):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        users = await load_json('users.json')
        if uid not in users: users[uid] = {}
        
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

        # Debit atomik dulu, baru set pet.
        if not await try_spend(uid, pet_info['price'], interaction.user.display_name):
            await send_embed(interaction, "❌ Koin nggak cukup!")
            return

        users.setdefault(uid, {})['pet'] = pet_name
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
        # Potong taruhan secara atomik dulu (anti double-spend via prefix+slash).
        if not await try_spend(uid, bet, interaction.user.display_name):
            await send_embed(interaction, "❌ Koin tidak cukup!")
            return

        player_score = random.randint(15, 25)
        dealer_score = random.randint(17, 23)

        payout = 0  # taruhan sudah dipotong; cabang menang/seri mengembalikan di sini
        if player_score > 21:
            msg = f"🃏 Nilai kamu {player_score}. **BUSTED!** Taruhan {bet} Koin hilang."
        elif dealer_score > 21 or player_score > dealer_score:
            win = bet * 2
            payout = win
            msg = f"🃏 Kamu {player_score}, Bandar {dealer_score}. **MENANG!** Dapat {win} Koin!"

            # Trophy check
            if win >= 1000000:
                users = await load_json('users.json')
                if 'gambler_king' not in users.get(uid, {}).get('achievements', []):
                    if uid not in users: users[uid] = {}
                    if 'achievements' not in users[uid]: users[uid]['achievements'] = []
                    users[uid]['achievements'].append('gambler_king')
                    await save_json('users.json', users)
                    msg += "\n🏆 **ACHIEVEMENT UNLOCKED: 👑 High Roller!**"
        elif player_score == dealer_score:
            payout = bet
            msg = f"🃏 Sama-sama {player_score}. **DRAW!** Uang dikembalikan."
        else:
            msg = f"🃏 Kamu {player_score}, Bandar {dealer_score}. **BANDAR MENANG!** Taruhan {bet} Koin hilang."

        if payout:
            await add_coins(uid, payout, interaction.user.display_name)
        # Track statistik minigame.
        won = payout > bet if payout else False
        draw = payout == bet
        await record_game(uid, 'blackjack', True if won else (None if draw else False))
        from w2e_views import BlackjackView
        await send_embed(interaction, msg, view=BlackjackView(interaction.user, bet))
    
    @tree.command(name="hunt", description="Jalankan RPG Hunt atau legacy bounty hunt")
    async def slash_hunt(interaction: discord.Interaction, target: discord.Member = None):
        await interaction.response.defer()
        if _phase3_enabled():
            from economy.adventures import reserve_hunt, settle_hunt
            from economy.equipment import initialize_phase3_profile
            try:
                await initialize_phase3_profile(DB_PATH, interaction.guild_id, str(interaction.user.id))
                profile = await get_profile_snapshot(DB_PATH, interaction.guild_id, str(interaction.user.id))
                area_id = "abyss_realm" if profile.level >= 45 else (
                    "eternal_ruins" if profile.level >= 25 else ("dark_cave" if profile.level >= 10 else "green_forest")
                )
                operation_id, _, _ = await reserve_hunt(
                    DB_PATH, guild_id=interaction.guild_id, user_id=str(interaction.user.id), area_id=area_id,
                )
                result = await settle_hunt(
                    DB_PATH, guild_id=interaction.guild_id, user_id=str(interaction.user.id), operation_id=operation_id,
                )
                await send_embed(interaction, result.message)
            except ValueError as exc:
                await send_embed(interaction, str(exc))
            return
        if target is None:
            await send_embed(interaction, "Target bounty wajib diisi. Gunakan `/bounty hunt`.")
            return
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
            bounties[tid] = 0
            await add_coins(uid, reward, interaction.user.display_name)
            await save_json('bounties.json', bounties)
            await record_game(uid, 'hunt', True)
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
            denda = int(reward / 2)
            await adjust_coins(uid, -denda, interaction.user.display_name)
            await record_game(uid, 'hunt', False)
            msg = f"❌ **HUNT GAGAL!** Kamu dikalahkan. Didenda hingga **{denda} Koin**."
            
        await send_embed(interaction, msg)
    
    
    
    @tree.command(name="shop", description="Lihat toko W2E Shop")
    async def slash_shop(interaction: discord.Interaction):
        await interaction.response.defer()
        from w2e_views import ShopView
        booster_msg = " (👑 Diskon 20% khusus Server Booster!)" if interaction.user.premium_since else ""
        res = f"🛒 **W2E Shop** 🛒{booster_msg}\n*Beli item langsung menggunakan tombol di bawah ini atau gunakan `/buy <item_id>`.*\n\n"
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

        item = SHOP_ITEMS[item_id]
        price = item['price']
        if interaction.user.premium_since:
            price = int(price * 0.8)

        # Debit atomik: potong koin hanya kalau saldo cukup, baru beri item.
        if not await try_spend(uid, price, interaction.user.display_name):
            await send_embed(interaction, f"❌ Koin kamu tidak cukup! Harga {item['name']} adalah {price} Koin.")
            return

        users = await load_json('users.json')
        if uid not in users: users[uid] = {'items': {}}
        if 'items' not in users[uid]: users[uid]['items'] = {}

        users[uid]['items'][item_id] = users[uid]['items'].get(item_id, 0) + 1
        await save_json('users.json', users)

        await send_embed(interaction, f"🛍️ Berhasil membeli **{item['name']}** seharga {price} Koin! (Cek `/inventory`)")
    
    @tree.command(name="inventory", description="Lihat isi tas kamu")
    async def slash_inventory(interaction: discord.Interaction, category: str = "all", page: int = 1):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        if _phase3_enabled():
            from economy.catalog import EQUIPMENT, STACK_ITEMS
            from economy.inventory import list_inventory
            try:
                page = max(1, int(page))
                data = await list_inventory(
                    DB_PATH, interaction.guild_id, uid, category=category, offset=(page - 1) * 20,
                )
            except ValueError as exc:
                await send_embed(interaction, str(exc))
                return
            embed = discord.Embed(title=f"Inventory: {interaction.user.display_name}", color=0x5865F2)
            for row in data["equipment"]:
                definition = EQUIPMENT.get(row["itemId"], {})
                embed.add_field(
                    name=definition.get("name", row["itemId"]),
                    value=(f"{definition.get('rarity', '-')} | {row['slot']} | +{row['enhancementLevel']}\n"
                           f"Binding: {row['bindingStatus']} | Status: {row['status']}\n"
                           f"ID: `{row['equipmentInstanceId']}`"), inline=False,
                )
            for row in data["stacks"]:
                definition = STACK_ITEMS.get(row["itemId"], (row["itemId"],))
                embed.add_field(
                    name=definition[0], value=f"ID: `{row['itemId']}` | Qty: **{row['quantity']}**", inline=False,
                )
            if not embed.fields:
                embed.description = "Inventory kosong untuk kategori ini."
            embed.set_footer(text=f"Halaman {page}")
            await interaction.followup.send(embed=embed)
            return
        users = await load_json('users.json')
        items = users.get(uid, {}).get('items', {})
        
        if not items:
            await send_embed(interaction, "🎒 Tas kamu kosong.")
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
        if _phase2_enabled():
            result = await claim_reward(
                DB_PATH, guild_id=interaction.guild_id, user_id=uid,
                claim_type="DAILY", request_id=_economy_request_id(interaction),
            )
            await send_embed(interaction, result.message)
            return
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

        await add_coins(uid, reward_coins, interaction.user.display_name)
        await add_xp(uid, interaction.user.display_name, reward_xp)
        await set_last_daily(uid, now.isoformat(), interaction.user.display_name)
        
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
        # Potong taruhan atomik dulu.
        if not await try_spend(uid, bet, interaction.user.display_name):
            await send_embed(interaction, "❌ Koin tidak cukup!")
            return

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
            msg += f"😢 Tidak beruntung. Taruhan **{bet} Koin** hilang."

        if win:
            await add_coins(uid, win, interaction.user.display_name)

        await record_game(uid, 'slot', win > 0)
        from w2e_views import SlotView
        await send_embed(interaction, msg, view=SlotView(interaction.user, bet))
    
    
    
    @tree.command(name="kas", description="Cek brankas pajak komunitas (Khusus Admin)")
    async def slash_kas(interaction: discord.Interaction):
        await interaction.response.defer()
        if not interaction.user.guild_permissions.administrator:
            await send_embed(interaction, "❌ Brankas Kas hanya bisa dibuka oleh Admin server ini.")
            return
            
        treasury = await load_json(TREASURY_FILE)
        balance = treasury.get('balance', 0) if treasury else 0
        await send_embed(interaction, f"🏦 **Brankas Komunitas (W2E Treasury)**\nUang pajak yang terkumpul: **{balance} Koin RPG**\n*(Uang ini akan digunakan untuk membayar hadiah Boss Raid!)*")
    
    
    
    @tree.command(name="work", description="Bekerja untuk mendapatkan koin")
    async def slash_work(interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        if _phase2_enabled():
            reserved = await reserve_work_roll(DB_PATH, guild_id=interaction.guild_id, user_id=uid)
            if not reserved.ok:
                await send_embed(interaction, reserved.message)
                return
            result = await settle_work_roll(
                DB_PATH, guild_id=interaction.guild_id, user_id=uid, roll_id=reserved.roll_id,
            )
            await send_embed(interaction, result.message)
            return
        users = await load_json('users.json')
        now = datetime.now()
        last_work = users.get(uid, {}).get('lastWork')
        
        if last_work:
            last = datetime.fromisoformat(last_work)
            delta = (now - last).total_seconds()
            if delta < 3600:
                await send_embed(interaction, f"⏳ Kamu masih cooldown. Kerja lagi dalam {int((3600-delta)//60)} menit.")
                return
    
        reward = random.randint(ECON_WORK_MIN, ECON_WORK_MAX)
        reward = await apply_soft_cap(uid, reward)
        users.setdefault(uid, {})['lastWork'] = now.isoformat()
        await save_json('users.json', users)
        
        await add_coins(uid, reward, interaction.user.display_name)
        await add_xp(uid, interaction.user.display_name, ECON_WORK_XP)
        
        jobs = ["kerja shift gudang", "jaga parkir", "nganter paket", "jadi barista", "data entry", "freelance desain", "jaga kasir", "cuci mobil"]
        job = random.choice(jobs)
        await send_embed(interaction, f"💼 Kamu {job} dan mendapatkan **{reward} Koin RPG**! (+10 XP)")
    
    @tree.command(name="rob", description="Mencuri koin dari member lain (Hati-hati ketahuan!)")
    async def slash_rob(interaction: discord.Interaction, target: discord.Member):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        tid = str(target.id)
        
        if uid == tid:
            await send_embed(interaction, "❌ Gak bisa ngerampok diri sendiri.")
            return
            
        stat_robber = await get_discord_stat(uid)
        stat_target = await get_discord_stat(tid)
        
        if stat_target['coins'] < 100:
            await send_embed(interaction, f"❌ Saldo {target.display_name} terlalu kecil buat dirampok.")
            return
            
        users = await load_json('users.json')
        now = datetime.now()
        last_rob = users.get(uid, {}).get('lastRob')
        
        if last_rob:
            last = datetime.fromisoformat(last_rob)
            delta = (now - last).total_seconds()
            if delta < 7200: # 2 hours
                await send_embed(interaction, f"⏳ Masih cooldown. Tunggu {int((7200-delta)//60)} menit lagi sebelum merampok.")
                return
    
        users.setdefault(uid, {})['lastRob'] = now.isoformat()
        await save_json('users.json', users)
    
        success = random.choice([True, False, False]) # 33% win rate
        if success:
            stolen = random.randint(10, int(stat_target['coins'] * 0.2)) # Max 20%
            # Tax 5% masuk treasury, perampok dapat 95%.
            tax = int(stolen * ECON_TRANSFER_TAX)
            net_stolen = stolen - tax
            await adjust_coins(uid, net_stolen, interaction.user.display_name)
            await adjust_coins(tid, -stolen, target.display_name)
            if tax > 0:
                await add_treasury(tax)
            await send_embed(interaction, f"🥷 **BERHASIL!** Kamu merampok **{stolen} Koin** dari {target.mention}!\n(Pajak 5% = {tax} masuk kas, kamu dapat {net_stolen}.)")
        else:
            fine = random.randint(10, 100)
            actual_fine = min(fine, stat_robber['coins'])
            await adjust_coins(uid, -actual_fine, interaction.user.display_name)
            await send_embed(interaction, f"🚓 **Terciduk Polisi!** Kamu gagal merampok {target.display_name} dan didenda **{actual_fine} Koin**!")
    
    @tree.command(name="top", description="Lihat peringkat member terkaya dan tertinggi")
    async def slash_top(interaction: discord.Interaction):
        await interaction.response.defer()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT id, displayName, coins, level FROM DiscordStat ORDER BY level DESC, coins DESC LIMIT 10") as cursor:
                rows = await cursor.fetchall()
        
        embed = discord.Embed(title="🏆 W2E Leaderboard 🏆", color=discord.Color.gold())
        for i, row in enumerate(rows):
            embed.add_field(name=f"#{i+1} {row[1]}", value=f"Level: {row[3]} | Koin: {row[2]}", inline=False)
        await interaction.followup.send(embed=embed)

    @tree.command(name="leaderboard", description="Lihat RPG level leaderboard")
    async def slash_leaderboard(interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.followup.send(embed=await _rpg_level_leaderboard_embed(interaction.guild))
    
    @tree.command(name="weekly", description="Ambil jatah koin mingguan")
    async def slash_weekly(interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        if _phase2_enabled():
            result = await claim_reward(
                DB_PATH, guild_id=interaction.guild_id, user_id=uid,
                claim_type="WEEKLY", request_id=_economy_request_id(interaction),
            )
            await send_embed(interaction, result.message)
            return
        weekly_data = await load_json('weekly.json')
        
        today = datetime.now()
        last_weekly_str = weekly_data.get(uid)
        
        if last_weekly_str:
            last_weekly = datetime.strptime(last_weekly_str, '%Y-%m-%d')
            if (today - last_weekly).days < 7:
                days_left = 7 - (today - last_weekly).days
                await send_embed(interaction, f"⏳ Tunggu {days_left} hari lagi untuk klaim weekly.")
                return
    
        reward = 5000
        weekly_data[uid] = today.strftime('%Y-%m-%d')
        await save_json('weekly.json', weekly_data)
        await add_coins(uid, reward, interaction.user.display_name)
        
        await send_embed(interaction, f"📅 **WEEKLY CLAIMED!**\nKamu mendapatkan **{reward} Koin RPG** mingguan!")
    
    @tree.command(name="transfer", description="Kirim koin ke member lain")
    async def slash_transfer(interaction: discord.Interaction, target: discord.Member, amount: int):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        tid = str(target.id)
        if _phase2_enabled():
            result = await transfer_etm(
                DB_PATH, guild_id=interaction.guild_id, sender_id=uid, recipient_id=tid,
                amount=amount, request_id=_economy_request_id(interaction),
                recipient_is_bot=bool(target.bot),
            )
            await send_embed(interaction, result.message)
            return
        
        if amount <= 0:
            await send_embed(interaction, "❌ Jumlah koin harus lebih dari 0!")
            return
        if uid == tid:
            await send_embed(interaction, "❌ Kamu tidak bisa transfer ke diri sendiri!")
            return

        # Debit pengirim atomik dulu; baru kredit penerima kalau berhasil.
        if not await try_spend(uid, amount, interaction.user.display_name):
            await send_embed(interaction, "❌ Koin kamu tidak cukup!")
            return

        # Tax 5% masuk treasury, penerima dapat 95%.
        tax = int(amount * ECON_TRANSFER_TAX)
        net = amount - tax
        await add_coins(tid, net, target.display_name)
        if tax > 0:
            await add_treasury(tax)

        await send_embed(interaction, f"💸 **Transfer Berhasil!**\nKamu mengirim **{amount} Koin** ke {target.mention}.\nPenerima dapat: **{net}** (pajak 5% = {tax} masuk kas).")
    
    @tree.command(name="exchange", description="Lihat atau gunakan Eternal Exchange ETM ke ECY")
    async def slash_exchange(interaction: discord.Interaction, amount: str = ""):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        enabled = _phase2_enabled()
        if not str(amount or "").strip():
            info = await get_exchange_info(DB_PATH, interaction.guild_id, uid, enabled=enabled)
            status = "Tersedia" if info.available else "Tidak tersedia"
            limit_text = f"{info.daily_limit:,} ETM" if info.daily_limit else "Terkunci"
            await send_embed(
                interaction,
                "**Eternal Exchange**\n"
                "Rate: **10 ETM = 1 ECY**\n"
                "Fee: **5%**\n"
                "Input wajib kelipatan **200 ETM**.\n\n"
                f"RPG Level: **{info.level}**\n"
                f"Limit harian: **{limit_text}**\n"
                f"Dipakai hari ini: **{info.used_today:,} ETM**\n"
                f"Sisa allowance: **{info.remaining:,} ETM**\n"
                f"Status fitur: **{status}**",
            )
            return
        if not enabled:
            await send_embed(interaction, "Economy Phase 2 belum diaktifkan. Exchange tidak memproses transaksi.")
            return
        try:
            parsed = parse_economy_amount(amount)
        except AmountParseError as exc:
            await send_embed(interaction, str(exc))
            return
        result = await exchange_etm_to_ecy(
            DB_PATH, guild_id=interaction.guild_id, user_id=uid, amount=parsed,
            request_id=_economy_request_id(interaction),
        )
        await send_embed(interaction, result.message)

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

        # Potong taruhan atomik dulu.
        if not await try_spend(uid, bet, interaction.user.display_name):
            await send_embed(interaction, "❌ Koin kamu tidak cukup!")
            return

        result = random.choice(['head', 'tail'])
        if tebakan == result:
            msg = f"🪙 Koin dilempar dan hasilnya: **{result.upper()}**\n🎉 Tebakanmu benar! Kamu menang **{bet} Koin**."
            await add_coins(uid, bet * 2, interaction.user.display_name)
            await record_game(uid, 'cf', True)
        else:
            msg = f"🪙 Koin dilempar dan hasilnya: **{result.upper()}**\n💀 Tebakanmu salah! Kamu kalah **{bet} Koin**."
            await record_game(uid, 'cf', False)

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
        # Potong taruhan atomik dulu.
        if not await try_spend(uid, bet, interaction.user.display_name):
            await send_embed(interaction, "❌ Koin kamu tidak cukup!")
            return
            
        bot_choice = random.choice(valid)
        if pilihan == bot_choice:
            # Seri: kembalikan taruhan.
            await add_coins(uid, bet, interaction.user.display_name)
            msg = f"🤖 Bot memilih **{bot_choice.upper()}**.\nSERI! Koin dikembalikan."
            await record_game(uid, 'rps', None)
        elif (pilihan == 'batu' and bot_choice == 'gunting') or \
             (pilihan == 'gunting' and bot_choice == 'kertas') or \
             (pilihan == 'kertas' and bot_choice == 'batu'):
            await add_coins(uid, bet * 2, interaction.user.display_name)
            msg = f"🤖 Bot memilih **{bot_choice.upper()}**.\n🎉 Kamu MENANG **{bet} Koin**!"
            await record_game(uid, 'rps', True)
        else:
            msg = f"🤖 Bot memilih **{bot_choice.upper()}**.\n💀 Kamu KALAH **{bet} Koin**!"
            await record_game(uid, 'rps', False)
            
        await send_embed(interaction, msg)
    
    @tree.command(name="gacha", description="Gacha Waifu/Item (Biaya 500 Koin)")
    async def slash_gacha(interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        uid = str(interaction.user.id)
        cost = 500
        # Debit atomik (sekalian validasi saldo).
        if not await try_spend(uid, cost, interaction.user.display_name):
            await send_embed(interaction, f"❌ Koin tidak cukup! Butuh {cost} Koin.")
            return

        pool = ["Ampas (Zonk)", "Nasi Bungkus", "Panci Bolong", "Kunci Jawaban UN", "Waifu Wangi", "Pedang Excalibur", "Gundam Bekas", "Sertifikat Rumah"]
        result = random.choice(pool)

        await record_game(uid, 'gacha', result not in ("Ampas (Zonk)", "Nasi Bungkus", "Panci Bolong"))
        from w2e_views import GachaView
        await send_embed(interaction, f"🎰 Kamu memutar Gacha seharga {cost} Koin...\n✨ Kamu mendapatkan: **{result}**!", view=GachaView(interaction.user))

    @tree.command(name="tebak", description="Game tebak angka 1-10")
    async def slash_tebak(interaction: discord.Interaction, tebakan: int):
        await interaction.response.defer()
        jawaban = random.randint(1, 10)
        uid = str(interaction.user.id)
        if tebakan == jawaban:
            await add_coins(uid, 100, interaction.user.display_name)
            await record_game(uid, 'tebak', True)
            await send_embed(interaction, f"🎯 BENAR! Angkanya adalah {jawaban}. Kamu dapat 100 Koin!")
        else:
            await record_game(uid, 'tebak', False)
            await send_embed(interaction, f"❌ SALAH! Angkanya adalah {jawaban}.")
    
    @tree.command(name="sell", description="Jual item dari inventory kamu")
    async def slash_sell(interaction: discord.Interaction, item_name: str):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        users = await load_json('users.json')
        user_items = users.get(uid, {}).get('items', {})

        # Match against SHOP_ITEMS keys (id or display name), case-insensitive
        item_key = next(
            (k for k in user_items
             if k.lower() == item_name.lower()
             or SHOP_ITEMS.get(k, {}).get('name', '').lower() == item_name.lower()),
            None
        )
        if not item_key or user_items.get(item_key, 0) <= 0:
            await send_embed(interaction, f"❌ Kamu tidak punya item **{item_name}** di tas.")
            return

        item_info = SHOP_ITEMS.get(item_key)
        if not item_info:
            await send_embed(interaction, "❌ Item ini tidak bisa dijual.")
            return

        sell_price = int(item_info['price'] * 0.5) # Sell for 50% price
        user_items[item_key] -= 1
        if user_items[item_key] <= 0:
            del user_items[item_key]

        users.setdefault(uid, {})['items'] = user_items
        await save_json('users.json', users)

        await add_coins(uid, sell_price, interaction.user.display_name)

        await send_embed(interaction, f"🛍️ Berhasil menjual **{item_info['name']}** seharga {sell_price} Koin!")
    
    @tree.command(name="crash", description="Main judi grafik Crash")
    async def slash_crash(interaction: discord.Interaction, bet: int):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        if bet < 10:
            await send_embed(interaction, "❌ Taruhan minimal 10 Koin.")
            return

        # Potong taruhan atomik dulu.
        if not await try_spend(uid, bet, interaction.user.display_name):
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
            msg = f"📈 Grafik Crash berhenti di **{multiplier}x**!\n🎉 Kamu MENANG dan saldo bertambah **{win_amount - bet} Koin**!"
            await add_coins(uid, win_amount, interaction.user.display_name)
            await record_game(uid, 'crash', True)
        else:
            msg = f"📉 Grafik langsung CRASH di **{multiplier}x**!\n💀 Kamu KALAH dan kehilangan **{bet} Koin**!"
            await record_game(uid, 'crash', False)

        await send_embed(interaction, msg)
    
    @tree.command(name="box", description="Buka Loot Box (Biaya: 1000 Koin)")
    async def slash_box(interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        uid = str(interaction.user.id)
        cost = 1000
        # Debit atomik (sekalian validasi saldo).
        if not await try_spend(uid, cost, interaction.user.display_name):
            await send_embed(interaction, f"❌ Butuh {cost} Koin untuk membuka Loot Box.")
            return

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

        if reward:
            await add_coins(uid, reward, interaction.user.display_name)
        await record_game(uid, 'box', reward > cost)
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
                # Format: desimal kalau < 1, integer kalau bulat besar.
                amt_str = f"{amount:.6f}".rstrip('0').rstrip('.') if amount < 1 else f"{amount:,.4f}".rstrip('0').rstrip('.')
                embed.add_field(name=f"{emoji} {coin}", value=f"Jumlah: {amt_str}\nNilai: {value:,.2f} Koin", inline=False)
                
        embed.add_field(name="Total Estimasi Nilai", value=f"**{total_value:.2f} Koin RPG**", inline=False)
        await interaction.followup.send(embed=embed)
    
    @tree.command(name="buycoin", description="Beli kripto pakai Koin (fee 2%)")
    async def slash_buycoin(interaction: discord.Interaction, symbol: str, jumlah: str):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        symbol = symbol.upper()

        market = await load_json(MARKET_FILE)
        coins_data = market.get('coins', {}) if market else {}
        if symbol not in coins_data:
            tersedia = ", ".join(coins_data.keys()) if coins_data else "-"
            await send_embed(interaction, f"❌ Kripto **{symbol}** tidak ada. Tersedia: {tersedia}")
            return

        price = coins_data[symbol]['price']
        stat = await get_discord_stat(uid)
        saldo = stat['coins']

        # Tentukan jumlah unit yang dibeli. "all" = sebanyak yang saldo sanggup
        # (sudah termasuk fee 2%).
        if jumlah.lower() == 'all':
            harga_per_unit = price * (1 + CRYPTO_FEE_RATE)
            qty = int(saldo // harga_per_unit) if harga_per_unit > 0 else 0
            if qty <= 0:
                await send_embed(interaction, "❌ Koin kamu tidak cukup untuk beli 1 unit pun.")
                return
        else:
            try:
                qty = int(jumlah)
            except ValueError:
                await send_embed(interaction, "❌ Jumlah harus berupa angka atau `all`.")
                return
            if qty <= 0:
                await send_embed(interaction, "❌ Jumlah harus lebih dari 0.")
                return

        gross = qty * price
        fee = round(gross * CRYPTO_FEE_RATE)
        total = gross + fee

        # Debit atomik dulu; baru tambahkan holding.
        if not await try_spend(uid, total, interaction.user.display_name):
            await send_embed(interaction, f"❌ Koin tidak cukup! Butuh **{total} Koin** (harga {gross} + fee {fee}).")
            return

        users = await load_json('users.json')
        crypto = users.setdefault(uid, {}).setdefault('crypto', {})
        crypto[symbol] = crypto.get(symbol, 0) + qty
        await save_json('users.json', users)

        await add_treasury(fee)

        await send_embed(interaction, f"📥 **BELI BERHASIL!**\nKamu membeli **{qty} {symbol}** @ {price} Koin.\nTotal: **{total} Koin** (termasuk fee 2% = {fee}).\nSaldo {symbol} sekarang: **{crypto[symbol]}**")

    @tree.command(name="sellcoin", description="Jual kripto jadi Koin (fee 2%)")
    async def slash_sellcoin(interaction: discord.Interaction, symbol: str, jumlah: str):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        symbol = symbol.upper()

        market = await load_json(MARKET_FILE)
        coins_data = market.get('coins', {}) if market else {}
        if symbol not in coins_data:
            tersedia = ", ".join(coins_data.keys()) if coins_data else "-"
            await send_embed(interaction, f"❌ Kripto **{symbol}** tidak ada. Tersedia: {tersedia}")
            return

        users = await load_json('users.json')
        crypto = users.get(uid, {}).get('crypto', {})
        held = crypto.get(symbol, 0)
        if held <= 0:
            await send_embed(interaction, f"❌ Kamu tidak punya **{symbol}** untuk dijual.")
            return

        if jumlah.lower() == 'all':
            qty = held
        else:
            try:
                qty = int(jumlah)
            except ValueError:
                await send_embed(interaction, "❌ Jumlah harus berupa angka atau `all`.")
                return
            if qty <= 0:
                await send_embed(interaction, "❌ Jumlah harus lebih dari 0.")
                return
            if qty > held:
                await send_embed(interaction, f"❌ Holding kamu cuma **{held} {symbol}**.")
                return

        price = coins_data[symbol]['price']
        gross = qty * price
        fee = round(gross * CRYPTO_FEE_RATE)
        net = gross - fee

        # Kurangi holding & simpan DULU, baru kredit koin (cegah jual > holding).
        crypto[symbol] = held - qty
        if crypto[symbol] <= 0:
            del crypto[symbol]
        users.setdefault(uid, {})['crypto'] = crypto
        await save_json('users.json', users)

        await add_coins(uid, net, interaction.user.display_name)
        await add_treasury(fee)

        sisa = crypto.get(symbol, 0)
        await send_embed(interaction, f"📤 **JUAL BERHASIL!**\nKamu menjual **{qty} {symbol}** @ {price} Koin.\nDapat: **{net} Koin** (harga {gross} - fee 2% = {fee}).\nSisa {symbol}: **{sisa}**")
    
    @tree.command(name="buyrig", description="Beli mesin Miner Kripto untuk koin tertentu")
    async def slash_buyrig(interaction: discord.Interaction, tier: int, koin: str = "ETHR"):
        if not interaction.response.is_done():
            await interaction.response.defer()
        uid = str(interaction.user.id)
        users = await load_json('users.json')
        koin = koin.upper()

        if tier not in RIG_PRICES:
            await send_embed(interaction, "❌ Pilihan tier: 1 (Basic), 2 (Pro), 3 (Quantum).")
            return

        if koin not in MINING_RATES:
            tersedia = ", ".join(MINING_RATES.keys())
            await send_embed(interaction, f"❌ Koin **{koin}** tidak bisa ditambang. Tersedia: {tersedia}")
            return

        cost = RIG_PRICES[tier]
        # Debit atomik dulu, baru daftarkan rig.
        if not await try_spend(uid, cost, interaction.user.display_name):
            await send_embed(interaction, f"❌ Koin tidak cukup! Harga Rig Tier {tier} adalah {cost} Koin.")
            return

        # Format rigs baru: {symbol: {tier: count}}
        rigs = users.setdefault(uid, {}).setdefault('rigs', {})
        # Migrasi format lama kalau ada
        if rigs and isinstance(next(iter(rigs.values()), None), int):
            rigs_old = dict(rigs)
            rigs.clear()
            rigs['ETHR'] = rigs_old
        coin_rigs = rigs.setdefault(koin, {})
        coin_rigs[str(tier)] = coin_rigs.get(str(tier), 0) + 1

        await save_json('users.json', users)

        lo, hi = MINING_RATES[koin][str(tier)]
        await send_embed(interaction, f"🖥️ Berhasil membeli **Mining Rig Tier {tier}** untuk **{koin}** seharga {cost} Koin!\nEst. yield: {lo}-{hi} {koin}/jam per unit. Rig otomatis menambang setiap jam.")

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
            await send_embed(interaction, "🖥️ Kamu belum memiliki Mining Rig. Beli dengan `/buyrig <tier> <koin>` (cth: `/buyrig 1 ETHR`).", view=view)
            return

        # Migrasi format lama kalau masih {tier: count}
        if rigs and isinstance(next(iter(rigs.values()), None), int):
            rigs = {'ETHR': rigs}

        embed = discord.Embed(title=f"⛏️ Mining Farm: {interaction.user.display_name}", color=discord.Color.dark_grey())

        for symbol, tier_map in rigs.items():
            if not isinstance(tier_map, dict):
                continue
            rates = MINING_RATES.get(symbol, {})
            lines = []
            for tier, count in tier_map.items():
                lo, hi = rates.get(str(tier), (0, 0))
                lines.append(f"Tier {tier}: **{count}** unit ({lo}-{hi} {symbol}/jam per unit)")
            embed.add_field(name=f"⛏️ {symbol}", value="\n".join(lines), inline=False)

        embed.set_footer(text="Rig menambang otomatis tiap jam. Beli: /buyrig <tier> <koin> | Pindah: /moverig <tier> <dari> <ke>")
        await interaction.followup.send(embed=embed, view=view)

    @tree.command(name="moverig", description="Pindahkan rig ke koin lain (gratis)")
    async def slash_moverig(interaction: discord.Interaction, tier: int, dari: str, ke: str):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        dari = dari.upper()
        ke = ke.upper()

        if tier not in (1, 2, 3):
            await send_embed(interaction, "❌ Tier harus 1, 2, atau 3.")
            return
        if dari not in MINING_RATES:
            await send_embed(interaction, f"❌ Koin **{dari}** tidak valid.")
            return
        if ke not in MINING_RATES:
            await send_embed(interaction, f"❌ Koin **{ke}** tidak valid.")
            return
        if dari == ke:
            await send_embed(interaction, "❌ Koin asal dan tujuan sama.")
            return

        users = await load_json('users.json')
        rigs = users.get(uid, {}).get('rigs', {})

        # Migrasi format lama kalau masih {tier: count}
        if rigs and isinstance(next(iter(rigs.values()), None), int):
            rigs_old = dict(rigs)
            rigs = {'ETHR': rigs_old}
            users.setdefault(uid, {})['rigs'] = rigs

        # Cek punya rig di koin asal
        dari_rigs = rigs.get(dari, {})
        count = dari_rigs.get(str(tier), 0)
        if count <= 0:
            await send_embed(interaction, f"❌ Kamu tidak punya Rig Tier {tier} yang mining **{dari}**.")
            return

        # Pindahkan 1 unit
        dari_rigs[str(tier)] = count - 1
        if dari_rigs[str(tier)] <= 0:
            del dari_rigs[str(tier)]
        if not dari_rigs:
            del rigs[dari]

        ke_rigs = rigs.setdefault(ke, {})
        ke_rigs[str(tier)] = ke_rigs.get(str(tier), 0) + 1

        await save_json('users.json', users)

        lo, hi = MINING_RATES[ke][str(tier)]
        await send_embed(interaction, f"🔄 **Rig dipindahkan!**\nRig Tier {tier} sekarang menambang **{ke}** (est. {lo}-{hi} {ke}/jam).\nGratis — rig kamu, kamu yang tentuin mau mining apa.")
    
    @tree.command(name="pray", description="Berdoa untuk mendapatkan Koin")
    async def slash_pray(interaction: discord.Interaction):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        users = await load_json('users.json')
        now = datetime.now()
        last_pray = users.get(uid, {}).get('lastPray')
        
        if last_pray:
            last = datetime.fromisoformat(last_pray)
            delta = (now - last).total_seconds()
            if delta < 3600:
                await send_embed(interaction, f"⏳ Masih cooldown. Berdoa lagi dalam {int((3600-delta)//60)} menit.")
                return
    
        users.setdefault(uid, {})['lastPray'] = now.isoformat()
        await save_json('users.json', users)
        
        rand = random.random()
        if rand < 0.1:
            reward = await apply_soft_cap(uid, ECON_PRAY_JACKPOT)
            await add_coins(uid, reward, interaction.user.display_name)
            msg = f"✨ **Jackpot!** Kamu mendapatkan **{reward} Koin**!"
        elif rand < 0.6:
            reward = await apply_soft_cap(uid, ECON_PRAY_NORMAL)
            await add_coins(uid, reward, interaction.user.display_name)
            msg = f"🙏 Doa dikabulkan. Kamu mendapatkan **{reward} Koin**."
        else:
            msg = "💨 Tidak beruntung. Coba lagi nanti."
            
        await send_embed(interaction, msg)
    
    @tree.command(name="curse", description="Mengutuk orang agar koinnya hilang")
    async def slash_curse(interaction: discord.Interaction, target: discord.Member):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        tid = str(target.id)
        
        if uid == tid:
            await send_embed(interaction, "❌ Gak bisa mengutuk diri sendiri.")
            return

        users = await load_json('users.json')
        now = datetime.now()
        last_curse = users.get(uid, {}).get('lastCurse')

        if last_curse:
            last = datetime.fromisoformat(last_curse)
            delta = (now - last).total_seconds()
            if delta < 14400: # 4 hours
                await send_embed(interaction, f"⏳ Masih cooldown. Tunggu {int((14400-delta)//3600)} jam lagi.")
                return

        # Bayar persembahan 100 Koin secara atomik (sekalian cek saldo).
        if not await try_spend(uid, 100, interaction.user.display_name):
            await send_embed(interaction, "❌ Butuh 100 Koin buat ngutuk. Saldo kamu kurang.")
            return

        users.setdefault(uid, {})['lastCurse'] = now.isoformat()
        await save_json('users.json', users)

        target_stat = await get_discord_stat(tid)
        rand = random.random()

        if rand < 0.4:
            loss = random.randint(50, 500)
            actual_loss = min(loss, target_stat['coins'])
            await adjust_coins(tid, -actual_loss, target.display_name)
            msg = f"😈 **Kutukan Berhasil!** {target.mention} kehilangan **{actual_loss} Koin**!"
        else:
            # Karma
            await adjust_coins(uid, -200, interaction.user.display_name)
            msg = f"🛡️ **KUTUKAN GAGAL!** {target.display_name} terlindungi. Kamu kena efek balik dan kehilangan ekstra **200 Koin**!"

        await send_embed(interaction, msg)
    
    @tree.command(name="quest", description="Lihat atau klaim Misi Harian/Mingguan")
    async def slash_quest(interaction: discord.Interaction, action: str = "", quest_type: str = ""):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        if _phase3_enabled():
            from economy.quests import claim_quest, quest_progress
            if str(action).lower() == "claim":
                result = await claim_quest(
                    DB_PATH, guild_id=interaction.guild_id, user_id=uid, quest_type=quest_type,
                )
                await send_embed(interaction, result.message)
                return
            try:
                progress = await quest_progress(DB_PATH, interaction.guild_id, uid)
            except ValueError as exc:
                await send_embed(interaction, str(exc))
                return
            embed = discord.Embed(title=f"Quest: {interaction.user.display_name}", color=0x5865F2)
            for kind, data in progress.items():
                lines = [
                    f"{name}: {data['progress'][name]:,}/{target:,}"
                    for name, target in data["targets"].items()
                ]
                lines.append(f"Berakhir: {data['assignment']['periodEndUtc']}")
                lines.append(f"Status: {data['assignment']['status']}")
                embed.add_field(name=kind.title(), value="\n".join(lines), inline=False)
            await interaction.followup.send(embed=embed)
            return
        quests = await get_user_quests(uid)
        
        if not quests:
            await send_embed(interaction, "📜 Tidak ada quest yang aktif.")
            return
            
        embed = discord.Embed(title=f"📜 Quest Log: {interaction.user.display_name}", color=discord.Color.dark_purple())
        quest_rows = quests.get("quests", []) if isinstance(quests, dict) else []
        for q_data in quest_rows:
            status = "✅ Selesai" if q_data['progress'] >= q_data['target'] else f"⏳ {q_data['progress']}/{q_data['target']}"
            embed.add_field(name=q_data['name'], value=f"{q_data['desc']}\nProgress: {status}\nReward: {q_data['reward']} Koin", inline=False)
            
        await interaction.followup.send(embed=embed)
    
