import discord
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

def load_json(filepath, default_val=None):
    if default_val is None: default_val = {}
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except: return default_val
    return default_val

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f)

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
            if vc.is_playing(): vc.pause(); await interaction.response.send_message("⏸️ Paused", ephemeral=True)
            elif vc.is_paused(): vc.resume(); await interaction.response.send_message("▶️ Resumed", ephemeral=True)
        else:
            await interaction.response.defer()

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_whitelisted(interaction.user.id): return
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏭️ Skipped", ephemeral=True)
        else:
            await interaction.response.defer()

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_whitelisted(interaction.user.id): return
        gid = interaction.guild.id
        if gid in queues: queues[gid].clear()
        vc = interaction.guild.voice_client
        if vc: vc.stop()
        await interaction.response.send_message("⏹️ Stopped and cleared queue", ephemeral=True)

async def play_next(ctx):
    gid = ctx.guild.id
    if gid not in queues or not queues[gid]:
        # Autoplay logic
        if autoplay_modes.get(gid, False) and gid in play_history and play_history[gid]:
            await ctx.send("🔍 Autoplay: Memilih lagu rekomendasi selanjutnya...")
            last_url = play_history[gid][-1]
            # Advanced Autoplay would fetch related tracks here via yt-dlp 
            # For simplicity, we fallback to a smart algorithm if implemented, otherwise stop
        
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
    
    vc = ctx.guild.voice_client
    if not vc:
        vc = await item['voice_channel'].connect(self_deaf=True)
        
    current_song_info[gid] = item
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

@bot.command(aliases=['p'])
@commands.check(check_whitelist)
async def play(ctx, *, query: str):
    if not ctx.author.voice: return
    vc_channel = ctx.author.voice.channel
    
    gid = ctx.guild.id
    if gid not in queues: queues[gid] = []
    
    is_spotify = "open.spotify.com" in query
    
    await ctx.send("🔍 Fetching track data...")
    
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
        await ctx.send("❌ Track not found.")
        return
        
    queues[gid].extend(items_to_add)
    await ctx.send(f"✅ Added {len(items_to_add)} track(s) to queue.")
    
    vc = ctx.guild.voice_client
    if not vc or not vc.is_playing():
        await play_next(ctx)

@bot.command(aliases=['q'])
@commands.check(check_whitelist)
async def queue(ctx):
    gid = ctx.guild.id
    if gid not in queues or not queues[gid]:
        await ctx.send("Queue is empty.")
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
        
        embed = discord.Embed(title="Now Playing", description=f"**[{item['title']}]({item['url']})**\n`{bar}` {time_str}", color=discord.Color.green())
        if item['thumbnail']: embed.set_thumbnail(url=item['thumbnail'])
        await ctx.send(embed=embed)
    else:
        await ctx.send("Nothing is currently playing.")

@bot.command()
@commands.check(check_whitelist)
async def profile(ctx, member: discord.Member = None):
    target = member or ctx.author
    uid = str(target.id)
    stats = load_json(MUSIC_STATS_FILE)
    
    if uid not in stats:
        await ctx.send(f"{target.display_name} hasn't played any music yet.")
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
            await ctx.send("No song is playing. Please provide a title: `!lyrics <title>`")
            return
            
    await ctx.send(f"🔍 Searching lyrics for: {query}")
    
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
                await ctx.send(f"**Lyrics: {query}**\n\n{lyrics_text}")
            else:
                chunks = [lyrics_text[i:i+1900] for i in range(0, len(lyrics_text), 1900)]
                for i, chunk in enumerate(chunks):
                    await ctx.send(f"**Lyrics: {query}** (Part {i+1})\n\n{chunk}")
        else:
            await ctx.send("❌ Lyrics not found or track is Instrumental.")
    except Exception as e:
        await ctx.send("❌ Error fetching lyrics. It might not exist.")

@bot.command()
@commands.check(check_whitelist)
async def skip(ctx):
    vc = ctx.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await ctx.send("⏭️ Skipped")

@bot.command()
@commands.check(check_whitelist)
async def stop(ctx):
    gid = ctx.guild.id
    if gid in queues: queues[gid].clear()
    vc = ctx.guild.voice_client
    if vc:
        vc.stop()
        await vc.disconnect()
        await ctx.send("⏹️ Stopped playback and disconnected.")

@bot.command()
@commands.has_permissions(administrator=True)
async def whitelist(ctx, member: discord.Member):
    users = load_json(WHITELIST_FILE, [])
    uid = str(member.id)
    if uid not in users:
        users.append(uid)
        save_json(WHITELIST_FILE, users)
        await ctx.send(f"✅ {member.display_name} added to Premium Whitelist.")
    else:
        users.remove(uid)
        save_json(WHITELIST_FILE, users)
        await ctx.send(f"❌ {member.display_name} removed from Premium Whitelist.")

@bot.event
async def on_ready():
    bot.loop.create_task(start_web_server())
    logging.info(f"Custom Premium Music Bot logged in as {bot.user}")

if __name__ == "__main__":
    bot.run(DISCORD_API_KEY)
