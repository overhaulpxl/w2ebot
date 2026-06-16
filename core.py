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
# Channel tempat bot auto-reply pakai AI tanpa perlu prefix. 0 = nonaktif.
AI_AUTO_REPLY_CHANNEL_ID = int(os.getenv('AI_AUTO_REPLY_CHANNEL_ID', '1341038015186862201'))
# Comma-separated origins yang boleh akses API (mis. web main way2eternal).
# Kosong = izinkan semua (dev only). Wajib diisi kalau web main di domain lain.
ALLOWED_ORIGINS = [o.strip() for o in os.getenv('ALLOWED_ORIGINS', '').split(',') if o.strip()]

# genai Client
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

# Waktu start proses (untuk uptime di /api/bot/stats).
BOT_START_TIME = datetime.utcnow()




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
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Reminder (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            channel_id TEXT,
            message TEXT,
            fire_at TEXT,
            created_at TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Giveaway (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT,
            message_id TEXT,
            prize TEXT,
            host_id TEXT,
            end_at TEXT,
            ended INTEGER DEFAULT 0
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS AuditLog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            action TEXT,
            target_id TEXT,
            detail TEXT,
            source TEXT
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
                                old_level = level
                                level += n
                                xp -= int(xp_consumed)
                                await db.execute("UPDATE DiscordStat SET xp=?, level=? WHERE id=?", (xp, level, str(uid)))
                                await db.commit()
                                logging.info(f"[LEVELUP] uid={uid} naik level {old_level} -> {level} (sisa XP {xp})")
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
            async with db.execute("SELECT coins FROM DiscordStat WHERE id=?", (str(uid),)) as c:
                row = await c.fetchone()
            saldo = row[0] if row else '?'
        arah = '+' if delta >= 0 else ''
        logging.info(f"[ECONOMY] {display_name or uid} ({uid}) koin {arah}{delta} -> saldo {saldo}")
    except Exception as e:
        logging.error(f"DB Error adjust_coins: {e}")


# Alias semantik untuk kredit koin (biar maksud kode jelas).
async def add_coins(uid, amount, display_name=None):
    await adjust_coins(uid, amount, display_name)


async def try_spend(uid, amount, display_name=None):
    # Debit ATOMIK dengan syarat saldo cukup. Mengembalikan True kalau berhasil
    # memotong koin, False kalau saldo kurang / user belum punya row.
    # Ini menutup race "cek saldo lalu potong" yang bisa dipakai untuk double-spend
    # via prefix + slash bersamaan. Selalu pakai ini untuk pembelian/biaya.
    if amount is None or amount <= 0:
        return True
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "UPDATE DiscordStat SET coins = coins - ?, "
                "displayName = COALESCE(?, displayName), updatedAt = ? "
                "WHERE id = ? AND coins >= ?",
                (amount, display_name, now, str(uid), amount))
            await db.commit()
            ok = cur.rowcount > 0
            if ok:
                async with db.execute("SELECT coins FROM DiscordStat WHERE id=?", (str(uid),)) as c:
                    row = await c.fetchone()
                saldo = row[0] if row else '?'
                logging.info(f"[ECONOMY] {display_name or uid} ({uid}) bayar -{amount} -> saldo {saldo}")
            else:
                logging.info(f"[ECONOMY] {display_name or uid} ({uid}) GAGAL bayar {amount} (saldo kurang)")
            return ok
    except Exception as e:
        logging.error(f"DB Error try_spend: {e}")
        return False


async def add_xp(uid, display_name, xp_delta):
    # Increment XP secara ATOMIK. Level-up di-resolve lazy oleh get_discord_stat
    # (rumus kuadratik di sana), jadi cukup tambah XP-nya saja.
    if not xp_delta:
        return
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO DiscordStat (id, displayName, xp, updatedAt) VALUES (?, ?, MAX(0, ?), ?) "
                "ON CONFLICT(id) DO UPDATE SET xp = MAX(0, xp + ?), "
                "displayName = COALESCE(?, displayName), updatedAt = ?",
                (str(uid), display_name or str(uid), xp_delta, now, xp_delta, display_name, now))
            await db.commit()
        logging.info(f"[XP] {display_name or uid} ({uid}) +{xp_delta} XP")
    except Exception as e:
        logging.error(f"DB Error add_xp: {e}")


async def set_last_daily(uid, value, display_name=None):
    # Update kolom lastDaily TANPA menyentuh coins/xp (menghindari clobber saldo).
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO DiscordStat (id, displayName, lastDaily, updatedAt) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET lastDaily = ?, "
                "displayName = COALESCE(?, displayName), updatedAt = ?",
                (str(uid), display_name or str(uid), value, now, value, display_name, now))
            await db.commit()
    except Exception as e:
        logging.error(f"DB Error set_last_daily: {e}")


# Fee transaksi kripto (2% dua arah). Dipakai /buycoin & /sellcoin.
CRYPTO_FEE_RATE = 0.02


async def add_treasury(amount):
    # Tambah saldo kas komunitas (treasury.json). Dipakai untuk menampung fee
    # transaksi kripto. Ini JSON blob (bukan kolom SQL), jadi tidak seatomik koin —
    # tapi risikonya rendah (fee kecil, bukan dompet user langsung).
    if not amount or amount <= 0:
        return
    try:
        treasury = await load_json(TREASURY_FILE)
        if not isinstance(treasury, dict):
            treasury = {}
        treasury['balance'] = treasury.get('balance', 0) + int(amount)
        await save_json(TREASURY_FILE, treasury)
        logging.info(f"[TREASURY] +{int(amount)} koin (fee) -> kas {treasury['balance']}")
    except Exception as e:
        logging.error(f"Error add_treasury: {e}")


async def record_game(uid, game, won):
    # Catat statistik minigame per user. Disimpan di users.json[uid]['games'][game].
    # game: 'slot','blackjack','cf','rps','crash','tebak','gacha','box','hunt'
    # won: True/False/None (None = seri/netral, dihitung sebagai plays tapi bukan win/loss).
    try:
        users = await load_json('users.json')
        u = users.setdefault(str(uid), {})
        games = u.setdefault('games', {})
        g = games.setdefault(game, {'plays': 0, 'wins': 0, 'losses': 0})
        g['plays'] += 1
        if won is True:
            g['wins'] += 1
        elif won is False:
            g['losses'] += 1
        await save_json('users.json', users)
    except Exception as e:
        logging.error(f"record_game error: {e}")






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
    stat_before = await get_discord_stat(uid)
    level_before = stat_before['level']
    # Tambah XP atomik; level-up di-resolve oleh get_discord_stat (rumus kuadratik).
    await add_xp(uid, user.display_name, xp_gained)
    stat_after = await get_discord_stat(uid)
    if stat_after['level'] > level_before:
        await channel.send(f"GG {user.mention}, kamu baru saja naik ke **Level {stat_after['level']}**!")

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

import ipaddress
import socket
from urllib.parse import urlparse


def is_safe_remote_url(url):
    # Guard SSRF: hanya izinkan http/https ke host publik. Blokir loopback,
    # private/link-local/reserved IP (mis. 169.254.169.254 metadata, 10.x, dst).
    # Dipakai sebelum bot mem-fetch URL yang dikontrol user (mis. /bg).
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


async def fetch_remote_image(url, max_bytes=8 * 1024 * 1024):
    # Fetch gambar dari URL user dengan proteksi SSRF + batas ukuran + cek tipe.
    # Mengembalikan PIL.Image atau None. Resolusi DNS divalidasi dulu lewat
    # is_safe_remote_url (best-effort; masih ada kemungkinan kecil TOCTOU tapi
    # jauh lebih aman daripada fetch mentah).
    if not await asyncio.to_thread(is_safe_remote_url, url):
        logging.warning(f"Blocked unsafe image URL: {url}")
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                ctype = resp.headers.get('Content-Type', '')
                if not ctype.startswith('image/'):
                    logging.warning(f"Rejected non-image content-type '{ctype}' from {url}")
                    return None
                data = await resp.content.read(max_bytes + 1)
                if len(data) > max_bytes:
                    logging.warning(f"Rejected oversized image from {url}")
                    return None
                return Image.open(io.BytesIO(data))
    except Exception as e:
        logging.error(f"Failed to fetch remote image: {e}")
        return None


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

    # Fetch background image if bg_url is provided (SSRF-guarded + size/type capped)
    bg_img = None
    if bg_url:
        bg_img = await fetch_remote_image(bg_url)

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

# Cache config.json di memori supaya get_announce_channel (dipanggil di banyak
# loop & event) tidak melakukan blocking file I/O di event loop tiap kali.
_config_cache = None

def _load_config():
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            _config_cache = json.load(f)
    except Exception:
        _config_cache = {}
    return _config_cache

def _save_config(cfg):
    # Tulis config.json dan refresh cache. Dipakai endpoint web write.
    global _config_cache
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(cfg, f)
    _config_cache = cfg

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
        if event_message:
            logging.info(f"[MARKET] Event harga: {target_coin} {event_type}")
        
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
                            # Kredit koin + XP secara atomik (hindari race read-modify-write).
                            await add_coins(uid, 50, m.display_name)

                            stat_before = await get_discord_stat(uid)
                            level_before = stat_before['level']
                            await add_xp(uid, m.display_name, 15)
                            stat_after = await get_discord_stat(uid)

                            if stat_after['level'] > level_before and announce_channel:
                                client.loop.create_task(
                                    announce_channel.send(f"GG {m.mention}, kamu baru saja naik ke **Level {stat_after['level']}** dari Voice Channel!")
                                )

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
                logging.info(f"[BOSS] Boss raid spawn: {boss_data['name']} HP {boss_data['hp']}")
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
        users = await load_json('users.json')

        # Hashrate per tier (ETHR per jam per unit rig).
        TIER_RATES = {'1': (1, 5), '2': (10, 20), '3': (50, 100)}

        has_mined = False
        total_mined = 0
        miner_count = 0
        for uid, udata in users.items():
            rigs = udata.get('rigs', {}) if isinstance(udata, dict) else {}
            if not rigs:
                continue
            mined_ethr = 0
            for tier, count in rigs.items():
                lo, hi = TIER_RATES.get(str(tier), (1, 5))
                mined_ethr += random.randint(lo, hi) * count
            if mined_ethr <= 0:
                continue
            has_mined = True
            miner_count += 1
            total_mined += mined_ethr
            crypto = udata.setdefault('crypto', {})
            crypto['ETHR'] = crypto.get('ETHR', 0) + mined_ethr

        if has_mined:
            await save_json('users.json', users)
            logging.info(f"[MINING] {miner_count} penambang dapat total {total_mined} ETHR")

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
    client.loop.create_task(resume_scheduled_jobs())
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
    except Exception:
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
    return web.json_response(_load_config())

async def update_config_api(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    try:
        data = await request.json()
        # Validasi: body harus objek JSON (dict), bukan list/str/null.
        if not isinstance(data, dict):
            return web.json_response({'error': 'Body must be a JSON object'}, status=400)
        # Jaga agar announce_channels (kalau ada) tetap berbentuk mapping valid,
        # supaya POST mentah ini tidak merusak struktur yang dipakai bot.
        if 'announce_channels' in data:
            ac = data['announce_channels']
            if not isinstance(ac, dict):
                return web.json_response({'error': 'announce_channels must be an object'}, status=400)
            for k, v in ac.items():
                if v is None:
                    ac[k] = ''
                elif not str(v).strip().isdigit() and str(v).strip() != '':
                    return web.json_response({'error': f'Invalid channel id for {k}'}, status=400)
        _save_config(data)
        return web.json_response({'status': 'success'})
    except Exception as e:
        logging.error(f"update_config_api error: {e}")
        return web.json_response({'status': 'error'}, status=500)

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
        _save_config(cfg)
        await write_audit('announce-config', None, str(announce), source="api")
        return web.json_response({'status': 'success', 'announce_channels': announce})
    except Exception as e:
        logging.error(f"update_announce_config_api error: {e}")
        return web.json_response({'status': 'error'}, status=500)

# ── Extra dashboard READ endpoints ───────────────────────────────────────────
def _resolve_name(uid):
    # Resolve display name dari cache discord; fallback ke "User <id>".
    try:
        u = client.get_user(int(uid))
        if u:
            return u.display_name
    except (ValueError, TypeError):
        pass
    return f"User {uid}"


async def api_leaderboard(request):
    # Top member dari DiscordStat. ?sort=coins|level (default level), ?limit=N (1..100).
    sort = request.query.get('sort', 'level')
    if sort not in ('coins', 'level'):
        return web.json_response({'error': "sort must be 'coins' or 'level'"}, status=400)
    try:
        limit = int(request.query.get('limit', '10'))
    except ValueError:
        limit = 10
    limit = max(1, min(limit, 100))
    order = "coins DESC, level DESC" if sort == 'coins' else "level DESC, coins DESC"
    rows_out = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                f"SELECT id, displayName, coins, xp, level FROM DiscordStat ORDER BY {order} LIMIT ?",
                (limit,)) as cur:
                rows = await cur.fetchall()
        for i, r in enumerate(rows):
            rows_out.append({
                'rank': i + 1, 'id': str(r[0]),
                'displayName': r[1] or _resolve_name(r[0]),
                'coins': r[2], 'xp': r[3], 'level': r[4],
            })
    except Exception as e:
        logging.error(f"api_leaderboard error: {e}")
        return web.json_response({'error': 'internal error'}, status=500)
    return web.json_response({'sort': sort, 'limit': limit, 'entries': rows_out})


def _cooldown_info(users, uid, now):
    # Hitung sisa cooldown (detik) untuk tiap aktivitas berbasis users.json.
    u = users.get(uid, {})
    specs = {'work': 3600, 'rob': 7200, 'pray': 3600, 'curse': 14400}
    keymap = {'work': 'lastWork', 'rob': 'lastRob', 'pray': 'lastPray', 'curse': 'lastCurse'}
    out = {}
    for name, dur in specs.items():
        ts = u.get(keymap[name])
        remaining = 0
        if ts:
            try:
                elapsed = (now - datetime.fromisoformat(ts)).total_seconds()
                remaining = max(0, int(dur - elapsed))
            except Exception:
                remaining = 0
        out[name] = remaining
    return out


async def api_user(request):
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    stat = await get_discord_stat(uid)
    rank = await get_user_rank(uid)
    users = await load_json('users.json')
    u = users.get(uid, {})
    marriages = await load_json('marriages.json')
    partner = marriages.get(uid)
    personas = await load_json(PERSONAS_FILE)
    bounties = await load_json('bounties.json')
    weekly_data = await load_json('weekly.json')
    quests_data = await load_json(QUESTS_FILE)
    items_data = await load_json(ITEMS_FILE)
    bdays = await load_json('birthdays.json')
    now = datetime.now()

    # Top 3 minigame berdasarkan jumlah main (plays).
    games = u.get('games', {})
    sorted_games = sorted(games.items(), key=lambda x: x[1].get('plays', 0), reverse=True)
    top_games = []
    for gname, gstats in sorted_games[:3]:
        plays = gstats.get('plays', 0)
        wins = gstats.get('wins', 0)
        win_rate = round((wins / plays) * 100, 1) if plays > 0 else 0
        top_games.append({'game': gname, 'plays': plays, 'wins': wins, 'win_rate': win_rate})

    data = {
        'id': uid,
        'displayName': _resolve_name(uid),
        'coins': stat['coins'],
        'xp': stat['xp'],
        'level': stat['level'],
        'xp_to_next': stat['level'] * 100,
        'rank': rank,
        'lastDaily': stat['lastDaily'],
        'crypto': u.get('crypto', {}),
        'rigs': u.get('rigs', {}),
        'items': u.get('items', {}),
        'pet': u.get('pet'),
        'achievements': u.get('achievements', []),
        'total_vc_minutes': u.get('total_vc_minutes', 0),
        'married_to': partner,
        'children': u.get('children', []),
        'bg_url': items_data.get(uid, {}).get('bg_url') or u.get('bg_url'),
        'cooldowns': _cooldown_info(users, uid, now),
        'games': games,
        'top_games': top_games,
        'persona': personas.get(uid),
        'birthday': bdays.get(uid),
        'bounty': bounties.get(uid, 0),
        'weekly_claimed': weekly_data.get(uid),
        'quest': quests_data.get(uid),
    }
    return web.json_response(data)


async def api_market(request):
    market = await load_json(MARKET_FILE)
    return web.json_response(market or {})


async def api_treasury(request):
    treasury = await load_json(TREASURY_FILE)
    balance = treasury.get('balance', 0) if isinstance(treasury, dict) else 0
    return web.json_response({'balance': balance})


async def api_boss(request):
    boss = await load_json(BOSS_FILE)
    return web.json_response(boss or {'active': False})


async def api_economy_stats(request):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*), COALESCE(SUM(coins),0), COALESCE(AVG(level),0), COALESCE(MAX(coins),0) FROM DiscordStat") as cur:
                count, total_coins, avg_level, max_coins = await cur.fetchone()
            async with db.execute(
                "SELECT id, displayName, coins FROM DiscordStat ORDER BY coins DESC LIMIT 1") as cur:
                top = await cur.fetchone()
    except Exception as e:
        logging.error(f"api_economy_stats error: {e}")
        return web.json_response({'error': 'internal error'}, status=500)
    treasury = await load_json(TREASURY_FILE)
    top_holder = None
    if top:
        top_holder = {'id': str(top[0]), 'displayName': top[1] or _resolve_name(top[0]), 'coins': top[2]}
    return web.json_response({
        'player_count': count,
        'total_coins_in_circulation': int(total_coins),
        'average_level': round(avg_level, 2),
        'richest_coins': int(max_coins),
        'top_holder': top_holder,
        'treasury_balance': treasury.get('balance', 0) if isinstance(treasury, dict) else 0,
    })


async def api_marriages(request):
    marriages = await load_json('marriages.json')
    seen = set()
    pairs = []
    for a, b in marriages.items():
        key = tuple(sorted((str(a), str(b))))
        if key in seen:
            continue
        seen.add(key)
        pairs.append({
            'a': {'id': str(a), 'displayName': _resolve_name(a)},
            'b': {'id': str(b), 'displayName': _resolve_name(b)},
        })
    return web.json_response(pairs)


async def api_stats_summary(request):
    guild = client.get_guild(ALLOWED_SERVER_ID)
    in_voice = 0
    member_count = 0
    if guild:
        member_count = guild.member_count
        for vc in guild.voice_channels:
            in_voice += len([m for m in vc.members if not m.bot])
    boss = await load_json(BOSS_FILE)
    treasury = await load_json(TREASURY_FILE)
    total_coins = 0
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT COALESCE(SUM(coins),0) FROM DiscordStat") as cur:
                row = await cur.fetchone()
                total_coins = int(row[0]) if row else 0
    except Exception as e:
        logging.error(f"api_stats_summary error: {e}")
    return web.json_response({
        'member_count': member_count,
        'members_in_voice': in_voice,
        'boss_active': bool(boss.get('active', False)) if isinstance(boss, dict) else False,
        'treasury_balance': treasury.get('balance', 0) if isinstance(treasury, dict) else 0,
        'total_coins_in_circulation': total_coins,
    })


# ── Extra dashboard WRITE endpoints (token wajib) ─────────────────────────────
async def api_user_coins(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    name = _resolve_name(uid)
    if 'delta' in body:
        try:
            delta = int(body['delta'])
        except (ValueError, TypeError):
            return web.json_response({'error': 'delta must be an integer'}, status=400)
        await adjust_coins(uid, delta, name)
    elif 'set' in body:
        try:
            value = int(body['set'])
        except (ValueError, TypeError):
            return web.json_response({'error': 'set must be an integer'}, status=400)
        if value < 0:
            return web.json_response({'error': 'set must be >= 0'}, status=400)
        stat = await get_discord_stat(uid)
        await update_discord_stat(uid, name, value, stat['xp'], stat['level'], stat['lastDaily'])
        logging.info(f"[ECONOMY] (api) {name} ({uid}) coins SET -> {value}")
    else:
        return web.json_response({'error': 'provide "delta" or "set"'}, status=400)
    stat = await get_discord_stat(uid)
    await write_audit('coins', uid, f"{'delta' if 'delta' in body else 'set'}={body.get('delta', body.get('set'))} -> {stat['coins']}")
    return web.json_response({'status': 'success', 'id': uid, 'coins': stat['coins']})


async def api_user_xp(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
        delta = int(body['delta'])
    except (ValueError, TypeError, KeyError):
        return web.json_response({'error': 'provide integer "delta"'}, status=400)
    await add_xp(uid, _resolve_name(uid), delta)
    stat = await get_discord_stat(uid)
    await write_audit('xp', uid, f"delta={delta} -> xp {stat['xp']} lvl {stat['level']}")
    return web.json_response({'status': 'success', 'id': uid, 'xp': stat['xp'], 'level': stat['level']})


async def api_user_give_item(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    item_id = body.get('item_id')
    if item_id not in SHOP_ITEMS:
        return web.json_response({'error': f'unknown item_id (valid: {", ".join(SHOP_ITEMS)})'}, status=400)
    try:
        qty = int(body.get('qty', 1))
    except (ValueError, TypeError):
        return web.json_response({'error': 'qty must be an integer'}, status=400)
    if qty <= 0:
        return web.json_response({'error': 'qty must be > 0'}, status=400)
    users = await load_json('users.json')
    items = users.setdefault(uid, {}).setdefault('items', {})
    items[item_id] = items.get(item_id, 0) + qty
    await save_json('users.json', users)
    logging.info(f"[ITEM] (api) beri {qty}x {item_id} ke {uid}")
    await write_audit('give-item', uid, f"{qty}x {item_id}")
    return web.json_response({'status': 'success', 'id': uid, 'items': items})


async def api_user_reset_cooldown(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    ctype = (body.get('type') or '').lower()
    keymap = {'work': 'lastWork', 'rob': 'lastRob', 'pray': 'lastPray', 'curse': 'lastCurse'}
    valid = set(keymap) | {'daily', 'all'}
    if ctype not in valid:
        return web.json_response({'error': f'type must be one of {", ".join(sorted(valid))}'}, status=400)
    users = await load_json('users.json')
    u = users.setdefault(uid, {})
    targets = list(keymap) if ctype in ('all',) else ([ctype] if ctype in keymap else [])
    for t in targets:
        u.pop(keymap[t], None)
    await save_json('users.json', users)
    if ctype in ('daily', 'all'):
        await set_last_daily(uid, '', _resolve_name(uid))
    logging.info(f"[COOLDOWN] (api) reset '{ctype}' untuk {uid}")
    await write_audit('reset-cooldown', uid, f"type={ctype}")
    return web.json_response({'status': 'success', 'id': uid, 'reset': ctype})


async def api_boss_spawn(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    boss_data = await load_json(BOSS_FILE)
    if boss_data.get('active', False):
        return web.json_response({'error': 'boss already active', 'boss': boss_data}, status=409)
    boss_data = {'active': True, 'hp': 10000, 'max_hp': 10000, 'name': '🐉 Naga Emas Koruptor'}
    await save_json(BOSS_FILE, boss_data)
    logging.info("[BOSS] (api) Boss raid dipaksa spawn lewat dashboard")
    await write_audit('boss-spawn', None, boss_data['name'])
    for guild in client.guilds:
        ch = get_announce_channel(guild, 'boss')
        if ch:
            client.loop.create_task(
                ch.send(f"⚠️ **BOSS RAID EVENT DIMULAI!** ⚠️\n**{boss_data['name']}** telah muncul dengan {boss_data['hp']} HP!\nKetik `!attack` untuk menyerang! Yang berhasil membunuhnya mendapat hadiah 5000 Koin!")
            )
    return web.json_response({'status': 'success', 'boss': boss_data})


async def api_announce(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    category = body.get('category')
    message = body.get('message')
    if category not in ANNOUNCE_CATEGORIES and category != 'default':
        return web.json_response({'error': f'category must be one of {", ".join(ANNOUNCE_CATEGORIES + ["default"])}'}, status=400)
    if not message:
        return web.json_response({'error': 'missing message'}, status=400)
    sent = 0
    for guild in client.guilds:
        ch = get_announce_channel(guild, category if category != 'default' else None)
        if ch:
            await send_long_message(ch, str(message))
            sent += 1
    await write_audit('announce', category, f"{sent} channel: {str(message)[:80]}")
    return web.json_response({'status': 'sent', 'channels': sent})


async def api_user_persona(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    persona = body.get('persona', '')
    personas = await load_json(PERSONAS_FILE)
    if persona and persona.strip():
        personas[uid] = persona.strip()
    else:
        personas.pop(uid, None)
    await save_json(PERSONAS_FILE, personas)
    await write_audit('persona', uid, persona[:80] if persona else 'reset')
    logging.info(f"[SETTING] (api) persona uid={uid} -> {persona[:40] if persona else 'reset'}")
    return web.json_response({'status': 'success', 'id': uid, 'persona': personas.get(uid)})


async def api_user_birthday(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    date = body.get('date', '')
    if date:
        date = str(date).strip()
        if len(date) != 5 or date[2] != '-':
            return web.json_response({'error': 'format harus DD-MM (cth. 25-12)'}, status=400)
        try:
            int(date[:2]); int(date[3:])
        except ValueError:
            return web.json_response({'error': 'format harus DD-MM (cth. 25-12)'}, status=400)
    users = await load_json('users.json')
    bdays = await load_json('birthdays.json')
    if date:
        users.setdefault(uid, {})['birthday'] = date
        bdays[uid] = date
    else:
        users.get(uid, {}).pop('birthday', None)
        bdays.pop(uid, None)
    await save_json('users.json', users)
    await save_json('birthdays.json', bdays)
    await write_audit('birthday', uid, date or 'hapus')
    return web.json_response({'status': 'success', 'id': uid, 'birthday': date or None})


async def api_user_bg(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    url = body.get('url', '')
    if url:
        url = str(url).strip()
        if not url.lower().startswith(('http://', 'https://')):
            return web.json_response({'error': 'URL harus http/https'}, status=400)
        if not await asyncio.to_thread(is_safe_remote_url, url):
            return web.json_response({'error': 'URL ditolak (host internal/privat)'}, status=400)
        test = await fetch_remote_image(url)
        if test is None:
            return web.json_response({'error': 'URL tidak mengarah ke gambar valid'}, status=400)
    items_data = await load_json(ITEMS_FILE)
    if url:
        items_data.setdefault(uid, {})['bg_url'] = url
    else:
        items_data.get(uid, {}).pop('bg_url', None)
    await save_json(ITEMS_FILE, items_data)
    await write_audit('bg', uid, url[:100] if url else 'hapus')
    return web.json_response({'status': 'success', 'id': uid, 'bg_url': url or None})


async def api_user_divorce(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    marriages = await load_json('marriages.json')
    partner = marriages.get(uid)
    if not partner:
        return web.json_response({'error': 'user tidak menikah'}, status=400)
    marriages.pop(uid, None)
    marriages.pop(partner, None)
    await save_json('marriages.json', marriages)
    await write_audit('divorce', uid, f'pasangan={partner}')
    logging.info(f"[SETTING] (api) paksa cerai uid={uid} pasangan={partner}")
    return web.json_response({'status': 'success', 'id': uid, 'divorced_from': partner})


async def api_user_bounty(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    amount = body.get('amount')
    if amount is None:
        return web.json_response({'error': 'sediakan "amount" (0 = hapus)'}, status=400)
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return web.json_response({'error': 'amount harus integer'}, status=400)
    bounties = await load_json('bounties.json')
    if amount <= 0:
        bounties.pop(uid, None)
    else:
        bounties[uid] = amount
    await save_json('bounties.json', bounties)
    await write_audit('bounty', uid, f'amount={amount}')
    return web.json_response({'status': 'success', 'id': uid, 'bounty': bounties.get(uid, 0)})


async def api_user_reset_weekly(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    weekly = await load_json('weekly.json')
    weekly.pop(uid, None)
    await save_json('weekly.json', weekly)
    await write_audit('reset-weekly', uid, 'weekly direset')
    return web.json_response({'status': 'success', 'id': uid, 'weekly_claimed': None})


async def api_user_reset_quest(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    quests = await load_json(QUESTS_FILE)
    quests.pop(uid, None)
    await save_json(QUESTS_FILE, quests)
    await write_audit('reset-quest', uid, 'quest direset')
    return web.json_response({'status': 'success', 'id': uid, 'quest': None})


async def api_audit(request):
    # Audit log aksi admin. Token wajib (isinya jejak aksi sensitif).
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    try:
        limit = int(request.query.get('limit', '100'))
    except ValueError:
        limit = 100
    limit = max(1, min(limit, 500))
    entries = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, ts, action, target_id, detail, source FROM AuditLog ORDER BY id DESC LIMIT ?",
                (limit,)) as cur:
                rows = await cur.fetchall()
        for r in rows:
            entries.append({
                'id': r[0], 'ts': r[1], 'action': r[2],
                'target_id': r[3], 'detail': r[4], 'source': r[5],
            })
    except Exception as e:
        logging.error(f"api_audit error: {e}")
        return web.json_response({'error': 'internal error'}, status=500)
    return web.json_response({'limit': limit, 'entries': entries})


async def api_level_distribution(request):
    # Distribusi jumlah pemain per level (untuk bar chart).
    buckets = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT level, COUNT(*) FROM DiscordStat GROUP BY level ORDER BY level") as cur:
                rows = await cur.fetchall()
        buckets = [{'level': r[0], 'count': r[1]} for r in rows]
    except Exception as e:
        logging.error(f"api_level_distribution error: {e}")
        return web.json_response({'error': 'internal error'}, status=500)
    return web.json_response({'buckets': buckets})


async def api_bot_stats(request):
    # Statistik detail bot: latency, uptime, info guild, agregat ekonomi.
    guild = client.get_guild(ALLOWED_SERVER_ID)

    # Latency gateway (ms)
    latency_ms = None
    try:
        if client.latency and client.latency == client.latency:  # bukan NaN
            latency_ms = round(client.latency * 1000)
    except Exception:
        latency_ms = None

    # Uptime
    uptime_seconds = int((datetime.utcnow() - BOT_START_TIME).total_seconds())

    # Info guild
    guild_info = None
    if guild:
        bots = sum(1 for m in guild.members if m.bot)
        humans = guild.member_count - bots if guild.member_count else None
        in_voice = sum(len([m for m in vc.members if not m.bot]) for vc in guild.voice_channels)
        guild_info = {
            'name': guild.name,
            'icon_url': str(guild.icon.url) if guild.icon else None,
            'member_count': guild.member_count,
            'humans': humans,
            'bots': bots,
            'members_in_voice': in_voice,
            'boosts': guild.premium_subscription_count,
            'boost_tier': guild.premium_tier,
            'text_channels': len(guild.text_channels),
            'voice_channels': len(guild.voice_channels),
            'roles': len(guild.roles),
        }

    # Agregat ekonomi dari DiscordStat
    economy = {}
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*), COALESCE(SUM(coins),0), COALESCE(AVG(level),0), COALESCE(MAX(level),0), COALESCE(SUM(xp),0) FROM DiscordStat") as cur:
                row = await cur.fetchone()
        economy = {
            'players': row[0],
            'total_coins': int(row[1]),
            'average_level': round(row[2], 2),
            'max_level': row[3],
            'total_xp': int(row[4]),
        }
    except Exception as e:
        logging.error(f"api_bot_stats economy error: {e}")

    treasury = await load_json(TREASURY_FILE)
    boss = await load_json(BOSS_FILE)

    # Jumlah kategori announce yang sudah dikonfigurasi
    cfg = _load_config()
    announce = cfg.get('announce_channels', {}) if isinstance(cfg, dict) else {}
    configured = sum(1 for k in (['default'] + ANNOUNCE_CATEGORIES) if announce.get(k))

    return web.json_response({
        'online': guild is not None,
        'latency_ms': latency_ms,
        'uptime_seconds': uptime_seconds,
        'guild': guild_info,
        'economy': economy,
        'treasury_balance': treasury.get('balance', 0) if isinstance(treasury, dict) else 0,
        'boss_active': bool(boss.get('active', False)) if isinstance(boss, dict) else False,
        'commands_registered': len(tree.get_commands()),
        'announce_channels_configured': configured,
        'prefix': BOT_PREFIX,
    })


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

    # READ tambahan (tanpa token)
    app.router.add_get('/api/leaderboard', api_leaderboard)
    app.router.add_get('/api/user/{id}', api_user)
    app.router.add_get('/api/market', api_market)
    app.router.add_get('/api/treasury', api_treasury)
    app.router.add_get('/api/boss', api_boss)
    app.router.add_get('/api/economy/stats', api_economy_stats)
    app.router.add_get('/api/marriages', api_marriages)
    app.router.add_get('/api/stats/summary', api_stats_summary)
    app.router.add_get('/api/bot/stats', api_bot_stats)
    app.router.add_get('/api/economy/level-distribution', api_level_distribution)
    app.router.add_get('/api/audit', api_audit)

    # WRITE tambahan (token wajib)
    app.router.add_post('/api/user/{id}/coins', api_user_coins)
    app.router.add_post('/api/user/{id}/xp', api_user_xp)
    app.router.add_post('/api/user/{id}/give-item', api_user_give_item)
    app.router.add_post('/api/user/{id}/reset-cooldown', api_user_reset_cooldown)
    app.router.add_post('/api/user/{id}/persona', api_user_persona)
    app.router.add_post('/api/user/{id}/birthday', api_user_birthday)
    app.router.add_post('/api/user/{id}/bg', api_user_bg)
    app.router.add_post('/api/user/{id}/divorce', api_user_divorce)
    app.router.add_post('/api/user/{id}/bounty', api_user_bounty)
    app.router.add_post('/api/user/{id}/reset-weekly', api_user_reset_weekly)
    app.router.add_post('/api/user/{id}/reset-quest', api_user_reset_quest)
    app.router.add_post('/api/boss/spawn', api_boss_spawn)
    app.router.add_post('/api/announce', api_announce)
    
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
                    users[uid] = {'items': {}, 'achievements': [], 'total_vc_minutes': 0}

                # Tambah XP & Koin
                xp_gained = minutes * 10
                coins_gained = minutes * 5
                users[uid]['total_vc_minutes'] = users[uid].get('total_vc_minutes', 0) + minutes

                # Koin masuk ke dompet asli (DiscordStat.coins) secara atomik,
                # bukan ke users.json['balance'] yang dulu cuma write-only.
                await add_coins(uid, coins_gained, member.display_name)

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

                # Tambah XP secara atomik (level-up di-resolve lazy oleh get_discord_stat).
                await add_xp(uid, member.display_name, xp_gained)

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


# ── Audit log ────────────────────────────────────────────────────────────────
async def write_audit(action, target_id=None, detail=None, source="api"):
    # Catat aksi admin/write ke tabel AuditLog. Best-effort; jangan sampai gagal
    # audit menggagalkan aksi utamanya.
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO AuditLog (ts, action, target_id, detail, source) VALUES (?, ?, ?, ?, ?)",
                (now, action, str(target_id) if target_id is not None else None, detail, source))
            # Batasi 1000 baris terbaru biar DB tidak membengkak.
            await db.execute("DELETE FROM AuditLog WHERE id NOT IN (SELECT id FROM AuditLog ORDER BY id DESC LIMIT 1000)")
            await db.commit()
    except Exception as e:
        logging.error(f"write_audit error: {e}")


# ── Reminder persistence ──────────────────────────────────────────────────────
async def add_reminder(user_id, channel_id, message, fire_at):
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "INSERT INTO Reminder (user_id, channel_id, message, fire_at, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(user_id), str(channel_id), message, fire_at.isoformat(), now))
            await db.commit()
            return cur.lastrowid
    except Exception as e:
        logging.error(f"add_reminder error: {e}")
        return None


async def delete_reminder(rid):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM Reminder WHERE id=?", (rid,))
            await db.commit()
    except Exception as e:
        logging.error(f"delete_reminder error: {e}")


async def _fire_reminder(rid, user_id, channel_id, message, delay):
    # Tunggu `delay` detik (boleh 0 untuk yang sudah lewat), kirim, lalu hapus baris.
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        channel = client.get_channel(int(channel_id))
        if channel:
            await channel.send(f"🔔 <@{user_id}> **REMINDER:** {message}")
    except Exception as e:
        logging.error(f"_fire_reminder error: {e}")
    finally:
        await delete_reminder(rid)


def schedule_reminder(rid, user_id, channel_id, message, fire_at):
    delay = (fire_at - datetime.utcnow()).total_seconds()
    client.loop.create_task(_fire_reminder(rid, user_id, channel_id, message, max(0, delay)))


# ── Giveaway persistence ──────────────────────────────────────────────────────
async def add_giveaway(channel_id, message_id, prize, host_id, end_at):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "INSERT INTO Giveaway (channel_id, message_id, prize, host_id, end_at, ended) VALUES (?, ?, ?, ?, ?, 0)",
                (str(channel_id), str(message_id), prize, str(host_id), end_at.isoformat()))
            await db.commit()
            return cur.lastrowid
    except Exception as e:
        logging.error(f"add_giveaway error: {e}")
        return None


async def _end_giveaway(gid, channel_id, message_id, prize, delay):
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        channel = client.get_channel(int(channel_id))
        if channel:
            try:
                msg = await channel.fetch_message(int(message_id))
                reaction = discord.utils.get(msg.reactions, emoji="🎉")
                entrants = [u async for u in reaction.users() if not u.bot] if reaction else []
            except Exception:
                entrants = []
            if not entrants:
                await channel.send(f"🎉 Giveaway **{prize}** selesai — tidak ada yang ikut.")
            else:
                winner = random.choice(entrants)
                await channel.send(f"🎊 Selamat {winner.mention}! Kamu memenangkan **{prize}**!")
    except Exception as e:
        logging.error(f"_end_giveaway error: {e}")
    finally:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE Giveaway SET ended=1 WHERE id=?", (gid,))
                await db.commit()
        except Exception as e:
            logging.error(f"_end_giveaway cleanup error: {e}")


def schedule_giveaway(gid, channel_id, message_id, prize, end_at):
    delay = (end_at - datetime.utcnow()).total_seconds()
    client.loop.create_task(_end_giveaway(gid, channel_id, message_id, prize, max(0, delay)))


async def resume_scheduled_jobs():
    # Dipanggil di on_ready: re-schedule reminder & giveaway yang tersimpan.
    # Reminder/giveaway yang sudah lewat fire_at langsung dieksekusi (delay 0).
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT id, user_id, channel_id, message, fire_at FROM Reminder") as cur:
                reminders = await cur.fetchall()
            async with db.execute("SELECT id, channel_id, message_id, prize, end_at FROM Giveaway WHERE ended=0") as cur:
                giveaways = await cur.fetchall()
        for rid, uid, cid, msg, fire_at in reminders:
            try:
                schedule_reminder(rid, uid, cid, msg, datetime.fromisoformat(fire_at))
            except Exception as e:
                logging.error(f"resume reminder {rid} error: {e}")
        for gid, cid, mid, prize, end_at in giveaways:
            try:
                schedule_giveaway(gid, cid, mid, prize, datetime.fromisoformat(end_at))
            except Exception as e:
                logging.error(f"resume giveaway {gid} error: {e}")
        if reminders or giveaways:
            logging.info(f"[RESUME] {len(reminders)} reminder & {len(giveaways)} giveaway dijadwalkan ulang")
    except Exception as e:
        logging.error(f"resume_scheduled_jobs error: {e}")


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
    except Exception:
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
        logging.error(f"Embed send error: {e}")

# ============================================================================
# SLASH COMMANDS (APP COMMANDS)

@client.event
async def on_interaction(interaction: discord.Interaction):
    # Log tiap pemakaian slash command ke console (prefix di-log di on_message).
    try:
        if interaction.type == discord.InteractionType.application_command:
            data = interaction.data or {}
            name = data.get('name', '?')
            opts = data.get('options', []) or []
            arg_str = " ".join(f"{o.get('name')}={o.get('value')}" for o in opts)
            user = interaction.user
            logging.info(f"[CMD] (slash) {user} ({getattr(user, 'id', '?')}) -> {name} {arg_str}".rstrip())
    except Exception as e:
        logging.error(f"on_interaction log error: {e}")

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    logging.error(f'App Command Error: {error}')
    # Jangan bocorkan detail exception ke user; cukup pesan generik.
    user_msg = '❌ Terjadi kesalahan saat menjalankan perintah. Coba lagi nanti ya.'
    try:
        if interaction.response.is_done():
            await interaction.followup.send(user_msg, ephemeral=True)
        else:
            await interaction.response.send_message(user_msg, ephemeral=True)
    except Exception:
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
            logging.info(f"[CMD] (prefix) {message.author} ({message.author.id}) -> {cmd_name} {' '.join(args_list)}".rstrip())
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
                await message.channel.send("❌ Gagal mengeksekusi perintah. Cek format argumennya ya.")
        return

    # ── Update Quest Progress ────────────────────────────────────────────────
    await update_quest_progress(str(message.author.id), 'send_msg', 1)

    # ── AI auto-reply in the dedicated channel ───────────────────────────────
    if message.channel.id == AI_AUTO_REPLY_CHANNEL_ID:
        nick = getattr(message.author, 'nick', None) or message.author.display_name
        response = await get_gemini_response(message.content, message.author.id, nick)
        await send_long_message(message.channel, response)
        await write_to_memory(f'User: {message.content}\nBot: {response}')
        return
