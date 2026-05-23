import discord

async def send_embed(ctx_or_channel, text, color=None, title=None, ephemeral=False, view=None, file=None):
    import discord
    if color is None:
        t_lower = text.lower()
        if "❌" in text or "error" in t_lower or "gagal" in t_lower or "not found" in t_lower or "kosong" in t_lower or "salah" in t_lower:
            color = discord.Color.red()
        elif "✅" in text or "berhasil" in t_lower or "added" in t_lower or "memuterkan" in t_lower or "playing" in t_lower or "lanjut" in t_lower:
            color = discord.Color.green()
        elif "🔍" in text or "mencari" in t_lower or "fetching" in t_lower or "autoplay" in t_lower:
            color = discord.Color.blurple()
        elif "⚠️" in text or "pause" in t_lower or "stop" in t_lower:
            color = discord.Color.orange()
        else:
            color = discord.Color.purple()

    embed = discord.Embed(description=text, color=color)
    if title:
        embed.title = title
    embed.set_footer(text="W2E Music System")
    
    try:
        author = None
        if hasattr(ctx_or_channel, 'author'):
            author = ctx_or_channel.author
        elif hasattr(ctx_or_channel, 'user'):
            author = ctx_or_channel.user
            
        if author:
            icon_url = author.display_avatar.url if author.display_avatar else None
            embed.set_author(name=author.display_name, icon_url=icon_url)
    except:
        pass
        
    kwargs = {'embed': embed}
    if view: kwargs['view'] = view
    if file: kwargs['file'] = file
    if ephemeral and hasattr(ctx_or_channel, 'response'): kwargs['ephemeral'] = True
    
    try:
        if hasattr(ctx_or_channel, 'send'):
            return await ctx_or_channel.send(**kwargs)
        elif hasattr(ctx_or_channel, 'response') and hasattr(ctx_or_channel.response, 'send_message'):
            if ctx_or_channel.response.is_done():
                return await ctx_or_channel.followup.send(**kwargs)
            else:
                return await ctx_or_channel.response.send_message(**kwargs)
    except Exception as e:
        print(f"Embed send error: {e}")


from discord.ext import commands
import os
import asyncio
import yt_dlp
import aiohttp
from aiohttp import web
from bs4 import BeautifulSoup
from discord import FFmpegPCMAudio, PCMVolumeTransformer
import logging
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import json
from datetime import datetime
import random
import io
from PIL import Image, ImageDraw, ImageFont, ImageFilter

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# Configuration (fallback to environment variables if set)
DISCORD_API_KEY = os.getenv('CUSTOM_MUSIC_BOT_TOKEN', 'YOUR_PREMIUM_BOT_TOKEN_HERE')
PREFIX = os.getenv('CUSTOM_MUSIC_BOT_PREFIX', '!')
SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID', 'YOUR_SPOTIFY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET', 'YOUR_SPOTIFY_CLIENT_SECRET')

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

sp = None
if SPOTIPY_CLIENT_ID != 'YOUR_SPOTIFY_CLIENT_ID':
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))

# Global states
WHITELIST_FILE = 'premium_users.json'
MUSIC_STATS_FILE = 'premium_music_stats.json'

queues = {} # guild_id -> list of {'title', 'url', 'requester', 'thumbnail', 'artist', 'duration'}
voice_clients = {}
current_song_info = {}
loop_modes = {} # guild_id -> OFF, TRACK, QUEUE
autoplay_modes = {} # guild_id -> bool
play_history = {} # guild_id -> list of urls to avoid in autoplay
volumes = {}
active_filters = {} # guild_id -> str
playlists = {} # user_id -> dict of playlist_name -> list of urls
seek_times = {} # guild_id -> seconds

import sqlite3

def _init_db():
    conn = sqlite3.connect('w2ebot.db')
    conn.execute("CREATE TABLE IF NOT EXISTS json_store (filename TEXT PRIMARY KEY, content TEXT)")
    conn.commit()
    conn.close()

_init_db()

def load_json(filepath, default_val=None):
    if default_val is None: default_val = {}
    basename = os.path.basename(filepath)
    try:
        conn = sqlite3.connect('w2ebot.db')
        c = conn.cursor()
        c.execute("SELECT content FROM json_store WHERE filename=?", (basename,))
        row = c.fetchone()
        conn.close()
        if row:
            try: return json.loads(row[0])
            except: pass
    except Exception:
        pass
    return default_val

def save_json(filepath, data):
    basename = os.path.basename(filepath)
    try:
        conn = sqlite3.connect('w2ebot.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO json_store (filename, content) VALUES (?, ?)", (basename, json.dumps(data, ensure_ascii=False)))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"DB Save Error: {e}")

def is_whitelisted(user_id):
    users = load_json(WHITELIST_FILE, [])
    return str(user_id) in users

async def check_whitelist(ctx):
    # Silent ignore if not whitelisted
    return is_whitelisted(ctx.author.id)

def add_music_stat(user_id, source):
    uid = str(user_id)
    stats = load_json(MUSIC_STATS_FILE)
    if uid not in stats:
        stats[uid] = {'total_plays': 0, 'total_duration': 0, 'favorite_source': {}, 'tracks': {}, 'friends': {}}
    
    stats[uid]['total_plays'] += 1
    
    src_key = source.lower()
    stats[uid]['favorite_source'][src_key] = stats[uid]['favorite_source'].get(src_key, 0) + 1
    save_json(MUSIC_STATS_FILE, stats)

def record_track_stat(user_id, track_title, duration, voice_channel):
    uid = str(user_id)
    stats = load_json(MUSIC_STATS_FILE)
    if uid not in stats: return
    
    stats[uid]['total_duration'] += duration
    stats[uid]['tracks'][track_title] = stats[uid]['tracks'].get(track_title, 0) + 1
    
    if voice_channel:
        for member in voice_channel.members:
            if member.id != user_id and not member.bot:
                fid = str(member.id)
                stats[uid]['friends'][fid] = stats[uid]['friends'].get(fid, 0) + 1
                
    save_json(MUSIC_STATS_FILE, stats)

async def search_yt(query):
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'default_search': 'ytsearch',
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = await asyncio.to_thread(ydl.extract_info, query, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            return info
        except Exception as e:
            logging.error(f"Search YT Error: {e}")
            return None

class MusicPlayerControls(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.secondary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_whitelisted(interaction.user.id): return
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing(): vc.pause(); await send_embed(interaction, "⏸️ Paused", ephemeral=True)
            elif vc.is_paused(): vc.resume(); await send_embed(interaction, "▶️ Resumed", ephemeral=True)
        else:
            await interaction.response.defer()

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_whitelisted(interaction.user.id): return
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await send_embed(interaction, "⏭️ Skipped", ephemeral=True)
        else:
            await interaction.response.defer()

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_whitelisted(interaction.user.id): return
        gid = interaction.guild.id
        if gid in queues: queues[gid].clear()
        vc = interaction.guild.voice_client
        if vc: vc.stop()
        await send_embed(interaction, "⏹️ Stopped and cleared queue", ephemeral=True)

async def play_next(ctx):
    gid = ctx.guild.id
    if gid not in queues or not queues[gid]:
        # Autoplay logic
        if autoplay_modes.get(gid, False) and gid in play_history and play_history[gid]:
            await send_embed(ctx, "🔍 Autoplay: Memilih lagu rekomendasi selanjutnya...")
            last_url = play_history[gid][-1]
            try:
                ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'extract_flat': True}
                # yt_dlp related search syntax
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, last_url, download=False)
                    related = info.get('entries', [])
                    if not related:
                        # try to get related by URL trick if direct extraction fails
                        pass
                
                # Sederhananya, jika autoplay aktif dan antrean habis, kita ulangi secara random dari history
                # Idealnya: kita fetch YouTube Mix. Tapi karena batas API, kita pakai algoritma Mix internal
                if len(play_history[gid]) > 0:
                    random_past = random.choice(play_history[gid])
                    query = f"mix {random_past}"
                    next_info = await search_yt(query)
                    if next_info:
                        if gid not in queues: queues[gid] = []
                        queues[gid].append({
                            'title': next_info.get('title', 'Unknown'),
                            'artist': next_info.get('uploader', 'Autoplay'),
                            'url': next_info.get('webpage_url', next_info.get('url')),
                            'thumbnail': next_info.get('thumbnail', None),
                            'duration': next_info.get('duration', 0),
                            'source': 'youtube',
                            'requester': ctx.author if ctx else None,
                            'voice_channel': ctx.guild.voice_client.channel if ctx and ctx.guild.voice_client else None
                        })
                        await play_next(ctx)
                        return
            except Exception as e:
                logging.error(f"Autoplay error: {e}")
                
        vc = ctx.guild.voice_client
        if vc: await vc.disconnect()
        return

    # Looping logic handled in after_play
    item = queues[gid][0]
    
    url = item['url']
    source = item['source']
    
    if source == 'spotify':
        # Need to fetch audio from YT
        query = f"{item['title']} {item['artist']} audio"
        yt_info = await search_yt(query)
        if yt_info:
            audio_url = yt_info['url']
        else:
            queues[gid].pop(0)
            await play_next(ctx)
            return
    else:
        # direct stream url
        yt_info = await search_yt(url)
        if yt_info:
            audio_url = yt_info['url']
        else:
            queues[gid].pop(0)
            await play_next(ctx)
            return
            
    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -c:v mp4v'
    }
    
    start_time_offset = seek_times.pop(gid, 0)
    if start_time_offset > 0:
        ffmpeg_options['before_options'] += f' -ss {start_time_offset}'
        
    audio_filters = []
    
    f_mode = active_filters.get(gid, 'clear')
    if f_mode == 'bassboost': audio_filters.append('bass=g=15')
    elif f_mode == 'nightcore': audio_filters.append('atempo=1.25,asetrate=44100*1.25')
    elif f_mode == 'vaporwave': audio_filters.append('atempo=0.8,asetrate=44100*0.8,aecho=0.8:0.9:1000:0.3')
    elif f_mode == '8d': audio_filters.append('apulsator=hz=0.125')
    
    dur = int(item.get('duration', 0))
    if dur > 10:
        audio_filters.append('afade=t=in:st=0:d=3')
        if start_time_offset == 0:
            audio_filters.append(f'afade=t=out:st={dur-3}:d=3')
            
    if audio_filters:
        ffmpeg_options['options'] += f' -af "{",".join(audio_filters)}"'
    
    vc = ctx.guild.voice_client
    if not vc:
        vc = await item['voice_channel'].connect(self_deaf=True)
        
    current_song_info[gid] = item
    if start_time_offset > 0:
        current_song_info[gid]['start_time'] = datetime.now().timestamp() - start_time_offset
    else:
        current_song_info[gid]['start_time'] = datetime.now().timestamp()
    
    if gid not in play_history: play_history[gid] = []
    play_history[gid].append(url)
    if len(play_history[gid]) > 10: play_history[gid].pop(0)

    def after_play(error):
        if error: logging.error(f"Player error: {error}")
        
        l_mode = loop_modes.get(gid, 'OFF')
        if gid in queues and len(queues[gid]) > 0:
            finished = queues[gid].pop(0)
            if l_mode == 'TRACK': queues[gid].insert(0, finished)
            elif l_mode == 'QUEUE': queues[gid].append(finished)
            
        asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

    vc.play(PCMVolumeTransformer(FFmpegPCMAudio(audio_url, **ffmpeg_options), volume=volumes.get(gid, 0.5)), after=after_play)
    
    record_track_stat(item['requester'].id, item['title'], item['duration'], item['voice_channel'])
    
    embed = discord.Embed(title=f"Now Playing", description=f"[{item['title']}]({item['url']})", color=discord.Color.green())
    embed.add_field(name="Artist", value=item['artist'], inline=True)
    embed.add_field(name="Duration", value=f"{int(item['duration']//60)}:{int(item['duration']%60):02d}", inline=True)
    if item['thumbnail']: embed.set_thumbnail(url=item['thumbnail'])
    
    source_icon = "🟢" if source == 'spotify' else "🔴"
    embed.set_footer(text=f"Requested by {item['requester'].display_name} | {source_icon} {source.upper()}")
    
    await ctx.send(embed=embed, view=MusicPlayerControls(ctx))

# --- Web Server API ---
@web.middleware
async def cors_middleware(request, handler):
    if request.method == 'OPTIONS':
        response = web.Response(status=200)
    else:
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            response = exc
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

async def api_premium_status(request):
    data = {}
    for gid in queues.keys():
        guild = bot.get_guild(gid)
        vc = guild.voice_client if guild else None
        if vc and (vc.is_playing() or vc.is_paused()) and gid in current_song_info:
            info = current_song_info[gid]
            elapsed = int(datetime.now().timestamp() - info.get('start_time', 0))
            data[str(gid)] = {
                'title': info.get('title', 'Unknown'),
                'artist': info.get('artist', 'Unknown'),
                'duration': info.get('duration', 0),
                'elapsed': elapsed,
                'source': info.get('source', 'unknown'),
                'queue': [item['title'] for item in queues.get(gid, [])][:10],
                'volume': volumes.get(gid, 0.5),
                'loop': loop_modes.get(gid, 'OFF'),
                'is_paused': vc.is_paused()
            }
    return web.json_response(data)

async def api_whitelist(request):
    users = load_json(WHITELIST_FILE, [])
    return web.json_response({'whitelisted_users': users})

async def api_premium_skip(request):
    try:
        data = await request.json()
        gid = int(data.get('guild_id'))
        guild = bot.get_guild(gid)
        if guild and guild.voice_client:
            vc = guild.voice_client
            if vc.is_playing() or vc.is_paused():
                vc.stop()
                return web.json_response({'status': 'skipped'})
        return web.json_response({'error': 'Not playing'}, status=400)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def api_premium_pause(request):
    try:
        data = await request.json()
        gid = int(data.get('guild_id'))
        guild = bot.get_guild(gid)
        if guild and guild.voice_client:
            vc = guild.voice_client
            if vc.is_playing():
                vc.pause()
                return web.json_response({'status': 'paused'})
            elif vc.is_paused():
                vc.resume()
                return web.json_response({'status': 'resumed'})
        return web.json_response({'error': 'Not playing'}, status=400)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def api_whitelist_add(request):
    try:
        data = await request.json()
        uid = str(data.get('user_id'))
        users = load_json(WHITELIST_FILE, [])
        if uid not in users:
            users.append(uid)
            save_json(WHITELIST_FILE, users)
            return web.json_response({'status': 'added', 'user_id': uid})
        return web.json_response({'status': 'already_exists'})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def api_whitelist_remove(request):
    try:
        data = await request.json()
        uid = str(data.get('user_id'))
        users = load_json(WHITELIST_FILE, [])
        if uid in users:
            users.remove(uid)
            save_json(WHITELIST_FILE, users)
            return web.json_response({'status': 'removed', 'user_id': uid})
        return web.json_response({'status': 'not_found'})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def start_web_server():
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get('/api/premium_status', api_premium_status)
    app.router.add_get('/api/whitelist', api_whitelist)
    app.router.add_post('/api/premium_skip', api_premium_skip)
    app.router.add_post('/api/premium_pause', api_premium_pause)
    app.router.add_post('/api/whitelist_add', api_whitelist_add)
    app.router.add_post('/api/whitelist_remove', api_whitelist_remove)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8082)
    await site.start()
    logging.info("Premium Web API started on port 8082")
# --- End Web Server API ---

@bot.group(invoke_without_command=True)
@commands.has_permissions(administrator=True)
async def whitelist(ctx):
    await send_embed(ctx, "Gunakan `!whitelist add @user`, `!whitelist remove @user`, atau `!whitelist list`")

@whitelist.command(name="add")
@commands.has_permissions(administrator=True)
async def whitelist_add_cmd(ctx, member: discord.Member):
    uid = str(member.id)
    users = load_json(WHITELIST_FILE, [])
    if uid not in users:
        users.append(uid)
        save_json(WHITELIST_FILE, users)
        await send_embed(ctx, f"✅ {member.mention} telah ditambahkan ke whitelist Premium Music!")
    else:
        await send_embed(ctx, f"⚠️ {member.display_name} sudah ada di whitelist.")

@whitelist.command(name="remove")
@commands.has_permissions(administrator=True)
async def whitelist_remove_cmd(ctx, member: discord.Member):
    uid = str(member.id)
    users = load_json(WHITELIST_FILE, [])
    if uid in users:
        users.remove(uid)
        save_json(WHITELIST_FILE, users)
        await send_embed(ctx, f"❌ {member.mention} telah dihapus dari whitelist.")
    else:
        await send_embed(ctx, f"⚠️ {member.display_name} tidak ada di whitelist.")

@whitelist.command(name="list")
@commands.has_permissions(administrator=True)
async def whitelist_list_cmd(ctx):
    users = load_json(WHITELIST_FILE, [])
    if not users:
        await send_embed(ctx, "Daftar whitelist masih kosong.")
        return
    
    msg = "**Daftar Member Premium:**\n"
    for uid in users:
        msg += f"- <@{uid}>\n"
    await ctx.send(msg)

@bot.command(aliases=['p'])
@commands.check(check_whitelist)
async def play(ctx, *, query: str):
    if not ctx.author.voice: return
    vc_channel = ctx.author.voice.channel
    
    gid = ctx.guild.id
    if gid not in queues: queues[gid] = []
    
    is_spotify = "open.spotify.com" in query
    
    await send_embed(ctx, "🔍 Fetching track data...")
    
    items_to_add = []
    if is_spotify and sp:
        if "track" in query:
            track = sp.track(query)
            items_to_add.append({
                'title': track['name'],
                'artist': track['artists'][0]['name'],
                'url': track['external_urls']['spotify'],
                'thumbnail': track['album']['images'][0]['url'] if track['album']['images'] else None,
                'duration': int(track['duration_ms'] / 1000),
                'source': 'spotify',
                'requester': ctx.author,
                'voice_channel': vc_channel
            })
            add_music_stat(ctx.author.id, 'spotify')
        elif "playlist" in query:
            playlist_id = query.split("/")[-1].split("?")[0]
            tracks = sp.playlist_tracks(playlist_id)
            for item in tracks['items']:
                t = item['track']
                items_to_add.append({
                    'title': t['name'],
                    'artist': t['artists'][0]['name'],
                    'url': t['external_urls']['spotify'],
                    'thumbnail': t['album']['images'][0]['url'] if t['album']['images'] else None,
                    'duration': int(t['duration_ms'] / 1000),
                    'source': 'spotify',
                    'requester': ctx.author,
                    'voice_channel': vc_channel
                })
            add_music_stat(ctx.author.id, 'spotify')
    else:
        info = await search_yt(query)
        if info:
            items_to_add.append({
                'title': info.get('title', 'Unknown'),
                'artist': info.get('uploader', 'Unknown'),
                'url': info.get('webpage_url', query),
                'thumbnail': info.get('thumbnail', None),
                'duration': info.get('duration', 0),
                'source': 'youtube',
                'requester': ctx.author,
                'voice_channel': vc_channel
            })
            add_music_stat(ctx.author.id, 'youtube')
            
    if not items_to_add:
        await send_embed(ctx, "❌ Track not found.")
        return
        
    queues[gid].extend(items_to_add)
    await send_embed(ctx, f"✅ Added {len(items_to_add)} track(s) to queue.")
    
    vc = ctx.guild.voice_client
    if not vc or not vc.is_playing():
        await play_next(ctx)

@bot.command(aliases=['q'])
@commands.check(check_whitelist)
async def queue(ctx):
    gid = ctx.guild.id
    if gid not in queues or not queues[gid]:
        await send_embed(ctx, "Queue is empty.")
        return
        
    q_list = queues[gid][:10]
    res = "**Current Queue:**\n\n"
    for i, item in enumerate(q_list):
        res += f"`{i+1}.` **{item['title']}** - {item['artist']}\n"
        
    if len(queues[gid]) > 10:
        res += f"\n...and {len(queues[gid]) - 10} more tracks."
        
    await ctx.send(res)

@bot.command(aliases=['np'])
@commands.check(check_whitelist)
async def nowplaying(ctx):
    gid = ctx.guild.id
    if gid in current_song_info and ctx.guild.voice_client and (ctx.guild.voice_client.is_playing() or ctx.guild.voice_client.is_paused()):
        item = current_song_info[gid]
        
        # Build initial embed
        def get_embed(visualizer_frame):
            elapsed = int(datetime.now().timestamp() - item['start_time'])
            dur = item['duration']
            progress = min(1.0, max(0.0, elapsed / dur)) if dur > 0 else 0
            
            bar_len = 20
            filled = int(bar_len * progress)
            bar = '▬' * filled + '🔘' + '▬' * (bar_len - filled - 1)
            
            def format_time(s):
                m, s = divmod(int(s), 60)
                h, m = divmod(m, 60)
                return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
                
            time_str = f"[{format_time(elapsed)} / {format_time(dur)}]"
            
            embed = discord.Embed(title="Now Playing", description=f"""**[{item['title']}]({item['url']})**
`{bar}` {time_str}

**Visualizer:**
`{visualizer_frame}`""", color=discord.Color.green())
            if item['thumbnail']: embed.set_thumbnail(url=item['thumbnail'])
            return embed
            
        visualizers = [
            "ılılıll|̲̅̅●̲̅̅|̲̅̅=̲̅̅|̲̅̅●̲̅̅|llılılı",
            "ıllılıl|̲̅̅●̲̅̅|̲̅̅=̲̅̅|̲̅̅●̲̅̅|lılıllı",
            "lıllılı|̲̅̅●̲̅̅|̲̅̅=̲̅̅|̲̅̅●̲̅̅|ılıllıl",
            "ıllllıl|̲̅̅●̲̅̅|̲̅̅=̲̅̅|̲̅̅●̲̅̅|lıllllı"
        ]
        
        msg = await ctx.send(embed=get_embed(visualizers[0]))
        
        # Animate for a short duration (e.g. 15 seconds) to avoid rate limits
        for i in range(1, 6):
            await asyncio.sleep(3)
            # check if still playing the same song
            if gid not in current_song_info or current_song_info[gid] != item: break
            try:
                await msg.edit(embed=get_embed(visualizers[i % len(visualizers)]))
            except:
                break
            
    else:
        await send_embed(ctx, "Nothing is currently playing.")

@bot.command()
@commands.check(check_whitelist)
async def profile(ctx, member: discord.Member = None):
    target = member or ctx.author
    uid = str(target.id)
    stats = load_json(MUSIC_STATS_FILE)
    
    if uid not in stats:
        await send_embed(ctx, f"{target.display_name} hasn't played any music yet.")
        return
        
    user_stat = stats[uid]
    
    embed = discord.Embed(title=f"🎧 Music Profile: {target.display_name}", color=discord.Color.purple())
    embed.add_field(name="Total Plays", value=str(user_stat.get('total_plays', 0)))
    d_mins = int(user_stat.get('total_duration', 0) // 60)
    embed.add_field(name="Total Listen Time", value=f"{d_mins} minutes")
    
    fav_src = max(user_stat.get('favorite_source', {'unknown':0}).items(), key=lambda x: x[1], default=('None', 0))[0]
    embed.add_field(name="Favorite Source", value=fav_src.upper())
    
    top_tracks = sorted(user_stat.get('tracks', {}).items(), key=lambda x: x[1], reverse=True)[:3]
    top_tracks_str = "\n".join([f"- {t} ({c}x)" for t, c in top_tracks]) if top_tracks else "None"
    embed.add_field(name="Top 3 Tracks", value=top_tracks_str, inline=False)
    
    if target.display_avatar:
        embed.set_thumbnail(url=target.display_avatar.url)
        
    await ctx.send(embed=embed)

@bot.command(aliases=['ly', 'lyric'])
@commands.check(check_whitelist)
async def lyrics(ctx, *, query: str = None):
    gid = ctx.guild.id
    if not query:
        if gid in current_song_info:
            query = f"{current_song_info[gid]['title']} {current_song_info[gid]['artist']}"
        else:
            await send_embed(ctx, "No song is playing. Please provide a title: `!lyrics <title>`")
            return
            
    await send_embed(ctx, f"🔍 Searching lyrics for: {query}")
    
    try:
        search_url = f"https://genius.com/api/search/multi?per_page=1&q={query}"
        async with aiohttp.ClientSession() as session:
            async with session.get(search_url) as response:
                data = await response.json()
                
        song_path = data['response']['sections'][0]['hits'][0]['result']['path']
        lyrics_url = f"https://genius.com{song_path}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(lyrics_url) as lyrics_page:
                html = await lyrics_page.text()
                
        soup = BeautifulSoup(html, 'html.parser')
        lyrics_div = soup.find('div', class_='lyrics') or soup.find_all('div', class_='Lyrics__Container-sc-1ynbvzw-6')
        
        if lyrics_div:
            if isinstance(lyrics_div, list):
                lyrics_text = '\n'.join([div.get_text(separator='\n') for div in lyrics_div])
            else:
                lyrics_text = lyrics_div.get_text(separator='\n')
                
            if len(lyrics_text) <= 2000:
                await send_embed(ctx, f"**Lyrics: {query}**\n\n{lyrics_text}")
            else:
                chunks = [lyrics_text[i:i+1900] for i in range(0, len(lyrics_text), 1900)]
                for i, chunk in enumerate(chunks):
                    await send_embed(ctx, f"**Lyrics: {query}** (Part {i+1})\n\n{chunk}")
        else:
            await send_embed(ctx, "❌ Lyrics not found or track is Instrumental.")
    except Exception as e:
        await send_embed(ctx, "❌ Error fetching lyrics. It might not exist.")

@bot.command()
@commands.check(check_whitelist)
async def filter(ctx, f_type: str = 'clear'):
    f_type = f_type.lower()
    valid_filters = ['bassboost', 'nightcore', 'vaporwave', '8d', 'clear']
    if f_type not in valid_filters:
        await send_embed(ctx, f"❌ Filter tidak valid! Pilihan: {', '.join(valid_filters)}")
        return
        
    active_filters[ctx.guild.id] = f_type
    await send_embed(ctx, f"🎛️ Audio Filter disetel ke: **{f_type.upper()}**\n*(Efek akan terasa di lagu berikutnya atau gunakan `!seek 0` untuk restart lagu saat ini)*")

@bot.command(aliases=['vol'])
@commands.check(check_whitelist)
async def volume(ctx, vol: int):
    if vol < 0 or vol > 100:
        await send_embed(ctx, "❌ Volume harus antara 0 - 100.")
        return
    volumes[ctx.guild.id] = vol / 100.0
    vc = ctx.guild.voice_client
    if vc and vc.source:
        vc.source.volume = volumes[ctx.guild.id]
    await send_embed(ctx, f"🔊 Volume diatur ke **{vol}%**")

@bot.command()
@commands.check(check_whitelist)
async def loop(ctx, mode: str = None):
    gid = ctx.guild.id
    current_mode = loop_modes.get(gid, 'OFF')
    
    if mode is None:
        if current_mode == 'OFF': new_mode = 'TRACK'
        elif current_mode == 'TRACK': new_mode = 'QUEUE'
        else: new_mode = 'OFF'
    else:
        mode = mode.upper()
        if mode not in ['OFF', 'TRACK', 'QUEUE']:
            await send_embed(ctx, "❌ Pilihan loop: OFF, TRACK, QUEUE")
            return
        new_mode = mode
        
    loop_modes[gid] = new_mode
    await send_embed(ctx, f"🔁 Loop mode: **{new_mode}**")

@bot.command()
@commands.check(check_whitelist)
async def seek(ctx, time_str: str):
    try:
        parts = time_str.split(':')
        if len(parts) == 2:
            total_seconds = int(parts[0]) * 60 + int(parts[1])
        else:
            total_seconds = int(time_str)
            
        gid = ctx.guild.id
        if gid not in current_song_info or not ctx.guild.voice_client:
            await send_embed(ctx, "❌ Tidak ada lagu yang diputar.")
            return
            
        dur = current_song_info[gid].get('duration', 0)
        if total_seconds > dur:
            await send_embed(ctx, "❌ Waktu melebihi durasi lagu.")
            return
            
        seek_times[gid] = total_seconds
        
        # Re-queue current song
        if gid not in queues: queues[gid] = []
        queues[gid].insert(0, current_song_info[gid])
        
        ctx.guild.voice_client.stop()
        await send_embed(ctx, f"⏩ Melompat ke **{time_str}**...")
        
    except ValueError:
        await send_embed(ctx, "❌ Format waktu salah! Contoh: `!seek 1:30` atau `!seek 90`")

@bot.command()
@commands.check(check_whitelist)
async def autoplay(ctx):
    gid = ctx.guild.id
    current = autoplay_modes.get(gid, False)
    autoplay_modes[gid] = not current
    status = "ON 🟢" if not current else "OFF 🔴"
    await send_embed(ctx, f"📻 Autoplay Mode is now **{status}**")

@bot.group(invoke_without_command=True)
@commands.check(check_whitelist)
async def playlist(ctx):
    await send_embed(ctx, "Gunakan: `!playlist save <nama>`, `!playlist list`, `!playlist play <nama>`")

@playlist.command(name="save")
@commands.check(check_whitelist)
async def playlist_save(ctx, name: str):
    gid = ctx.guild.id
    uid = str(ctx.author.id)
    if gid not in queues or not queues[gid]:
        await send_embed(ctx, "❌ Antrean kosong!")
        return
        
    pl = load_json('playlists.json', {})
    if uid not in pl: pl[uid] = {}
    
    pl[uid][name] = queues[gid].copy()
    save_json('playlists.json', pl)
    await send_embed(ctx, f"💾 Berhasil menyimpan {len(queues[gid])} lagu ke playlist **{name}**!")

@playlist.command(name="list")
@commands.check(check_whitelist)
async def playlist_list(ctx):
    uid = str(ctx.author.id)
    pl = load_json('playlists.json', {})
    user_pl = pl.get(uid, {})
    
    if not user_pl:
        await send_embed(ctx, "Kamu belum punya playlist pribadi.")
        return
        
    msg = "**Daftar Playlist Kamu:**\n"
    for name, tracks in user_pl.items():
        msg += f"- **{name}** ({len(tracks)} lagu)\n"
    await ctx.send(msg)

@playlist.command(name="play")
@commands.check(check_whitelist)
async def playlist_play(ctx, name: str):
    uid = str(ctx.author.id)
    pl = load_json('playlists.json', {})
    user_pl = pl.get(uid, {})
    
    if name not in user_pl:
        await send_embed(ctx, f"❌ Playlist '{name}' tidak ditemukan.")
        return
        
    if not ctx.author.voice:
        await send_embed(ctx, "Masuk voice channel dulu!")
        return
        
    gid = ctx.guild.id
    if gid not in queues: queues[gid] = []
    
    queues[gid].extend(user_pl[name])
    await send_embed(ctx, f"✅ Berhasil memuat {len(user_pl[name])} lagu dari playlist **{name}**!")
    
    vc = ctx.guild.voice_client
    if not vc or not vc.is_playing():
        await play_next(ctx)

@bot.command()
@commands.check(check_whitelist)
async def quote(ctx, *, text: str):
    gid = ctx.guild.id
    if gid not in current_song_info:
        await send_embed(ctx, "❌ Tidak ada lagu yang diputar.")
        return
        
    item = current_song_info[gid]
    thumbnail_url = item.get('thumbnail')
    title = item.get('title', 'Unknown')
    artist = item.get('artist', 'Unknown')
    
    await send_embed(ctx, "🎨 Membuat Lyric Card...")
    
    try:
        # Download thumbnail
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail_url) as resp:
                if resp.status == 200:
                    img_data = await resp.read()
                    
        # Generate image using Pillow
        base_img = Image.open(io.BytesIO(img_data)).convert("RGBA")
        base_img = base_img.resize((800, 800))
        base_img = base_img.filter(ImageFilter.GaussianBlur(15))
        
        # Darken background
        overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 150))
        base_img = Image.alpha_composite(base_img, overlay)
        
        draw = ImageDraw.Draw(base_img)
        # Try to load a font, otherwise use default
        try:
            font_large = ImageFont.truetype("arial.ttf", 50)
            font_small = ImageFont.truetype("arial.ttf", 30)
        except:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()
            
        # Draw quote
        draw.text((100, 300), f'"{text}"', font=font_large, fill="white")
        draw.text((100, 400), f"— {title}", font=font_small, fill="lightgray")
        draw.text((100, 450), f"by {artist}", font=font_small, fill="gray")
        
        # Save to buffer
        buf = io.BytesIO()
        base_img.save(buf, format="PNG")
        buf.seek(0)
        
        await ctx.send(file=discord.File(buf, filename="quote.png"))
    except Exception as e:
        await send_embed(ctx, f"❌ Gagal membuat gambar: {e}")

@bot.command()
@commands.check(check_whitelist)
async def skip(ctx):
    vc = ctx.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await send_embed(ctx, "⏭️ Skipped")

@bot.command()
@commands.check(check_whitelist)
async def stop(ctx):
    gid = ctx.guild.id
    if gid in queues: queues[gid].clear()
    vc = ctx.guild.voice_client
    if vc:
        vc.stop()
        await vc.disconnect()
        await send_embed(ctx, "⏹️ Stopped playback and disconnected.")


@bot.event
async def on_ready():
    bot.loop.create_task(start_web_server())
    logging.info(f"Custom Premium Music Bot logged in as {bot.user}")

if __name__ == "__main__":
    bot.run(DISCORD_API_KEY)
