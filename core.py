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
import hmac

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
DASHBOARD_TOKEN = os.getenv('DASHBOARD_TOKEN', '')
# Comma-separated origins yang boleh akses API (mis. web main way2eternal).
# Kosong = izinkan semua (dev only). Wajib diisi kalau web main di domain lain.
ALLOWED_ORIGINS = [o.strip() for o in os.getenv('ALLOWED_ORIGINS', '').split(',') if o.strip()]

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


async def adjust_coins(uid, delta, display_name=None):
    # Atomic coin delta — avoids the read-modify-write race where two concurrent
    # commands read the same balance and the last writer wins. Clamps at 0.
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO DiscordStat (id, displayName, coins, updatedAt) VALUES (?, ?, MAX(0, ?), ?) "
                "ON CONFLICT(id) DO UPDATE SET coins = MAX(0, coins + ?), "
                "displayName = COALESCE(?, displayName), updatedAt = ?",
                (str(uid), display_name or str(uid), delta, now, delta, display_name, now))
            await db.commit()
    except Exception as e:
        logging.error(f"DB Error adjust_coins: {e}")






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


ANNOUNCE_CATEGORIES = ['market', 'levelup', 'birthday', 'boss', 'booster', 'binomo']

def _load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def _find_fallback_channel(guild):
    # Logika lama: cari channel general/chat, kalau gagal ambil channel pertama yang writable.
    for ch in guild.text_channels:
        if 'general' in ch.name.lower() or 'chat' in ch.name.lower():
            if ch.permissions_for(guild.me).send_messages:
                return ch
    for ch in guild.text_channels:
        if ch.permissions_for(guild.me).send_messages:
            return ch
    return None

def get_announce_channel(guild, category):
    # Resolusi: announce_channels[category] -> announce_channels[default] -> fallback lama.
    # Mengembalikan channel yang writable, atau None.
    cfg = _load_config()
    announce = cfg.get('announce_channels', {}) if isinstance(cfg, dict) else {}

    candidates = []
    if category:
        candidates.append(announce.get(category))
    candidates.append(announce.get('default'))
    # Kompatibilitas: key lama booster_channel_id untuk kategori booster
    if category == 'booster':
        candidates.append(cfg.get('booster_channel_id'))

    for cid in candidates:
        if not cid:
            continue
        try:
            ch = guild.get_channel(int(cid))
        except (ValueError, TypeError):
            ch = None
        if ch and ch.permissions_for(guild.me).send_messages:
            return ch

    return _find_fallback_channel(guild)

async def check_birthdays():
    await client.wait_until_ready()
    while not client.is_closed():
        today_str = datetime.now().strftime("%d-%m")
        bdays = await load_json('birthdays.json')
        
        # We need a channel to announce birthdays.
        for guild in client.guilds:
            announce_channel = get_announce_channel(guild, 'birthday')

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
                        user = client.get_user(int(uid))
                        name = user.display_name if user else f"User {uid}"
                        await adjust_coins(uid, 1000, name)
                        
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
                ch = get_announce_channel(guild, 'market')
                if ch:
                    client.loop.create_task(ch.send(event_message))
                            
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
                    await adjust_coins(uid, winnings, f"User_{uid}")
                    results.append(f"<@{uid}> **MENANG {winnings} Koin!** (Tebak {symbol} {direction} | Entry: {entry_price}, Now: {new_price})")
                else:
                    results.append(f"<@{uid}> **RUGI {bet_amount} Koin!** (Tebak {symbol} {direction} | Entry: {entry_price}, Now: {new_price})")
                
                del binomo[uid]
            await save_json(BINOMO_FILE, binomo)
            
            if results:
                result_str = "🎰 **HASIL JUDI BINOMO 10 MENIT INI:** 🎰\n" + "\n".join(results)
                for guild in client.guilds:
                    ch = get_announce_channel(guild, 'binomo')
                    if ch:
                        client.loop.create_task(ch.send(result_str))
                            
        await asyncio.sleep(600) # Every 10 minutes

async def voice_salary_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(600) # Wait 10 minutes
        for guild in client.guilds:
            # Channel pengumuman level-up dari VC
            announce_channel = get_announce_channel(guild, 'levelup')

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
                    ch = get_announce_channel(guild, 'boss')
                    if ch:
                        client.loop.create_task(
                            ch.send(f"⚠️ **BOSS RAID EVENT DIMULAI!** ⚠️\n**{boss_data['name']}** telah muncul dengan {boss_data['hp']} HP!\nKetik `!attack` untuk menyerang! Yang berhasil membunuhnya mendapat hadiah 5000 Koin!")
                        )
                                
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
    origin = request.headers.get('Origin')
    if ALLOWED_ORIGINS:
        if origin in ALLOWED_ORIGINS:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Vary'] = 'Origin'
    else:
        # Dev mode: tidak ada whitelist, izinkan semua.
        response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Auth-Token'
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

def require_token(request):
    # Returns True if the request carries a valid X-Auth-Token. If DASHBOARD_TOKEN
    # is unset, all access is denied (fail closed) to avoid an open write surface.
    if not DASHBOARD_TOKEN:
        return False
    supplied = request.headers.get('X-Auth-Token', '')
    return hmac.compare_digest(supplied, DASHBOARD_TOKEN)

async def api_broadcast(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
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
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    try:
        data = await request.json()
        with open('config.json', 'w') as f:
            json.dump(data, f)
        return web.json_response({'status': 'success'})
    except Exception as e:
        return web.json_response({'status': 'error', 'msg': str(e)}, status=500)

async def api_channels(request):
    # Daftar text channel guild untuk dropdown di dashboard / web main.
    guild = client.get_guild(ALLOWED_SERVER_ID)
    if not guild:
        return web.json_response({'error': 'Bot is not in the allowed server'}, status=404)
    channels = [{'id': str(c.id), 'name': c.name} for c in guild.text_channels]
    return web.json_response(channels)

async def get_announce_config_api(request):
    cfg = _load_config()
    announce = cfg.get('announce_channels', {}) if isinstance(cfg, dict) else {}
    # Pastikan semua kategori hadir (default + 6) supaya client gampang render.
    result = {'default': announce.get('default', '')}
    for cat in ANNOUNCE_CATEGORIES:
        result[cat] = announce.get(cat, '')
    return web.json_response(result)

async def update_announce_config_api(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    try:
        data = await request.json()
        allowed = ['default'] + ANNOUNCE_CATEGORIES
        announce = {}
        for key in allowed:
            val = data.get(key, '')
            if val is None:
                val = ''
            val = str(val).strip()
            # Hanya terima channel ID berupa digit, atau string kosong (= pakai fallback).
            if val and not val.isdigit():
                return web.json_response({'error': f'Invalid channel id for {key}'}, status=400)
            announce[key] = val
        cfg = _load_config()
        if not isinstance(cfg, dict):
            cfg = {}
        cfg['announce_channels'] = announce
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(cfg, f)
        return web.json_response({'status': 'success', 'announce_channels': announce})
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
    app.router.add_get('/api/channels', api_channels)
    app.router.add_get('/api/announce-config', get_announce_config_api)
    app.router.add_post('/api/announce-config', update_announce_config_api)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8081)
    await site.start()
    logging.info("Bot API started on port 8081")
    if not DASHBOARD_TOKEN:
        logging.warning("DASHBOARD_TOKEN is not set — /api/broadcast and POST /api/config are disabled (fail closed). Set DASHBOARD_TOKEN to enable them.")

@client.event
async def on_voice_state_update(member, before, after):
    if before.channel is None and after.channel is not None:
        voice_join_times[member.id] = datetime.now()
        # 👑 Booster Voice Intro

        if member.premium_since and not member.bot:
            guild = member.guild
            notify_channel = get_announce_channel(guild, 'booster')

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

async def write_to_memory(content):
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO ChatMemory (timestamp, content) VALUES (?, ?)", (now, content))
            # Keep only the last 2000 log entries to prevent DB bloat
            await db.execute("DELETE FROM ChatMemory WHERE id NOT IN (SELECT id FROM ChatMemory ORDER BY id DESC LIMIT 2000)")
            await db.commit()
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
        return response.text or "Hmm, gue lagi nggak bisa jawab itu. Coba tanya yang lain deh."
    except Exception as e:
        logging.error(f"Error getting Gemini response: {str(e)}")
        return "Error getting response from Gemini."


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
    
    # rob_cooldowns (30 min)
    expired_rob = [k for k, v in rob_cooldowns.items() if (now - v).total_seconds() > 1800]
    for k in expired_rob: del rob_cooldowns[k]

    # boss_cooldowns (30 sec)
    expired_boss = [k for k, v in boss_cooldowns.items() if (now - v).total_seconds() > 30]
    for k in expired_boss: del boss_cooldowns[k]

    # work_cooldowns (1 hour)
    expired_work = [k for k, v in work_cooldowns.items() if (now - v).total_seconds() > 3600]
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
        return

    # ── Update Quest Progress ────────────────────────────────────────────────
    await update_quest_progress(str(message.author.id), 'send_msg', 1)

    # ── AI auto-reply in the dedicated channel ───────────────────────────────
    if message.channel.id == 1341038015186862201:
        nick = getattr(message.author, 'nick', None) or message.author.display_name
        response = await get_gemini_response(message.content, message.author.id, nick)
        await send_long_message(message.channel, response)
        await write_to_memory(f'User: {message.content}\nBot: {response}')
        return
