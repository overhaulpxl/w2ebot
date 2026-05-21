import discord
import os
import google.generativeai as genai
import asyncio
from discord import FFmpegPCMAudio
import logging
from datetime import datetime, timedelta
import random
import sqlite3
import gtts
from aiohttp import web
import aiohttp
import io
import json
import re

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logging.warning("Pillow not installed. Family tree images will use text fallback.")

DB_PATH = r"C:\Users\blur\Downloads\ABDM\Compressed\w2e-next\my-app\prisma\dev.db"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

DISCORD_API_KEY = 'MMM'
GEMINI_API_KEY = 'MMM'

genai.configure(api_key=GEMINI_API_KEY)

generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-pro",
    generation_config=generation_config,
)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True
client = discord.Client(intents=intents)

CHAT_MEMORY_FILE = 'chat_memory.txt'
MAX_FILE_SIZE_MB = 50

voice_join_times = {} # user_id -> datetime
chat_sessions = {} # user_id -> chat session
rob_cooldowns = {}  # (attacker_id, target_id) -> datetime
rps_pending = {}    # challenger_id -> {target, bet, choice}
quest_progress = {} # user_id -> {quest_id: progress}
work_cooldowns = {} # user_id -> datetime
boss_cooldowns = {} # user_id -> datetime

# ── File paths ────────────────────────────────────────────────────────────────
FAMILY_FILE    = 'family.json'
ITEMS_FILE     = 'items.json'
WEEKLY_FILE    = 'weekly.json'
QUESTS_FILE    = 'quests.json'
CUSTOM_ROLES_FILE = 'custom_roles.json'
MARKET_FILE       = 'market.json'
PORTFOLIO_FILE    = 'portfolio.json'
PERSONAS_FILE     = 'personas.json'
BOSS_FILE         = 'boss.json'
RIGS_FILE         = 'rigs.json'
TREASURY_FILE     = 'treasury.json'
BINOMO_FILE       = 'binomo.json'
RIGS_FILE         = 'rigs.json'

# ⬇ Set this to the channel ID of your #custom-role channel
CUSTOM_ROLE_CHANNEL_ID = 0  # TODO: ganti dengan ID channel #custom-role kamu

# ── JSON helpers ─────────────────────────────────────────────────────────────
import sqlite3
import os

def _init_db():
    conn = sqlite3.connect('w2ebot.db')
    conn.execute("CREATE TABLE IF NOT EXISTS json_store (filename TEXT PRIMARY KEY, content TEXT)")
    conn.commit()
    conn.close()

_init_db()

def load_json(filepath):
    basename = os.path.basename(filepath)
    try:
        conn = sqlite3.connect('w2ebot.db')
        c = conn.cursor()
        c.execute("SELECT content FROM json_store WHERE filename=?", (basename,))
        row = c.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception:
        pass
    return {}

def save_json(filepath, data):
    basename = os.path.basename(filepath)
    try:
        conn = sqlite3.connect('w2ebot.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO json_store (filename, content) VALUES (?, ?)", (basename, json.dumps(data, ensure_ascii=False)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Save Error: {e}")

# ── Shop items ────────────────────────────────────────────────────────────────
SHOP_ITEMS = {
    'shield':      {'name': '🛡️ Shield',      'price': 500,  'desc': 'Kebal dari curse & rob 1x'},
    'double_xp':   {'name': '⚡ Double XP',   'price': 800,  'desc': '2x XP selama 2 jam'},
    'lucky_charm': {'name': '🍀 Lucky Charm', 'price': 300,  'desc': '+20% slot winrate 1x'},
}

# ── Quest templates ──────────────────────────────────────────────────────────
QUEST_TEMPLATES = [
    {'id': 'send_msg',    'desc': 'Kirim 5 pesan',           'target': 5},
    {'id': 'do_coinflip', 'desc': 'Lakukan coin flip 1x',    'target': 1},
    {'id': 'open_box',    'desc': 'Buka 1 lootbox',          'target': 1},
    {'id': 'pray_user',   'desc': 'Doakan 1 member',         'target': 1},
    {'id': 'use_slot',    'desc': 'Main slot 1x',            'target': 1},
    {'id': 'check_top',   'desc': 'Lihat leaderboard',       'target': 1},
    {'id': 'give_coins',  'desc': 'Berikan koin ke seseorang','target': 1},
]

def get_discord_stat(uid):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT coins, xp, level, lastDaily FROM DiscordStat WHERE id=?", (str(uid),))
        row = cur.fetchone()
        conn.close()
        if row:
            return {'coins': row[0], 'xp': row[1], 'level': row[2], 'lastDaily': row[3]}
    except Exception as e:
        logging.error(f"DB Error get: {e}")
    return {'coins': 0, 'xp': 0, 'level': 1, 'lastDaily': ''}

def update_discord_stat(uid, display_name, coins, xp, level, last_daily):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        now = datetime.utcnow().isoformat() + "Z"
        cur.execute('''
            INSERT INTO DiscordStat (id, displayName, coins, xp, level, lastDaily, updatedAt) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET 
            displayName=excluded.displayName,
            coins=excluded.coins,
            xp=excluded.xp,
            level=excluded.level,
            lastDaily=excluded.lastDaily,
            updatedAt=excluded.updatedAt
        ''', (str(uid), display_name, coins, xp, level, last_daily, now))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"DB Error update: {e}")

async def check_level_up(channel, user, xp_gained):
    uid = str(user.id)
    stat = get_discord_stat(uid)
    stat['xp'] += xp_gained
    next_level_xp = stat['level'] * 100
    if stat['xp'] >= next_level_xp:
        stat['level'] += 1
        stat['xp'] -= next_level_xp
        await channel.send(f"🎉 Selamat {user.mention}, kamu naik ke **Level {stat['level']}**!")
    update_discord_stat(uid, user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])

async def check_toxicity(text):
    prompt = f"Evaluasi pesan berikut. Jika mengandung ujaran kebencian parah, rasisme, atau NSFW ekstrim, balas HANYA dengan kata 'TOXIC'. Jika aman, balas 'SAFE'.\nPesan: {text}"
    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        return "TOXIC" in response.text.upper()
    except Exception:
        return False

# ── Quest helpers ─────────────────────────────────────────────────────────────
def get_user_quests(uid):
    quests_data = load_json(QUESTS_FILE)
    today = datetime.now().strftime('%Y-%m-%d')
    if uid not in quests_data or quests_data[uid].get('date') != today:
        chosen = random.sample(QUEST_TEMPLATES, min(3, len(QUEST_TEMPLATES)))
        quests_data[uid] = {
            'date': today,
            'quests': [{'id': q['id'], 'desc': q['desc'], 'target': q['target'], 'progress': 0, 'done': False} for q in chosen],
            'claimed': False
        }
        save_json(QUESTS_FILE, quests_data)
    return quests_data[uid]

def update_quest_progress(uid, quest_id, amount=1):
    quests_data = load_json(QUESTS_FILE)
    today = datetime.now().strftime('%Y-%m-%d')
    if uid not in quests_data or quests_data[uid].get('date') != today:
        return
    for q in quests_data[uid]['quests']:
        if q['id'] == quest_id and not q['done']:
            q['progress'] = min(q['progress'] + amount, q['target'])
            if q['progress'] >= q['target']:
                q['done'] = True
    save_json(QUESTS_FILE, quests_data)

# ── Family tree image generator ───────────────────────────────────────────────
async def fetch_avatar(session, url, size=80):
    try:
        async with session.get(url) as resp:
            data = await resp.read()
            img = Image.open(io.BytesIO(data)).convert('RGBA').resize((size, size))
            mask = Image.new('L', (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
            img.putalpha(mask)
            return img
    except Exception:
        img = Image.new('RGBA', (size, size), (80, 80, 100, 255))
        ImageDraw.Draw(img).ellipse((0, 0, size, size), fill=(100, 100, 120, 255))
        return img

async def generate_family_image(guild, uid):
    if not PILLOW_AVAILABLE:
        return None
    family = load_json(FAMILY_FILE)
    udata = family.get(str(uid), {})
    partner_id = udata.get('partner')
    children_ids = udata.get('children', [])

    async def get_member(mid):
        m = guild.get_member(int(mid)) if mid else None
        return m

    user_m   = await get_member(uid)
    partner_m = await get_member(partner_id) if partner_id else None
    child_ms  = [await get_member(cid) for cid in children_ids[:6]]

    W = max(900, 200 + len(child_ms) * 140)
    H = 420
    img = Image.new('RGB', (W, H), (13, 13, 23))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 14)
        font_small = ImageFont.truetype("arial.ttf", 11)
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    AVSIZE = 80
    async with aiohttp.ClientSession() as session:
        # Main user avatar
        u_av_url = user_m.display_avatar.with_size(128).url if user_m else None
        u_av = await fetch_avatar(session, u_av_url) if u_av_url else None

        # Partner avatar
        p_av_url = partner_m.display_avatar.with_size(128).url if partner_m else None
        p_av = await fetch_avatar(session, p_av_url) if p_av_url else None

        # Children avatars
        c_avs = []
        for cm in child_ms:
            av_url = cm.display_avatar.with_size(128).url if cm else None
            c_avs.append(await fetch_avatar(session, av_url) if av_url else None)

    cx = W // 2

    # Draw user (left of center if partner exists, else center)
    if partner_m:
        u_x, p_x = cx - 100, cx + 20
    else:
        u_x = cx - 40

    u_y = 40
    if u_av:
        img.paste(u_av, (u_x, u_y), u_av)
    u_name = (user_m.display_name if user_m else "You")[:14]
    draw.text((u_x + AVSIZE//2, u_y + AVSIZE + 4), u_name, fill=(200, 200, 255), font=font, anchor="mm")

    # Draw heart between couple
    couple_mid_x = cx
    if partner_m:
        if p_av:
            img.paste(p_av, (p_x, u_y), p_av)
        p_name = (partner_m.display_name)[:14]
        draw.text((p_x + AVSIZE//2, u_y + AVSIZE + 4), p_name, fill=(255, 180, 220), font=font, anchor="mm")
        draw.text((cx - 10, u_y + 30), "💑", fill=(255, 100, 150), font=font)
        # Line down from couple
        line_top = u_y + AVSIZE + 20
        draw.line([(couple_mid_x, line_top), (couple_mid_x, line_top + 40)], fill=(100, 100, 150), width=2)
    else:
        line_top = u_y + AVSIZE + 20
        draw.line([(u_x + AVSIZE//2, line_top), (u_x + AVSIZE//2, line_top + 40)], fill=(100, 100, 150), width=2)
        couple_mid_x = u_x + AVSIZE//2

    # Draw children
    if child_ms:
        n = len(child_ms)
        child_y = 260
        spacing = min(140, (W - 60) // n)
        start_x = cx - (n * spacing) // 2

        draw.line([(start_x + 40, child_y - 30), (start_x + (n-1)*spacing + 40, child_y - 30)], fill=(100, 100, 150), width=2)

        for i, (cm, cav) in enumerate(zip(child_ms, c_avs)):
            cx_i = start_x + i * spacing
            draw.line([(cx_i + 40, child_y - 30), (cx_i + 40, child_y)], fill=(100, 100, 150), width=2)
            if cav:
                img.paste(cav, (cx_i, child_y), cav)
            c_name = (cm.display_name if cm else "?")[:12]
            draw.text((cx_i + 40, child_y + AVSIZE + 4), c_name, fill=(180, 255, 180), font=font_small, anchor="mm")

    # Title
    draw.text((W//2, 15), "👨‍👩‍👧‍👦  W2E Family", fill=(180, 160, 255), font=font, anchor="mm")
    draw.rounded_rectangle([(5, 5), (W-5, H-5)], radius=16, outline=(60, 60, 90), width=2)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

async def generate_profile_image(member, stat, bg_url=None):
    if not PILLOW_AVAILABLE:
        return None
        
    W, H = 600, 300
    
    # Try fetching background if provided
    img = None
    if bg_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(bg_url) as resp:
                    data = await resp.read()
                    bg = Image.open(io.BytesIO(data)).convert('RGBA')
                    # Resize to fit and crop or just resize
                    bg = bg.resize((W, H))
                    img = Image.new('RGBA', (W, H))
                    img.paste(bg, (0, 0))
        except Exception:
            pass
            
    if not img:
        img = Image.new('RGB', (W, H), (20, 25, 35))
        
    # Dark overlay for readability
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 128))
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    img = Image.alpha_composite(img, overlay)
    
    draw = ImageDraw.Draw(img)
    try:
        font_lg = ImageFont.truetype("arial.ttf", 36)
        font_md = ImageFont.truetype("arial.ttf", 24)
        font_sm = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font_lg = ImageFont.load_default()
        font_md = font_lg
        font_sm = font_lg

    # Fetch avatar
    av_img = None
    av_url = member.display_avatar.with_size(128).url if member.display_avatar else None
    if av_url:
        async with aiohttp.ClientSession() as session:
            av_img = await fetch_avatar(session, av_url, size=120)
            
    if av_img:
        img.paste(av_img, (40, 40), av_img)
        
    # User info
    draw.text((180, 50), member.display_name, fill=(255, 255, 255), font=font_lg)
    booster_text = "👑 Server Booster" if member.premium_since else "Member"
    draw.text((180, 95), booster_text, fill=(255, 200, 50) if member.premium_since else (150, 150, 150), font=font_md)
    
    # Stats
    draw.text((40, 200), f"Level: {stat['level']}", fill=(180, 220, 255), font=font_md)
    draw.text((200, 200), f"XP: {stat['xp']} / {stat['level']*100}", fill=(180, 220, 255), font=font_md)
    draw.text((400, 200), f"💰 {stat['coins']} Koin", fill=(255, 215, 0), font=font_md)
    
    # Border
    draw.rectangle([(0, 0), (W-1, H-1)], outline=(60, 100, 150), width=4)

    buf = io.BytesIO()
    img.convert('RGB').save(buf, format='PNG')
    buf.seek(0)
    return buf

async def check_birthdays():
    await client.wait_until_ready()
    while not client.is_closed():
        today_str = datetime.now().strftime("%d-%m")
        bdays = load_json('birthdays.json')
        
        # We need a channel to announce birthdays.
        # Let's try to find a general channel.
        for guild in client.guilds:
            announce_channel = None
            for ch in guild.text_channels:
                if 'general' in ch.name.lower() or 'chat' in ch.name.lower():
                    if ch.permissions_for(guild.me).send_messages:
                        announce_channel = ch
                        break
            if not announce_channel:
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages:
                        announce_channel = ch
                        break
                        
            if announce_channel:
                for uid, date_str in bdays.items():
                    if date_str == today_str:
                        # Check if we already announced this year
                        last_bday = load_json('last_bday.json')
                        year = str(datetime.now().year)
                        key = f"{uid}_{year}"
                        if last_bday.get(key):
                            continue
                            
                        # Reward
                        stat = get_discord_stat(uid)
                        stat['coins'] += 1000
                        user = client.get_user(int(uid))
                        name = user.display_name if user else f"User {uid}"
                        update_discord_stat(uid, name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
                        
                        await announce_channel.send(f"🎉 **SELAMAT ULANG TAHUN!** 🎉\nHari ini adalah hari ulang tahun {user.mention if user else name}!\nSebagai hadiah, kamu mendapatkan **1000 Koin**! 🎁")
                        
                        last_bday[key] = True
                        save_json('last_bday.json', last_bday)
                        
        await asyncio.sleep(3600) # Check every hour

def init_market():
    market = load_json(MARKET_FILE)
    if not market or 'coins' not in market:
        market = {
            'last_updated': datetime.now().isoformat(),
            'coins': {
                'ETHR': {'name': 'ETHERnal', 'price': 1000, 'history': [1000]},
                'ORCL': {'name': 'Cosmic Oracle', 'price': 2000, 'history': [2000]},
                'MTR': {'name': 'Meteorite', 'price': 500, 'history': [500]},
                'ECLP': {'name': 'Eclipsoin', 'price': 250, 'history': [250]},
                'ORBT': {'name': 'Orbitcoin', 'price': 100, 'history': [100]},
                'TRST': {'name': 'TrustCoin', 'price': 50, 'history': [50]},
                'LUNA': {'name': 'Lunniera', 'price': 5000, 'history': [5000]}
            }
        }
        save_json(MARKET_FILE, market)
    return market

async def update_market_prices():
    await client.wait_until_ready()
    while not client.is_closed():
        market = init_market()
        for symbol, data in market['coins'].items():
            current_price = data['price']
            
            # Volatility setting
            if symbol == 'ETHR':
                volatility = 0.05 # 5%
            elif symbol == 'ORCL':
                volatility = 0.08 # 8%
            elif symbol == 'ECLP':
                volatility = 0.15 # 15%
            elif symbol == 'ORBT':
                volatility = 0.20 # 20%
            elif symbol == 'MTR':
                volatility = 0.25 # 25%
            elif symbol == 'LUNA':
                volatility = 0.40 # 40% high risk
            elif symbol == 'TRST':
                volatility = 0.50 # 50% extreme risk
            else:
                volatility = 0.10
                
            change_pct = random.uniform(-volatility, volatility)
            new_price = int(current_price * (1 + change_pct))
            
            # Prevent going to 0
            if new_price < 10:
                new_price = 10
                
            # Update history (keep last 10)
            data['history'].append(new_price)
            if len(data['history']) > 10:
                data['history'].pop(0)
                
            data['price'] = new_price
            
        # Random Market Event (10% chance)
        event_message = None
        if random.random() < 0.10:
            target_coin = random.choice(list(market['coins'].keys()))
            event_type = random.choice(['pump', 'dump'])
            
            if event_type == 'pump':
                pump_pct = random.uniform(0.5, 1.2) # 50% to 120% pump
                market['coins'][target_coin]['price'] = int(market['coins'][target_coin]['price'] * (1 + pump_pct))
                event_message = f"📰 **BREAKING NEWS!** 📰\nAda rumor besar tentang {market['coins'][target_coin]['name']} ({target_coin})! Harga mendadak meroket **+{int(pump_pct*100)}%**! 🚀🌕"
            else:
                dump_pct = random.uniform(0.4, 0.8) # 40% to 80% dump
                market['coins'][target_coin]['price'] = int(market['coins'][target_coin]['price'] * (1 - dump_pct))
                event_message = f"🚨 **PANIC SELL!** 🚨\nRegulator menemukan celah keamanan di {market['coins'][target_coin]['name']} ({target_coin})! Harga anjlok **-{int(dump_pct*100)}%**! 📉🩸"
                
            # Prevent going to 0 again
            if market['coins'][target_coin]['price'] < 10:
                market['coins'][target_coin]['price'] = 10
                
            # Update latest history point to reflect massive change
            market['coins'][target_coin]['history'][-1] = market['coins'][target_coin]['price']
            
        market['last_updated'] = datetime.now().isoformat()
        save_json(MARKET_FILE, market)
        
        # Broadcast event message
        if event_message:
            for guild in client.guilds:
                for ch in guild.text_channels:
                    if 'general' in ch.name.lower() or 'chat' in ch.name.lower():
                        if ch.permissions_for(guild.me).send_messages:
                            client.loop.create_task(ch.send(event_message))
                            break
                            
        # Resolve Binomo Bets
        binomo = load_json(BINOMO_FILE)
        if binomo:
            results = []
            for uid, bet_data in list(binomo.items()):
                symbol = bet_data['symbol']
                direction = bet_data['direction'] # 'UP' or 'DOWN'
                bet_amount = bet_data['bet']
                entry_price = bet_data['entry_price']
                
                new_price = market['coins'][symbol]['price']
                won = False
                if direction == 'UP' and new_price > entry_price:
                    won = True
                elif direction == 'DOWN' and new_price < entry_price:
                    won = True
                    
                if won:
                    winnings = bet_amount * 2
                    stat = get_discord_stat(uid)
                    stat['coins'] += winnings
                    update_discord_stat(uid, f"User_{uid}", stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
                    results.append(f"<@{uid}> **MENANG {winnings} Koin!** (Tebak {symbol} {direction} | Entry: {entry_price}, Now: {new_price})")
                else:
                    results.append(f"<@{uid}> **RUGI {bet_amount} Koin!** (Tebak {symbol} {direction} | Entry: {entry_price}, Now: {new_price})")
                
                del binomo[uid]
            save_json(BINOMO_FILE, binomo)
            
            if results:
                result_str = "🎰 **HASIL JUDI BINOMO 10 MENIT INI:** 🎰\n" + "\n".join(results)
                for guild in client.guilds:
                    for ch in guild.text_channels:
                        if 'general' in ch.name.lower() or 'chat' in ch.name.lower():
                            if ch.permissions_for(guild.me).send_messages:
                                client.loop.create_task(ch.send(result_str))
                                break
                            
        await asyncio.sleep(600) # Every 10 minutes

async def voice_salary_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(600) # Wait 10 minutes
        for guild in client.guilds:
            # Cari channel pengumuman (general/chat)
            announce_channel = None
            for ch in guild.text_channels:
                if 'general' in ch.name.lower() or 'chat' in ch.name.lower():
                    if ch.permissions_for(guild.me).send_messages:
                        announce_channel = ch
                        break
            if not announce_channel:
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages:
                        announce_channel = ch
                        break
                        
            # Loop setiap voice channel
            for vc in guild.voice_channels:
                members = [m for m in vc.members if not m.bot]
                if len(members) >= 2: # Minimal 2 orang (anti solo farming)
                    for m in members:
                        if not m.voice.self_deaf and not m.voice.deaf:
                            uid = str(m.id)
                            stat = get_discord_stat(uid)
                            stat['xp'] += 15
                            stat['coins'] += 50
                            
                            next_level_xp = stat['level'] * 100
                            leveled_up = False
                            while stat['xp'] >= next_level_xp:
                                stat['level'] += 1
                                stat['xp'] -= next_level_xp
                                next_level_xp = stat['level'] * 100
                                leveled_up = True
                                
                            if leveled_up and announce_channel:
                                client.loop.create_task(
                                    announce_channel.send(f"🎙️ 🎉 {m.mention} baru saja naik ke **Level {stat['level']}** karena rajin mabar di Voice Channel!")
                                )
                                
                            update_discord_stat(uid, m.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])

async def boss_raid_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(3600) # Every 1 hour
        if random.random() < 0.20: # 20% chance to spawn boss
            boss_data = load_json(BOSS_FILE)
            if not boss_data.get('active', False):
                boss_data = {
                    'active': True,
                    'hp': 10000,
                    'max_hp': 10000,
                    'name': '🐉 Naga Emas Koruptor'
                }
                save_json(BOSS_FILE, boss_data)
                
                # Cari channel pengumuman
                for guild in client.guilds:
                    for ch in guild.text_channels:
                        if 'general' in ch.name.lower() or 'chat' in ch.name.lower():
                            if ch.permissions_for(guild.me).send_messages:
                                client.loop.create_task(
                                    ch.send(f"⚠️ **BOSS RAID EVENT DIMULAI!** ⚠️\n**{boss_data['name']}** telah muncul dengan {boss_data['hp']} HP!\nKetik `!attack` untuk menyerang! Yang berhasil membunuhnya mendapat hadiah 5000 Koin!")
                                )
                                break
                                break
                                
async def crypto_mining_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(3600) # Every 1 hour
        rigs = load_json(RIGS_FILE)
        portfolio = load_json(PORTFOLIO_FILE)
        
        has_mined = False
        for uid, count in rigs.items():
            if count > 0:
                has_mined = True
                mined_ethr = random.randint(1, 5) * count
                if uid not in portfolio:
                    portfolio[uid] = {}
                if 'ETHR' not in portfolio[uid]:
                    # Format is now dict due to PnL changes
                    portfolio[uid]['ETHR'] = {'amount': 0, 'avg_price': 1000}
                elif isinstance(portfolio[uid]['ETHR'], int):
                    # Migration from old format
                    portfolio[uid]['ETHR'] = {'amount': portfolio[uid]['ETHR'], 'avg_price': 1000}
                    
                portfolio[uid]['ETHR']['amount'] += mined_ethr
                
        if has_mined:
            save_json(PORTFOLIO_FILE, portfolio)

@client.event
async def on_ready():
    client.loop.create_task(start_web_server())
    client.loop.create_task(check_birthdays())
    client.loop.create_task(update_market_prices())
    client.loop.create_task(voice_salary_loop())
    client.loop.create_task(boss_raid_loop())
    client.loop.create_task(crypto_mining_loop())
    logging.info(f'We have logged in as {client.user}')

@web.middleware
async def cors_middleware(request, handler):
    response = await handler(request)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

async def handle_options(request):
    return web.Response(status=200)

async def api_radar(request):
    data = []
    for uid, join_time in voice_join_times.items():
        delta = datetime.now() - join_time
        minutes = int(delta.total_seconds() // 60)
        
        # Try to find the user in discord cache
        user = client.get_user(uid)
        username = user.display_name if user else f"User {uid}"
        
        # Find which voice channel they are in
        channel_name = "Unknown"
        for guild in client.guilds:
            member = guild.get_member(uid)
            if member and member.voice and member.voice.channel:
                channel_name = member.voice.channel.name
                break
                
        data.append({
            'user_id': str(uid),
            'username': username,
            'channel': channel_name,
            'minutes': minutes
        })
    return web.json_response(data)

async def api_broadcast(request):
    try:
        data = await request.json()
        channel_type = data.get('channel')
        message = data.get('message')
        
        if not channel_type or not message:
            return web.json_response({'error': 'Missing channel or message'}, status=400)
            
        channel_id_map = {
            'bhot': 1332111384523309156,
            'general': 1332113600894079131,
            'console': 1340942564379070535
        }
        
        cid = channel_id_map.get(channel_type)
        if not cid:
            return web.json_response({'error': 'Invalid channel type'}, status=400)
            
        channel = client.get_channel(cid)
        if not channel:
            return web.json_response({'error': 'Channel not found by bot'}, status=404)
            
        await send_long_message(channel, message)
            
        return web.json_response({'status': 'sent'})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def start_web_server():
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_options('/{tail:.*}', handle_options)
    app.router.add_get('/api/radar', api_radar)
    app.router.add_post('/api/broadcast', api_broadcast)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8081)
    await site.start()
    logging.info("Bot API started on port 8081")

@client.event
async def on_voice_state_update(member, before, after):
    if before.channel is None and after.channel is not None:
        voice_join_times[member.id] = datetime.now()
        # 👑 Booster Voice Intro
        if member.premium_since and not member.bot:
            guild = member.guild
            notify_channel = None
            for ch in guild.text_channels:
                if 'general' in ch.name.lower() or 'chat' in ch.name.lower():
                    if ch.permissions_for(guild.me).send_messages:
                        notify_channel = ch
                        break
            if notify_channel is None:
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages:
                        notify_channel = ch
                        break
            if notify_channel:
                intros = [
                    f"📢 **Perhatian seisi server!** Donatur server kami, **{member.display_name}**, telah hadir di 🔊 **{after.channel.name}**! Sambut kedatangannya! 👑",
                    f"🎺 *Terompet berbunyi...* **{member.display_name}** (Server Booster) telah memasuki VC **{after.channel.name}**! Siap-siap! 👑",
                    f"🌟 **{member.display_name}** si Sultan server baru saja join **{after.channel.name}**! Selawat dulu dong~ 👑",
                ]
                await notify_channel.send(random.choice(intros))

    elif before.channel is not None and after.channel is None:
        if member.id in voice_join_times:
            join_time = voice_join_times[member.id]
            del voice_join_times[member.id]
            
            # VC Farming Leveling System
            duration = datetime.now() - join_time
            minutes = int(duration.total_seconds() // 60)
            
            if minutes > 0 and not member.bot:
                uid = str(member.id)
                users = load_json('users.json')
                if uid not in users:
                    users[uid] = {'balance': 0, 'items': {}, 'achievements': [], 'total_vc_minutes': 0}
                
                # Tambah XP & Koin
                xp_gained = minutes * 10
                coins_gained = minutes * 5
                users[uid]['balance'] += coins_gained
                users[uid]['total_vc_minutes'] = users[uid].get('total_vc_minutes', 0) + minutes
                
                # Check No-Lifer Achievement
                if users[uid]['total_vc_minutes'] >= 1440 and 'no_lifer' not in users[uid].get('achievements', []):
                    if 'achievements' not in users[uid]: users[uid]['achievements'] = []
                    users[uid]['achievements'].append('no_lifer')
                    # Send congrats message
                    guild = member.guild
                    for ch in guild.text_channels:
                        if ch.permissions_for(guild.me).send_messages:
                            asyncio.create_task(ch.send(f"🏆 **ACHIEVEMENT UNLOCKED!** {member.mention} baru saja mendapatkan gelar **🧟‍♂️ No-Lifer** karena telah menghabiskan total 24 jam di Voice Channel!"))
                            break
                            
                save_json('users.json', users)
                
                # Update DB XP (using existing get/update_discord_stat)
                stat = get_discord_stat(uid)
                new_xp = stat['xp'] + xp_gained
                update_discord_stat(uid, member.display_name, stat['coins'], new_xp, stat['level'], stat['last_daily'])
                
                # Optional: Send DM or channel message for XP gained if you want, but it might be spammy.
                logging.info(f"{member.display_name} earned {xp_gained} XP and {coins_gained} Coins from {minutes} mins in VC.")

async def send_long_message(channel, message):
    if len(message) <= 2000:
        await channel.send(message)
    else:
        for i in range(0, len(message), 2000):
            await channel.send(message[i:i+2000])

def write_to_memory(content):
    if os.path.exists(CHAT_MEMORY_FILE):
        if os.path.getsize(CHAT_MEMORY_FILE) > MAX_FILE_SIZE_MB * 1024 * 1024:
            os.remove(CHAT_MEMORY_FILE)
    with open(CHAT_MEMORY_FILE, 'a', encoding='utf-8') as f:
        f.write(content + '\n')

async def finished_callback(sink, channel: discord.TextChannel, *args):
    recorded_users = [
        f"<@{user_id}>"
        for user_id, audio in sink.audio_data.items()
    ]
    if not recorded_users:
        await channel.send("Tidak ada suara yang terekam.")
        return

    await channel.send(f"Selesai merekam {', '.join(recorded_users)}. Memproses audio ke Gemini AI...")

    for user_id, audio in sink.audio_data.items():
        file_path = f"rekaman_{user_id}.wav"
        with open(file_path, "wb") as f:
            f.write(audio.file.read())

        try:
            uploaded_file = genai.upload_file(path=file_path)
            prompt = "Ini adalah rekaman suara dari percakapan discord. Tuliskan transkripnya, lalu berikan balasan yang santai dan lucu berdasarkan ucapan tersebut."
            response = await asyncio.to_thread(model.generate_content, [uploaded_file, prompt])
            await channel.send(f"🎙️ **AI Merespons Suara <@{user_id}>:**\n{response.text}")
            uploaded_file.delete()
        except Exception as e:
            logging.error(f"Error processing audio: {str(e)}")
            await channel.send(f"Gagal memproses suara <@{user_id}> dengan AI.")
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

def get_gemini_response(query, user_id=None):
    try:
        final_query = query
        if user_id:
            personas = load_json(PERSONAS_FILE)
            if str(user_id) in personas:
                final_query = f"[SYSTEM INSTRUCTION: Mulai sekarang kamu HARUS berbicara dan bertingkah sepenuhnya dengan persona/gaya ini: '{personas[str(user_id)]}'. Jangan pernah keluar dari karakter.]\n\nPesan User: {query}"
                
            if user_id not in chat_sessions:
                chat_sessions[user_id] = model.start_chat(history=[])
            response = chat_sessions[user_id].send_message(final_query)
        else:
            chat_session = model.start_chat(history=[])
            response = chat_session.send_message(final_query)
        return response.text
    except Exception as e:
        logging.error(f"Error getting Gemini response: {str(e)}")
        return "Error getting response from Gemini."

@client.event
async def on_message(message):
    if message.author == client.user:
        return



    # ── Update Quest Progress ────────────────────────────────────────────────
    update_quest_progress(str(message.author.id), 'send_msg', 1)
    
    # ── Booster Custom Role ──────────────────────────────────────────────────
    if message.channel.id == CUSTOM_ROLE_CHANNEL_ID:
        # Check jika user adalah Server Booster
        if message.author.premium_since:
            # Pastikan format bener (nama role + image attachment)
            if message.attachments and len(message.attachments) > 0 and message.content:
                attachment = message.attachments[0]
                # Boleh PNG atau JPG (maksimal harus kecil biasanya 256kb, tp kita download)
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    # Extract Nama Role and Hex Color using Regex
                    name_match = re.search(r'Nama Role\s*:\s*(.+)', message.content, re.IGNORECASE)
                    color_match = re.search(r'role color\s*:\s*(?:#)?([0-9a-fA-F]{6})', message.content, re.IGNORECASE)
                    
                    if name_match:
                        role_name = name_match.group(1).strip()[:100]
                    else:
                        role_name = message.content.split('\n')[0][:100]
                    
                    role_kwargs = {
                        "name": role_name,
                        "reason": f"Custom role for booster {message.author.display_name}"
                    }
                    if color_match:
                        role_kwargs["color"] = discord.Color(int(color_match.group(1), 16))

                    try:
                        # Download icon
                        raw_icon_bytes = await attachment.read()
                        
                        # Process icon to make it a circle with transparent background
                        if PILLOW_AVAILABLE:
                            try:
                                img = Image.open(io.BytesIO(raw_icon_bytes)).convert("RGBA")
                                # Crop to square
                                min_dim = min(img.size)
                                left = (img.width - min_dim) / 2
                                top = (img.height - min_dim) / 2
                                right = (img.width + min_dim) / 2
                                bottom = (img.height + min_dim) / 2
                                img = img.crop((left, top, right, bottom))
                                # Resize
                                img = img.resize((256, 256), Image.Resampling.LANCZOS)
                                # Create circular mask
                                mask = Image.new('L', (256, 256), 0)
                                draw = ImageDraw.Draw(mask)
                                draw.ellipse((0, 0, 256, 256), fill=255)
                                # Apply mask
                                img.putalpha(mask)
                                out = io.BytesIO()
                                img.save(out, format="PNG")
                                processed_icon_bytes = out.getvalue()
                            except Exception as e:
                                logging.error(f"Error processing custom role icon: {e}")
                                processed_icon_bytes = raw_icon_bytes
                        else:
                            processed_icon_bytes = raw_icon_bytes
                            
                        role_kwargs["display_icon"] = processed_icon_bytes
                        
                        # Cek apakah user udah punya custom role sebelumnya
                        croles_data = load_json(CUSTOM_ROLES_FILE)
                        old_role_id = croles_data.get(str(message.author.id))
                        
                        if old_role_id:
                            old_role = message.guild.get_role(int(old_role_id))
                            if old_role:
                                await old_role.delete(reason="Replaced custom role")
                        
                        # Bikin role baru
                        new_role = await message.guild.create_role(**role_kwargs)
                        
                        # Assign ke user
                        await message.author.add_roles(new_role)
                        
                        # Simpan ID role barunya
                        croles_data[str(message.author.id)] = new_role.id
                        save_json(CUSTOM_ROLES_FILE, croles_data)
                        
                        await message.add_reaction("✅")
                        await message.channel.send(f"🎉 Sukses! Custom Role **{role_name}** dengan icon tersebut telah dibuat dan diberikan kepadamu {message.author.mention}.")
                        
                    except discord.Forbidden:
                        await message.channel.send("❌ Bot tidak memiliki permission untuk membuat/mengelola role atau emoji.")
                    except discord.HTTPException as e:
                        await message.channel.send(f"❌ Gagal membuat role. Pastikan server sudah Level 2 Boost untuk fitur Role Icon!\nError: {e.text}")
                else:
                    await message.channel.send(f"{message.author.mention} Tolong lampirkan gambar (PNG/JPG) untuk icon role-nya.")
            elif not message.author.bot:
                # Kalo booster chat biasa tanpa attachment di channel ini, ingetin
                pass 
        else:
            if not message.author.bot:
                await message.delete()
                await message.channel.send(f"❌ {message.author.mention}, channel ini khusus untuk **Server Booster** membuat custom role!", delete_after=5)
        return


    if message.channel.id == 1341038015186862201:
        response = get_gemini_response(message.content, message.author.id)
        await send_long_message(message.channel, response)
        write_to_memory(f'User: {message.content}\nBot: {response}')
        return

    if message.content.startswith('w2e ') or message.content.startswith('!ai '):
        prefix = 'w2e ' if message.content.startswith('w2e ') else '!ai '
        query = message.content[len(prefix):].strip()
        if not query:
            await message.channel.send('Please provide a query.')
            return
        response = get_gemini_response(query, message.author.id)
        await send_long_message(message.channel, response)
        write_to_memory(f'User: {query}\nBot: {response}')
    
    if message.content.startswith('w2e1'):
        channel_id = 1332111384523309156
        message_content = message.content[len('w2e1 '):].strip()
        channel = client.get_channel(channel_id)
        if channel:
            await send_long_message(channel, message_content)
            await message.channel.send("Message sent to bhot.")
            write_to_memory(f'User: {message_content}\nBot: Message sent to bhot.')
        else:
            await message.channel.send("Invalid channel ID for bhot.")
    
    if message.content.startswith('w2e2'):
        channel_id = 1332113600894079131
        message_content = message.content[len('w2e2 '):].strip()
        channel = client.get_channel(channel_id)
        if channel:
            await send_long_message(channel, message_content)
            await message.channel.send("Message sent to general.")
            write_to_memory(f'User: {message_content}\nBot: Message sent to general.')
        else:
            await message.channel.send("Invalid channel ID for general.")
    
    if message.content.startswith('w2e3'):
        channel_id = 1340942564379070535
        message_content = message.content[len('w2e3 '):].strip()
        channel = client.get_channel(channel_id)
        if channel:
            await send_long_message(channel, message_content)
            await message.channel.send("Message sent to console.")
            write_to_memory(f'User: {message_content}\nBot: Message sent to console.')
        else:
            await message.channel.send("Invalid channel ID for console.")

    if message.content.startswith('w2echannel'):
        await message.channel.send("List of channels:\n1. bhot (1332111384523309156)\n2. general (1332113600894079131)\n3. console (1340942564379070535)")

    if message.content.startswith('w2ehelp'):
        await message.channel.send(
            "Here are the available commands:\n"
            "1. `w2e <query>` or `!ai <query>`: Generate a response using the Gemini model.\n"
            "2. `w2e1 <message>`: Send a message to the bhot channel.\n"
            "3. `w2e2 <message>`: Send a message to the general channel.\n"
            "4. `w2e3 <message>`: Send a message to the console channel.\n"
            "5. `w2echannel`: List all available channels and their IDs.\n"
            "6. `w2ehelp`: Show this help message.\n"
            "7. `!find @user`: Find which voice channel a user is in and for how long.\n"
            "8. `!profile`: View your stats.\n"
            "9. `!w2edaily`: Claim your daily coins.\n"
            "10. `!w2egacha`: Gacha title for 200 coins.\n"
            "11. `!w2evalo <username>`: Generate fake Valorant stats.\n"
            "12. `!w2elisten`: Join voice and record audio for Gemini AI.\n"
            "13. `!w2eremindme <minutes> <message>`: Set a reminder.\n"
            "14. `!w2eping`: Check bot latency.\n"
        )

    if message.content.startswith('!w2eping'):
        latency = round(client.latency * 1000)
        await message.channel.send(f"🏓 Pong! Latency: **{latency}ms**")

    if message.content.startswith('!find '):
        if not message.mentions:
            await message.channel.send("Silakan mention user yang ingin dicari: `!find @user`")
            return
        target = message.mentions[0]
        if target.voice and target.voice.channel:
            channel = target.voice.channel
            link = f"https://discord.com/channels/{message.guild.id}/{channel.id}"
            duration_str = "Tidak diketahui"
            if target.id in voice_join_times:
                delta = datetime.now() - voice_join_times[target.id]
                minutes = int(delta.total_seconds() // 60)
                duration_str = f"{minutes} menit"
            await message.channel.send(f"{target.display_name} sedang berada di voice channel **{channel.name}** selama {duration_str}.\nJoin link: {link}")
        else:
            await message.channel.send(f"{target.display_name} tidak sedang berada di voice channel mana pun.")

    if message.content.startswith('!checkbots'):
        active_bots = []
        idle_bots = []
        for member in message.guild.members:
            if member.bot:
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
            
        await message.channel.send(res)

    if message.content.startswith('!w2edaily'):
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        today = datetime.now().strftime('%Y-%m-%d')
        if stat['lastDaily'] == today:
            await message.channel.send(f"❌ Kamu sudah klaim daily hari ini. Tunggu besok ya!")
            return
            
        reward = random.randint(100, 500)
        multiplier_str = ""
        if message.author.premium_since:
            reward *= 2
            multiplier_str = " (👑 Booster Bonus x2!)"
            
        await check_level_up(message.channel, message.author, 20)
        stat = get_discord_stat(uid) # Re-fetch after level up to ensure correct save
        stat['coins'] += reward
        stat['lastDaily'] = today
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], today)
        await message.channel.send(f"🎉 **{message.author.display_name}** mendapatkan **{reward} Koin** dari Daily!{multiplier_str} (Total koin: {stat['coins']})")

    if message.content.startswith('!w2egacha'):
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        if stat['coins'] < 200:
            await message.channel.send("❌ Koin kamu tidak cukup! Butuh 200 Koin untuk gacha.")
            return
            
        stat['coins'] -= 200
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        gacha_titles = ['Raja Skip Lagu', 'Penyepong Spotify', 'Pendengar Setia', 'DJ Amatir', 'Sobat Indie', 'Kuli Discord', 'Budak Layar', 'Auto Muted', 'Noise Cancellation Manusia', 'Toxic Tapi Lucu']
        
        if message.author.premium_since:
            gacha_titles.extend(['👑 Pemilik Server', '🐉 Naga Emas', '💎 Donatur Elit', '🌟 Sultan Bintang', '🗿 Sepuh VIP'])
            
        won_title = random.choice(gacha_titles)
        await message.channel.send(f"🎰 **GACHA RESULT** 🎰\nSelamat {message.author.mention}, kamu mendapatkan gelar: **{won_title}**! (-200 Koin)")
        await check_level_up(message.channel, message.author, 50)

    if message.content.startswith('!market') or message.content.startswith('!crypto'):
        market = load_json(MARKET_FILE)
        if not market or 'coins' not in market:
            await message.channel.send("❌ Pasar belum siap. Coba lagi nanti.")
            return
            
        embed = discord.Embed(title="📈 W2E Crypto Market (Roblox Edition)", description="Harga koin berfluktuasi setiap 10 menit!\n(Ada peluang 10% terjadi Kejadian Luar Biasa)", color=discord.Color.green())
        
        for symbol, data in market['coins'].items():
            price = data['price']
            history = data['history']
            old_price = history[-2] if len(history) > 1 else price
            
            trend_emoji = "📈" if price > old_price else "📉" if price < old_price else "➖"
            diff = price - old_price
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            
            # Sparkline generation
            spark_chars = " ▂▃▄▅▆▇█"
            if len(history) > 1:
                min_h = min(history)
                max_h = max(history)
                diff_h = max_h - min_h
                if diff_h == 0: diff_h = 1
                spark = "".join([spark_chars[int(((h - min_h) / diff_h) * 7)] for h in history])
            else:
                spark = "➖"
            
            embed.add_field(name=f"{data['name']} ({symbol})", value=f"**{price} Koin** {trend_emoji} ({diff_str})\nTrend: `[{spark}]`", inline=False)
            
        last_upd = market.get('last_updated', 'N/A')
        if last_upd != 'N/A':
            last_upd = last_upd.replace('T', ' ')[:19]
        embed.set_footer(text=f"Terakhir update: {last_upd} UTC")
        await message.channel.send(embed=embed)

    if message.content.startswith('!buy '):
        parts = message.content.split()
        if len(parts) < 3:
            await message.channel.send("Format: `!buy <koin> <jumlah>` — contoh: `!buy RBUX 5`")
            return
            
        symbol = parts[1].upper()
        try:
            amount = int(parts[2])
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.channel.send("❌ Jumlah harus berupa angka positif.")
            return
            
        market = load_json(MARKET_FILE)
        if symbol not in market.get('coins', {}):
            await message.channel.send(f"❌ Koin **{symbol}** tidak ditemukan di pasar! Ketik `!market` untuk daftar koin.")
            return
            
        price = market['coins'][symbol]['price']
        total_cost = price * amount
        
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        
        if stat['coins'] < total_cost:
            await message.channel.send(f"❌ Saldo Koin kamu tidak cukup! Butuh **{total_cost} Koin** untuk membeli {amount} {symbol}.")
            return
            
        # Potong koin
        stat['coins'] -= total_cost
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        # Tambah ke portfolio
        portfolio = load_json(PORTFOLIO_FILE)
        if uid not in portfolio:
            portfolio[uid] = {}
        if symbol not in portfolio[uid]:
            portfolio[uid][symbol] = {'amount': 0, 'avg_price': 0.0}
        elif isinstance(portfolio[uid][symbol], int):
            # Migrate old format
            portfolio[uid][symbol] = {'amount': portfolio[uid][symbol], 'avg_price': price}
            
        old_amount = portfolio[uid][symbol]['amount']
        old_avg = portfolio[uid][symbol]['avg_price']
        
        new_amount = old_amount + amount
        new_avg = ((old_amount * old_avg) + (amount * price)) / new_amount if new_amount > 0 else price
        
        portfolio[uid][symbol]['amount'] = new_amount
        portfolio[uid][symbol]['avg_price'] = new_avg
        save_json(PORTFOLIO_FILE, portfolio)
        
        await message.channel.send(f"✅ Sukses membeli **{amount} {symbol}** seharga **{total_cost} Koin**!\nSisa Koin RPG kamu: {stat['coins']}.")

    if message.content.startswith('!sell '):
        parts = message.content.split()
        if len(parts) < 3:
            await message.channel.send("Format: `!sell <koin> <jumlah>` — contoh: `!sell RBUX 5`")
            return
            
        symbol = parts[1].upper()
        try:
            amount = int(parts[2])
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.channel.send("❌ Jumlah harus berupa angka positif.")
            return
            
        uid = str(message.author.id)
        portfolio = load_json(PORTFOLIO_FILE)
        
        if uid not in portfolio:
            await message.channel.send(f"❌ Portofoliomu kosong!")
            return
            
        user_asset = portfolio[uid].get(symbol)
        
        if user_asset is None:
            await message.channel.send(f"❌ Kamu tidak memiliki koin {symbol} di portofolio kamu!")
            return
            
        if isinstance(user_asset, int):
            user_asset = {'amount': user_asset, 'avg_price': 1000}
            portfolio[uid][symbol] = user_asset
            
        if user_asset['amount'] < amount:
            await message.channel.send(f"❌ Kamu cuma punya **{user_asset['amount']} {symbol}**, tidak cukup untuk menjual {amount}!")
            return
            
        market = load_json(MARKET_FILE)
        if symbol not in market.get('coins', {}):
            await message.channel.send(f"❌ Pasar error, koin tidak valid.")
            return
            
        price = market['coins'][symbol]['price']
        total_revenue = price * amount
        
        # TAX 2%
        tax = int(total_revenue * 0.02)
        net_revenue = total_revenue - tax
        
        # Tambah ke Treasury
        treasury = load_json(TREASURY_FILE)
        if not treasury: treasury = {'balance': 0}
        treasury['balance'] = treasury.get('balance', 0) + tax
        save_json(TREASURY_FILE, treasury)
        
        # Hapus dari portfolio
        portfolio[uid][symbol]['amount'] -= amount
        if portfolio[uid][symbol]['amount'] <= 0:
            del portfolio[uid][symbol]
        save_json(PORTFOLIO_FILE, portfolio)
        
        # Tambah koin
        stat = get_discord_stat(uid)
        stat['coins'] += net_revenue
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        # Kalkulasi Profit 
        avg_price = user_asset['avg_price']
        cost = avg_price * amount
        pnl = net_revenue - cost
        pnl_str = f"🟩 Untung +{int(pnl)}" if pnl >= 0 else f"🟥 Rugi {int(pnl)}"
        
        await message.channel.send(f"✅ Sukses menjual **{amount} {symbol}**!\nValuasi: {total_revenue} | Pajak (2%): -{tax}\n💰 Diterima Bersih: **{net_revenue} Koin**\n📊 Status Trade: {pnl_str} Koin")

    if message.content.startswith('!kas') or message.content.startswith('!treasury'):
        treasury = load_json(TREASURY_FILE)
        balance = treasury.get('balance', 0) if treasury else 0
        await message.channel.send(f"🏦 **Brankas Komunitas (W2E Treasury)**\nUang pajak yang terkumpul: **{balance} Koin RPG**\n*(Uang ini akan digunakan untuk membayar hadiah Boss Raid!)*")

    if message.content.startswith('!tebak '):
        parts = message.content.split()
        if len(parts) < 4:
            await message.channel.send("Format: `!tebak <KOIN> <UP/DOWN> <TARUHAN>`\nContoh: `!tebak LUNA UP 500`")
            return
            
        symbol = parts[1].upper()
        direction = parts[2].upper()
        if direction not in ['UP', 'DOWN']:
            await message.channel.send("❌ Arah harus **UP** atau **DOWN**.")
            return
            
        try:
            bet = int(parts[3])
            if bet < 100:
                await message.channel.send("❌ Taruhan minimal 100 Koin.")
                return
        except ValueError:
            await message.channel.send("❌ Taruhan harus angka.")
            return
            
        market = load_json(MARKET_FILE)
        if symbol not in market.get('coins', {}):
            await message.channel.send("❌ Koin tidak ditemukan.")
            return
            
        uid = str(message.author.id)
        binomo = load_json(BINOMO_FILE)
        if uid in binomo:
            await message.channel.send("❌ Kamu sudah punya taruhan aktif! Tunggu pasar *update* (maks 10 menit).")
            return
            
        stat = get_discord_stat(uid)
        if stat['coins'] < bet:
            await message.channel.send("❌ Koin kamu kurang!")
            return
            
        stat['coins'] -= bet
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        current_price = market['coins'][symbol]['price']
        if not binomo: binomo = {}
        binomo[uid] = {
            'symbol': symbol,
            'direction': direction,
            'bet': bet,
            'entry_price': current_price
        }
        save_json(BINOMO_FILE, binomo)
        
        await message.channel.send(f"🎰 **TARUHAN DITERIMA!**\n{message.author.mention} bertaruh **{bet} Koin** bahwa {symbol} akan **{direction}** dari harga {current_price}.\n*Tunggu maksimal 10 menit untuk hasilnya!*")

    if message.content.startswith('!portfolio'):
        uid = str(message.author.id)
        portfolio = load_json(PORTFOLIO_FILE)
        market = load_json(MARKET_FILE)
        
        if uid not in portfolio or not portfolio[uid]:
            await message.channel.send("💼 Portofolio kamu masih kosong. Ayo beli koin dengan `!buy`!")
            return
            
        embed = discord.Embed(title=f"💼 Portofolio Koin {message.author.display_name}", color=discord.Color.gold())
        total_value = 0
        total_cost = 0
        
        for symbol, data in portfolio[uid].items():
            if isinstance(data, int):
                data = {'amount': data, 'avg_price': 1000}
                
            amount = data['amount']
            avg_price = data['avg_price']
            
            if symbol in market.get('coins', {}):
                current_price = market['coins'][symbol]['price']
                value = current_price * amount
                cost = avg_price * amount
                total_value += value
                total_cost += cost
                
                pnl = value - cost
                pnl_pct = (pnl / cost * 100) if cost > 0 else 0
                
                pnl_emoji = "🟩" if pnl >= 0 else "🟥"
                pnl_sign = "+" if pnl >= 0 else ""
                
                embed.add_field(
                    name=f"{symbol} ({amount} koin)", 
                    value=f"Modal: {int(cost)} | Valuasi: {int(value)}\nPnL: {pnl_emoji} **{pnl_sign}{int(pnl)} Koin** ({pnl_sign}{pnl_pct:.1f}%)", 
                    inline=False
                )
                
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
        t_pnl_sign = "+" if total_pnl >= 0 else ""
        
        embed.description = f"**Total Modal:** {int(total_cost)} Koin\n**Total Valuasi:** {int(total_value)} Koin\n**Net PnL:** {t_pnl_sign}{int(total_pnl)} ({t_pnl_sign}{total_pnl_pct:.1f}%)"
        await message.channel.send(embed=embed)

    if message.content.startswith('!buyrig'):
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        cost = 10000000 # 10 Juta
        
        if stat['coins'] < cost:
            await message.channel.send(f"❌ Koin kamu kurang! Butuh **10.000.000 Koin** untuk beli 1 Mesin Tambang Sultan.")
            return
            
        stat['coins'] -= cost
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        rigs = load_json(RIGS_FILE)
        if uid not in rigs: rigs[uid] = 0
        rigs[uid] += 1
        save_json(RIGS_FILE, rigs)
        
        await message.channel.send(f"⛏️💎 **PEMBELIAN SUKSES!**\n{message.author.mention} baru saja membeli 1 Mesin Tambang Sultan seharga 10 Juta Koin!\nMesin ini akan menambang ETHR setiap 1 jam otomatis. Cek dengan `!miner`.")

    if message.content.startswith('!miner'):
        uid = str(message.author.id)
        rigs = load_json(RIGS_FILE)
        count = rigs.get(uid, 0)
        
        if count == 0:
            await message.channel.send("❌ Kamu belum punya Mesin Tambang. Beli dengan `!buyrig` (10 Juta Koin).")
            return
            
        await message.channel.send(f"⛏️ {message.author.mention}, kamu memiliki **{count} Mesin Tambang Sultan**.\nMesin-mesin ini sedang bekerja mencetak uang untukmu setiap jam!")

    if message.content.startswith('!w2eslot'):
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        
        # Parse bet amount, default 50
        parts = message.content.split()
        bet = 50
        if len(parts) > 1:
            try:
                bet = int(parts[1])
                if bet < 10:
                    await message.channel.send("❌ Minimal bet adalah **10 Koin**.")
                    return
                if bet > 1000:
                    await message.channel.send("❌ Maksimal bet adalah **1000 Koin**.")
                    return
            except ValueError:
                await message.channel.send("Format: `!w2eslot [jumlah]` — contoh: `!w2eslot 100`")
                return
        
        if stat['coins'] < bet:
            await message.channel.send(f"❌ Koin tidak cukup! Kamu punya **{stat['coins']} Koin**, butuh **{bet} Koin**.")
            return

        # === SLOT SYMBOLS — mirip OwO bot style ===
        # Format: (emoji, nama, berat/probabilitas, multiplier jika 3x)
        SYMBOLS = [
            ("🌟", "Lucky Star",  2,  50),   # Jackpot!
            ("💎", "Diamond",     4,  20),
            ("🎰", "Seven",       5,  10),
            ("🍀", "Clover",      8,   5),
            ("🎵", "Music",      12,   3),
            ("🔮", "Orb",        15,   2),
            ("🍒", "Cherry",     20, 1.5),
            ("🐾", "Paw",        34,   1),   # Paling umum
        ]
        
        emojis = [s[0] for s in SYMBOLS]
        weights = [s[2] for s in SYMBOLS]
        multipliers = {s[0]: s[3] for s in SYMBOLS}
        names = {s[0]: s[1] for s in SYMBOLS}
        
        # Spin 3 reels
        reel1, reel2, reel3 = random.choices(emojis, weights=weights, k=3)
        
        # Animated reveal — kirim pesan dulu lalu edit
        loading_msg = await message.channel.send(
            f"🎰 **SLOT MACHINE** — **{message.author.display_name}** bet **{bet} Koin**\n"
            f"```\n[ ❓ | ❓ | ❓ ]\n```\n*Memutar...*"
        )
        await asyncio.sleep(0.8)
        
        await loading_msg.edit(content=(
            f"🎰 **SLOT MACHINE** — **{message.author.display_name}** bet **{bet} Koin**\n"
            f"```\n[ {reel1} | ❓ | ❓ ]\n```\n*Memutar...*"
        ))
        await asyncio.sleep(0.7)
        
        await loading_msg.edit(content=(
            f"🎰 **SLOT MACHINE** — **{message.author.display_name}** bet **{bet} Koin**\n"
            f"```\n[ {reel1} | {reel2} | ❓ ]\n```\n*Memutar...*"
        ))
        await asyncio.sleep(0.7)
        
        # Hitung hasil
        winnings = 0
        result_text = ""
        
        if reel1 == reel2 == reel3:
            # JACKPOT — 3 sama
            mult = multipliers[reel1]
            winnings = int(bet * mult)
            if reel1 == "🌟":
                result_text = f"🌟 **JACKPOT ULTRA!!** 🌟\n`{reel1} {reel2} {reel3}` — **{names[reel1]}** x{mult}\n💰 **+{winnings} Koin!**"
            else:
                result_text = f"🎊 **JACKPOT!** 🎊\n`{reel1} {reel2} {reel3}` — **{names[reel1]}** x{mult}\n💰 **+{winnings} Koin!**"
        elif reel1 == reel2 or reel2 == reel3 or reel1 == reel3:
            # 2 sama — menang kecil (kembalikan bet saja)
            winnings = bet
            matched = reel1 if reel1 == reel2 else (reel2 if reel2 == reel3 else reel1)
            result_text = f"✨ **MENANG KECIL!**\n`{reel1} {reel2} {reel3}` — 2x **{names[matched]}**\n💰 **+{winnings} Koin** (balik modal)"
        else:
            # Kalah
            winnings = -bet
            result_text = f"💨 **ZONK...**\n`{reel1} {reel2} {reel3}`\n💸 **-{bet} Koin**"
        
        # Update coins
        stat['coins'] += winnings  # winnings bisa negatif jika kalah
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        if winnings > 0:
            await check_level_up(message.channel, message.author, 10)
        
        # Final reveal
        border = "═" * 20
        await loading_msg.edit(content=(
            f"🎰 **SLOT MACHINE** — **{message.author.display_name}** bet **{bet} Koin**\n"
            f"```\n{border}\n  {reel1}  |  {reel2}  |  {reel3}  \n{border}\n```\n"
            f"{result_text}\n"
            f"💼 Sisa Koin: **{stat['coins']}**"
        ))

    # ── Coinflip: !w2ecf heads/tails [bet] ───────────────────────────────────
    if message.content.startswith('!w2ecf'):
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        parts = message.content.split()

        if len(parts) < 2:
            await message.channel.send("Format: `!w2ecf <heads/tails> [bet]` — contoh: `!w2ecf heads 100`")
            return

        choice = parts[1].lower()
        if choice not in ('heads', 'tails', 'h', 't'):
            await message.channel.send("Pilihannya hanya `heads` atau `tails`!")
            return
        choice_normalized = 'heads' if choice in ('heads', 'h') else 'tails'

        bet = 50
        if len(parts) >= 3:
            try:
                bet = int(parts[2])
                if bet < 10:
                    await message.channel.send("❌ Minimal bet **10 Koin**.")
                    return
                if bet > 2000:
                    await message.channel.send("❌ Maksimal bet **2000 Koin**.")
                    return
            except ValueError:
                await message.channel.send("Format: `!w2ecf heads 100`")
                return

        if stat['coins'] < bet:
            await message.channel.send(f"❌ Koin tidak cukup! Punya **{stat['coins']}**, butuh **{bet}**.")
            return

        result = random.choice(['heads', 'tails'])
        coin_emoji = "🟡" if result == 'heads' else "⚪"
        flip_msg = await message.channel.send(
            f"🪙 **COIN FLIP** — **{message.author.display_name}** pilih **{choice_normalized}**, bet **{bet} Koin**\n"
            f"*Melempar koin...*"
        )
        await asyncio.sleep(1.2)

        if result == choice_normalized:
            winnings = bet
            stat['coins'] += winnings
            result_line = f"{coin_emoji} Koin jatuh: **{result.upper()}** — **MENANG! +{winnings} Koin** 🎉"
        else:
            stat['coins'] -= bet
            result_line = f"{coin_emoji} Koin jatuh: **{result.upper()}** — **KALAH! -{bet} Koin** 💸"

        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await flip_msg.edit(content=(
            f"🪙 **COIN FLIP** — **{message.author.display_name}** pilih **{choice_normalized}**, bet **{bet} Koin**\n"
            f"{result_line}\n"
            f"💼 Sisa Koin: **{stat['coins']}**"
        ))

    # ── Lootbox: !w2ebox [common/rare/epic] ──────────────────────────────────
    if message.content.startswith('!w2ebox'):
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        parts = message.content.split()
        tier = parts[1].lower() if len(parts) > 1 else 'common'

        BOXES = {
            'common':    {'cost': 100,  'emoji': '📦', 'color': '⬜', 'min': 50,   'max': 250,  'xp': 10},
            'rare':      {'cost': 300,  'emoji': '🎁', 'color': '🟦', 'min': 200,  'max': 700,  'xp': 30},
            'epic':      {'cost': 800,  'emoji': '💜', 'color': '🟪', 'min': 600,  'max': 2000, 'xp': 80},
            'legendary': {'cost': 2500, 'emoji': '🌟', 'color': '🟨', 'min': 2000, 'max': 8000, 'xp': 200},
        }

        if tier not in BOXES:
            box_list = "\n".join([f"{v['emoji']} **{k.capitalize()}** — {v['cost']} Koin" for k, v in BOXES.items()])
            await message.channel.send(f"Pilih tier box:\n{box_list}\nContoh: `!w2ebox rare`")
            return

        box = BOXES[tier]
        if stat['coins'] < box['cost']:
            await message.channel.send(f"❌ Butuh **{box['cost']} Koin** untuk {tier} box. Punya: **{stat['coins']}**.")
            return

        stat['coins'] -= box['cost']
        reward_coins = random.randint(box['min'], box['max'])

        # 10% bonus jackpot multiplier
        jackpot = False
        if random.random() < 0.10:
            reward_coins = int(reward_coins * 2.5)
            jackpot = True

        stat['coins'] += reward_coins
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await check_level_up(message.channel, message.author, box['xp'])

        open_msg = await message.channel.send(f"{box['emoji']} **Membuka {tier.capitalize()} Box...** {box['color']}{box['color']}{box['color']}")
        await asyncio.sleep(1.5)

        jackpot_tag = "⚡ **JACKPOT BONUS x2.5!**\n" if jackpot else ""
        await open_msg.edit(content=(
            f"{box['emoji']} **{tier.capitalize()} Box Dibuka!**\n"
            f"{jackpot_tag}"
            f"💰 Kamu mendapat **+{reward_coins} Koin**!\n"
            f"💼 Total Koin: **{stat['coins']}**"
        ))

    # ── Pray: !w2epray @user ─────────────────────────────────────────────────
    if message.content.startswith('!w2epray'):
        if not message.mentions:
            await message.channel.send("Mention seseorang dulu! `!w2epray @user`")
            return
        target = message.mentions[0]
        if target == message.author:
            await message.channel.send("❌ Kamu tidak bisa mendoakan diri sendiri!")
            return
        if target.bot:
            await message.channel.send("❌ Bot tidak butuh doa.")
            return

        uid_target = str(target.id)
        stat_target = get_discord_stat(uid_target)

        # Pray memberi 5–50 koin ke target secara random
        blessing = random.randint(5, 50)
        stat_target['coins'] += blessing
        update_discord_stat(uid_target, target.display_name, stat_target['coins'], stat_target['xp'], stat_target['level'], stat_target['lastDaily'])

        pray_msgs = [
            f"🙏 **{message.author.display_name}** mendoakan **{target.display_name}**... Semoga rezekinya lancar! (+{blessing} Koin)",
            f"✨ Doa **{message.author.display_name}** dikabulkan untuk **{target.display_name}**! (+{blessing} Koin diberikan oleh alam semesta)",
            f"🌟 Langit menurunkan berkah atas doa **{message.author.display_name}** kepada **{target.display_name}**! +{blessing} Koin~",
        ]
        await message.channel.send(random.choice(pray_msgs))

    # ── Curse: !w2ecurse @user ───────────────────────────────────────────────
    if message.content.startswith('!w2ecurse'):
        if not message.mentions:
            await message.channel.send("Mention seseorang dulu! `!w2ecurse @user`")
            return
        target = message.mentions[0]
        if target == message.author:
            await message.channel.send("❌ Kamu tidak bisa mengutuk diri sendiri!")
            return
        if target.bot:
            await message.channel.send("❌ Bot kebal dari kutukan.")
            return

        uid_target = str(target.id)
        stat_target = get_discord_stat(uid_target)

        stolen = random.randint(5, 40)
        # 30% chance curse backfires
        if random.random() < 0.30:
            uid_self = str(message.author.id)
            stat_self = get_discord_stat(uid_self)
            stat_self['coins'] = max(0, stat_self['coins'] - stolen)
            update_discord_stat(uid_self, message.author.display_name, stat_self['coins'], stat_self['xp'], stat_self['level'], stat_self['lastDaily'])
            await message.channel.send(
                f"💀 **{message.author.display_name}** mencoba mengutuk **{target.display_name}**...\n"
                f"⚡ KUTUKAN BERBALIK! **{message.author.display_name}** kehilangan **{stolen} Koin** sendiri!"
            )
        else:
            actual_stolen = min(stolen, stat_target['coins'])
            stat_target['coins'] = max(0, stat_target['coins'] - actual_stolen)
            update_discord_stat(uid_target, target.display_name, stat_target['coins'], stat_target['xp'], stat_target['level'], stat_target['lastDaily'])
            curse_msgs = [
                f"💀 **{message.author.display_name}** mengutuk **{target.display_name}**! Nasibnya buruk hari ini... (-{actual_stolen} Koin)",
                f"🌑 Kutukan dari **{message.author.display_name}** menghantam **{target.display_name}**! Kehilangan **{actual_stolen} Koin**!",
                f"😈 **{message.author.display_name}** melempar kutukan maut ke **{target.display_name}**! -{actual_stolen} Koin~",
            ]
            await message.channel.send(random.choice(curse_msgs))

    # ── Admin Add Coin: !w2eaddcoin @user <amount> ───────────────────────────
    if message.content.startswith('!w2eaddcoin'):
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Kamu bukan admin, jangan ngide!")
            return
            
        parts = message.content.split()
        if len(parts) < 3 or not message.mentions:
            await message.channel.send("Format: `!w2eaddcoin @user <jumlah>`")
            return
            
        target = message.mentions[0]
        try:
            amount = int(parts[-1])
        except ValueError:
            await message.channel.send("❌ Jumlah harus berupa angka!")
            return
            
        uid = str(target.id)
        stat = get_discord_stat(uid)
        stat['coins'] += amount
        update_discord_stat(uid, target.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        await message.channel.send(f"👑 **ADMIN MAGIC!** {message.author.mention} baru saja menambahkan **{amount} Koin** kepada {target.mention}! Cuan gratis dari pusat!")

    # ── Give: !w2egive @user <amount> ────────────────────────────────────────
    if message.content.startswith('!w2egive'):
        if not message.mentions:
            await message.channel.send("Format: `!w2egive @user <jumlah>` — contoh: `!w2egive @teman 100`")
            return
        target = message.mentions[0]
        if target == message.author:
            await message.channel.send("❌ Kamu tidak bisa memberikan koin ke diri sendiri.")
            return
        if target.bot:
            await message.channel.send("❌ Bot tidak bisa menerima koin.")
            return

        # Ambil angka dari content, abaikan mention
        content_clean = message.content.replace(f'<@{target.id}>', '').replace(f'<@!{target.id}>', '').replace('!w2egive', '').strip()
        try:
            amount = int(content_clean)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.channel.send("Masukin jumlah koin yang valid! Contoh: `!w2egive @teman 100`")
            return

        uid_self = str(message.author.id)
        stat_self = get_discord_stat(uid_self)

        if stat_self['coins'] < amount:
            await message.channel.send(f"❌ Koin tidak cukup! Punya **{stat_self['coins']}**, mau kasih **{amount}**.")
            return

        uid_target = str(target.id)
        stat_target = get_discord_stat(uid_target)

        stat_self['coins'] -= amount
        stat_target['coins'] += amount
        update_discord_stat(uid_self, message.author.display_name, stat_self['coins'], stat_self['xp'], stat_self['level'], stat_self['lastDaily'])
        update_discord_stat(uid_target, target.display_name, stat_target['coins'], stat_target['xp'], stat_target['level'], stat_target['lastDaily'])

        await message.channel.send(
            f"💸 **{message.author.display_name}** memberikan **{amount} Koin** kepada **{target.display_name}**!\n"
            f"💼 Sisa koin {message.author.display_name}: **{stat_self['coins']}**"
        )

    # ── Top Leaderboard: !w2etop ─────────────────────────────────────────────
    if message.content.startswith('!w2etop'):
        # Sort users by coins using sqlite directly or just fetch all and sort
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT username, coins, level FROM UserStat ORDER BY coins DESC LIMIT 10')
            top_users = c.fetchall()
            conn.close()
            
            res = "🏆 **W2E LEADERBOARD - SULTAN SERVER** 🏆\n\n"
            medals = ["🥇", "🥈", "🥉"]
            for i, user in enumerate(top_users):
                rank = medals[i] if i < 3 else f"`#{i+1}`"
                res += f"{rank} **{user[0]}** — 💰 {user[1]} Koin | Lvl {user[2]}\n"
            
            await message.channel.send(res)
        except Exception as e:
            await message.channel.send("Gagal mengambil data leaderboard.")

    # ── Weekly Bonus: !w2eweekly ─────────────────────────────────────────────
    if message.content.startswith('!w2eweekly'):
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        weekly_data = load_json(WEEKLY_FILE)
        
        today = datetime.now()
        last_weekly_str = weekly_data.get(uid)
        
        can_claim = True
        if last_weekly_str:
            last_weekly = datetime.strptime(last_weekly_str, '%Y-%m-%d')
            if (today - last_weekly).days < 7:
                can_claim = False
                days_left = 7 - (today - last_weekly).days
                
        if not can_claim:
            await message.channel.send(f"❌ Kamu sudah klaim bonus mingguan! Tunggu **{days_left} hari** lagi.")
            return
            
        reward = random.randint(500, 2000)
        multiplier_str = ""
        if message.author.premium_since:
            reward *= 2
            multiplier_str = "\n*(👑 Booster Bonus x2!)*"
            
        weekly_data[uid] = today.strftime('%Y-%m-%d')
        save_json(WEEKLY_FILE, weekly_data)
        
        stat['coins'] += reward
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await message.channel.send(f"🎁 **BONUS MINGGUAN!** {message.author.display_name} mendapatkan **{reward} Koin**! (Total: {stat['coins']}){multiplier_str}")
        await check_level_up(message.channel, message.author, 100)

    # ── Rob: !w2erob @user ───────────────────────────────────────────────────
    if message.content.startswith('!w2erob'):
        if not message.mentions:
            await message.channel.send("Format: `!w2erob @user`")
            return
        target = message.mentions[0]
        if target == message.author:
            await message.channel.send("❌ Masa merampok diri sendiri...")
            return
        if target.bot:
            await message.channel.send("❌ Tidak bisa merampok bot.")
            return

        uid_self = str(message.author.id)
        uid_target = str(target.id)
        
        # Check cooldown (30 menit per attacker-target combo)
        cooldown_key = (uid_self, uid_target)
        if cooldown_key in rob_cooldowns:
            delta = datetime.now() - rob_cooldowns[cooldown_key]
            if delta.total_seconds() < 1800:
                mins_left = int((1800 - delta.total_seconds()) // 60)
                await message.channel.send(f"⏳ Polisi masih patroli di area {target.display_name}. Tunggu {mins_left} menit lagi!")
                return
                
        stat_self = get_discord_stat(uid_self)
        stat_target = get_discord_stat(uid_target)

        if stat_target['coins'] < 100:
            await message.channel.send(f"❌ {target.display_name} terlalu miskin untuk dirampok (Koin < 100). Kasihanilah dia.")
            return

        rob_cooldowns[cooldown_key] = datetime.now()

        # Cek shield target
        target_items = load_json(ITEMS_FILE).get(uid_target, {})
        if target_items.get('shield', 0) > 0:
            target_items['shield'] -= 1
            all_items = load_json(ITEMS_FILE)
            if uid_target not in all_items: all_items[uid_target] = {}
            all_items[uid_target]['shield'] = target_items['shield']
            save_json(ITEMS_FILE, all_items)
            
            await message.channel.send(f"🛡️ **{message.author.display_name}** mencoba merampok, tapi **{target.display_name}** punya Shield! Perampokan GAGAL.")
            return

        # Cek apakah target adalah booster
        is_target_booster = False
        if isinstance(target, discord.Member) and target.premium_since:
            is_target_booster = True

        # 40% success rate (10% jika target booster)
        success_chance = 0.10 if is_target_booster else 0.40
        if random.random() < success_chance:
            # Sukses
            pct = random.uniform(0.2, 0.5)
            stolen = int(stat_target['coins'] * pct)
            stat_target['coins'] -= stolen
            stat_self['coins'] += stolen
            booster_msg = "\n(Gila lu berani ngerampok donatur server!)" if is_target_booster else ""
            await message.channel.send(f"🥷 **PERAMPOKAN SUKSES!**\n**{message.author.display_name}** berhasil mencuri **{stolen} Koin** dari **{target.display_name}**!{booster_msg}")
        else:
            # Gagal
            fine = random.randint(100, 200)
            if is_target_booster:
                fine *= 2 # Denda 2x lipat
            stat_self['coins'] = max(0, stat_self['coins'] - fine)
            booster_msg = "\n(Kena karma nyoba ngerampok donatur!)" if is_target_booster else ""
            await message.channel.send(f"🚨 **TERCYDUK!**\n**{message.author.display_name}** tertangkap basah mencoba merampok **{target.display_name}** dan didenda **{fine} Koin**!{booster_msg}")

        update_discord_stat(uid_self, message.author.display_name, stat_self['coins'], stat_self['xp'], stat_self['level'], stat_self['lastDaily'])
        update_discord_stat(uid_target, target.display_name, stat_target['coins'], stat_target['xp'], stat_target['level'], stat_target['lastDaily'])

    # ── Shop: !w2eshop / !w2ebuy ─────────────────────────────────────────────
    if message.content.startswith('!w2eshop'):
        is_booster = message.author.premium_since is not None
        booster_msg = "\n👑 **(Diskon Booster 50% Aktif!)**" if is_booster else ""
        res = f"🛒 **W2E SULTAN SHOP** 🛒{booster_msg}\n*Gunakan `!w2ebuy <item_id>` untuk membeli*\n\n"
        for i_id, i_data in SHOP_ITEMS.items():
            price = int(i_data['price'] * 0.5) if is_booster else i_data['price']
            res += f"**{i_data['name']}** (`{i_id}`) — 💰 {price}\n└ {i_data['desc']}\n\n"
        await message.channel.send(res)

    if message.content.startswith('!w2ebuy'):
        parts = message.content.split()
        if len(parts) < 2:
            await message.channel.send("Mau beli apa? Contoh: `!w2ebuy shield`")
            return
            
        item_id = parts[1].lower()
        if item_id not in SHOP_ITEMS:
            await message.channel.send("❌ Item tidak ditemukan. Cek `!w2eshop`.")
            return
            
        item = SHOP_ITEMS[item_id]
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        
        is_booster = message.author.premium_since is not None
        price = int(item['price'] * 0.5) if is_booster else item['price']
        
        if stat['coins'] < price:
            await message.channel.send(f"❌ Uang tidak cukup. Butuh **{price} Koin**.")
            return
            
        stat['coins'] -= price
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        items_data = load_json(ITEMS_FILE)
        if uid not in items_data: items_data[uid] = {}
        
        if item_id == 'double_xp':
            items_data[uid]['double_xp_until'] = (datetime.now() + timedelta(hours=2)).timestamp()
        else:
            items_data[uid][item_id] = items_data[uid].get(item_id, 0) + 1
            
        save_json(ITEMS_FILE, items_data)
        await message.channel.send(f"🛍️ Berhasil membeli **{item['name']}**! Sisa Koin: {stat['coins']}")

    # ── Inventory & Transfer ───────────────────────────────────────────────
    if message.content.startswith('!w2einventory'):
        uid = str(message.author.id)
        items_data = load_json(ITEMS_FILE).get(uid, {})
        
        if not items_data:
            await message.channel.send("🎒 Tas kamu kosong melompong.")
            return
            
        res = f"🎒 **Inventory {message.author.display_name}** 🎒\n"
        for i_id, count in items_data.items():
            if isinstance(count, int) and count > 0:
                name = SHOP_ITEMS.get(i_id, {}).get('name', i_id)
                res += f"🔸 **{name}**: {count}x\n"
            elif i_id == 'bg_url' and count:
                res += f"🔸 **Custom Background**: Aktif\n"
        await message.channel.send(res)

    if message.content.startswith('!w2etransfer'):
        parts = message.content.split()
        if len(parts) < 3 or not message.mentions:
            await message.channel.send("Format: `!w2etransfer @user <jumlah>`")
            return
            
        target = message.mentions[0]
        if target == message.author or target.bot:
            await message.channel.send("❌ Gak bisa transfer ke bot atau diri sendiri.")
            return
            
        try:
            amount = int(parts[-1])
            if amount <= 0: raise ValueError
        except ValueError:
            await message.channel.send("❌ Jumlah koin harus angka positif.")
            return
            
        uid1 = str(message.author.id)
        uid2 = str(target.id)
        stat1 = get_discord_stat(uid1)
        stat2 = get_discord_stat(uid2)
        
        if stat1['coins'] < amount:
            await message.channel.send(f"❌ Koin kamu gak cukup! Kamu cuma punya **{stat1['coins']} Koin**.")
            return
            
        stat1['coins'] -= amount
        stat2['coins'] += amount
        update_discord_stat(uid1, message.author.display_name, stat1['coins'], stat1['xp'], stat1['level'], stat1['lastDaily'])
        update_discord_stat(uid2, target.display_name, stat2['coins'], stat2['xp'], stat2['level'], stat2['lastDaily'])
        
        await message.channel.send(f"💸 **Transfer Sukses!**\n{message.author.display_name} mengirimkan **{amount} Koin** ke {target.display_name}.")

    if message.content.startswith('!w2ework'):
        uid = str(message.author.id)
        if uid in work_cooldowns:
            delta = datetime.now() - work_cooldowns[uid]
            if delta.total_seconds() < 3600:
                mins_left = int((3600 - delta.total_seconds()) // 60)
                await message.channel.send(f"⏳ Kamu masih capek kerja. Istirahat dulu **{mins_left} menit** lagi!")
                return
                
        work_cooldowns[uid] = datetime.now()
        
        jobs = [
            ("jadi tukang parkir minimarket", 50, 150),
            ("nge-joki tugas temen", 100, 300),
            ("mulung botol plastik", 20, 80),
            ("jadi buzzer Twitter", 150, 400),
            ("ikut giveaway abal-abal", 10, 50),
            ("jadi admin judi online", 200, 500),
        ]
        job_name, min_c, max_c = random.choice(jobs)
        reward = random.randint(min_c, max_c)
        
        if message.author.premium_since:
            reward = int(reward * 1.5) # Booster gets 50% more from working
            
        stat = get_discord_stat(uid)
        stat['coins'] += reward
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        booster_txt = " (Boost x1.5)" if message.author.premium_since else ""
        await message.channel.send(f"💼 {message.author.display_name} baru saja {job_name} dan mendapatkan **{reward} Koin**!{booster_txt}")

    if message.content.startswith('!w2ecurse'):
        parts = message.content.split()
        if len(parts) < 2 or not message.mentions:
            await message.channel.send("Format: `!w2ecurse @user`\nBiaya: 100 Koin. Jika target punya Shield, kutukan gagal.")
            return
            
        target = message.mentions[0]
        if target == message.author or target.bot:
            await message.channel.send("❌ Masa ngutuk bot atau diri sendiri...")
            return
            
        uid1 = str(message.author.id)
        uid2 = str(target.id)
        stat1 = get_discord_stat(uid1)
        
        if stat1['coins'] < 100:
            await message.channel.send("❌ Dukun minta bayaran 100 Koin buat ngutuk. Duit kamu gak cukup.")
            return
            
        stat1['coins'] -= 100
        update_discord_stat(uid1, message.author.display_name, stat1['coins'], stat1['xp'], stat1['level'], stat1['lastDaily'])
        
        target_items = load_json(ITEMS_FILE).get(uid2, {})
        if target_items.get('shield', 0) > 0:
            target_items['shield'] -= 1
            all_items = load_json(ITEMS_FILE)
            if uid2 not in all_items: all_items[uid2] = {}
            all_items[uid2]['shield'] = target_items['shield']
            save_json(ITEMS_FILE, all_items)
            
            await message.channel.send(f"🧿 **KUTUKAN GAGAL!**\n{message.author.display_name} ngirim santet ke {target.display_name}, tapi dia pake **Shield**! Santet mental.")
            return
            
        stat2 = get_discord_stat(uid2)
        curse_types = ['coins', 'xp']
        c_type = random.choice(curse_types)
        
        if c_type == 'coins':
            lost = random.randint(50, 300)
            stat2['coins'] = max(0, stat2['coins'] - lost)
            eff_msg = f"kehilangan **{lost} Koin**!"
        else:
            lost = random.randint(10, 50)
            stat2['xp'] = max(0, stat2['xp'] - lost)
            eff_msg = f"kehilangan **{lost} XP**!"
            
        update_discord_stat(uid2, target.display_name, stat2['coins'], stat2['xp'], stat2['level'], stat2['lastDaily'])
        await message.channel.send(f"☠️ **KUTUKAN BERHASIL!**\n{target.mention} kena santet dari {message.author.display_name} dan {eff_msg} 👻")

    # ── W2E Casino ───────────────────────────────────────────────────────────
    if message.content.startswith('!w2eslot'):
        parts = message.content.split()
        if len(parts) < 2:
            await message.channel.send("Format: `!w2eslot <taruhan>`")
            return
            
        try:
            bet = int(parts[1])
            if bet < 10: raise ValueError
        except ValueError:
            await message.channel.send("Taruhan harus angka minimal 10.")
            return
            
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        
        if stat['coins'] < bet:
            await message.channel.send(f"❌ Koin tidak cukup. Kamu punya **{stat['coins']} Koin**.")
            return
            
        stat['coins'] -= bet
        
        emojis = ['🍎', '🍒', '🍋', '💎', '7️⃣']
        r1, r2, r3 = random.choice(emojis), random.choice(emojis), random.choice(emojis)
        
        res_msg = f"🎰 **W2E SLOTS** 🎰\n\n" \
                  f"| {r1} | {r2} | {r3} |\n\n"
                  
        if r1 == r2 == r3:
            multiplier = 10 if r1 == '7️⃣' else (5 if r1 == '💎' else 3)
            win_amount = bet * multiplier
            stat['coins'] += win_amount
            res_msg += f"🎉 **JACKPOT!** Tiga simbol sama! Menang **{win_amount} Koin** (x{multiplier})!"
        elif r1 == r2 or r2 == r3 or r1 == r3:
            # 2 match, refund money
            stat['coins'] += bet
            res_msg += f"👍 Dua simbol sama. Taruhan kembali."
        else:
            res_msg += f"❌ Zonk! Uang taruhan hangus."
            
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await message.channel.send(res_msg)

    if message.content.startswith('!w2eflip'):
        parts = message.content.split()
        if len(parts) < 3:
            await message.channel.send("Format: `!w2eflip <heads/tails> <taruhan>`")
            return
            
        choice = parts[1].lower()
        if choice not in ['heads', 'tails']:
            await message.channel.send("Pilihannya cuma `heads` (Angka) atau `tails` (Gambar).")
            return
            
        try:
            bet = int(parts[2])
            if bet < 10: raise ValueError
        except ValueError:
            await message.channel.send("Taruhan harus angka minimal 10.")
            return
            
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        
        if stat['coins'] < bet:
            await message.channel.send(f"❌ Koin tidak cukup. Kamu punya **{stat['coins']} Koin**.")
            return
            
        stat['coins'] -= bet
        
        result = random.choice(['heads', 'tails'])
        if choice == result:
            win = bet * 2
            stat['coins'] += win
            await message.channel.send(f"🪙 Koin menunjukkan **{result.upper()}**!\n✅ Tebakanmu benar, memenangkan **{win} Koin**!")
        else:
            await message.channel.send(f"🪙 Koin menunjukkan **{result.upper()}**!\n❌ Yah kalah. Uang taruhan hangus.")
            
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])

    if message.content.startswith('!w2ecrash'):
        parts = message.content.split()
        if len(parts) < 2:
            await message.channel.send("Format: `!w2ecrash <taruhan>`")
            return
            
        try:
            bet = int(parts[1])
            if bet < 10: raise ValueError
        except ValueError:
            await message.channel.send("Taruhan harus angka minimal 10.")
            return
            
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        
        if stat['coins'] < bet:
            await message.channel.send(f"❌ Koin tidak cukup. Kamu punya **{stat['coins']} Koin**.")
            return
            
        stat['coins'] -= bet
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        crash_point = round(random.uniform(1.1, 5.0), 1)
        if random.random() < 0.2: # 20% chance to crash very early
            crash_point = round(random.uniform(1.0, 1.2), 1)
        elif random.random() < 0.1: # 10% chance to go very high
            crash_point = round(random.uniform(5.0, 15.0), 1)
            
        current_mult = 1.0
        
        embed = discord.Embed(title="🚀 W2E Crash", description=f"**Multiplier:** `{current_mult}x`\n\nKetik `stop` di chat untuk menarik koin!", color=discord.Color.green())
        embed.set_footer(text=f"Taruhan: {bet} | Dimainkan oleh {message.author.display_name}")
        msg = await message.channel.send(embed=embed)
        
        def check(m):
            return m.author == message.author and m.channel == message.channel and m.content.lower() == 'stop'
            
        crashed = False
        stopped = False
        
        while not crashed and not stopped:
            try:
                # Wait 1.5s for stop command
                resp = await client.wait_for('message', timeout=1.5, check=check)
                stopped = True
            except asyncio.TimeoutError:
                # Increment multiplier
                current_mult = round(current_mult + random.uniform(0.1, 0.4), 1)
                if current_mult >= crash_point:
                    crashed = True
                    current_mult = crash_point
                else:
                    embed.description = f"**Multiplier:** `{current_mult}x`\n\nKetik `stop` di chat untuk menarik koin!"
                    if current_mult > 3.0: embed.color = discord.Color.gold()
                    if current_mult > 6.0: embed.color = discord.Color.red()
                    await msg.edit(embed=embed)
                    
        if stopped:
            win_amount = int(bet * current_mult)
            stat['coins'] += win_amount
            update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            
            embed.description = f"**Multiplier Akhir:** `{current_mult}x`\n\n✅ Kamu berhenti tepat waktu dan memenangkan **{win_amount} Koin**!"
            embed.color = discord.Color.green()
            await msg.edit(embed=embed)
        else:
            embed.description = f"**Multiplier Akhir:** `{current_mult}x`\n\n💥 **CRASH!** Roket meledak! Uang taruhan **{bet}** hangus."
            embed.color = discord.Color.dark_red()
            await msg.edit(embed=embed)

    # ── RPS PvP: !w2erps @user [bet] ─────────────────────────────────────────
    if message.content.startswith('!w2erps'):
        parts = message.content.split()
        if not message.mentions or len(parts) < 3:
            await message.channel.send("Format: `!w2erps @user <bet>`")
            return
            
        target = message.mentions[0]
        if target == message.author or target.bot:
            await message.channel.send("❌ Gak bisa lawan bot / diri sendiri.")
            return
            
        try:
            bet = int(parts[-1])
            if bet < 10: raise ValueError
        except ValueError:
            await message.channel.send("Bet harus angka dan minimal 10.")
            return
            
        uid1 = str(message.author.id)
        uid2 = str(target.id)
        stat1 = get_discord_stat(uid1)
        stat2 = get_discord_stat(uid2)
        
        if stat1['coins'] < bet:
            await message.channel.send(f"❌ Koin kamu gak cukup! Punya: {stat1['coins']}")
            return
        if stat2['coins'] < bet:
            await message.channel.send(f"❌ Koin musuh gak cukup! Dia punya: {stat2['coins']}")
            return
            
        # Potong koin di awal
        stat1['coins'] -= bet
        stat2['coins'] -= bet
        update_discord_stat(uid1, message.author.display_name, stat1['coins'], stat1['xp'], stat1['level'], stat1['lastDaily'])
        update_discord_stat(uid2, target.display_name, stat2['coins'], stat2['xp'], stat2['level'], stat2['lastDaily'])
        
        await message.channel.send(
            f"⚔️ **DUEL RPS** ⚔️\n"
            f"{message.author.mention} menantang {target.mention} bertaruh **{bet} Koin**!\n"
            f"Kalian berdua punya **30 detik** untuk membalas pesan ini dengan `batu`, `gunting`, atau `kertas`."
        )
        
        choices = {uid1: None, uid2: None}
        def check(m):
            return m.channel == message.channel and str(m.author.id) in choices and m.content.lower() in ['batu', 'gunting', 'kertas']
            
        end_time = datetime.now() + timedelta(seconds=30)
        
        while None in choices.values() and datetime.now() < end_time:
            try:
                msg = await client.wait_for('message', timeout=2.0, check=check)
                pid = str(msg.author.id)
                if choices[pid] is None:
                    choices[pid] = msg.content.lower()
                    await msg.add_reaction('✅')
            except asyncio.TimeoutError:
                pass
                
        c1, c2 = choices[uid1], choices[uid2]
        
        # Jika ada yg AFK
        if not c1 or not c2:
            refund = bet
            stat1 = get_discord_stat(uid1)
            stat2 = get_discord_stat(uid2)
            stat1['coins'] += refund
            stat2['coins'] += refund
            update_discord_stat(uid1, message.author.display_name, stat1['coins'], stat1['xp'], stat1['level'], stat1['lastDaily'])
            update_discord_stat(uid2, target.display_name, stat2['coins'], stat2['xp'], stat2['level'], stat2['lastDaily'])
            await message.channel.send("⏱️ Duel dibatalkan karena ada yang tidak menjawab. Koin dikembalikan.")
            return
            
        # Tentukan pemenang
        win_rules = {'batu': 'gunting', 'gunting': 'kertas', 'kertas': 'batu'}
        emojis = {'batu': '🪨', 'gunting': '✂️', 'kertas': '📄'}
        
        winnings = bet * 2
        stat1 = get_discord_stat(uid1)
        stat2 = get_discord_stat(uid2)
        
        if c1 == c2:
            stat1['coins'] += bet
            stat2['coins'] += bet
            result = "🤝 **SERI!** Koin dikembalikan."
        elif win_rules[c1] == c2:
            stat1['coins'] += winnings
            result = f"👑 **{message.author.display_name} MENANG!** (+{winnings} Koin)"
        else:
            stat2['coins'] += winnings
            result = f"👑 **{target.display_name} MENANG!** (+{winnings} Koin)"
            
        update_discord_stat(uid1, message.author.display_name, stat1['coins'], stat1['xp'], stat1['level'], stat1['lastDaily'])
        update_discord_stat(uid2, target.display_name, stat2['coins'], stat2['xp'], stat2['level'], stat2['lastDaily'])
        
        await message.channel.send(
            f"**HASIL DUEL:**\n"
            f"{message.author.display_name}: {emojis[c1]} {c1.upper()}\n"
            f"{target.display_name}: {emojis[c2]} {c2.upper()}\n\n"
            f"{result}"
        )

    # ── Daily Quests: !w2equest ──────────────────────────────────────────────
    if message.content.startswith('!w2equest'):
        uid = str(message.author.id)
        qdata = get_user_quests(uid)
        
        parts = message.content.split()
        if len(parts) > 1 and parts[1].lower() == 'claim':
            if qdata['claimed']:
                await message.channel.send("❌ Kamu sudah klaim reward hari ini!")
                return
            all_done = all(q['done'] for q in qdata['quests'])
            if not all_done:
                await message.channel.send("❌ Selesaikan semua quest dulu!")
                return
                
            qdata['claimed'] = True
            save_json(QUESTS_FILE, load_json(QUESTS_FILE) | {uid: qdata})
            
            stat = get_discord_stat(uid)
            stat['coins'] += 300
            update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            await message.channel.send("🎁 **QUEST SELESAI!** Kamu mendapatkan **300 Koin**!")
            await check_level_up(message.channel, message.author, 50)
            return

        res = f"📋 **DAILY QUESTS - {message.author.display_name}** 📋\n*Ketik `!w2equest claim` jika semua selesai (+300 Koin)*\n\n"
        for q in qdata['quests']:
            status = "✅" if q['done'] else "❌"
            res += f"{status} **{q['desc']}** ({q['progress']}/{q['target']})\n"
        
        if qdata['claimed']:
            res += "\n🌟 *Semua quest hari ini sudah selesai & diklaim!*"
            
        await message.channel.send(res)

    # ── Family System ────────────────────────────────────────────────────────
    if message.content.startswith('!w2emarry'):
        if not message.mentions:
            await message.channel.send("Mau nikah sama siapa? Mention orangnya! `!w2emarry @user`")
            return
        target = message.mentions[0]
        if target == message.author or target.bot:
            await message.channel.send("❌ Kamu gak bisa nikah sama diri sendiri/bot.")
            return

        uid1 = str(message.author.id)
        uid2 = str(target.id)
        fam_data = load_json(FAMILY_FILE)
        
        if fam_data.get(uid1, {}).get('partner'):
            await message.channel.send("❌ Kamu sudah menikah! Cerai dulu pakai `!w2edivorce`.")
            return
        if fam_data.get(uid2, {}).get('partner'):
            await message.channel.send("❌ Dia sudah punya pasangan. Cari yang lain!")
            return

        # Biaya nikah
        stat = get_discord_stat(uid1)
        if stat['coins'] < 500:
            await message.channel.send(f"❌ Biaya KUA mahal bos. Butuh **500 Koin** (Koinmu: {stat['coins']}).")
            return

        await message.channel.send(
            f"💍 **LAMARAN NIKAH!** 💍\n"
            f"{message.author.display_name} melamar {target.mention}!\n"
            f"{target.mention}, ketik `terima` atau `tolak` dalam 60 detik."
        )

        def check(m):
            return m.channel == message.channel and m.author == target and m.content.lower() in ['terima', 'tolak']

        try:
            msg = await client.wait_for('message', timeout=60.0, check=check)
            if msg.content.lower() == 'terima':
                stat['coins'] -= 500
                update_discord_stat(uid1, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
                
                if uid1 not in fam_data: fam_data[uid1] = {}
                if uid2 not in fam_data: fam_data[uid2] = {}
                fam_data[uid1]['partner'] = uid2
                fam_data[uid2]['partner'] = uid1
                save_json(FAMILY_FILE, fam_data)
                
                await message.channel.send(f"🎉 **SAAAHHH!** 🎉\n{message.author.mention} dan {target.mention} resmi menikah! (-500 Koin)")
            else:
                await message.channel.send(f"💔 Yah... {message.author.mention} lamaranmu ditolak mentah-mentah.")
        except asyncio.TimeoutError:
            await message.channel.send(f"⏱️ {target.display_name} kelamaan mikir. Lamaran dibatalkan.")

    if message.content.startswith('!w2edivorce'):
        uid = str(message.author.id)
        fam_data = load_json(FAMILY_FILE)
        
        partner_id = fam_data.get(uid, {}).get('partner')
        if not partner_id:
            await message.channel.send("❌ Kamu aja masih jomblo, mau cerai sama siapa?")
            return

        fam_data[uid]['partner'] = None
        if partner_id in fam_data:
            fam_data[partner_id]['partner'] = None
        save_json(FAMILY_FILE, fam_data)
        
        partner_user = client.get_user(int(partner_id))
        pname = partner_user.display_name if partner_user else f"User {partner_id}"
        await message.channel.send(f"💔 **CERAI!** {message.author.display_name} resmi bercerai dengan {pname}.")

    if message.content.startswith('!w2eadopt'):
        if not message.mentions:
            await message.channel.send("Format: `!w2eadopt @user`")
            return
        target = message.mentions[0]
        uid1 = str(message.author.id)
        uid2 = str(target.id)
        
        if uid1 == uid2 or target.bot:
            await message.channel.send("❌ Gak bisa adopsi diri sendiri/bot.")
            return

        fam_data = load_json(FAMILY_FILE)
        
        if fam_data.get(uid2, {}).get('parent'):
            await message.channel.send(f"❌ {target.display_name} sudah punya orang tua.")
            return
            
        if uid1 not in fam_data: fam_data[uid1] = {}
        if uid2 not in fam_data: fam_data[uid2] = {}
        
        children = fam_data[uid1].get('children', [])
        max_children = 15 if message.author.premium_since else 6
        if len(children) >= max_children:
            await message.channel.send(f"❌ Keluarga kamu sudah kepenuhan (Maksimal {max_children} anak).")
            return

        await message.channel.send(f"👶 {message.author.mention} ingin mengadopsi {target.mention} sebagai anak. Ketik `mau` atau `ngga` (60 dtk).")

        def check(m):
            return m.channel == message.channel and m.author == target and m.content.lower() in ['mau', 'ngga']

        try:
            msg = await client.wait_for('message', timeout=60.0, check=check)
            if msg.content.lower() == 'mau':
                fam_data[uid2]['parent'] = uid1
                if 'children' not in fam_data[uid1]: fam_data[uid1]['children'] = []
                fam_data[uid1]['children'].append(uid2)
                
                # Jika pengadopsi punya partner, tambah anak ke partner juga
                partner_id = fam_data[uid1].get('partner')
                if partner_id:
                    if 'children' not in fam_data[partner_id]: fam_data[partner_id]['children'] = []
                    if uid2 not in fam_data[partner_id]['children']:
                        fam_data[partner_id]['children'].append(uid2)
                        
                save_json(FAMILY_FILE, fam_data)
                await message.channel.send(f"🍼 **SAH!** {target.mention} sekarang adalah anak dari {message.author.mention}.")
            else:
                await message.channel.send("👶 Adopsi ditolak.")
        except asyncio.TimeoutError:
            await message.channel.send("⏱️ Waktu habis. Adopsi batal.")

    if message.content.startswith('!w2eleave'):
        uid = str(message.author.id)
        fam_data = load_json(FAMILY_FILE)
        parent_id = fam_data.get(uid, {}).get('parent')
        
        if not parent_id:
            await message.channel.send("❌ Kamu bukan anak siapa-siapa.")
            return
            
        fam_data[uid]['parent'] = None
        # Hapus dari semua daftar anak
        for k, v in fam_data.items():
            if 'children' in v and uid in v['children']:
                v['children'].remove(uid)
                
        save_json(FAMILY_FILE, fam_data)
        await message.channel.send(f"🚪 **MABUR!** {message.author.mention} kabur dari rumah dan bukan anak siapa-siapa lagi.")

    if message.content.startswith('!w2efamily'):
        target = message.mentions[0] if message.mentions else message.author
        if not PILLOW_AVAILABLE:
            await message.channel.send("🖼️ Modul pembuat gambar tidak tersedia. Info keluarga hanya via database (hubungi dev).")
            return
            
        await message.channel.send(f"📸 Sedang memotret keluarga **{target.display_name}**...")
        img_buf = await generate_family_image(message.guild, target.id)
        if img_buf:
            file = discord.File(fp=img_buf, filename="family_tree.png")
            await message.channel.send(file=file)
        else:
            await message.channel.send("❌ Terjadi kesalahan saat membuat foto keluarga.")

    if message.content.startswith('!w2eimage'):
        if not message.author.premium_since:
            await message.channel.send("❌ Maaf, fitur AI Image Generation HANYA tersedia untuk **Server Booster**! 👑")
            return
            
        prompt = message.content[len('!w2eimage '):].strip()
        if not prompt:
            await message.channel.send("Format: `!w2eimage <deskripsi gambar>`\nContoh: `!w2eimage a cute cat playing guitar in cyberpunk city`")
            return
            
        import urllib.parse
        encoded_prompt = urllib.parse.quote(prompt)
        # Tambahkan param random untuk mencegah cache jika prompt sama
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?nologo=true&seed={random.randint(1,100000)}"
        
        embed = discord.Embed(title="🎨 AI Image Generator", description=f"**Prompt:** {prompt}\n*Powered by Pollinations.ai*", color=discord.Color.purple())
        embed.set_image(url=url)
        embed.set_footer(text=f"Requested by {message.author.display_name} (Booster Exclusive)", icon_url=message.author.display_avatar.url if message.author.display_avatar else None)
        
        await message.channel.send(embed=embed)

    # ── Community & Engagement ───────────────────────────────────────────────
    if message.content.startswith('!w2epoll'):
        parts = message.content[len('!w2epoll '):].strip().split('|')
        if len(parts) < 2:
            await message.channel.send("Format: `!w2epoll Pertanyaan | Opsi 1 | Opsi 2 | ...`")
            return
            
        question = parts[0].strip()
        options = [opt.strip() for opt in parts[1:]]
        
        if len(options) > 10:
            await message.channel.send("❌ Maksimal 10 opsi untuk polling.")
            return
            
        emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
        
        desc = ""
        for i, opt in enumerate(options):
            desc += f"{emojis[i]} {opt}\n\n"
            
        embed = discord.Embed(title=f"📊 {question}", description=desc, color=discord.Color.blue())
        embed.set_footer(text=f"Polling dibuat oleh {message.author.display_name}")
        
        poll_msg = await message.channel.send(embed=embed)
        for i in range(len(options)):
            await poll_msg.add_reaction(emojis[i])

    if message.content.startswith('!w2egiveaway'):
        parts = message.content.split()
        if len(parts) < 3:
            await message.channel.send("Format: `!w2egiveaway <waktu_menit> <hadiah>`")
            return
            
        try:
            mins = int(parts[1])
            prize = " ".join(parts[2:])
        except ValueError:
            await message.channel.send("Format waktu harus angka (menit).")
            return
            
        embed = discord.Embed(title="🎉 **GIVEAWAY!** 🎉", description=f"**Hadiah:** {prize}\n**Berakhir dalam:** {mins} menit\n\nReact dengan 🎉 untuk ikutan!", color=discord.Color.gold())
        embed.set_footer(text=f"Giveaway dari {message.author.display_name}")
        ga_msg = await message.channel.send(embed=embed)
        await ga_msg.add_reaction("🎉")
        
        # Async wait
        await asyncio.sleep(mins * 60)
        
        # Fetch latest message state
        new_msg = await message.channel.fetch_message(ga_msg.id)
        reaction = discord.utils.get(new_msg.reactions, emoji="🎉")
        
        users = [user async for user in reaction.users() if not user.bot]
        if not users:
            await message.channel.send(f"Yah, gak ada yang ikut giveaway **{prize}** 😢")
            return
            
        winner = random.choice(users)
        await message.channel.send(f"🎊 Selamat {winner.mention}! Kamu memenangkan **{prize}** dari {message.author.mention}! 🎊")

    if message.content.startswith('!w2equiz'):
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        
        if stat['coins'] < 50:
            await message.channel.send("❌ Biaya main kuis adalah 50 Koin. Uangmu gak cukup.")
            return
            
        stat['coins'] -= 50
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        await message.channel.send("🤔 **Mencari soal yang sulit...**")
        prompt = "Berikan SATU pertanyaan pengetahuan umum singkat dan jawabannya dalam satu kata. Format: Pertanyaan | Jawaban. Jangan ada teks tambahan."
        try:
            response = await asyncio.to_thread(model.generate_content, prompt)
            res_text = response.text.strip()
            if '|' not in res_text: raise ValueError
            q, a = res_text.split('|')
            q = q.strip()
            a = a.strip().lower()
        except Exception:
            await message.channel.send("Gagal mengambil kuis dari AI. Koin dikembalikan.")
            stat['coins'] += 50
            update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            return
            
        await message.channel.send(f"🎯 **KUIS W2E** 🎯\n{q}\n\n*Jawab dalam 30 detik! Hadiah: 200 Koin! (-50 Koin modal)*")
        
        def check(m):
            return m.channel == message.channel and not m.author.bot
            
        try:
            # Tunggu siapa saja yang jawab benar duluan
            start_time = datetime.now()
            while (datetime.now() - start_time).seconds < 30:
                msg = await client.wait_for('message', timeout=30.0, check=check)
                if msg.content.lower().strip() == a:
                    winner_uid = str(msg.author.id)
                    w_stat = get_discord_stat(winner_uid)
                    w_stat['coins'] += 200
                    update_discord_stat(winner_uid, msg.author.display_name, w_stat['coins'], w_stat['xp'], w_stat['level'], w_stat['lastDaily'])
                    await message.channel.send(f"✅ **BENAR!** {msg.author.mention} menjawab **{a.upper()}** dan memenangkan 200 Koin!")
                    return
        except asyncio.TimeoutError:
            pass
            
        await message.channel.send(f"⏱️ Waktu habis! Jawaban yang benar adalah: **{a.upper()}**")

    # ── Fun & Hiburan ────────────────────────────────────────────────────────
    if message.content.startswith('!w2eshipper'):
        if len(message.mentions) < 1:
            await message.channel.send("Format: `!w2eshipper @user1 [@user2]`")
            return
            
        user1 = message.author
        user2 = message.mentions[0]
        if len(message.mentions) >= 2:
            user1 = message.mentions[0]
            user2 = message.mentions[1]
            
        if user1 == user2:
            await message.channel.send("❌ Jomblo ngenes banget nge-ship diri sendiri...")
            return
            
        # Consistent random based on ID
        seed = int(user1.id) + int(user2.id)
        random.seed(seed)
        match_pct = random.randint(0, 100)
        random.seed() # reset
        
        await message.channel.send(f"❤️ Menerawang kecocokan cinta **{user1.display_name}** & **{user2.display_name}**...")
        
        prompt = f"Buatkan ramalan cinta super singkat dan lucu (bisa sarkas atau romantis) untuk dua orang dengan tingkat kecocokan {match_pct}%. Gunakan bahasa gaul indo."
        try:
            response = await asyncio.to_thread(model.generate_content, prompt)
            desc = response.text.strip()
            
            embed = discord.Embed(title="💖 W2E Shipper 💖", description=f"**{user1.display_name}** x **{user2.display_name}**\n\n**Kecocokan: {match_pct}%**\n\n{desc}", color=discord.Color.brand_red())
            await message.channel.send(embed=embed)
        except Exception:
            await message.channel.send(f"**Kecocokan: {match_pct}%**\n(API Error: Gagal generate ramalan).")

    if message.content.startswith('!w2eroast'):
        if not message.mentions:
            await message.channel.send("Mau roast siapa? `!w2eroast @user`")
            return
        target = message.mentions[0]
        
        await message.channel.send(f"🔥 Sedang menyiapkan panggangan untuk **{target.display_name}**...")
        prompt = f"Roast / hina dengan candaan (tapi jangan kelewatan batas SARA) orang yang bernama {target.display_name}. Gunakan bahasa gaul tongkrongan indo yang pedas tapi lucu."
        try:
            response = await asyncio.to_thread(model.generate_content, prompt)
            await message.channel.send(f"{target.mention} 🔥\n{response.text.strip()}")
        except Exception:
            await message.channel.send("Tungku roasting sedang rusak (API Error).")

    if message.content.startswith('!w2echat '):
        chat_msg = message.content[len('!w2echat '):].strip()
        if not chat_msg:
            await message.channel.send("Mau ngomong apa? `!w2echat halo bot`")
            return
            
        await message.channel.typing()
        prompt = f"Anda adalah bot Discord bernama W2E. Kepribadian Anda adalah teman tongkrongan yang asik, sedikit sarkas, suka bercanda, tapi selalu membantu. Gunakan bahasa gaul Indonesia (lo, gue, bro, cuy). Jawab pesan berikut dengan singkat dan padat:\nUser ({message.author.display_name}) bilang: {chat_msg}"
        try:
            response = await asyncio.to_thread(model.generate_content, prompt)
            await message.reply(response.text.strip())
        except Exception:
            await message.channel.send("Lagi males mikir nih (API Error).")

    if message.content.startswith('!w2erate'):
        target = message.mentions[0] if message.mentions else message.author
        
        uid = str(target.id)
        stat = get_discord_stat(uid)
        
        # Prepare data for AI
        avatar_desc = "Avatar default Discord" if not target.display_avatar else "Punya avatar custom"
        is_booster = "Ya (Sultan)" if target.premium_since else "Bukan"
        
        profile_data = f"Nama: {target.display_name}\nLevel: {stat['level']}\nKoin: {stat['coins']}\nBooster: {is_booster}\nAvatar: {avatar_desc}"
        
        await message.channel.send(f"🧐 Sedang membedah profil **{target.display_name}**...")
        prompt = f"Berikan rating (1-10) dan roasting/pujian yang lucu ala komentator profesional (bahasa gaul indo) untuk profil Discord ini:\n{profile_data}\n\nBuat singkat aja, 2-3 kalimat max."
        
        try:
            response = await asyncio.to_thread(model.generate_content, prompt)
            
            embed = discord.Embed(title=f"📈 AI Profile Rating: {target.display_name}", description=response.text.strip(), color=discord.Color.teal())
            if target.display_avatar:
                embed.set_thumbnail(url=target.display_avatar.url)
            await message.channel.send(embed=embed)
        except Exception:
            await message.channel.send("Gagal merating profil (API Error).")

    if message.content.startswith('!w2ebirthday set'):
        parts = message.content.split()
        if len(parts) < 3:
            await message.channel.send("Format: `!w2ebirthday set DD-MM` (Contoh: `!w2ebirthday set 25-12`)")
            return
            
        bday_str = parts[2]
        try:
            # Validate
            datetime.strptime(bday_str, "%d-%m")
            
            bdays = load_json('birthdays.json')
            bdays[str(message.author.id)] = bday_str
            save_json('birthdays.json', bdays)
            await message.channel.send(f"🎂 Tanggal lahirmu berhasil disimpan! Kamu akan dapat kejutan di hari H!")
        except ValueError:
            await message.channel.send("❌ Format salah! Gunakan DD-MM (Tanggal-Bulan).")

    if message.content.startswith('!w2evalo '):
        target = message.content[len('!w2evalo '):].strip()
        if target:
            await message.channel.send(f"🔍 Sedang menerawang stats Valorant untuk **{target}**...")
            prompt = f"Buatlah statistik Valorant palsu dan lucu untuk pemain bernama '{target}'. Cantumkan Rank (yang aneh/rendah), Win Rate (jelek), dan Senjata Andalan yang tidak masuk akal. Buat singkat seperti report dalam bahasa gaul."
            try:
                response = await asyncio.to_thread(model.generate_content, prompt)
                await message.channel.send(response.text)
            except Exception:
                await message.channel.send("API error saat mencari stat Valorant.")
        return

    if message.content.startswith('!w2elisten'):
        if message.author.voice and message.author.voice.channel:
            vc = message.guild.voice_client
            if not vc:
                vc = await message.author.voice.channel.connect()
            
            try:
                vc.start_recording(
                    discord.sinks.WaveSink(),
                    finished_callback,
                    message.channel
                )
                await message.channel.send("🎙️ **Merekam obrolan selama 10 detik...** Mulai bicara!")
                await asyncio.sleep(10)
                if vc.recording:
                    vc.stop_recording()
            except Exception as e:
                await message.channel.send(f"Error memulai recording: {str(e)}\nPastikan sudah menggunakan **Pycord** (`pip install py-cord[voice]`).")
        else:
            await message.channel.send("Kamu harus berada di voice channel terlebih dahulu.")
        return

    if message.content.startswith('!w2eremindme '):
        parts = message.content[len('!w2eremindme '):].strip().split(' ', 1)
        if len(parts) < 2:
            await message.channel.send("Format: `!w2eremindme <menit> <pesan>`")
            return
        try:
            minutes = float(parts[0])
            msg_text = parts[1]
            await message.channel.send(f"⏰ Siap! Aku akan mengingatkanmu tentang **{msg_text}** dalam {minutes} menit.")
            
            async def reminder_task(channel, voice_ch, user, delay, text):
                await asyncio.sleep(delay * 60)
                await channel.send(f"🔔 {user.mention} Pengingat: {text}")
                if voice_ch:
                    vc = message.guild.voice_client
                    if not vc:
                        try:
                            vc = await voice_ch.connect()
                        except:
                            return
                    tts = gtts.gTTS(text=f"Halo {user.display_name}, saatnya {text}", lang='id')
                    tts.save(f"reminder_{user.id}.mp3")
                    if not vc.is_playing():
                        source = FFmpegPCMAudio(f"reminder_{user.id}.mp3")
                        vc.play(source)
                        while vc.is_playing():
                            await asyncio.sleep(1)
                        if os.path.exists(f"reminder_{user.id}.mp3"):
                            os.remove(f"reminder_{user.id}.mp3")
            
            client.loop.create_task(reminder_task(message.channel, message.author.voice.channel if message.author.voice else None, message.author, minutes, msg_text))
        except ValueError:
            await message.channel.send("Format menit harus berupa angka.")
        return

    if message.content.startswith('!w2echeckmusic') or message.content.startswith('!w2echeckbots'):
        if not message.guild:
            await message.channel.send("❌ Perintah ini hanya bisa digunakan di dalam server.")
            return
            
        active_bots = []
        for member in message.guild.members:
            if member.bot and member.id != client.user.id:
                if member.voice and member.voice.channel:
                    active_bots.append(f"🎵 **{member.display_name}** sedang aktif di 🔊 **{member.voice.channel.name}**")
                    
        if active_bots:
            embed = discord.Embed(
                title="🔊 Status Aktivitas Bot Musik",
                description="\n".join(active_bots),
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Diakses oleh {message.author.display_name}")
            await message.channel.send(embed=embed)
        else:
            await message.channel.send("ℹ️ Tidak ada bot musik yang sedang aktif di Voice Channel saat ini.")
        return

    if message.content.startswith('!profile'):
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        
        items_data = load_json(ITEMS_FILE).get(uid, {})
        bg_url = items_data.get('bg_url')
        
        if PILLOW_AVAILABLE:
            await message.channel.send("🖼️ Sedang memuat profil card...")
            img_buf = await generate_profile_image(message.author, stat, bg_url)
            if img_buf:
                file = discord.File(fp=img_buf, filename="profile.png")
                await message.channel.send(file=file)
                return
                
        # Fallback text
        res = f"**User Profile - {message.author.display_name}**\n"
        res += f"🏅 **Level:** {stat['level']} | ⚡ **XP:** {stat['xp']}/{stat['level']*100}\n"
        res += f"💰 **Koin:** {stat['coins']}\n\n"
        await message.channel.send(res)

    if message.content.startswith('!w2ebg'):
        if not message.author.premium_since:
            await message.channel.send("❌ Custom Background Profil cuma buat **Server Booster**! 👑")
            return
            
        parts = message.content.split()
        if len(parts) < 2:
            await message.channel.send("Format: `!w2ebg <URL_GAMBAR>`\nContoh: `!w2ebg https://example.com/image.jpg`")
            return
            
        bg_url = parts[1]
        if not bg_url.startswith('http'):
            await message.channel.send("❌ URL tidak valid.")
            return
            
        uid = str(message.author.id)
        items_data = load_json(ITEMS_FILE)
        if uid not in items_data: items_data[uid] = {}
        items_data[uid]['bg_url'] = bg_url
        save_json(ITEMS_FILE, items_data)
        
        await message.channel.send("✅ Background profil berhasil diupdate! Cek dengan `!profile`")

    if message.content.startswith('!setpersona '):
        persona = message.content[len('!setpersona '):].strip()
        uid = str(message.author.id)
        personas = load_json(PERSONAS_FILE)
        
        if persona.lower() == 'reset' or persona.lower() == 'hapus':
            if uid in personas:
                del personas[uid]
                save_json(PERSONAS_FILE, personas)
            if uid in chat_sessions:
                del chat_sessions[uid] # Reset memory so persona takes effect immediately
            await message.channel.send("✅ Persona AI kamu telah direset ke default.")
            return
            
        personas[uid] = persona
        save_json(PERSONAS_FILE, personas)
        if uid in chat_sessions:
            del chat_sessions[uid] # Reset history to force new persona
        
        await message.channel.send(f"🎭 Berhasil! Gemini AI sekarang akan membalasmu dengan persona: **{persona}**\nCoba chat pakai `!ai Halo!`")

    if message.content.startswith('!w2ebj '):
        uid = str(message.author.id)
        stat = get_discord_stat(uid)
        
        try:
            bet = int(message.content.split()[1])
            if bet < 50:
                await message.channel.send("❌ Minimal taruhan Blackjack adalah 50 Koin.")
                return
            if stat['coins'] < bet:
                await message.channel.send("❌ Koin kamu tidak cukup!")
                return
        except (IndexError, ValueError):
            await message.channel.send("Format: `!w2ebj <jumlah_taruhan>`")
            return
            
        stat['coins'] -= bet
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        # Simple Blackjack Logic
        deck = [2,3,4,5,6,7,8,9,10,10,10,10,11] * 4
        random.shuffle(deck)
        
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]
        
        def calculate_score(hand):
            score = sum(hand)
            aces = hand.count(11)
            while score > 21 and aces > 0:
                score -= 10
                aces -= 1
            return score
            
        player_score = calculate_score(player_hand)
        dealer_score = calculate_score(dealer_hand)
        
        if player_score == 21:
            win_amount = int(bet * 2.5)
            stat['coins'] += win_amount
            update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            await message.channel.send(f"🃏 **BLACKJACK!** 🃏\nKartu kamu: {player_hand} (21)\nKamu langsung menang **{win_amount} Koin**!")
            return
            
        embed = discord.Embed(title="🃏 W2E Blackjack Casino", color=discord.Color.red())
        embed.add_field(name=f"Pemain ({player_score})", value=str(player_hand), inline=True)
        embed.add_field(name="Bandar", value=f"[{dealer_hand[0]}, ?]", inline=True)
        embed.set_footer(text="Ketik 'hit' untuk tambah kartu, atau 'stand' untuk bertahan.")
        
        msg = await message.channel.send(embed=embed)
        
        def check(m):
            return m.author.id == message.author.id and m.channel.id == message.channel.id and m.content.lower() in ['hit', 'stand']
            
        playing = True
        while playing:
            try:
                reply = await client.wait_for('message', timeout=30.0, check=check)
                if reply.content.lower() == 'hit':
                    player_hand.append(deck.pop())
                    player_score = calculate_score(player_hand)
                    
                    if player_score > 21:
                        embed.set_field_at(0, name=f"Pemain ({player_score})", value=str(player_hand), inline=True)
                        embed.description = f"💥 **BUST!** Kamu kelebihan 21. Taruhan **{bet} Koin** hangus."
                        await message.channel.send(embed=embed)
                        return
                    else:
                        embed.set_field_at(0, name=f"Pemain ({player_score})", value=str(player_hand), inline=True)
                        await message.channel.send(embed=embed)
                else:
                    playing = False
            except asyncio.TimeoutError:
                await message.channel.send(f"⏳ Waktu habis! Kamu otomatis Stand.")
                playing = False
                
        # Dealer's turn
        while dealer_score < 17:
            dealer_hand.append(deck.pop())
            dealer_score = calculate_score(dealer_hand)
            
        embed.set_field_at(0, name=f"Pemain ({player_score})", value=str(player_hand), inline=True)
        embed.set_field_at(1, name=f"Bandar ({dealer_score})", value=str(dealer_hand), inline=True)
        
        if dealer_score > 21:
            win_amount = bet * 2
            stat['coins'] += win_amount
            embed.description = f"🎉 Bandar **Bust!** Kamu menang **{win_amount} Koin**!"
        elif dealer_score > player_score:
            embed.description = f"😢 Bandar menang. Taruhan **{bet} Koin** hangus."
        elif dealer_score < player_score:
            win_amount = bet * 2
            stat['coins'] += win_amount
            embed.description = f"🎉 Kamu menang! Dapet **{win_amount} Koin**!"
        else:
            stat['coins'] += bet
            embed.description = f"🤝 **Seri (Push)!** Taruhan {bet} Koin dikembalikan."
            
        update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await message.channel.send(embed=embed)

    if message.content.startswith('!attack'):
        boss_data = load_json(BOSS_FILE)
        if not boss_data.get('active', False):
            await message.channel.send("❌ Tidak ada Boss yang sedang aktif saat ini.")
            return
            
        uid = str(message.author.id)
        # Cek cooldown 30 detik
        if uid in boss_cooldowns:
            delta = datetime.now() - boss_cooldowns[uid]
            if delta.total_seconds() < 30:
                await message.channel.send(f"⏳ Senjatamu masih *cooldown*! Tunggu {int(30 - delta.total_seconds())} detik lagi.")
                return
                
        boss_cooldowns[uid] = datetime.now()
        
        damage = random.randint(50, 300)
        boss_data['hp'] -= damage
        
        if boss_data['hp'] <= 0:
            boss_data['active'] = False
            save_json(BOSS_FILE, boss_data)
            # Ambil dari kas server
            treasury = load_json(TREASURY_FILE)
            if not treasury: treasury = {'balance': 0}
            balance = treasury.get('balance', 0)
            
            reward = 5000
            if balance < reward:
                reward = max(1000, balance) # Kasih seadanya, minimal 1000
                
            if balance >= reward:
                treasury['balance'] -= reward
            else:
                treasury['balance'] = 0
            save_json(TREASURY_FILE, treasury)
            
            stat = get_discord_stat(uid)
            stat['coins'] += reward
            update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            
            await message.channel.send(f"💥 **FATAL BLOW!** 💥\n{message.author.mention} berhasil memberikan serangan terakhir sebesar **{damage} DMG** dan membunuh **{boss_data['name']}**!\n🎉 Hadiah pembunuh: **{reward} Koin RPG!** (Diambil dari Kas Server)")
        else:
            save_json(BOSS_FILE, boss_data)
            await message.channel.send(f"⚔️ {message.author.mention} menyerang **{boss_data['name']}** sebesar **{damage} DMG**! (Sisa HP Boss: {boss_data['hp']}/{boss_data['max_hp']})")

client.run(DISCORD_API_KEY)
