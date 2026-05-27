import discord
import os
from google import genai
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

import math

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logging.warning("Pillow not installed. Family tree/profile images will use text fallback.")


DB_PATH = "w2ebot.db"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_API_KEY = os.getenv('DISCORD_TOKEN', 'MMM')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'MMM')
ALLOWED_SERVER_ID = int(os.getenv('ALLOWED_SERVER_ID', '887968847842402355'))
BOT_PREFIX = os.getenv('BOT_PREFIX', 'w!')

# genai Client
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.message_content = True
intents.voice_states = True
intents.members = True

client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)




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
    conn.execute('''
        CREATE TABLE IF NOT EXISTS DiscordStat (
            id TEXT PRIMARY KEY,
            displayName TEXT,
            coins INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            lastDaily TEXT,
            updatedAt TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ChatMemory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            content TEXT
        )
    ''')
    conn.commit()
    conn.close()

_init_db()

import aiosqlite
import asyncio
from math import floor, sqrt
import json
import logging
from datetime import datetime

_json_cache = {}

async def load_json(filepath):
    basename = os.path.basename(filepath)
    if basename in _json_cache:
        return _json_cache[basename]
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT content FROM json_store WHERE filename=?", (basename,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    data = json.loads(row[0])
                    _json_cache[basename] = data
                    return data
    except Exception as e:
        logging.error(f"DB Load Error: {e}")
    _json_cache[basename] = {}
    return {}

async def save_json(filepath, data):
    basename = os.path.basename(filepath)
    _json_cache[basename] = data
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO json_store (filename, content) VALUES (?, ?)", (basename, json.dumps(data, ensure_ascii=False)))
            await db.commit()
    except Exception as e:
        logging.error(f"DB Save Error: {e}")

async def get_discord_stat(uid):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT coins, xp, level, lastDaily FROM DiscordStat WHERE id=?", (str(uid),)) as cursor:
                row = await cursor.fetchone()
                if row:
                    coins, xp, level, lastDaily = row[0], row[1], row[2], row[3]
                    
                    # O(1) Level Up Math
                    if xp >= level * 100:
                        a = 50
                        b = 100 * level - 50
                        c = -xp
                        discriminant = b**2 - 4*a*c
                        if discriminant > 0:
                            n = floor((-b + sqrt(discriminant)) / (2*a))
                            if n > 0:
                                xp_consumed = 100 * n * level + 50 * n * (n - 1)
                                level += n
                                xp -= int(xp_consumed)
                                await db.execute("UPDATE DiscordStat SET xp=?, level=? WHERE id=?", (xp, level, str(uid)))
                                await db.commit()
                    return {'coins': coins, 'xp': xp, 'level': level, 'lastDaily': lastDaily}
    except Exception as e:
        logging.error(f"DB Error get: {e}")
    return {'coins': 0, 'xp': 0, 'level': 1, 'lastDaily': ''}

async def update_discord_stat(uid, display_name, coins, xp, level, last_daily):
    if xp >= level * 100:
        a = 50
        b = 100 * level - 50
        c = -xp
        discriminant = b**2 - 4*a*c
        if discriminant > 0:
            n = floor((-b + sqrt(discriminant)) / (2*a))
            if n > 0:
                xp_consumed = 100 * n * level + 50 * n * (n - 1)
                level += n
                xp -= int(xp_consumed)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            now = datetime.utcnow().isoformat() + "Z"
            await db.execute("""
                INSERT INTO DiscordStat (id, displayName, coins, xp, level, lastDaily, updatedAt) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET 
                displayName=excluded.displayName,
                coins=excluded.coins,
                xp=excluded.xp,
                level=excluded.level,
                lastDaily=excluded.lastDaily,
                updatedAt=excluded.updatedAt
            """, (str(uid), display_name, coins, xp, level, last_daily, now))
            await db.commit()
    except Exception as e:
        logging.error(f"DB Error update: {e}")

import asyncio
from math import floor, sqrt
import json
import logging
from datetime import datetime

_json_cache = {}

async def load_json(filepath):
    basename = os.path.basename(filepath)
    if basename in _json_cache:
        return _json_cache[basename]
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT content FROM json_store WHERE filename=?", (basename,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    data = json.loads(row[0])
                    _json_cache[basename] = data
                    return data
    except Exception as e:
        logging.error(f"DB Load Error: {e}")
    _json_cache[basename] = {}
    return {}

async def save_json(filepath, data):
    basename = os.path.basename(filepath)
    _json_cache[basename] = data
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO json_store (filename, content) VALUES (?, ?)", (basename, json.dumps(data, ensure_ascii=False)))
            await db.commit()
    except Exception as e:
        logging.error(f"DB Save Error: {e}")

async def get_discord_stat(uid):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT coins, xp, level, lastDaily FROM DiscordStat WHERE id=?", (str(uid),)) as cursor:
                row = await cursor.fetchone()
                if row:
                    coins, xp, level, lastDaily = row[0], row[1], row[2], row[3]
                    
                    # O(1) Level Up Math
                    if xp >= level * 100:
                        a = 50
                        b = 100 * level - 50
                        c = -xp
                        discriminant = b**2 - 4*a*c
                        if discriminant > 0:
                            n = floor((-b + sqrt(discriminant)) / (2*a))
                            if n > 0:
                                xp_consumed = 100 * n * level + 50 * n * (n - 1)
                                level += n
                                xp -= int(xp_consumed)
                                await db.execute("UPDATE DiscordStat SET xp=?, level=? WHERE id=?", (xp, level, str(uid)))
                                await db.commit()
                    return {'coins': coins, 'xp': xp, 'level': level, 'lastDaily': lastDaily}
    except Exception as e:
        logging.error(f"DB Error get: {e}")
    return {'coins': 0, 'xp': 0, 'level': 1, 'lastDaily': ''}

async def update_discord_stat(uid, display_name, coins, xp, level, last_daily):
    if xp >= level * 100:
        a = 50
        b = 100 * level - 50
        c = -xp
        discriminant = b**2 - 4*a*c
        if discriminant > 0:
            n = floor((-b + sqrt(discriminant)) / (2*a))
            if n > 0:
                xp_consumed = 100 * n * level + 50 * n * (n - 1)
                level += n
                xp -= int(xp_consumed)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            now = datetime.utcnow().isoformat() + "Z"
            await db.execute("""
                INSERT INTO DiscordStat (id, displayName, coins, xp, level, lastDaily, updatedAt) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET 
                displayName=excluded.displayName,
                coins=excluded.coins,
                xp=excluded.xp,
                level=excluded.level,
                lastDaily=excluded.lastDaily,
                updatedAt=excluded.updatedAt
            """, (str(uid), display_name, coins, xp, level, last_daily, now))
            await db.commit()
    except Exception as e:
        logging.error(f"DB Error update: {e}")






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






async def check_level_up(channel, user, xp_gained):
    uid = str(user.id)
    stat = await get_discord_stat(uid)
    stat['xp'] += xp_gained
    next_level_xp = stat['level'] * 100
    leveled_up = False
    while stat['xp'] >= next_level_xp:
        stat['level'] += 1
        stat['xp'] -= next_level_xp
        next_level_xp = stat['level'] * 100
        leveled_up = True
    if leveled_up:
        await channel.send(f"GG {user.mention}, kamu baru saja naik ke **Level {stat['level']}**!")
    await update_discord_stat(uid, user.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])

async def check_toxicity(text):
    prompt = f"Evaluasi pesan berikut. Jika mengandung ujaran kebencian parah, rasisme, atau NSFW ekstrim, balas HANYA dengan kata 'TOXIC'. Jika aman, balas 'SAFE'.\nPesan: {text}"
    try:
        response = await asyncio.to_thread(gemini_client.models.generate_content, model='gemini-2.5-flash', contents=prompt)
        return "TOXIC" in response.text.upper()
    except Exception:
        return False

# ── Quest helpers ─────────────────────────────────────────────────────────────
async def get_user_quests(uid):
    quests_data = await load_json(QUESTS_FILE)
    today = datetime.now().strftime('%Y-%m-%d')
    if uid not in quests_data or quests_data[uid].get('date') != today:
        chosen = random.sample(QUEST_TEMPLATES, min(3, len(QUEST_TEMPLATES)))
        quests_data[uid] = {
            'date': today,
            'quests': [{'id': q['id'], 'desc': q['desc'], 'target': q['target'], 'progress': 0, 'done': False} for q in chosen],
            'claimed': False
        }
        await save_json(QUESTS_FILE, quests_data)
    return quests_data[uid]

async def update_quest_progress(uid, quest_id, amount=1):
    quests_data = await load_json(QUESTS_FILE)
    today = datetime.now().strftime('%Y-%m-%d')
    if uid not in quests_data or quests_data[uid].get('date') != today:
        return
    for q in quests_data[uid]['quests']:
        if q['id'] == quest_id and not q['done']:
            q['progress'] = min(q['progress'] + amount, q['target'])
            if q['progress'] >= q['target']:
                q['done'] = True
    await save_json(QUESTS_FILE, quests_data)

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
    family = await load_json(FAMILY_FILE)
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

# ── Config & Helpers for Premium Profile Card ────────────────────────────────
W, H = 1600, 400

# Palette
BG            = (13, 15, 30)
ACCENT        = (99, 102, 241)   # indigo
ACCENT2       = (168, 85, 247)   # purple
GOLD          = (250, 189, 47)
CYAN          = (56, 189, 248)
GREEN         = (52, 211, 153)
WHITE         = (240, 242, 255)
MUTED         = (120, 128, 160)
STAT_BG       = (25, 28, 50)
XP_TRACK      = (30, 35, 68)
DIVIDER_C     = (60, 65, 100)

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_BOLD_PATH   = os.path.join(FONT_DIR, "Poppins-Bold.ttf")
FONT_MED_PATH    = os.path.join(FONT_DIR, "Poppins-Medium.ttf")
FONT_REG_PATH    = os.path.join(FONT_DIR, "Poppins-Regular.ttf")
FONT_LIGHT_PATH  = os.path.join(FONT_DIR, "Poppins-Light.ttf")

def get_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.truetype("arial.ttf", size)
        except Exception:
            return ImageFont.load_default()

def ensure_fonts():
    import urllib.request
    urls = {
        FONT_BOLD_PATH: "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf",
        FONT_MED_PATH: "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Medium.ttf",
        FONT_REG_PATH: "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf",
        FONT_LIGHT_PATH: "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Light.ttf"
    }
    if not os.path.exists(FONT_DIR):
        os.makedirs(FONT_DIR, exist_ok=True)
    for path, url in urls.items():
        if not os.path.exists(path):
            logging.info(f"Downloading font: {os.path.basename(path)}...")
            try:
                urllib.request.urlretrieve(url, path)
                logging.info(f"Downloaded {os.path.basename(path)} successfully.")
            except Exception as e:
                logging.error(f"Failed to download font {os.path.basename(path)}: {e}")

# Pre-download fonts if possible on import/startup
try:
    ensure_fonts()
except Exception as e:
    logging.error(f"Error checking/downloading Poppins fonts on startup: {e}")

def rounded_rectangle(draw, xy, radius, fill=None, outline=None, width=4):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill,
                            outline=outline, width=width)

def draw_glow_circle(img, center, radius, color, alpha_max=45):
    """Draw a soft radial glow"""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for r in range(radius, 0, -6):
        a = int(alpha_max * (1 - r / radius) ** 2)
        draw.ellipse(
            [center[0] - r, center[1] - r, center[0] + r, center[1] + r],
            fill=(*color, a)
        )
    return Image.alpha_composite(img.convert("RGBA"), overlay)

def circle_avatar(av_source, size):
    """Crop avatar to a crisp circle, accepts path/BytesIO or PIL Image"""
    if isinstance(av_source, Image.Image):
        av = av_source.convert("RGBA").resize((size, size), Image.LANCZOS)
    else:
        av = Image.open(av_source).convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    av.putalpha(mask)
    return av

def draw_xp_bar(draw, x, y, w, h, progress, radius=10):
    """Rounded XP progress bar with gradient feel"""
    rounded_rectangle(draw, [x, y, x + w, y + h], radius, fill=XP_TRACK)
    if progress > 0:
        fill_w = max(int(w * progress), radius * 2)
        for i in range(fill_w):
            t = i / max(fill_w - 1, 1)
            r = int(ACCENT[0] + (ACCENT2[0] - ACCENT[0]) * t)
            g = int(ACCENT[1] + (ACCENT2[1] - ACCENT[1]) * t)
            b = int(ACCENT[2] + (ACCENT2[2] - ACCENT[2]) * t)
            draw.line([(x + i, y + 2), (x + i, y + h - 2)], fill=(r, g, b))
        rounded_rectangle(draw, [x, y, x + w, y + h], radius,
                           fill=None, outline=XP_TRACK, width=2)

def resize_and_crop(img, target_size):
    target_w, target_h = target_size
    img_w, img_h = img.size
    scale = max(target_w / img_w, target_h / img_h)
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    right = left + target_w
    bottom = top + target_h
    return resized.crop((left, top, right, bottom))

async def get_user_rank(uid):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM DiscordStat WHERE id=?", (str(uid),)) as c:
                if not await c.fetchone():
                    return None
            async with db.execute("""
                WITH user_stat AS (SELECT level, coins FROM DiscordStat WHERE id=?)
                SELECT COUNT(*) + 1 FROM DiscordStat, user_stat
                WHERE DiscordStat.level > user_stat.level
                OR (DiscordStat.level = user_stat.level AND DiscordStat.coins > user_stat.coins)
            """, (str(uid),)) as c:
                row = await c.fetchone()
                if row:
                    return row[0]
    except Exception as e:
        logging.error(f"Error getting user rank: {e}")
    return None


def build_profile_card_sync(
    username="blurred",
    role="Member",
    level=1,
    xp=0,
    xp_max=100,
    coins=0,
    rank=None,
    avatar_img=None,
    bg_img=None,
):
    # layout
    STAT_H  = 96
    PAD_T   = (H - (52 + 16 + 52 + 16 + 2 + 16 + STAT_H)) // 2 # 74
    Y_NAME    = PAD_T
    Y_XP_LBL  = Y_NAME + 52 + 16
    Y_XP_BAR  = Y_XP_LBL + 28
    Y_DIV     = Y_XP_BAR + 20 + 16
    Y_STATS   = Y_DIV + 2 + 16

    # Base background
    if bg_img:
        bg_card_resized = resize_and_crop(bg_img, (W, H))
        overlay = Image.new("RGBA", (W, H), (*BG, 140))  # dark overlay for text readability
        card = Image.alpha_composite(bg_card_resized, overlay)
    else:
        card = Image.new("RGBA", (W, H), BG)

    # Glow behind avatar
    card = draw_glow_circle(card, (236, H // 2), 180, ACCENT, alpha_max=45)
    draw = ImageDraw.Draw(card)

    # Accent bar on left
    bar_h = H - 56
    bar = Image.new("RGBA", (8, bar_h), (0,0,0,0))
    bd = ImageDraw.Draw(bar)
    for y in range(bar_h):
        t = y / bar_h
        c = tuple(int(ACCENT[i] + (ACCENT2[i]-ACCENT[i])*t) for i in range(3))
        bd.line([(0,y),(7,y)], fill=(*c, 220))
    card.paste(bar, (0, 28), bar)

    # Corner lines
    for i, a in enumerate([25, 15, 8]):
        o = i * 18
        draw.line([(W-160+o, 12), (W-12, 160-o)], fill=(*ACCENT, a), width=2)

    # Avatar ring & image
    AV, AV_X, AV_Y = 200, 44, (H - 200) // 2
    for extra, alpha in [(10, 28), (6, 55)]:
        draw.ellipse([AV_X-extra, AV_Y-extra, AV_X+AV+extra, AV_Y+AV+extra], outline=(*ACCENT2, alpha), width=4)
    draw.ellipse([AV_X-4, AV_Y-4, AV_X+AV+2, AV_Y+AV+2], outline=(*ACCENT, 210), width=4)

    # Avatar
    if avatar_img:
        av = circle_avatar(avatar_img, AV)
        card.paste(av, (AV_X, AV_Y), av)
    else:
        # Fallback circle with initial letter
        draw.ellipse([AV_X, AV_Y, AV_X + AV, AV_Y + AV], fill=(25, 28, 50))
        letter_font = get_font(FONT_BOLD_PATH, 96)
        draw.text((AV_X + AV // 2, AV_Y + AV // 2 - 4), username[0].upper() if username else "?", font=letter_font, fill=MUTED, anchor="mm")

    # Online dot
    dx, dy = AV_X+AV-28, AV_Y+AV-28
    draw.ellipse([dx-14, dy-14, dx+14, dy+14], fill=BG)
    draw.ellipse([dx-10, dy-10, dx+10, dy+10], fill=GREEN)

    # Columns
    COL_X = AV_X + AV + 40
    COL_W = W - COL_X - 40

    # Username + badge
    name_fnt  = get_font(FONT_BOLD_PATH, 44)
    badge_fnt = get_font(FONT_MED_PATH, 22)
    name_w = int(draw.textlength(username, font=name_fnt))
    draw.text((COL_X, Y_NAME), username, font=name_fnt, fill=WHITE)

    badge_txt = role.upper()
    badge_tw  = int(draw.textlength(badge_txt, font=badge_fnt))
    bx = COL_X + name_w + 24
    by = Y_NAME + (52 - 40) // 2
    rounded_rectangle(draw, [bx, by, bx+badge_tw+28, by+40], 20, fill=(*ACCENT, 38))
    rounded_rectangle(draw, [bx, by, bx+badge_tw+28, by+40], 20, fill=None, outline=(*ACCENT, 165), width=2)
    draw.text((bx+14, by+8), badge_txt, font=badge_fnt, fill=(*ACCENT, 255))

    # XP Label + Bar
    xp_fnt = get_font(FONT_REG_PATH, 20)
    xp_str = f"{xp:,} / {xp_max:,} XP"
    xp_str_w = int(draw.textlength(xp_str, font=xp_fnt))
    draw.text((COL_X, Y_XP_LBL), "EXPERIENCE", font=xp_fnt, fill=MUTED)
    draw.text((COL_X+COL_W-xp_str_w, Y_XP_LBL), xp_str, font=xp_fnt, fill=MUTED)
    
    # XP Bar
    progress = xp / xp_max if xp_max > 0 else 0
    draw_xp_bar(draw, COL_X, Y_XP_BAR, COL_W, 20, progress, radius=10)

    # Divider
    draw.line([(COL_X, Y_DIV), (COL_X+COL_W, Y_DIV)], fill=DIVIDER_C, width=2)

    # Stats
    GAP = 16
    SW = (COL_W - GAP * 2) // 3
    stats = [
        ("LEVEL", str(level), ACCENT),
        ("RANK", f"#{rank}" if rank else "—", CYAN),
        ("KOIN", f"{coins:,}", GOLD),
    ]
    for i, (lbl, val, col) in enumerate(stats):
        sx = COL_X + i * (SW + GAP)
        rounded_rectangle(draw, [sx, Y_STATS, sx+SW, Y_STATS+STAT_H], 20, fill=STAT_BG)
        # Dot
        cx_dot, cy_dot = sx + 32, Y_STATS + STAT_H // 2
        draw.ellipse([cx_dot-10, cy_dot-10, cx_dot+10, cy_dot+10], fill=col)
        # Text
        tx = sx + 60
        lbl_font = get_font(FONT_REG_PATH, 20)
        val_font = get_font(FONT_BOLD_PATH, 34)
        draw.text((tx, Y_STATS + STAT_H//2 - 36), lbl, font=lbl_font, fill=MUTED)
        draw.text((tx, Y_STATS + STAT_H//2 - 8), val, font=val_font, fill=WHITE)

    # Outer border
    draw.rounded_rectangle([2, 2, W-4, H-4], radius=32, outline=(*ACCENT, 60), width=4)

    # Rounded crop
    out = Image.new("RGBA", (W, H), (0,0,0,0))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0,0,W,H], radius=32, fill=255)
    out.paste(card, (0,0), mask)

    buf = io.BytesIO()
    out.save(buf, format='PNG')
    buf.seek(0)
    return buf

async def generate_profile_image(member, stat, bg_url=None):
    if not PILLOW_AVAILABLE:
        return None

    # Fetch avatar image (with size 512 for high resolution)
    avatar_img = None
    av_url = member.display_avatar.with_size(512).url if member.display_avatar else None
    if av_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(av_url) as resp:
                    if resp.status == 200:
                        av_data = await resp.read()
                        avatar_img = Image.open(io.BytesIO(av_data))
        except Exception as e:
            logging.error(f"Failed to fetch user avatar: {e}")

    # Fetch background image if bg_url is provided
    bg_img = None
    if bg_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(bg_url) as resp:
                    if resp.status == 200:
                        bg_data = await resp.read()
                        bg_img = Image.open(io.BytesIO(bg_data))
        except Exception as e:
            logging.error(f"Failed to fetch user background: {e}")

    # Determine user role
    role = "Member"
    if hasattr(member, "roles") and member.roles:
        non_everyone = [r for r in member.roles if not r.is_default()]
        if non_everyone:
            non_everyone.sort(key=lambda r: r.position, reverse=True)
            role = non_everyone[0].name
            if len(role) > 15:
                role = role[:12] + "..."

    # Determine rank
    rank = await get_user_rank(member.id)

    # XP calculations
    xp = stat.get('xp', 0)
    level = stat.get('level', 1)
    xp_max = level * 100
    coins = stat.get('coins', 0)
    username = member.display_name

    # Generate profile card in background thread to avoid blocking event loop
    try:
        buf = await asyncio.to_thread(
            build_profile_card_sync,
            username=username,
            role=role,
            level=level,
            xp=xp,
            xp_max=xp_max,
            coins=coins,
            rank=rank,
            avatar_img=avatar_img,
            bg_img=bg_img
        )
        return buf
    except Exception as e:
        logging.error(f"Error in profile card generation: {e}")
        return None

def heart_polygon(cx, cy, size, n=500):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x =  16 * math.sin(t)**3
        y = -(13*math.cos(t) - 5*math.cos(2*t)
               - 2*math.cos(3*t) - math.cos(4*t))
        pts.append((cx + x*size/16, cy + y*size/13))
    return pts

def build_love_card(name1="Blurred", name2="Equiv", percentage=59, avatar_img1=None, avatar_img2=None):
    W, H = 660, 175

    # ── Elegant rose palette ──────────────────────────────────────────────────────
    BG_TOP      = (255, 228, 235)
    BG_BOT      = (252, 205, 220)
    BORDER_C    = (240, 170, 190)
    WHITE       = (255, 255, 255)
    AVATAR_BG   = (255, 245, 248)   # circle fill
    AVATAR_RIM  = (240, 185, 200)   # circle border
    INITIAL_C   = (200,  70, 110)   # letter color
    HEART_EMPTY = (255, 242, 247)
    FILL_A      = (255, 165, 195)   # gradient top
    FILL_B      = (235,  50, 100)   # gradient bottom
    PCT_COLOR   = (180,  25,  65)
    NAME_COLOR  = (190,  85, 115)
    HEART_RIM   = (245, 175, 200)   # outline of heart

    card = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(card)

    # ── Gradient background ───────────────────────────────────────────────────
    for y in range(H):
        t = y / H
        r = int(BG_TOP[0] + (BG_BOT[0]-BG_TOP[0])*t)
        g = int(BG_TOP[1] + (BG_BOT[1]-BG_TOP[1])*t)
        b = int(BG_TOP[2] + (BG_BOT[2]-BG_TOP[2])*t)
        draw.line([(0,y),(W,y)], fill=(r,g,b,255))

    rr_mask = Image.new("L", (W,H), 0)
    ImageDraw.Draw(rr_mask).rounded_rectangle([0,0,W-1,H-1], radius=24, fill=255)
    card.putalpha(rr_mask)

    # Soft border
    bl = Image.new("RGBA", (W,H), (0,0,0,0))
    ImageDraw.Draw(bl).rounded_rectangle([0,0,W-1,H-1], radius=24,
                                          outline=(*BORDER_C,200), width=3)
    card = Image.alpha_composite(card, bl)
    draw = ImageDraw.Draw(card)

    # ── Avatar circles with initials/images ────────────────────────────────────
    AV     = 110
    HEART_HALF_W = 68         # half the heart's visual width (reserve space)
    GAP          = 28         # gap between avatar edge and heart

    # Direct placement: avatars equidistant from card centre
    cx1 = W//2 - HEART_HALF_W - GAP - AV//2
    cx2 = W//2 + HEART_HALF_W + GAP + AV//2
    cy  = H//2

    init_font_size = 38
    name_font_size = 13

    for cx, name, av_img in [(cx1, name1, avatar_img1), (cx2, name2, avatar_img2)]:
        # Outer soft glow ring
        for r_off, a in [(7,40),(5,80),(3,130)]:
            rr = AV//2 + r_off
            draw.ellipse([cx-rr, cy-rr, cx+rr, cy+rr],
                         outline=(*WHITE, a), width=2)
        # White ring
        rim = AV//2 + 3
        draw.ellipse([cx-rim, cy-rim, cx+rim, cy+rim],
                     outline=AVATAR_RIM, width=2)
        # Circle fill
        draw.ellipse([cx-AV//2, cy-AV//2, cx+AV//2, cy+AV//2],
                     fill=AVATAR_BG)
        
        if av_img:
            av = circle_avatar(av_img, AV)
            card.paste(av, (cx - AV//2, cy - AV//2), av)
        else:
            # Initial letter
            initial  = name[0].upper() if name else "?"
            if_font  = get_font(FONT_BOLD_PATH, init_font_size)
            iw = int(draw.textlength(initial, font=if_font))
            # textbbox for vertical centering
            bb = draw.textbbox((0,0), initial, font=if_font)
            ih = bb[3] - bb[1]
            draw.text((cx - iw//2, cy - ih//2 - bb[1]//2 - 2),
                      initial, font=if_font, fill=INITIAL_C)
        # Name below circle
        nf  = get_font(FONT_MED_PATH, name_font_size)
        nw  = int(draw.textlength(name, font=nf))
        ny  = cy + AV//2 + 7
        if ny + 16 < H:
            draw.text((cx - nw//2, ny), name, font=nf, fill=NAME_COLOR)

    # ── Heart ─────────────────────────────────────────────────────────────────
    HCX, HCY, HSIZE = W//2, H//2 - 2, 46
    pts = heart_polygon(HCX, HCY, HSIZE)

    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    hx0, hx1 = min(xs), max(xs)
    hy0, hy1 = min(ys), max(ys)
    hh  = hy1 - hy0
    fill_y = hy1 - hh * percentage / 100

    # Heart shape mask
    heart_mask = Image.new("L", (W,H), 0)
    ImageDraw.Draw(heart_mask).polygon(pts, fill=255)

    # 1. Empty heart fill
    el = Image.new("RGBA", (W,H), (0,0,0,0))
    ImageDraw.Draw(el).polygon(pts, fill=(*HEART_EMPTY, 255))
    card = Image.alpha_composite(card, el)

    # 2. Gradient fill — only bottom %
    fl = Image.new("RGBA", (W,H), (0,0,0,0))
    fd = ImageDraw.Draw(fl)
    for y in range(int(fill_y), int(hy1)+2):
        t = (y - fill_y) / max(hy1 - fill_y, 1)
        t = min(max(t, 0), 1)
        r = int(FILL_A[0] + (FILL_B[0]-FILL_A[0])*t)
        g = int(FILL_A[1] + (FILL_B[1]-FILL_A[1])*t)
        b = int(FILL_A[2] + (FILL_B[2]-FILL_A[2])*t)
        fd.line([(int(hx0), y),(int(hx1), y)], fill=(r,g,b,255))
    fz = Image.new("L", (W,H), 0)
    ImageDraw.Draw(fz).rectangle([0, int(fill_y), W, H], fill=255)
    fl.putalpha(ImageChops.multiply(heart_mask, fz))
    card = Image.alpha_composite(card, fl)
    draw = ImageDraw.Draw(card)

    # Subtle divider
    if 0 < percentage < 100:
        draw.line([(int(hx0)+4, int(fill_y)), (int(hx1)-4, int(fill_y))],
                  fill=(*WHITE, 140), width=1)

    # Heart outline — soft rose, thin and clean
    for i in range(len(pts)):
        draw.line([pts[i], pts[(i+1)%len(pts)]],
                  fill=(*HEART_RIM, 220), width=2)

    # Percentage text — centred in heart
    pf   = get_font(FONT_BOLD_PATH, 22)
    ptxt = f"{percentage}%"
    pw   = int(draw.textlength(ptxt, font=pf))
    bb   = draw.textbbox((0,0), ptxt, font=pf)
    ph   = bb[3] - bb[1]
    tx   = HCX - pw//2
    ty   = HCY - ph//2 + 2
    # Subtle white shadow
    draw.text((tx+1, ty+1), ptxt, font=pf, fill=(*WHITE, 160))
    draw.text((tx,   ty),   ptxt, font=pf, fill=PCT_COLOR)

    # ── Final rounded crop ─────────────────────────────────────────────────────
    fm = Image.new("L", (W,H), 0)
    ImageDraw.Draw(fm).rounded_rectangle([0,0,W-1,H-1], radius=24, fill=255)
    card.putalpha(fm)

    buf = io.BytesIO()
    card.save(buf, format='PNG')
    buf.seek(0)
    return buf

async def generate_love_image(member1, member2, percentage):
    if not PILLOW_AVAILABLE:
        return None

    avatar_img1 = None
    av_url1 = member1.display_avatar.with_size(128).url if member1.display_avatar else None
    if av_url1:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(av_url1) as resp:
                    if resp.status == 200:
                        av_data = await resp.read()
                        avatar_img1 = Image.open(io.BytesIO(av_data))
        except Exception as e:
            logging.error(f"Failed to fetch user1 avatar: {e}")

    avatar_img2 = None
    av_url2 = member2.display_avatar.with_size(128).url if member2.display_avatar else None
    if av_url2:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(av_url2) as resp:
                    if resp.status == 200:
                        av_data = await resp.read()
                        avatar_img2 = Image.open(io.BytesIO(av_data))
        except Exception as e:
            logging.error(f"Failed to fetch user2 avatar: {e}")

    name1 = member1.display_name
    name2 = member2.display_name

    try:
        buf = await asyncio.to_thread(
            build_love_card,
            name1=name1,
            name2=name2,
            percentage=percentage,
            avatar_img1=avatar_img1,
            avatar_img2=avatar_img2
        )
        return buf
    except Exception as e:
        logging.error(f"Error in love card generation: {e}")
        return None


async def check_birthdays():
    await client.wait_until_ready()
    while not client.is_closed():
        today_str = datetime.now().strftime("%d-%m")
        bdays = await load_json('birthdays.json')
        
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
                        last_bday = await load_json('last_bday.json')
                        year = str(datetime.now().year)
                        key = f"{uid}_{year}"
                        if last_bday.get(key):
                            continue
                            
                        # Reward
                        stat = await get_discord_stat(uid)
                        stat['coins'] += 1000
                        user = client.get_user(int(uid))
                        name = user.display_name if user else f"User {uid}"
                        await update_discord_stat(uid, name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
                        
                        await announce_channel.send(f"🎉 **SELAMAT ULANG TAHUN!** 🎉\nHari ini adalah hari ulang tahun {user.mention if user else name}!\nSebagai hadiah, kamu mendapatkan **1000 Koin**! 🎁")
                        
                        last_bday[key] = True
                        await save_json('last_bday.json', last_bday)
                        
        await asyncio.sleep(3600) # Check every hour

async def init_market():
    market = await load_json(MARKET_FILE)
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
        await save_json(MARKET_FILE, market)
    return market

async def update_market_prices():
    await client.wait_until_ready()
    while not client.is_closed():
        market = await init_market()
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
                event_message = f"📈 **MARKET UPDATE:** Harga {market['coins'][target_coin]['name']} ({target_coin}) naik sebesar **+{int(pump_pct*100)}%**!"
            else:
                dump_pct = random.uniform(0.4, 0.8) # 40% to 80% dump
                market['coins'][target_coin]['price'] = int(market['coins'][target_coin]['price'] * (1 - dump_pct))
                event_message = f"📉 **MARKET UPDATE:** Harga {market['coins'][target_coin]['name']} ({target_coin}) turun sebesar **-{int(dump_pct*100)}%**!"
                
            # Prevent going to 0 again
            if market['coins'][target_coin]['price'] < 10:
                market['coins'][target_coin]['price'] = 10
                
            # Update latest history point to reflect massive change
            market['coins'][target_coin]['history'][-1] = market['coins'][target_coin]['price']
            
        market['last_updated'] = datetime.now().isoformat()
        await save_json(MARKET_FILE, market)
        
        # Broadcast event message
        if event_message:
            for guild in client.guilds:
                for ch in guild.text_channels:
                    if 'general' in ch.name.lower() or 'chat' in ch.name.lower():
                        if ch.permissions_for(guild.me).send_messages:
                            client.loop.create_task(ch.send(event_message))
                            break
                            
        # Resolve Binomo Bets
        binomo = await load_json(BINOMO_FILE)
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
                    stat = await get_discord_stat(uid)
                    stat['coins'] += winnings
                    await update_discord_stat(uid, f"User_{uid}", stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
                    results.append(f"<@{uid}> **MENANG {winnings} Koin!** (Tebak {symbol} {direction} | Entry: {entry_price}, Now: {new_price})")
                else:
                    results.append(f"<@{uid}> **RUGI {bet_amount} Koin!** (Tebak {symbol} {direction} | Entry: {entry_price}, Now: {new_price})")
                
                del binomo[uid]
            await save_json(BINOMO_FILE, binomo)
            
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
                            stat = await get_discord_stat(uid)
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
                                    announce_channel.send(f"GG {m.mention}, kamu baru saja naik ke **Level {stat['level']}** dari Voice Channel!")
                                )
                                
                            await update_discord_stat(uid, m.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])

async def boss_raid_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(3600) # Every 1 hour
        if random.random() < 0.20: # 20% chance to spawn boss
            boss_data = await load_json(BOSS_FILE)
            if not boss_data.get('active', False):
                boss_data = {
                    'active': True,
                    'hp': 10000,
                    'max_hp': 10000,
                    'name': '🐉 Naga Emas Koruptor'
                }
                await save_json(BOSS_FILE, boss_data)
                
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
        rigs = await load_json(RIGS_FILE)
        portfolio = await load_json(PORTFOLIO_FILE)
        
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
            await save_json(PORTFOLIO_FILE, portfolio)

@client.event
async def on_ready():
    if not clean_caches.is_running():
        clean_caches.start()
    # Single Server Lock
    for guild in client.guilds:
        if guild.id != ALLOWED_SERVER_ID:
            logging.warning(f"Leaving unauthorized server: {guild.name}")
            await guild.leave()

    tree.copy_global_to(guild=discord.Object(id=ALLOWED_SERVER_ID))
    await tree.sync(guild=discord.Object(id=ALLOWED_SERVER_ID))
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
            
        try:
            cid = int(channel_type)
        except ValueError:
            return web.json_response({'error': 'Invalid channel ID format'}, status=400)
            
        channel = client.get_channel(cid)
        if not channel:
            return web.json_response({'error': 'Channel not found by bot'}, status=404)
            
        await send_long_message(channel, message)
            
        return web.json_response({'status': 'sent'})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def serve_dashboard(request):
    try:
        with open('dashboard.html', 'r', encoding='utf-8') as f:
            html = f.read()
        return web.Response(text=html, content_type='text/html')
    except:
        return web.Response(text="Dashboard not found.", status=404)


async def get_server_data(request):
    try:
        guild = client.get_guild(ALLOWED_SERVER_ID)
        if not guild:
            return web.json_response({'error': 'Bot is not in the allowed server'})
            
        data = {
            'id': str(guild.id),
            'name': guild.name,
            'icon_url': str(guild.icon.url) if guild.icon else None,
            'member_count': guild.member_count,
            'description': guild.description,
            'premium_subscription_count': guild.premium_subscription_count,
            'text_channels': [{'id': str(c.id), 'name': c.name} for c in guild.text_channels],
            'voice_channels': [{'id': str(c.id), 'name': c.name, 'connected_members': len(c.members)} for c in guild.voice_channels],
            'roles': [{'id': str(r.id), 'name': r.name, 'color': str(r.color)} for r in guild.roles if r.name != '@everyone']
        }
        return web.json_response(data)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def get_config_api(request):
    try:
        with open('config.json', 'r') as f:
            data = json.load(f)
        return web.json_response(data)
    except:
        return web.json_response({})

async def update_config_api(request):
    try:
        data = await request.json()
        with open('config.json', 'w') as f:
            json.dump(data, f)
        return web.json_response({'status': 'success'})
    except Exception as e:
        return web.json_response({'status': 'error', 'msg': str(e)}, status=500)

async def start_web_server():
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_options('/{tail:.*}', handle_options)
    app.router.add_get('/', serve_dashboard)
    app.router.add_get('/api/config', get_config_api)
    app.router.add_get('/api/server', get_server_data)
    app.router.add_post('/api/config', update_config_api)
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
            
            # Check config.json first
            try:
                import json
                with open('config.json', 'r') as f:
                    cfg = json.load(f)
                if cfg.get('booster_channel_id'):
                    ch_id = int(cfg['booster_channel_id'])
                    notify_channel = guild.get_channel(ch_id)
            except:
                pass
                
            if notify_channel is None:
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
                    f"👑 **{member.display_name}** (Donatur) telah bergabung ke VC **{after.channel.name}**.",
                    f"✨ **{member.display_name}** (Server Booster) telah bergabung ke VC **{after.channel.name}**.",
                    f"💎 **{member.display_name}** telah bergabung ke VC **{after.channel.name}**.",
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
                users = await load_json('users.json')
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
                            
                await save_json('users.json', users)
                
                # Update DB XP (using existing get/update_discord_stat)
                stat = await get_discord_stat(uid)
                new_xp = stat['xp'] + xp_gained
                await update_discord_stat(uid, member.display_name, stat['coins'], new_xp, stat['level'], stat['lastDaily'])
                
                # Optional: Send DM or channel message for XP gained if you want, but it might be spammy.
                logging.info(f"{member.display_name} earned {xp_gained} XP and {coins_gained} Coins from {minutes} mins in VC.")

async def send_long_message(channel, message):
    if len(message) <= 2000:
        await channel.send(message)
    else:
        for i in range(0, len(message), 2000):
            await channel.send(message[i:i+2000])

def write_to_memory(content):
    try:
        conn = sqlite3.connect(DB_PATH)
        now = datetime.utcnow().isoformat() + "Z"
        conn.execute("INSERT INTO ChatMemory (timestamp, content) VALUES (?, ?)", (now, content))
        # Keep only the last 2000 log entries to prevent DB bloat
        conn.execute("DELETE FROM ChatMemory WHERE id NOT IN (SELECT id FROM ChatMemory ORDER BY id DESC LIMIT 2000)")
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Error saving chat memory to DB: {e}")

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
            uploaded_file = client.files.upload(file=file_path)
            prompt = "Ini adalah rekaman suara dari percakapan discord. Tuliskan transkripnya, lalu berikan balasan yang santai dan lucu (dalam bahasa gaul tongkrongan Indonesia, JANGAN formal, JANGAN ada basa-basi AI) berdasarkan ucapan tersebut."
            response = await asyncio.to_thread(gemini_client.models.generate_content, model='gemini-2.5-flash', contents=[uploaded_file, prompt])
            await channel.send(f"🎙️ **AI Merespons Suara <@{user_id}>:**\n{response.text}")
            uploaded_file.delete()
        except Exception as e:
            logging.error(f"Error processing audio: {str(e)}")
            await channel.send(f"Gagal memproses suara <@{user_id}> dengan AI.")
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

async def get_gemini_response(query, user_id=None, user_name=None):
    try:
        final_query = query
        system_prefix = (
            "[SYSTEM INSTRUCTION: Kamu adalah W2E Bot, teman tongkrongan Discord yang asik, gaul, santai, kocak, dan kadang agak sarkas/savage. "
            "Gunakan bahasa gaul Indonesia Gen-Z (seperti lo, gue, bro, cuy, wkwk, anjir, dll.). "
            "Jawablah dengan singkat, padat, dan sangat santai (maksimal 2-3 kalimat saja). JANGAN PERNAH ada basa-basi khas AI "
            "seperti 'Tentu, ini dia', 'Mari kita...', 'Sebagai AI...', dll. JANGAN berbicara formal layaknya robot customer service. "
            "Langsung jawab dengan natural seperti chat discord dari temen tongkrongan biasa.]\n"
        )
        
        # Inject user's server nickname/display name so AI recognizes them
        if user_name:
            system_prefix += f"[SYSTEM: Kamu sedang berbicara dengan user bernama '{user_name}'. Panggil nama atau sapa mereka jika relevan.]\n"
            
        if user_id:
            personas = await load_json(PERSONAS_FILE)
            if str(user_id) in personas:
                system_prefix += f"[SYSTEM INSTRUCTION: Mulai sekarang kamu HARUS berbicara dan bertingkah sepenuhnya dengan persona/gaya ini: '{personas[str(user_id)]}'. Jangan pernah keluar dari karakter.]\n"
            
            final_query = f"{system_prefix}\nPesan User: {query}"
                
            if user_id not in chat_sessions:
                chat_sessions[user_id] = gemini_client.chats.create(model='gemini-2.5-flash')
            response = await asyncio.to_thread(chat_sessions[user_id].send_message, final_query)
        else:
            final_query = f"{system_prefix}\nPesan User: {query}"
            chat_session = gemini_client.chats.create(model='gemini-2.5-flash')
            response = await asyncio.to_thread(chat_session.send_message, final_query)
        return response.text
    except Exception as e:
        logging.error(f"Error getting Gemini response: {str(e)}")
        return "Error getting response from Gemini."

    # ── Update Quest Progress ────────────────────────────────────────────────
    await update_quest_progress(str(message.author.id), 'send_msg', 1)
    
    if message.channel.id == 1341038015186862201:
        nick = getattr(message.author, 'nick', None) or message.author.display_name
        response = await get_gemini_response(message.content, message.author.id, nick)
        await send_long_message(message.channel, response)
        write_to_memory(f'User: {message.content}\nBot: {response}')
        return

    if message.content.startswith('w2e ai '):
        prefix = 'w2e ai '
        query = message.content[len(prefix):].strip()
        if not query:
            await send_msg_embed(message.channel, 'Please provide a query.')
            return
        nick = getattr(message.author, 'nick', None) or message.author.display_name
        response = await get_gemini_response(query, message.author.id, nick)
        await send_long_message(message.channel, response)
        write_to_memory(f'User: {query}\nBot: {response}')
    
    if message.content.startswith('w2e1'):
        channel_id = 1332111384523309156
        message_content = message.content[len('w2e1 '):].strip()
        channel = client.get_channel(channel_id)
        if channel:
            await send_long_message(channel, message_content)
            await send_msg_embed(message.channel, "Message sent to bhot.")
            write_to_memory(f'User: {message_content}\nBot: Message sent to bhot.')
        else:
            await send_msg_embed(message.channel, "Invalid channel ID for bhot.")
    
    if message.content.startswith('w2e2'):
        channel_id = 1332113600894079131
        message_content = message.content[len('w2e2 '):].strip()
        channel = client.get_channel(channel_id)
        if channel:
            await send_long_message(channel, message_content)
            await send_msg_embed(message.channel, "Message sent to general.")
            write_to_memory(f'User: {message_content}\nBot: Message sent to general.')
        else:
            await send_msg_embed(message.channel, "Invalid channel ID for general.")
    
    if message.content.startswith('w2e3'):
        channel_id = 1340942564379070535
        message_content = message.content[len('w2e3 '):].strip()
        channel = client.get_channel(channel_id)
        if channel:
            await send_long_message(channel, message_content)
            await send_msg_embed(message.channel, "Message sent to console.")
            write_to_memory(f'User: {message_content}\nBot: Message sent to console.')
        else:
            await send_msg_embed(message.channel, "Invalid channel ID for console.")

    if message.content.startswith('w2echannel'):
        await send_msg_embed(message.channel, "List of channels:\n1. bhot (1332111384523309156)\n2. general (1332113600894079131)\n3. console (1340942564379070535)")

    content_clean = message.content.strip().lower()
    if content_clean in ['w2ehelp', 'w2e help', '!help', '!w2ehelp', 'w2e w2ehelp', f'{BOT_PREFIX.lower()}help', f'{BOT_PREFIX.lower()} help']:
        from w2e_help import send_w2e_help
        await send_w2e_help(message)
        return
        
# ── Coinflip: !w2ecf heads/tails [bet] ───────────────────────────────────
    if message.content.startswith('w2e cf'):
        uid = str(message.author.id)
        stat = await get_discord_stat(uid)
        parts = message.content.split()

        if len(parts) < 3:
            await send_msg_embed(message.channel, "Format: `!w2ecf <heads/tails> [bet]` — contoh: `!w2ecf heads 100`")
            return

        choice = parts[2].lower()
        if choice not in ('heads', 'tails', 'head', 'tail', 'h', 't'):
            await send_msg_embed(message.channel, "Pilihannya hanya `heads` atau `tails`!")
            return
        choice_normalized = 'heads' if choice in ('heads', 'head', 'h') else 'tails'

        bet = 50
        if len(parts) >= 4:
            try:
                bet = int(parts[3])
                if bet < 10:
                    await send_msg_embed(message.channel, "❌ Minimal bet **10 Koin**.")
                    return
                if bet > 2000:
                    await send_msg_embed(message.channel, "❌ Maksimal bet **2000 Koin**.")
                    return
            except ValueError:
                await send_msg_embed(message.channel, "Format: `!w2ecf heads 100`")
                return

        if stat['coins'] < bet:
            await send_msg_embed(message.channel, f"❌ Koin tidak cukup! Punya **{stat['coins']}**, butuh **{bet}**.")
            return

        result = random.choice(['heads', 'tails'])
        coin_emoji = "🟡" if result == 'heads' else "⚪"
        flip_msg = await send_msg_embed(message.channel, 
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

        await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        color = discord.Color.green() if result == choice_normalized else discord.Color.red()
        embed = discord.Embed(
            description=(
                f"🪙 **COIN FLIP** — **{message.author.display_name}** pilih **{choice_normalized}**, bet **{bet} Koin**\n"
                f"{result_line}\n"
                f"💼 Sisa Koin: **{stat['coins']}**"
            ),
            color=color
        )
        await flip_msg.edit(embed=embed)

    # ── Lootbox: !w2ebox [common/rare/epic] ──────────────────────────────────
    if message.content.startswith('w2e box'):
        uid = str(message.author.id)
        stat = await get_discord_stat(uid)
        parts = message.content.split()
        tier = parts[2].lower() if len(parts) > 2 else 'common'

        BOXES = {
            'common':    {'cost': 100,  'emoji': '📦', 'color': '⬜', 'min': 50,   'max': 250,  'xp': 10},
            'rare':      {'cost': 300,  'emoji': '🎁', 'color': '🟦', 'min': 200,  'max': 700,  'xp': 30},
            'epic':      {'cost': 800,  'emoji': '💜', 'color': '🟪', 'min': 600,  'max': 2000, 'xp': 80},
            'legendary': {'cost': 2500, 'emoji': '🌟', 'color': '🟨', 'min': 2000, 'max': 8000, 'xp': 200},
        }

        if tier not in BOXES:
            box_list = "\n".join([f"{v['emoji']} **{k.capitalize()}** — {v['cost']} Koin" for k, v in BOXES.items()])
            await send_msg_embed(message.channel, f"Pilih tier box:\n{box_list}\nContoh: `!w2ebox rare`")
            return

        box = BOXES[tier]
        if stat['coins'] < box['cost']:
            await send_msg_embed(message.channel, f"❌ Butuh **{box['cost']} Koin** untuk {tier} box. Punya: **{stat['coins']}**.")
            return

        stat['coins'] -= box['cost']
        reward_coins = random.randint(box['min'], box['max'])

        # 10% bonus jackpot multiplier
        jackpot = False
        if random.random() < 0.10:
            reward_coins = int(reward_coins * 2.5)
            jackpot = True

        stat['coins'] += reward_coins
        await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await check_level_up(message.channel, message.author, box['xp'])

        open_msg = await send_msg_embed(message.channel, f"{box['emoji']} **Membuka {tier.capitalize()} Box...** {box['color']}{box['color']}{box['color']}")
        await asyncio.sleep(1.5)

        jackpot_tag = "⚡ **JACKPOT BONUS x2.5!**\n" if jackpot else ""
        color = discord.Color.gold()
        embed = discord.Embed(
            description=(
                f"{box['emoji']} **{tier.capitalize()} Box Dibuka!**\n"
                f"{jackpot_tag}"
                f"💰 Kamu mendapat **+{reward_coins} Koin**!\n"
                f"💼 Total Koin: **{stat['coins']}**"
            ),
            color=color
        )
        await open_msg.edit(embed=embed)

    # ── Pray: !w2epray @user ─────────────────────────────────────────────────
    if message.content.startswith('w2e pray'):
        if not message.mentions:
            await send_msg_embed(message.channel, "Mention seseorang dulu! `!w2epray @user`")
            return
        target = message.mentions[0]
        if target == message.author:
            await send_msg_embed(message.channel, "❌ Kamu tidak bisa mendoakan diri sendiri!")
            return
        if target.bot:
            await send_msg_embed(message.channel, "❌ Bot tidak butuh doa.")
            return

        uid_target = str(target.id)
        stat_target = await get_discord_stat(uid_target)

        # Pray memberi 5–50 koin ke target secara random
        blessing = random.randint(5, 50)
        stat_target['coins'] += blessing
        await update_discord_stat(uid_target, target.display_name, stat_target['coins'], stat_target['xp'], stat_target['level'], stat_target['lastDaily'])

        pray_msgs = [
            f"🙏 **{message.author.display_name}** mendoakan **{target.display_name}**... Semoga rezekinya lancar! (+{blessing} Koin)",
            f"✨ Doa **{message.author.display_name}** dikabulkan untuk **{target.display_name}**! (+{blessing} Koin diberikan oleh alam semesta)",
            f"🌟 Langit menurunkan berkah atas doa **{message.author.display_name}** kepada **{target.display_name}**! +{blessing} Koin~",
        ]
        await send_msg_embed(message.channel, random.choice(pray_msgs))

    # (Removed duplicate curse command block)

    # ── Admin Add Coin: !w2eaddcoin @user <amount> ───────────────────────────
    if message.content.startswith('w2e addcoin'):
        if not message.author.guild_permissions.administrator:
            await send_msg_embed(message.channel, "❌ Kamu bukan admin, jangan ngide!")
            return
            
        parts = message.content.split()
        if len(parts) < 3 or not message.mentions:
            await send_msg_embed(message.channel, "Format: `!w2eaddcoin @user <jumlah>`")
            return
            
        target = message.mentions[0]
        try:
            amount = int(parts[-1])
        except ValueError:
            await send_msg_embed(message.channel, "❌ Jumlah harus berupa angka!")
            return
            
        uid = str(target.id)
        stat = await get_discord_stat(uid)
        stat['coins'] += amount
        await update_discord_stat(uid, target.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        await send_msg_embed(message.channel, f"👑 **ADMIN MAGIC!** {message.author.mention} baru saja menambahkan **{amount} Koin** kepada {target.mention}! Cuan gratis dari pusat!")

    # ── Give: !w2egive @user <amount> ────────────────────────────────────────
    if message.content.startswith('w2e give'):
        if not message.mentions:
            await send_msg_embed(message.channel, "Format: `!w2egive @user <jumlah>` — contoh: `!w2egive @teman 100`")
            return
        target = message.mentions[0]
        if target == message.author:
            await send_msg_embed(message.channel, "❌ Kamu tidak bisa memberikan koin ke diri sendiri.")
            return
        if target.bot:
            await send_msg_embed(message.channel, "❌ Bot tidak bisa menerima koin.")
            return

        parts = message.content.split()
        try:
            amount = int(parts[-1])
            if amount <= 0:
                raise ValueError
        except ValueError:
            await send_msg_embed(message.channel, "Masukin jumlah koin yang valid! Contoh: `!w2egive @teman 100`")
            return

        uid_self = str(message.author.id)
        stat_self = await get_discord_stat(uid_self)

        if stat_self['coins'] < amount:
            await send_msg_embed(message.channel, f"❌ Koin tidak cukup! Punya **{stat_self['coins']}**, mau kasih **{amount}**.")
            return

        uid_target = str(target.id)
        stat_target = await get_discord_stat(uid_target)

        stat_self['coins'] -= amount
        stat_target['coins'] += amount
        await update_discord_stat(uid_self, message.author.display_name, stat_self['coins'], stat_self['xp'], stat_self['level'], stat_self['lastDaily'])
        await update_discord_stat(uid_target, target.display_name, stat_target['coins'], stat_target['xp'], stat_target['level'], stat_target['lastDaily'])

        await send_msg_embed(message.channel, 
            f"💸 **{message.author.display_name}** memberikan **{amount} Koin** kepada **{target.display_name}**!\n"
            f"💼 Sisa koin {message.author.display_name}: **{stat_self['coins']}**"
        )

    # ── Top Leaderboard: !w2etop ─────────────────────────────────────────────
    if message.content.startswith('w2e top'):
        # Sort users by coins using sqlite directly or just fetch all and sort
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT displayName, coins, level FROM DiscordStat ORDER BY coins DESC LIMIT 10')
            top_users = c.fetchall()
            conn.close()
            
            res = "🏆 **W2E LEADERBOARD - SULTAN SERVER** 🏆\n\n"
            medals = ["🥇", "🥈", "🥉"]
            for i, user in enumerate(top_users):
                rank = medals[i] if i < 3 else f"`#{i+1}`"
                res += f"{rank} **{user[0]}** — 💰 {user[1]} Koin | Lvl {user[2]}\n"
            
            await send_msg_embed(message.channel, res)
        except Exception as e:
            await send_msg_embed(message.channel, "Gagal mengambil data leaderboard.")

    # ── Weekly Bonus: !w2eweekly ─────────────────────────────────────────────
    if message.content.startswith('w2e weekly'):
        uid = str(message.author.id)
        stat = await get_discord_stat(uid)
        weekly_data = await load_json(WEEKLY_FILE)
        
        today = datetime.now()
        last_weekly_str = weekly_data.get(uid)
        
        can_claim = True
        if last_weekly_str:
            last_weekly = datetime.strptime(last_weekly_str, '%Y-%m-%d')
            if (today - last_weekly).days < 7:
                can_claim = False
                days_left = 7 - (today - last_weekly).days
                
        if not can_claim:
            await send_msg_embed(message.channel, f"❌ Kamu sudah klaim bonus mingguan! Tunggu **{days_left} hari** lagi.")
            return
            
        reward = random.randint(500, 2000)
        multiplier_str = ""
        if message.author.premium_since:
            reward *= 2
            multiplier_str = "\n*(👑 Booster Bonus x2!)*"
            
        weekly_data[uid] = today.strftime('%Y-%m-%d')
        await save_json(WEEKLY_FILE, weekly_data)
        
        stat['coins'] += reward
        await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await send_msg_embed(message.channel, f"🎁 **BONUS MINGGUAN!** {message.author.display_name} mendapatkan **{reward} Koin**! (Total: {stat['coins']}){multiplier_str}")
        await check_level_up(message.channel, message.author, 100)

    # ── Rob: !w2erob @user ───────────────────────────────────────────────────
    if message.content.startswith('w2e rob'):
        if not message.mentions:
            await send_msg_embed(message.channel, "Format: `!w2erob @user`")
            return
        target = message.mentions[0]
        if target == message.author:
            await send_msg_embed(message.channel, "❌ Masa merampok diri sendiri...")
            return
        if target.bot:
            await send_msg_embed(message.channel, "❌ Tidak bisa merampok bot.")
            return

        uid_self = str(message.author.id)
        uid_target = str(target.id)
        
        # Check cooldown (30 menit per attacker-target combo)
        cooldown_key = (uid_self, uid_target)
        if cooldown_key in rob_cooldowns:
            delta = datetime.now() - rob_cooldowns[cooldown_key]
            if delta.total_seconds() < 1800:
                mins_left = int((1800 - delta.total_seconds()) // 60)
                await send_msg_embed(message.channel, f"⏳ Polisi masih patroli di area {target.display_name}. Tunggu {mins_left} menit lagi!")
                return
                
        stat_self = await get_discord_stat(uid_self)
        stat_target = await get_discord_stat(uid_target)

        if stat_target['coins'] < 100:
            await send_msg_embed(message.channel, f"❌ {target.display_name} terlalu miskin untuk dirampok (Koin < 100). Kasihanilah dia.")
            return

        rob_cooldowns[cooldown_key] = datetime.now()

        # Cek shield target
        target_items = await load_json(ITEMS_FILE).get(uid_target, {})
        if target_items.get('shield', 0) > 0:
            target_items['shield'] -= 1
            all_items = await load_json(ITEMS_FILE)
            if uid_target not in all_items: all_items[uid_target] = {}
            all_items[uid_target]['shield'] = target_items['shield']
            await save_json(ITEMS_FILE, all_items)
            
            await send_msg_embed(message.channel, f"🛡️ **{message.author.display_name}** mencoba merampok, tapi **{target.display_name}** punya Shield! Perampokan GAGAL.")
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
            await send_msg_embed(message.channel, f"🥷 **PERAMPOKAN SUKSES!**\n**{message.author.display_name}** berhasil mencuri **{stolen} Koin** dari **{target.display_name}**!{booster_msg}")
        else:
            # Gagal
            fine = random.randint(100, 200)
            if is_target_booster:
                fine *= 2 # Denda 2x lipat
            stat_self['coins'] = max(0, stat_self['coins'] - fine)
            booster_msg = "\n(Kena karma nyoba ngerampok donatur!)" if is_target_booster else ""
            await send_msg_embed(message.channel, f"🚨 **TERCYDUK!**\n**{message.author.display_name}** tertangkap basah mencoba merampok **{target.display_name}** dan didenda **{fine} Koin**!{booster_msg}")

        await update_discord_stat(uid_self, message.author.display_name, stat_self['coins'], stat_self['xp'], stat_self['level'], stat_self['lastDaily'])
        await update_discord_stat(uid_target, target.display_name, stat_target['coins'], stat_target['xp'], stat_target['level'], stat_target['lastDaily'])

    # ── Shop: !w2eshop / !w2ebuy ─────────────────────────────────────────────
    if message.content.startswith('w2e shop'):
        is_booster = message.author.premium_since is not None
        booster_msg = "\n👑 **(Diskon Booster 50% Aktif!)**" if is_booster else ""
        res = f"🛒 **W2E SULTAN SHOP** 🛒{booster_msg}\n*Gunakan `!w2ebuy <item_id>` untuk membeli*\n\n"
        for i_id, i_data in SHOP_ITEMS.items():
            price = int(i_data['price'] * 0.5) if is_booster else i_data['price']
            res += f"**{i_data['name']}** (`{i_id}`) — 💰 {price}\n└ {i_data['desc']}\n\n"
        await send_msg_embed(message.channel, res)

    if message.content.startswith('w2e buy'):
        parts = message.content.split()
        if len(parts) < 3:
            await send_msg_embed(message.channel, "Mau beli apa? Contoh: `!w2ebuy shield`")
            return
            
        item_id = parts[2].lower()
        if item_id not in SHOP_ITEMS:
            await send_msg_embed(message.channel, "❌ Item tidak ditemukan. Cek `!w2eshop`.")
            return
            
        item = SHOP_ITEMS[item_id]
        uid = str(message.author.id)
        stat = await get_discord_stat(uid)
        
        is_booster = message.author.premium_since is not None
        price = int(item['price'] * 0.5) if is_booster else item['price']
        
        if stat['coins'] < price:
            await send_msg_embed(message.channel, f"❌ Uang tidak cukup. Butuh **{price} Koin**.")
            return
            
        stat['coins'] -= price
        await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        items_data = await load_json(ITEMS_FILE)
        if uid not in items_data: items_data[uid] = {}
        
        if item_id == 'double_xp':
            items_data[uid]['double_xp_until'] = (datetime.now() + timedelta(hours=2)).timestamp()
        else:
            items_data[uid][item_id] = items_data[uid].get(item_id, 0) + 1
            
        await save_json(ITEMS_FILE, items_data)
        await send_msg_embed(message.channel, f"🛍️ Berhasil membeli **{item['name']}**! Sisa Koin: {stat['coins']}")

    # ── Inventory & Transfer ───────────────────────────────────────────────
    if message.content.startswith('w2e inventory'):
        uid = str(message.author.id)
        items_data = await load_json(ITEMS_FILE).get(uid, {})
        
        if not items_data:
            await send_msg_embed(message.channel, "🎒 Tas kamu kosong melompong.")
            return
            
        res = f"🎒 **Inventory {message.author.display_name}** 🎒\n"
        for i_id, count in items_data.items():
            if isinstance(count, int) and count > 0:
                name = SHOP_ITEMS.get(i_id, {}).get('name', i_id)
                res += f"🔸 **{name}**: {count}x\n"
            elif i_id == 'bg_url' and count:
                res += "🔸 **Custom Background**: Aktif\n"
        await send_msg_embed(message.channel, res)

    if message.content.startswith('w2e transfer'):
        parts = message.content.split()
        if len(parts) < 3 or not message.mentions:
            await send_msg_embed(message.channel, "Format: `!w2etransfer @user <jumlah>`")
            return
            
        target = message.mentions[0]
        if target == message.author or target.bot:
            await send_msg_embed(message.channel, "❌ Gak bisa transfer ke bot atau diri sendiri.")
            return
            
        try:
            amount = int(parts[-1])
            if amount <= 0: raise ValueError
        except ValueError:
            await send_msg_embed(message.channel, "❌ Jumlah koin harus angka positif.")
            return
            
        uid1 = str(message.author.id)
        uid2 = str(target.id)
        stat1 = await get_discord_stat(uid1)
        stat2 = await get_discord_stat(uid2)
        
        if stat1['coins'] < amount:
            await send_msg_embed(message.channel, f"❌ Koin kamu gak cukup! Kamu cuma punya **{stat1['coins']} Koin**.")
            return
            
        stat1['coins'] -= amount
        stat2['coins'] += amount
        await update_discord_stat(uid1, message.author.display_name, stat1['coins'], stat1['xp'], stat1['level'], stat1['lastDaily'])
        await update_discord_stat(uid2, target.display_name, stat2['coins'], stat2['xp'], stat2['level'], stat2['lastDaily'])
        
        await send_msg_embed(message.channel, f"💸 **Transfer Sukses!**\n{message.author.display_name} mengirimkan **{amount} Koin** ke {target.display_name}.")

    if message.content.startswith('w2e work'):
        uid = str(message.author.id)
        if uid in work_cooldowns:
            delta = datetime.now() - work_cooldowns[uid]
            if delta.total_seconds() < 3600:
                mins_left = int((3600 - delta.total_seconds()) // 60)
                await send_msg_embed(message.channel, f"⏳ Kamu masih capek kerja. Istirahat dulu **{mins_left} menit** lagi!")
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
            
        stat = await get_discord_stat(uid)
        stat['coins'] += reward
        await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        booster_txt = " (Boost x1.5)" if message.author.premium_since else ""
        await send_msg_embed(message.channel, f"💼 {message.author.display_name} baru saja {job_name} dan mendapatkan **{reward} Koin**!{booster_txt}")

    if message.content.startswith('w2e curse'):
        parts = message.content.split()
        if len(parts) < 2 or not message.mentions:
            await send_msg_embed(message.channel, "Format: `!w2ecurse @user`\nBiaya: 100 Koin. Jika target punya Shield, kutukan gagal.")
            return
            
        target = message.mentions[0]
        if target == message.author or target.bot:
            await send_msg_embed(message.channel, "❌ Masa ngutuk bot atau diri sendiri...")
            return
            
        uid1 = str(message.author.id)
        uid2 = str(target.id)
        stat1 = await get_discord_stat(uid1)
        
        if stat1['coins'] < 100:
            await send_msg_embed(message.channel, "❌ Dukun minta bayaran 100 Koin buat ngutuk. Duit kamu gak cukup.")
            return
            
        stat1['coins'] -= 100
        await update_discord_stat(uid1, message.author.display_name, stat1['coins'], stat1['xp'], stat1['level'], stat1['lastDaily'])
        
        target_items = await load_json(ITEMS_FILE).get(uid2, {})
        if target_items.get('shield', 0) > 0:
            target_items['shield'] -= 1
            all_items = await load_json(ITEMS_FILE)
            if uid2 not in all_items: all_items[uid2] = {}
            all_items[uid2]['shield'] = target_items['shield']
            await save_json(ITEMS_FILE, all_items)
            
            await send_msg_embed(message.channel, f"🧿 **KUTUKAN GAGAL!**\n{message.author.display_name} ngirim santet ke {target.display_name}, tapi dia pake **Shield**! Santet mental.")
            return
            
        stat2 = await get_discord_stat(uid2)
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
            
        await update_discord_stat(uid2, target.display_name, stat2['coins'], stat2['xp'], stat2['level'], stat2['lastDaily'])
        await send_msg_embed(message.channel, f"☠️ **KUTUKAN BERHASIL!**\n{target.mention} kena santet dari {message.author.display_name} dan {eff_msg} 👻")

    # ── W2E Casino ───────────────────────────────────────────────────────────
    if message.content.startswith('w2e slot'):
        parts = message.content.split()
        if len(parts) < 3:
            await send_msg_embed(message.channel, "Format: `!w2eslot <taruhan>`")
            return
            
        try:
            bet = int(parts[2])
            if bet < 10: raise ValueError
        except ValueError:
            await send_msg_embed(message.channel, "Taruhan harus angka minimal 10.")
            return
            
        uid = str(message.author.id)
        stat = await get_discord_stat(uid)
        
        if stat['coins'] < bet:
            await send_msg_embed(message.channel, f"❌ Koin tidak cukup. Kamu punya **{stat['coins']} Koin**.")
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
            res_msg += "👍 Dua simbol sama. Taruhan kembali."
        else:
            res_msg += "❌ Zonk! Uang taruhan hangus."
            
        await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await send_msg_embed(message.channel, res_msg)

    if message.content.startswith('w2e flip'):
        parts = message.content.split()
        if len(parts) < 4:
            await send_msg_embed(message.channel, "Format: `!w2eflip <heads/tails> <taruhan>`")
            return
            
        choice = parts[2].lower()
        if choice not in ('heads', 'tails', 'head', 'tail', 'h', 't'):
            await send_msg_embed(message.channel, "Pilihannya cuma `heads` (Angka) atau `tails` (Gambar).")
            return
        choice_normalized = 'heads' if choice in ('heads', 'head', 'h') else 'tails'
            
        try:
            bet = int(parts[3])
            if bet < 10: raise ValueError
        except ValueError:
            await send_msg_embed(message.channel, "Taruhan harus angka minimal 10.")
            return
            
        uid = str(message.author.id)
        stat = await get_discord_stat(uid)
        
        if stat['coins'] < bet:
            await send_msg_embed(message.channel, f"❌ Koin tidak cukup. Kamu punya **{stat['coins']} Koin**.")
            return
            
        stat['coins'] -= bet
        
        result = random.choice(['heads', 'tails'])
        if choice_normalized == result:
            win = bet * 2
            stat['coins'] += win
            await send_msg_embed(message.channel, f"🪙 Koin menunjukkan **{result.upper()}**!\n✅ Tebakanmu benar, memenangkan **{win} Koin**!")
        else:
            await send_msg_embed(message.channel, f"🪙 Koin menunjukkan **{result.upper()}**!\n❌ Yah kalah. Uang taruhan hangus.")
            
        await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])

    if message.content.startswith('w2e crash'):
        parts = message.content.split()
        if len(parts) < 3:
            await send_msg_embed(message.channel, "Format: `!w2ecrash <taruhan>`")
            return
            
        try:
            bet = int(parts[2])
            if bet < 10: raise ValueError
        except ValueError:
            await send_msg_embed(message.channel, "Taruhan harus angka minimal 10.")
            return
            
        uid = str(message.author.id)
        stat = await get_discord_stat(uid)
        
        if stat['coins'] < bet:
            await send_msg_embed(message.channel, f"❌ Koin tidak cukup. Kamu punya **{stat['coins']} Koin**.")
            return
            
        stat['coins'] -= bet
        await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        crash_point = round(random.uniform(1.1, 5.0), 1)
        if random.random() < 0.2: # 20% chance to crash very early
            crash_point = round(random.uniform(1.0, 1.2), 1)
        elif random.random() < 0.1: # 10% chance to go very high
            crash_point = round(random.uniform(5.0, 15.0), 1)
            
        current_mult = 1.0
        
        embed = discord.Embed(title="🚀 W2E Crash", description=f"**Multiplier:** `{current_mult}x`\n\nKetik `stop` di chat untuk menarik koin!", color=discord.Color.green())
        embed.set_footer(text=f"Taruhan: {bet} | Dimainkan oleh {message.author.display_name}")
        msg = await send_msg_embed(message.channel, embed=embed)
        
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
            await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            
            embed.description = f"**Multiplier Akhir:** `{current_mult}x`\n\n✅ Kamu berhenti tepat waktu dan memenangkan **{win_amount} Koin**!"
            embed.color = discord.Color.green()
            await msg.edit(embed=embed)
        else:
            embed.description = f"**Multiplier Akhir:** `{current_mult}x`\n\n💥 **CRASH!** Roket meledak! Uang taruhan **{bet}** hangus."
            embed.color = discord.Color.dark_red()
            await msg.edit(embed=embed)

    # ── RPS PvP: !w2erps @user [bet] ─────────────────────────────────────────
    if message.content.startswith('w2e rps'):
        parts = message.content.split()
        if not message.mentions or len(parts) < 3:
            await send_msg_embed(message.channel, "Format: `!w2erps @user <bet>`")
            return
            
        target = message.mentions[0]
        if target == message.author or target.bot:
            await send_msg_embed(message.channel, "❌ Gak bisa lawan bot / diri sendiri.")
            return
            
        try:
            bet = int(parts[-1])
            if bet < 10: raise ValueError
        except ValueError:
            await send_msg_embed(message.channel, "Bet harus angka dan minimal 10.")
            return
            
        uid1 = str(message.author.id)
        uid2 = str(target.id)
        stat1 = await get_discord_stat(uid1)
        stat2 = await get_discord_stat(uid2)
        
        if stat1['coins'] < bet:
            await send_msg_embed(message.channel, f"❌ Koin kamu gak cukup! Punya: {stat1['coins']}")
            return
        if stat2['coins'] < bet:
            await send_msg_embed(message.channel, f"❌ Koin musuh gak cukup! Dia punya: {stat2['coins']}")
            return
            
        # Potong koin di awal
        stat1['coins'] -= bet
        stat2['coins'] -= bet
        await update_discord_stat(uid1, message.author.display_name, stat1['coins'], stat1['xp'], stat1['level'], stat1['lastDaily'])
        await update_discord_stat(uid2, target.display_name, stat2['coins'], stat2['xp'], stat2['level'], stat2['lastDaily'])
        
        await send_msg_embed(message.channel, 
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
            stat1 = await get_discord_stat(uid1)
            stat2 = await get_discord_stat(uid2)
            stat1['coins'] += refund
            stat2['coins'] += refund
            await update_discord_stat(uid1, message.author.display_name, stat1['coins'], stat1['xp'], stat1['level'], stat1['lastDaily'])
            await update_discord_stat(uid2, target.display_name, stat2['coins'], stat2['xp'], stat2['level'], stat2['lastDaily'])
            await send_msg_embed(message.channel, "⏱️ Duel dibatalkan karena ada yang tidak menjawab. Koin dikembalikan.")
            return
            
        # Tentukan pemenang
        win_rules = {'batu': 'gunting', 'gunting': 'kertas', 'kertas': 'batu'}
        emojis = {'batu': '🪨', 'gunting': '✂️', 'kertas': '📄'}
        
        winnings = bet * 2
        stat1 = await get_discord_stat(uid1)
        stat2 = await get_discord_stat(uid2)
        
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
            
        await update_discord_stat(uid1, message.author.display_name, stat1['coins'], stat1['xp'], stat1['level'], stat1['lastDaily'])
        await update_discord_stat(uid2, target.display_name, stat2['coins'], stat2['xp'], stat2['level'], stat2['lastDaily'])
        
        await send_msg_embed(message.channel, 
            f"**HASIL DUEL:**\n"
            f"{message.author.display_name}: {emojis[c1]} {c1.upper()}\n"
            f"{target.display_name}: {emojis[c2]} {c2.upper()}\n\n"
            f"{result}"
        )

    # ── Daily Quests: !w2equest ──────────────────────────────────────────────
    if message.content.startswith('w2e quest'):
        uid = str(message.author.id)
        qdata = await get_user_quests(uid)
        
        parts = message.content.split()
        if len(parts) > 2 and parts[2].lower() == 'claim':
            if qdata['claimed']:
                await send_msg_embed(message.channel, "❌ Kamu sudah klaim reward hari ini!")
                return
            all_done = all(q['done'] for q in qdata['quests'])
            if not all_done:
                await send_msg_embed(message.channel, "❌ Selesaikan semua quest dulu!")
                return
                
            qdata['claimed'] = True
            await save_json(QUESTS_FILE, await load_json(QUESTS_FILE) | {uid: qdata})
            
            stat = await get_discord_stat(uid)
            stat['coins'] += 300
            await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            await send_msg_embed(message.channel, "🎁 **QUEST SELESAI!** Kamu mendapatkan **300 Koin**!")
            await check_level_up(message.channel, message.author, 50)
            return

        res = f"📋 **DAILY QUESTS - {message.author.display_name}** 📋\n*Ketik `!w2equest claim` jika semua selesai (+300 Koin)*\n\n"
        for q in qdata['quests']:
            status = "✅" if q['done'] else "❌"
            res += f"{status} **{q['desc']}** ({q['progress']}/{q['target']})\n"
        
        if qdata['claimed']:
            res += "\n🌟 *Semua quest hari ini sudah selesai & diklaim!*"
            
        await send_msg_embed(message.channel, res)

    # ── Family System ────────────────────────────────────────────────────────
    if message.content.startswith('w2e marry'):
        if not message.mentions:
            await send_msg_embed(message.channel, "Mau nikah sama siapa? Mention orangnya! `!w2emarry @user`")
            return
        target = message.mentions[0]
        if target == message.author or target.bot:
            await send_msg_embed(message.channel, "❌ Kamu gak bisa nikah sama diri sendiri/bot.")
            return

        uid1 = str(message.author.id)
        uid2 = str(target.id)
        fam_data = await load_json(FAMILY_FILE)
        
        if fam_data.get(uid1, {}).get('partner'):
            await send_msg_embed(message.channel, "❌ Kamu sudah menikah! Cerai dulu pakai `!w2edivorce`.")
            return
        if fam_data.get(uid2, {}).get('partner'):
            await send_msg_embed(message.channel, "❌ Dia sudah punya pasangan. Cari yang lain!")
            return

        # Biaya nikah
        stat = await get_discord_stat(uid1)
        if stat['coins'] < 500:
            await send_msg_embed(message.channel, f"❌ Biaya KUA mahal bos. Butuh **500 Koin** (Koinmu: {stat['coins']}).")
            return

        await send_msg_embed(message.channel, 
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
                await update_discord_stat(uid1, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
                
                if uid1 not in fam_data: fam_data[uid1] = {}
                if uid2 not in fam_data: fam_data[uid2] = {}
                fam_data[uid1]['partner'] = uid2
                fam_data[uid2]['partner'] = uid1
                await save_json(FAMILY_FILE, fam_data)
                
                await send_msg_embed(message.channel, f"🎉 **SAAAHHH!** 🎉\n{message.author.mention} dan {target.mention} resmi menikah! (-500 Koin)")
            else:
                await send_msg_embed(message.channel, f"💔 Yah... {message.author.mention} lamaranmu ditolak mentah-mentah.")
        except asyncio.TimeoutError:
            await send_msg_embed(message.channel, f"⏱️ {target.display_name} kelamaan mikir. Lamaran dibatalkan.")

    if message.content.startswith('w2e divorce'):
        uid = str(message.author.id)
        fam_data = await load_json(FAMILY_FILE)
        
        partner_id = fam_data.get(uid, {}).get('partner')
        if not partner_id:
            await send_msg_embed(message.channel, "❌ Kamu aja masih jomblo, mau cerai sama siapa?")
            return

        fam_data[uid]['partner'] = None
        if partner_id in fam_data:
            fam_data[partner_id]['partner'] = None
        await save_json(FAMILY_FILE, fam_data)
        
        partner_user = client.get_user(int(partner_id))
        pname = partner_user.display_name if partner_user else f"User {partner_id}"
        await send_msg_embed(message.channel, f"💔 **CERAI!** {message.author.display_name} resmi bercerai dengan {pname}.")

    if message.content.startswith('w2e adopt'):
        if not message.mentions:
            await send_msg_embed(message.channel, "Format: `!w2eadopt @user`")
            return
        target = message.mentions[0]
        uid1 = str(message.author.id)
        uid2 = str(target.id)
        
        if uid1 == uid2 or target.bot:
            await send_msg_embed(message.channel, "❌ Gak bisa adopsi diri sendiri/bot.")
            return

        fam_data = await load_json(FAMILY_FILE)
        
        if fam_data.get(uid2, {}).get('parent'):
            await send_msg_embed(message.channel, f"❌ {target.display_name} sudah punya orang tua.")
            return
            
        if uid1 not in fam_data: fam_data[uid1] = {}
        if uid2 not in fam_data: fam_data[uid2] = {}
        
        children = fam_data[uid1].get('children', [])
        max_children = 15 if message.author.premium_since else 6
        if len(children) >= max_children:
            await send_msg_embed(message.channel, f"❌ Keluarga kamu sudah kepenuhan (Maksimal {max_children} anak).")
            return

        await send_msg_embed(message.channel, f"👶 {message.author.mention} ingin mengadopsi {target.mention} sebagai anak. Ketik `mau` atau `ngga` (60 dtk).")

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
                        
                await save_json(FAMILY_FILE, fam_data)
                await send_msg_embed(message.channel, f"🍼 **SAH!** {target.mention} sekarang adalah anak dari {message.author.mention}.")
            else:
                await send_msg_embed(message.channel, "👶 Adopsi ditolak.")
        except asyncio.TimeoutError:
            await send_msg_embed(message.channel, "⏱️ Waktu habis. Adopsi batal.")

    if message.content.startswith('w2e leave'):
        uid = str(message.author.id)
        fam_data = await load_json(FAMILY_FILE)
        parent_id = fam_data.get(uid, {}).get('parent')
        
        if not parent_id:
            await send_msg_embed(message.channel, "❌ Kamu bukan anak siapa-siapa.")
            return
            
        fam_data[uid]['parent'] = None
        # Hapus dari semua daftar anak
        for k, v in fam_data.items():
            if 'children' in v and uid in v['children']:
                v['children'].remove(uid)
                
        await save_json(FAMILY_FILE, fam_data)
        await send_msg_embed(message.channel, f"🚪 **MABUR!** {message.author.mention} kabur dari rumah dan bukan anak siapa-siapa lagi.")

    if message.content.startswith('w2e family'):
        target = message.mentions[0] if message.mentions else message.author
        if not PILLOW_AVAILABLE:
            await send_msg_embed(message.channel, "🖼️ Modul pembuat gambar tidak tersedia. Info keluarga hanya via database (hubungi dev).")
            return
            
        await send_msg_embed(message.channel, f"📸 Sedang memotret keluarga **{target.display_name}**...")
        img_buf = await generate_family_image(message.guild, target.id)
        if img_buf:
            file = discord.File(fp=img_buf, filename="family_tree.png")
            await send_msg_embed(message.channel, file=file)
        else:
            await send_msg_embed(message.channel, "❌ Terjadi kesalahan saat membuat foto keluarga.")

    if message.content.startswith('w2e image'):
        if not message.author.premium_since:
            await send_msg_embed(message.channel, "❌ Maaf, fitur AI Image Generation HANYA tersedia untuk **Server Booster**! 👑")
            return
            
        prompt = message.content[len('w2e image'):].strip()
        if not prompt:
            await send_msg_embed(message.channel, "Format: `!w2eimage <deskripsi gambar>`\nContoh: `!w2eimage a cute cat playing guitar in cyberpunk city`")
            return
            
        import urllib.parse
        encoded_prompt = urllib.parse.quote(prompt)
        # Tambahkan param random untuk mencegah cache jika prompt sama
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?nologo=true&seed={random.randint(1,100000)}"
        
        embed = discord.Embed(title="🎨 AI Image Generator", description=f"**Prompt:** {prompt}\n*Powered by Pollinations.ai*", color=discord.Color.purple())
        embed.set_image(url=url)
        embed.set_footer(text=f"Requested by {message.author.display_name} (Booster Exclusive)", icon_url=message.author.display_avatar.url if message.author.display_avatar else None)
        
        await send_msg_embed(message.channel, embed=embed)

    # ── Community & Engagement ───────────────────────────────────────────────
    if message.content.startswith('w2e poll'):
        parts = message.content[len('w2e poll'):].strip().split('|')
        if len(parts) < 2:
            await send_msg_embed(message.channel, "Format: `!w2epoll Pertanyaan | Opsi 1 | Opsi 2 | ...`")
            return
            
        question = parts[0].strip()
        options = [opt.strip() for opt in parts[1:]]
        
        if len(options) > 10:
            await send_msg_embed(message.channel, "❌ Maksimal 10 opsi untuk polling.")
            return
            
        emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
        
        desc = ""
        for i, opt in enumerate(options):
            desc += f"{emojis[i]} {opt}\n\n"
            
        embed = discord.Embed(title=f"📊 {question}", description=desc, color=discord.Color.blue())
        embed.set_footer(text=f"Polling dibuat oleh {message.author.display_name}")
        
        poll_msg = await send_msg_embed(message.channel, embed=embed)
        for i in range(len(options)):
            await poll_msg.add_reaction(emojis[i])

    if message.content.startswith('w2e giveaway'):
        parts = message.content.split()
        if len(parts) < 4:
            await send_msg_embed(message.channel, "Format: `!w2egiveaway <waktu_menit> <hadiah>`")
            return
            
        try:
            mins = int(parts[2])
            prize = " ".join(parts[3:])
        except ValueError:
            await send_msg_embed(message.channel, "Format waktu harus angka (menit).")
            return
            
        embed = discord.Embed(title="🎉 **GIVEAWAY!** 🎉", description=f"**Hadiah:** {prize}\n**Berakhir dalam:** {mins} menit\n\nReact dengan 🎉 untuk ikutan!", color=discord.Color.gold())
        embed.set_footer(text=f"Giveaway dari {message.author.display_name}")
        ga_msg = await send_msg_embed(message.channel, embed=embed)
        await ga_msg.add_reaction("🎉")
        
        # Async wait
        await asyncio.sleep(mins * 60)
        
        # Fetch latest message state
        new_msg = await message.channel.fetch_message(ga_msg.id)
        reaction = discord.utils.get(new_msg.reactions, emoji="🎉")
        
        users = [user async for user in reaction.users() if not user.bot]
        if not users:
            await send_msg_embed(message.channel, f"Yah, gak ada yang ikut giveaway **{prize}** 😢")
            return
            
        winner = random.choice(users)
        await send_msg_embed(message.channel, f"🎊 Selamat {winner.mention}! Kamu memenangkan **{prize}** dari {message.author.mention}! 🎊")

    if message.content.startswith('w2e quiz'):
        uid = str(message.author.id)
        stat = await get_discord_stat(uid)
        
        if stat['coins'] < 50:
            await send_msg_embed(message.channel, "❌ Biaya main kuis adalah 50 Koin. Uangmu gak cukup.")
            return
            
        stat['coins'] -= 50
        await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
        await send_msg_embed(message.channel, "🤔 **Mencari soal yang sulit...**")
        prompt = "Berikan SATU pertanyaan pengetahuan umum singkat dan jawabannya dalam satu kata. Format: Pertanyaan | Jawaban. Jangan ada teks tambahan."
        try:
            response = await asyncio.to_thread(gemini_client.models.generate_content, model='gemini-2.5-flash', contents=prompt)
            res_text = response.text.strip()
            if '|' not in res_text: raise ValueError
            q, a = res_text.split('|')
            q = q.strip()
            a = a.strip().lower()
        except Exception:
            await send_msg_embed(message.channel, "Gagal mengambil kuis dari AI. Koin dikembalikan.")
            stat['coins'] += 50
            await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            return
            
        await send_msg_embed(message.channel, f"🎯 **KUIS W2E** 🎯\n{q}\n\n*Jawab dalam 30 detik! Hadiah: 200 Koin! (-50 Koin modal)*")
        
        def check(m):
            return m.channel == message.channel and not m.author.bot
            
        try:
            # Tunggu siapa saja yang jawab benar duluan
            start_time = datetime.now()
            while (datetime.now() - start_time).seconds < 30:
                msg = await client.wait_for('message', timeout=30.0, check=check)
                if msg.content.lower().strip() == a:
                    winner_uid = str(msg.author.id)
                    w_stat = await get_discord_stat(winner_uid)
                    w_stat['coins'] += 200
                    await update_discord_stat(winner_uid, msg.author.display_name, w_stat['coins'], w_stat['xp'], w_stat['level'], w_stat['lastDaily'])
                    await send_msg_embed(message.channel, f"✅ **BENAR!** {msg.author.mention} menjawab **{a.upper()}** dan memenangkan 200 Koin!")
                    return
        except asyncio.TimeoutError:
            pass
            
        await send_msg_embed(message.channel, f"⏱️ Waktu habis! Jawaban yang benar adalah: **{a.upper()}**")

    # ── Fun & Hiburan ────────────────────────────────────────────────────────
    if message.content.startswith('w2e shipper'):
        if len(message.mentions) < 1:
            await send_msg_embed(message.channel, "Format: `!w2eshipper @user1 [@user2]`")
            return
            
        user1 = message.author
        user2 = message.mentions[0]
        if len(message.mentions) >= 2:
            user1 = message.mentions[0]
            user2 = message.mentions[1]
            
        if user1 == user2:
            await send_msg_embed(message.channel, "❌ Jomblo ngenes banget nge-ship diri sendiri...")
            return
            
        # Consistent random based on ID
        seed = int(user1.id) + int(user2.id)
        random.seed(seed)
        match_pct = random.randint(0, 100)
        random.seed() # reset
        
        await send_msg_embed(message.channel, f"❤️ Menerawang kecocokan cinta **{user1.display_name}** & **{user2.display_name}**...")
        
        prompt = f"Buatkan ramalan cinta super singkat dan lucu (bisa sarkas atau romantis) untuk dua orang dengan tingkat kecocokan {match_pct}%. Gunakan bahasa gaul anak discord Indonesia (lo-gue, santai, kocak). JANGAN ada basa-basi khas AI seperti 'Ini dia...' atau 'Semoga...'. Langsung ke ramalannya secara natural."
        try:
            response = await asyncio.to_thread(gemini_client.models.generate_content, model='gemini-2.5-flash', contents=prompt)
            desc = response.text.strip()
            
            if PILLOW_AVAILABLE:
                img_buf = await generate_love_image(user1, user2, match_pct)
                if img_buf:
                    file = discord.File(fp=img_buf, filename="love.png")
                    embed = discord.Embed(title="💖 W2E Shipper 💖", description=f"**{user1.display_name}** x **{user2.display_name}**\n\n{desc}", color=discord.Color.brand_red())
                    embed.set_image(url="attachment://love.png")
                    await send_msg_embed(message.channel, embed=embed, file=file)
                    return

            embed = discord.Embed(title="💖 W2E Shipper 💖", description=f"**{user1.display_name}** x **{user2.display_name}**\n\n**Kecocokan: {match_pct}%**\n\n{desc}", color=discord.Color.brand_red())
            await send_msg_embed(message.channel, embed=embed)
        except Exception as e:
            logging.error(f"Error in prefix shipper command: {e}")
            await send_msg_embed(message.channel, f"**Kecocokan: {match_pct}%**\n(API/Render Error: Gagal generate ramalan).")


    if message.content.startswith('w2e roast'):
        if not message.mentions:
            await send_msg_embed(message.channel, "Mau roast siapa? `!w2eroast @user`")
            return
        target = message.mentions[0]
        
        roles = [r.name for r in getattr(target, 'roles', []) if r.name != "@everyone"]
        roles_str = ", ".join(roles) if roles else "Gak punya role/Polosan"
        created_date = target.created_at.strftime("%Y") if getattr(target, 'created_at', None) else "Tidak diketahui"
        avatar_desc = "Default" if not target.display_avatar else "Custom"
        
        discord_info = f"Nama: {target.display_name}, Akun dibuat: {created_date}, Roles: {roles_str}, Avatar: {avatar_desc}"
        
        await send_msg_embed(message.channel, f"🔥 Sedang menyiapkan panggangan untuk profil Discord **{target.display_name}**...")
        prompt = f"Roast / hina dengan candaan profil Discord orang ini:\n{discord_info}\n(Jangan kelewatan batas SARA). Gunakan bahasa gaul tongkrongan indo yang pedas, savage, dan lucu. JANGAN pakai bahasa baku khas AI, JANGAN ada basa-basi di awal/akhir seperti 'Tentu, ini dia...' atau 'Semoga terhibur'. Langsung tembak dengan hinaan kocak dan natural."
        try:
            response = await asyncio.to_thread(gemini_client.models.generate_content, model='gemini-2.5-flash', contents=prompt)
            await send_msg_embed(message.channel, f"{target.mention} 🔥\n{response.text.strip()}")
        except Exception:
            await send_msg_embed(message.channel, "Tungku roasting sedang rusak (API Error).")

    if message.content.startswith('w2e chat '):
        chat_msg = message.content[len('!w2echat '):].strip()
        if not chat_msg:
            await send_msg_embed(message.channel, "Mau ngomong apa? `!w2echat halo bot`")
            return
            
        await message.channel.typing()
        prompt = f"Anda adalah bot Discord bernama W2E. Kepribadian Anda adalah teman tongkrongan yang asik, sedikit sarkas, suka bercanda, tapi selalu membantu. Gunakan bahasa gaul Indonesia (lo, gue, bro, cuy, wkwk). Jawab pesan berikut dengan singkat dan padat. JANGAN ada basa-basi formal khas AI, langsung jawab seperti manusia di chat Discord:\nUser ({message.author.display_name}) bilang: {chat_msg}"
        try:
            response = await asyncio.to_thread(gemini_client.models.generate_content, model='gemini-2.5-flash', contents=prompt)
            await send_msg_embed(message, response.text.strip(), reply=True)
        except Exception:
            await send_msg_embed(message.channel, "Lagi males mikir nih (API Error).")

    if message.content.startswith('w2e rate'):
        target = message.mentions[0] if message.mentions else message.author
        
        roles = [r.name for r in getattr(target, 'roles', []) if r.name != "@everyone"]
        roles_str = ", ".join(roles) if roles else "Gak punya role/Polosan"
        created_date = target.created_at.strftime("%Y") if getattr(target, 'created_at', None) else "Tidak diketahui"
        joined_date = getattr(target, 'joined_at', None)
        joined_str = joined_date.strftime("%Y") if joined_date else "Tidak diketahui"
        is_booster = "Sultan Booster" if getattr(target, 'premium_since', None) else "Member biasa"
        avatar_desc = "Avatar default" if not target.display_avatar else "Custom avatar"
        
        profile_data = f"Nama: {target.display_name}\nAkun dibuat: {created_date}\nJoin server: {joined_str}\nStatus: {is_booster}\nRoles: {roles_str}\nAvatar: {avatar_desc}"
        
        await send_msg_embed(message.channel, f"🧐 Sedang membedah profil Discord **{target.display_name}**...")
        prompt = f"Berikan rating profil (1-10) dan roasting/pujian yang lucu ala komentator (bahasa gaul indo) untuk profil Discord ini:\n{profile_data}\n\nBuat singkat aja, 2-3 kalimat max. Gunakan gaya bahasa santai banget, JANGAN formal, JANGAN pake template tulisan khas AI."
        
        try:
            response = await asyncio.to_thread(gemini_client.models.generate_content, model='gemini-2.5-flash', contents=prompt)
            
            embed = discord.Embed(title=f"📈 AI Profile Rating: {target.display_name}", description=response.text.strip(), color=discord.Color.teal())
            if target.display_avatar:
                embed.set_thumbnail(url=target.display_avatar.url)
            await send_msg_embed(message.channel, embed=embed)
        except Exception:
            await send_msg_embed(message.channel, "Gagal merating profil (API Error).")

    if message.content.startswith('w2e birthday set'):
        parts = message.content.split()
        if len(parts) < 4:
            await send_msg_embed(message.channel, "Format: `!w2ebirthday set DD-MM` (Contoh: `!w2ebirthday set 25-12`)")
            return
            
        bday_str = parts[3]
        try:
            # Validate
            datetime.strptime(bday_str, "%d-%m")
            
            bdays = await load_json('birthdays.json')
            bdays[str(message.author.id)] = bday_str
            await save_json('birthdays.json', bdays)
            await send_msg_embed(message.channel, "🎂 Tanggal lahirmu berhasil disimpan! Kamu akan dapat kejutan di hari H!")
        except ValueError:
            await send_msg_embed(message.channel, "❌ Format salah! Gunakan DD-MM (Tanggal-Bulan).")

    if message.content.startswith('w2e valo '):
        target = message.content[len('!w2evalo '):].strip()
        if target:
            await send_msg_embed(message.channel, f"🔍 Sedang menerawang stats Valorant untuk **{target}**...")
            prompt = f"Buatlah statistik Valorant palsu dan lucu untuk pemain bernama '{target}'. Cantumkan Rank (yang aneh/rendah), Win Rate (jelek), dan Senjata Andalan yang tidak masuk akal. Buat singkat seperti report dalam bahasa gaul tongkrongan. JANGAN ada basa-basi AI."
            try:
                response = await asyncio.to_thread(gemini_client.models.generate_content, model='gemini-2.5-flash', contents=prompt)
                await send_msg_embed(message.channel, response.text)
            except Exception:
                await send_msg_embed(message.channel, "API error saat mencari stat Valorant.")
        return

    if message.content.startswith('w2e listen'):
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
                await send_msg_embed(message.channel, "🎙️ **Merekam obrolan selama 10 detik...** Mulai bicara!")
                await asyncio.sleep(10)
                if vc.recording:
                    vc.stop_recording()
            except Exception as e:
                await send_msg_embed(message.channel, f"Error memulai recording: {str(e)}\nPastikan sudah menggunakan **Pycord** (`pip install py-cord[voice]`).")
        else:
            await send_msg_embed(message.channel, "Kamu harus berada di voice channel terlebih dahulu.")
        return

    if message.content.startswith('w2e remindme '):
        parts = message.content.split()
        if len(parts) < 4:
            await send_msg_embed(message.channel, "Format: `!w2eremindme <menit> <pesan>`")
            return
        try:
            minutes = float(parts[2])
            msg_text = message.content.split(None, 3)[3]
            await send_msg_embed(message.channel, f"⏰ Siap! Aku akan mengingatkanmu tentang **{msg_text}** dalam {minutes} menit.")
            
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
            await send_msg_embed(message.channel, "Format menit harus berupa angka.")
        return

    if message.content.startswith('w2e checkmusic') or message.content.startswith('w2e checkbots'):
        if not message.guild:
            await send_msg_embed(message.channel, "❌ Perintah ini hanya bisa digunakan di dalam server.")
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
            await send_msg_embed(message.channel, embed=embed)
        else:
            await send_msg_embed(message.channel, "ℹ️ Tidak ada bot musik yang sedang aktif di Voice Channel saat ini.")
        return

    if message.content.startswith('w2e profile'):
        uid = str(message.author.id)
        stat = await get_discord_stat(uid)
        
        items_data = await load_json(ITEMS_FILE).get(uid, {})
        bg_url = items_data.get('bg_url')
        
        if PILLOW_AVAILABLE:
            await send_msg_embed(message.channel, "🖼️ Sedang memuat profil card...")
            img_buf = await generate_profile_image(message.author, stat, bg_url)
            if img_buf:
                file = discord.File(fp=img_buf, filename="profile.png")
                await send_msg_embed(message.channel, file=file)
                return
                
        # Fallback text
        res = f"**User Profile - {message.author.display_name}**\n"
        res += f"🏅 **Level:** {stat['level']} | ⚡ **XP:** {stat['xp']}/{stat['level']*100}\n"
        res += f"💰 **Koin:** {stat['coins']}\n\n"
        await send_msg_embed(message.channel, res)

    if message.content.startswith('w2e bg'):
        if not message.author.premium_since:
            await send_msg_embed(message.channel, "❌ Custom Background Profil cuma buat **Server Booster**! 👑")
            return
            
        parts = message.content.split()
        if len(parts) < 3:
            await send_msg_embed(message.channel, "Format: `!w2ebg <URL_GAMBAR>`\nContoh: `!w2ebg https://example.com/image.jpg`")
            return
            
        bg_url = parts[2]
        if not bg_url.startswith('http'):
            await send_msg_embed(message.channel, "❌ URL tidak valid.")
            return
            
        uid = str(message.author.id)
        items_data = await load_json(ITEMS_FILE)
        if uid not in items_data: items_data[uid] = {}
        items_data[uid]['bg_url'] = bg_url
        await save_json(ITEMS_FILE, items_data)
        
        await send_msg_embed(message.channel, "✅ Background profil berhasil diupdate! Cek dengan `!profile`")

    if message.content.startswith('w2e setpersona '):
        persona = message.content[len('!setpersona '):].strip()
        uid = str(message.author.id)
        personas = await load_json(PERSONAS_FILE)
        
        if persona.lower() == 'reset' or persona.lower() == 'hapus':
            if uid in personas:
                del personas[uid]
                await save_json(PERSONAS_FILE, personas)
            if uid in chat_sessions:
                del chat_sessions[uid] # Reset memory so persona takes effect immediately
            await send_msg_embed(message.channel, "✅ Persona AI kamu telah direset ke default.")
            return
            
        personas[uid] = persona
        await save_json(PERSONAS_FILE, personas)
        if uid in chat_sessions:
            del chat_sessions[uid] # Reset history to force new persona
        
        await send_msg_embed(message.channel, f"🎭 Berhasil! Gemini AI sekarang akan membalasmu dengan persona: **{persona}**\nCoba chat pakai `!ai Halo!`")

    if message.content.startswith('w2e bj '):
        uid = str(message.author.id)
        stat = await get_discord_stat(uid)
        
        try:
            bet = int(message.content.split()[2])
            if bet < 50:
                await send_msg_embed(message.channel, "❌ Minimal taruhan Blackjack adalah 50 Koin.")
                return
            if stat['coins'] < bet:
                await send_msg_embed(message.channel, "❌ Koin kamu tidak cukup!")
                return
        except (IndexError, ValueError):
            await send_msg_embed(message.channel, "Format: `!w2ebj <jumlah_taruhan>`")
            return
            
        stat['coins'] -= bet
        await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        
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
            await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            await send_msg_embed(message.channel, f"🃏 **BLACKJACK!** 🃏\nKartu kamu: {player_hand} (21)\nKamu langsung menang **{win_amount} Koin**!")
            return
            
        embed = discord.Embed(title="🃏 W2E Blackjack Casino", color=discord.Color.red())
        embed.add_field(name=f"Pemain ({player_score})", value=str(player_hand), inline=True)
        embed.add_field(name="Bandar", value=f"[{dealer_hand[0]}, ?]", inline=True)
        embed.set_footer(text="Ketik 'hit' untuk tambah kartu, atau 'stand' untuk bertahan.")
        
        msg = await send_msg_embed(message.channel, embed=embed)
        
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
                        await send_msg_embed(message.channel, embed=embed)
                        return
                    else:
                        embed.set_field_at(0, name=f"Pemain ({player_score})", value=str(player_hand), inline=True)
                        await send_msg_embed(message.channel, embed=embed)
                else:
                    playing = False
            except asyncio.TimeoutError:
                await send_msg_embed(message.channel, "⏳ Waktu habis! Kamu otomatis Stand.")
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
            
        await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
        await send_msg_embed(message.channel, embed=embed)

    if message.content.startswith('w2e attack'):
        boss_data = await load_json(BOSS_FILE)
        if not boss_data.get('active', False):
            await send_msg_embed(message.channel, "❌ Tidak ada Boss yang sedang aktif saat ini.")
            return
            
        uid = str(message.author.id)
        # Cek cooldown 30 detik
        if uid in boss_cooldowns:
            delta = datetime.now() - boss_cooldowns[uid]
            if delta.total_seconds() < 30:
                await send_msg_embed(message.channel, f"⏳ Senjatamu masih *cooldown*! Tunggu {int(30 - delta.total_seconds())} detik lagi.")
                return
                
        boss_cooldowns[uid] = datetime.now()
        
        damage = random.randint(50, 300)
        boss_data['hp'] -= damage
        
        if boss_data['hp'] <= 0:
            boss_data['active'] = False
            await save_json(BOSS_FILE, boss_data)
            # Ambil dari kas server
            treasury = await load_json(TREASURY_FILE)
            if not treasury: treasury = {'balance': 0}
            balance = treasury.get('balance', 0)
            
            reward = 5000
            if balance < reward:
                reward = max(1000, balance) # Kasih seadanya, minimal 1000
                
            if balance >= reward:
                treasury['balance'] -= reward
            else:
                treasury['balance'] = 0
            await save_json(TREASURY_FILE, treasury)
            
            stat = await get_discord_stat(uid)
            stat['coins'] += reward
            await update_discord_stat(uid, message.author.display_name, stat['coins'], stat['xp'], stat['level'], stat['lastDaily'])
            
            await send_msg_embed(message.channel, f"💥 **FATAL BLOW!** 💥\n{message.author.mention} berhasil memberikan serangan terakhir sebesar **{damage} DMG** dan membunuh **{boss_data['name']}**!\n🎉 Hadiah pembunuh: **{reward} Koin RPG!** (Diambil dari Kas Server)")
        else:
            await save_json(BOSS_FILE, boss_data)
            await send_msg_embed(message.channel, f"⚔️ {message.author.mention} menyerang **{boss_data['name']}** sebesar **{damage} DMG**! (Sisa HP Boss: {boss_data['hp']}/{boss_data['max_hp']})")




async def send_msg_embed(target, *args, reply=False, **kwargs):
    content = kwargs.pop('content', None)
    if args:
        content = args[0]
        args = args[1:]
        
    func = target.reply if reply else target.send
        
    if 'embed' in kwargs or 'embeds' in kwargs or not content:
        if content:
            return await func(content, *args, **kwargs)
        return await func(*args, **kwargs)
        
    text = str(content)
    color = discord.Color.blurple()
    t_lower = text.lower()
    if "❌" in text or "kalah" in t_lower or "busted" in t_lower or "gagal" in t_lower or "hangus" in t_lower or "hilang" in t_lower:
        color = discord.Color.red()
    elif "✅" in text or "menang" in t_lower or "berhasil" in t_lower or "selamat" in t_lower or "claimed" in t_lower:
        color = discord.Color.green()
    elif "💰" in text or "koin" in t_lower or "market" in t_lower or "gacha" in t_lower or "box" in t_lower:
        color = discord.Color.gold()
        
    embed = discord.Embed(description=text, color=color)
    return await func(embed=embed, *args, **kwargs)


async def send_embed(interaction, text, color=None, title=None, ephemeral=False, view=None):
    if color is None:
        t_lower = text.lower()
        if "❌" in text or "kalah" in t_lower or "busted" in t_lower or "gagal" in t_lower or "hangus" in t_lower or "hilang" in t_lower:
            color = discord.Color.red()
        elif "✅" in text or "menang" in t_lower or "berhasil" in t_lower or "selamat" in t_lower or "claimed" in t_lower or "berkah" in t_lower:
            color = discord.Color.green()
        elif "💰" in text or "koin" in t_lower or "market" in t_lower or "gacha" in t_lower or "box" in t_lower or "jual" in t_lower or "beli" in t_lower:
            color = discord.Color.gold()
        elif "💍" in text or "keluarga" in t_lower or "menikah" in t_lower or "cerai" in t_lower or "adopsi" in t_lower:
            color = discord.Color.purple()
        else:
            color = discord.Color.blurple()

    embed = discord.Embed(description=text, color=color)
    if title:
        embed.title = title
    embed.set_footer(text="W2E Official Bot")
    try:
        if interaction.user:
            icon_url = interaction.user.display_avatar.url if interaction.user.display_avatar else None
            embed.set_author(name=interaction.user.display_name, icon_url=icon_url)
    except:
        pass
        
    kwargs = {'embed': embed}
    if view: kwargs['view'] = view
    if ephemeral: kwargs['ephemeral'] = True

    try:
        if interaction.response.is_done():
            return await interaction.followup.send(**kwargs)
        else:
            return await interaction.response.send_message(**kwargs)
    except Exception as e:
        print(f"Embed send error: {e}")

# ============================================================================
# SLASH COMMANDS (APP COMMANDS)

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    logging.error(f'App Command Error: {error}')
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f'❌ Terjadi kesalahan saat menjalankan perintah: {str(error)}', ephemeral=True)
        else:
            await interaction.response.send_message(f'❌ Terjadi kesalahan saat menjalankan perintah: {str(error)}', ephemeral=True)
    except:
        pass


# ============================================================================

@client.event
async def on_guild_join(guild):
    if guild.id != ALLOWED_SERVER_ID:
        logging.warning(f"Invited to unauthorized server {guild.name}. Leaving automatically.")
        await guild.leave()



from discord.ext import tasks
import time

@tasks.loop(minutes=30)
async def clean_caches():
    now = datetime.now()
    # clean voice_join_times
    expired_voice = [k for k, v in voice_join_times.items() if (now - v).total_seconds() > 3600]
    for k in expired_voice: del voice_join_times[k]
    
    # rob_cooldowns
    expired_rob = [k for k, v in rob_cooldowns.items() if v < now]
    for k in expired_rob: del rob_cooldowns[k]
    
    # boss_cooldowns
    expired_boss = [k for k, v in boss_cooldowns.items() if v < now]
    for k in expired_boss: del boss_cooldowns[k]
    
    # work_cooldowns
    expired_work = [k for k, v in work_cooldowns.items() if v < now]
    for k in expired_work: del work_cooldowns[k]


# ── PREFIX COMMAND SYSTEM (FakeInteraction) ──────────────────────────────────
class FakeResponse:
    def __init__(self, message):
        self.message = message
    def is_done(self):
        return True
    async def defer(self, ephemeral=False, thinking=False):
        pass

class FakeFollowup:
    def __init__(self, message):
        self.message = message
    async def send(self, *args, **kwargs):
        # Remove ephemeral from kwargs since normal send doesn't support it
        kwargs.pop("ephemeral", None)
        return await self.message.channel.send(*args, **kwargs)

class FakeInteraction:
    def __init__(self, message):
        self.message = message
        self.user = message.author
        self.guild = message.guild
        self.channel = message.channel
        self.response = FakeResponse(message)
        self.followup = FakeFollowup(message)
    
    # Meniru fungsi-fungsi Interaction dasar yang sering dipakai
    @property
    def client(self):
        return client

    async def send(self, *args, **kwargs):
        kwargs.pop("ephemeral", None)
        return await self.message.channel.send(*args, **kwargs)

        
@client.event
async def on_message(message):
    if message.author.bot:
        return

    # Auto-read prefix commands
    if message.content.startswith(BOT_PREFIX):
        parts = message.content[len(BOT_PREFIX):].strip().split()
        if not parts:
            return
            
        cmd_name = parts[0].lower()
        args_list = parts[1:]
        
        # Check if the command exists in the CommandTree
        cmd = tree.get_command(cmd_name)
        if cmd:
            interaction = FakeInteraction(message)
            
            # Sangat basic argument parsing (untuk command yg butuh target dll)
            # Karena argumen slash command memiliki typing, kita lewati validasi dan passing string mentah 
            # untuk diatasi oleh fallback code atau biarkan bot mencoba parsing sendiri.
            
            # We must use kwargs based on function signature if possible, or just pass args for text
            # However, app_commands callback signatures are strict.
            import inspect
            sig = inspect.signature(cmd.callback)
            
            kwargs = {}
            params = list(sig.parameters.values())[1:] # Skip interaction
            
            try:
                for i, param in enumerate(params):
                    if i < len(args_list):
                        val = args_list[i]
                        
                        # Parsing primitive types
                        if param.annotation == int:
                            val = int(val)
                        elif param.annotation == float:
                            val = float(val)
                        elif param.annotation == discord.Member:
                            # Parse <@id> or <@!id>
                            match = re.match(r'<@!?([0-9]+)>', val)
                            if match:
                                user_id = int(match.group(1))
                                val = message.guild.get_member(user_id)
                                if not val:
                                    val = await message.guild.fetch_member(user_id)
                            else:
                                # Not a mention, maybe an ID?
                                try:
                                    val = message.guild.get_member(int(val))
                                except ValueError:
                                    pass
                        elif param.annotation == discord.Role:
                            match = re.match(r'<@&([0-9]+)>', val)
                            if match:
                                role_id = int(match.group(1))
                                val = message.guild.get_role(role_id)
                        
                        kwargs[param.name] = val
                    else:
                        break
                        
                await cmd.callback(interaction, **kwargs)
            except Exception as e:
                logging.error(f"Error executing prefix command !{cmd_name}: {e}")
                await message.channel.send(f"❌ Error mengeksekusi perintah: `{e}`")
                
    # Lanjutkan memproses on_message (jika ada AI chat listener dsb nanti)
