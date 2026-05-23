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


import os
import asyncio
import yt_dlp as youtube_dl
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
import sqlite3


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# NOTE: Use a different API key if you want to run this alongside your main bot
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_API_KEY = os.getenv('MUSIC_BOT_TOKEN', 'YOUR_MUSIC_BOT_TOKEN_HERE') 
SPOTIPY_CLIENT_ID = 'your_spotify_client_id'  # Replace with your actual Client ID
SPOTIPY_CLIENT_SECRET = 'your_spotify_client_secret'  # Replace with your actual Client Secret

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True # needed for checkbots
client = discord.Client(intents=intents)

voice_clients = {}
current_song_info = {}
queues = {} # guild_id -> list of query strings
session_owners = {} # guild_id -> user_id
loop_modes = {} # guild_id -> 'OFF', 'TRACK', 'QUEUE'
voice_join_times = {} # user_id -> datetime
volumes = {} # guild_id -> float volume


class MusicControls(discord.ui.View):
    def __init__(self, gid):
        super().__init__(timeout=None)
        self.gid = gid

    @discord.ui.button(label="Pause/Resume", style=discord.ButtonStyle.primary, emoji="⏯️")
    async def toggle_pause(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.gid in voice_clients:
            vc = voice_clients[self.gid]
            if vc.is_playing():
                vc.pause()
                await send_embed(interaction, "Lagu di-pause.", ephemeral=True)
            elif vc.is_paused():
                vc.resume()
                await send_embed(interaction, "Lagu di-resume.", ephemeral=True)
            else:
                await send_embed(interaction, "Tidak ada lagu yang diputar.", ephemeral=True)
        else:
            await send_embed(interaction, "Bot tidak terhubung.", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_song(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.gid in voice_clients:
            vc = voice_clients[self.gid]
            if vc.is_playing() or vc.is_paused():
                vc.stop()
                await send_embed(interaction, "Lagu di-skip.", ephemeral=True)
            else:
                await send_embed(interaction, "Tidak ada lagu untuk di-skip.", ephemeral=True)
        else:
            await send_embed(interaction, "Bot tidak terhubung.", ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop_song(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.gid in voice_clients:
            vc = voice_clients[self.gid]
            if self.gid in queues: queues[self.gid].clear()
            if vc.is_playing() or vc.is_paused():
                vc.stop()
            await send_embed(interaction, "Musik dihentikan dan antrean dibersihkan.", ephemeral=True)
        else:
            await send_embed(interaction, "Bot tidak terhubung.", ephemeral=True)

# Spotify client
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET))



async def afk_timer(gid, vc):
    await asyncio.sleep(300) # 5 mins
    if gid in voice_clients and voice_clients[gid] == vc:
        if not vc.is_playing() and not vc.is_paused() and (gid not in queues or not queues[gid]):
            await vc.disconnect()
            if gid in voice_clients: del voice_clients[gid]
            if gid in session_owners: del session_owners[gid]
            if gid in loop_modes: del loop_modes[gid]
            logging.info(f"Disconnected from {gid} due to AFK timeout.")

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

async def api_status(request):
    data = {}
    for gid, vc in voice_clients.items():
        if vc.is_playing() and gid in current_song_info:
            info = current_song_info[gid]
            elapsed = int(datetime.now().timestamp() - info.get('start_time', 0))
            data[str(gid)] = {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'elapsed': elapsed,
                'queue': [item['query'] for item in queues.get(gid, [])][:10],
                'volume': volumes.get(gid, 0.15),
                'loop': loop_modes.get(gid, 'OFF'),
                'is_paused': vc.is_paused()
            }
    return web.json_response(data)

async def api_pause(request):
    try:
        data = await request.json()
        gid = int(data.get('guild_id'))
        if gid in voice_clients:
            vc = voice_clients[gid]
            if vc.is_playing():
                vc.pause()
                return web.json_response({'status': 'paused'})
            elif vc.is_paused():
                vc.resume()
                return web.json_response({'status': 'resumed'})
        return web.json_response({'error': 'Not connected or playing'}, status=400)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def api_skip(request):
    try:
        data = await request.json()
        gid = int(data.get('guild_id'))
        if gid in voice_clients:
            vc = voice_clients[gid]
            if vc.is_playing() or vc.is_paused():
                vc.stop()
                return web.json_response({'status': 'skipped'})
        return web.json_response({'error': 'Not connected or playing'}, status=400)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def api_volume(request):
    try:
        data = await request.json()
        gid = int(data.get('guild_id'))
        vol = int(data.get('volume', 15))
        if vol < 0 or vol > 100:
            return web.json_response({'error': 'Invalid volume'}, status=400)
        volumes[gid] = vol / 100.0
        if gid in voice_clients and hasattr(voice_clients[gid], 'source') and voice_clients[gid].source:
            voice_clients[gid].source.volume = volumes[gid]
        return web.json_response({'status': 'volume_set'})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def start_web_server():
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get('/api/status', api_status)
    app.router.add_post('/api/pause', api_pause)
    app.router.add_post('/api/skip', api_skip)
    app.router.add_post('/api/volume', api_volume)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logging.info("Web API started on port 8080")

@client.event
async def on_ready():
    client.loop.create_task(start_web_server())
    logging.info(f'Music bot has logged in as {client.user}')

@client.event
async def on_voice_state_update(member, before, after):
    if before.channel is None and after.channel is not None:
        # Joined a voice channel
        voice_join_times[member.id] = datetime.now()
    elif before.channel is not None and after.channel is None:
        # Left a voice channel
        if member.id in voice_join_times:
            del voice_join_times[member.id]

async def send_long_message(channel, message):
    if len(message) <= 2000:
        await channel.send(message)
    else:
        for i in range(0, len(message), 2000):
            await channel.send(message[i:i+2000])



@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('!w2evolume '):
        gid = message.guild.id
        vol_str = message.content[len('!w2evolume '):].strip()
        try:
            vol = int(vol_str)
            if vol < 0 or vol > 100:
                await send_embed(message.channel, "Volume harus antara 0 sampai 100.")
                return
            
            volumes[gid] = vol / 100.0
            if gid in voice_clients and voice_clients[gid].source:
                voice_clients[gid].source.volume = volumes[gid]
            await send_embed(message.channel, f"Volume diubah ke {vol}%")
        except ValueError:
            await send_embed(message.channel, "Format volume salah. Gunakan angka, misal: `!w2evolume 50`")

    if message.content.startswith('!w2enp') or message.content.startswith('!np'):
        gid = message.guild.id
        if gid in current_song_info and gid in voice_clients and (voice_clients[gid].is_playing() or voice_clients[gid].is_paused()):
            info = current_song_info[gid]
            title = info.get('title', 'Unknown')
            start_time = info.get('start_time', 0)
            duration = info.get('duration', 0)
            
            if duration > 0 and start_time > 0:
                elapsed = int(datetime.now().timestamp() - start_time)
                progress = min(1.0, max(0.0, elapsed / duration))
                bar_len = 20
                filled = int(bar_len * progress)
                bar = '▬' * filled + '🔘' + '▬' * (bar_len - filled - 1)
                
                def format_time(seconds):
                    m, s = divmod(int(seconds), 60)
                    h, m = divmod(m, 60)
                    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
                
                time_str = f"{format_time(elapsed)} / {format_time(duration)}"
                res = f"🎵 **Now Playing:** {title}\n`[{bar}] {time_str}`"
            else:
                res = f"🎵 **Now Playing:** {title}"
            await message.channel.send(res, view=MusicControls(gid))
        else:
            await send_embed(message.channel, "Tidak ada lagu yang sedang diputar.")

    if message.content.startswith('!find '):
        if not message.mentions:
            await send_embed(message.channel, "Silakan mention user yang ingin dicari: `!find @user`")
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
            await send_embed(message.channel, f"{target.display_name} sedang berada di voice channel **{channel.name}** selama {duration_str}.\nJoin link: {link}")
        else:
            await send_embed(message.channel, f"{target.display_name} tidak sedang berada di voice channel mana pun.")

    if message.content.startswith('!checkbots'):
        active_bots = []
        idle_bots = []
        for member in message.guild.members:
            if member.bot and member.id != client.user.id:
                if member.voice and member.voice.channel:
                    active_bots.append(f"{member.name} (di {member.voice.channel.name})")
                else:
                    idle_bots.append(member.name)
        
        res = "**Music Bot Checker:**\n"
        res += "**Sedang Digunakan:**\n" + ("\n".join(active_bots) if active_bots else "-") + "\n\n"
        res += "**Tersedia (Idle):**\n" + ("\n".join(idle_bots) if idle_bots else "-")
        await message.channel.send(res)

    if message.content.startswith('w2esession'):
        gid = message.guild.id
        if gid not in voice_clients:
            await send_embed(message.channel, "Bot tidak sedang memutar lagu di server ini.")
            return
        owner_id = session_owners.get(gid)
        owner_name = "Unknown"
        if owner_id:
            owner = message.guild.get_member(owner_id)
            if owner: owner_name = owner.display_name
        
        q_len = len(queues.get(gid, []))
        l_mode = loop_modes.get(gid, 'OFF')
        await send_embed(message.channel, f"**Session Info:**\nOwner: {owner_name}\nLoop Mode: {l_mode}\nSongs in queue: {q_len}")

    if message.content.startswith('w2eclaim'):
        gid = message.guild.id
        if gid not in voice_clients:
            await send_embed(message.channel, "Tidak ada session yang aktif.")
            return
        
        current_owner = session_owners.get(gid)
        vc = voice_clients[gid].channel
        
        if current_owner:
            owner_member = message.guild.get_member(current_owner)
            if owner_member and owner_member in vc.members:
                await send_embed(message.channel, "Owner saat ini masih berada di dalam voice channel. Tidak bisa di-claim.")
                return
                
        if message.author not in vc.members:
            await send_embed(message.channel, "Kamu harus berada di voice channel yang sama dengan bot untuk melakukan claim.")
            return
            
        session_owners[gid] = message.author.id
        await send_embed(message.channel, f"{message.author.display_name} telah mengambil alih ownership session ini.")

    if message.content.startswith('w2etransfer '):
        gid = message.guild.id
        if gid not in voice_clients or session_owners.get(gid) != message.author.id:
            await send_embed(message.channel, "Kamu bukan owner dari session ini.")
            return
        
        if not message.mentions:
            await send_embed(message.channel, "Mention user yang ingin ditransfer: `w2etransfer @user`")
            return
            
        target = message.mentions[0]
        vc = voice_clients[gid].channel
        if target not in vc.members:
            await send_embed(message.channel, "Target harus berada di voice channel yang sama dengan bot.")
            return
            
        session_owners[gid] = target.id
        await send_embed(message.channel, f"Ownership telah ditransfer kepada {target.display_name}.")

    if message.content.startswith('w2eloop'):
        gid = message.guild.id
        if gid not in voice_clients:
            await send_embed(message.channel, "Tidak ada lagu yang sedang diputar.")
            return
            
        current_mode = loop_modes.get(gid, 'OFF')
        if current_mode == 'OFF':
            loop_modes[gid] = 'TRACK'
        elif current_mode == 'TRACK':
            loop_modes[gid] = 'QUEUE'
        else:
            loop_modes[gid] = 'OFF'
            
        await send_embed(message.channel, f"Loop mode diubah ke: **{loop_modes[gid]}**")

    # Music Player — !w2eplay, !w2ep, !play
    PLAY_ALIASES = ('!w2eplay ', '!w2ep ', '!play ')
    play_alias = next((p for p in PLAY_ALIASES if message.content.startswith(p)), None)
    if play_alias:
        query = message.content[len(play_alias):].strip()
        if not query:
            await send_embed(message.channel, 'Isi dulu judulnya. Contoh: `!w2eplay Judul Lagu`')
            return
        if message.author.voice is None or message.author.voice.channel is None:
            await send_embed(message.channel, 'Masuk voice channel dulu ya!')
            return
            
        voice_channel = message.author.voice.channel
        feedback_channel = client.get_channel(1332111384523309156) or message.channel
        
        gid = message.guild.id
        if gid not in queues:
            queues[gid] = []
        if gid not in loop_modes:
            loop_modes[gid] = 'OFF'
            
        if gid not in session_owners:
            session_owners[gid] = message.author.id

        await send_embed(feedback_channel, "🔍 Mencari lagu...")
        
        if "open.spotify.com/playlist" in query:
            try:
                playlist_id = query.split("/")[-1].split("?")[0]
                playlist_tracks = sp.playlist_tracks(playlist_id)
                for item in playlist_tracks['items']:
                    track = item['track']
                    track_query = f"{track['name']} {track['artists'][0]['name']}"
                    queues[gid].append({'query': track_query, 'requester': message.author.id})
                await send_embed(feedback_channel, f"✅ Menambahkan {len(playlist_tracks['items'])} lagu dari playlist Spotify!")
            except Exception as e:
                await send_embed(feedback_channel, f"Error parsing playlist: {str(e)}")
        elif "youtube.com/playlist" in query or "&list=" in query:
            try:
                ydl_opts_pl = {'extract_flat': True, 'quiet': True}
                with youtube_dl.YoutubeDL(ydl_opts_pl) as ydl:
                    info = ydl.extract_info(query, download=False)
                    if 'entries' in info:
                        added = 0
                        for entry in info['entries']:
                            if entry.get('title'):
                                queues[gid].append({'query': f"https://www.youtube.com/watch?v={entry['id']}", 'requester': message.author.id})
                                added += 1
                        await send_embed(feedback_channel, f"✅ Menambahkan {added} lagu dari playlist YouTube!")
            except Exception as e:
                await send_embed(feedback_channel, f"Error parsing YT playlist: {str(e)}")
        else:
            queues[gid].append({'query': query, 'requester': message.author.id})

        if gid not in voice_clients:
            await play_next_song(voice_channel, feedback_channel, message.guild)


    # Pause — !w2epause
    if message.content.startswith('!w2epause'):
        if message.guild.id in voice_clients:
            vc = voice_clients[message.guild.id]
            if vc.is_playing():
                vc.pause()
                await send_embed(message.channel, "⏸️ Lagu di-pause!")
            else:
                await send_embed(message.channel, "Tidak ada lagu yang sedang diputar.")
        else:
            await send_embed(message.channel, "Bot tidak terhubung ke voice channel.")

    # Resume — !w2eresume
    if message.content.startswith('!w2eresume'):
        if message.guild.id in voice_clients:
            vc = voice_clients[message.guild.id]
            if vc.is_paused():
                vc.resume()
                await send_embed(message.channel, "▶️ Lagu dilanjutkan!")
            else:
                await send_embed(message.channel, "Lagu tidak sedang di-pause.")
        else:
            await send_embed(message.channel, "Bot tidak terhubung ke voice channel.")

    # Disconnect — !w2edc
    if message.content.startswith('!w2edc'):
        gid = message.guild.id
        if gid in voice_clients:
            vc = voice_clients[gid]
            await vc.disconnect()
            del voice_clients[gid]
            if gid in queues: del queues[gid]
            if gid in session_owners: del session_owners[gid]
            if gid in loop_modes: del loop_modes[gid]
            await send_embed(message.channel, "👋 Bot keluar dari voice channel.")
        else:
            await send_embed(message.channel, "Bot tidak sedang terhubung ke voice channel.")

    # Rejoin/Restart — !w2erejoin
    if message.content.startswith('!w2erejoin'):
        gid = message.guild.id
        if gid in voice_clients:
            vc = voice_clients[gid]
            vc.stop()
            feedback_channel = client.get_channel(1332111384523309156) or message.channel
            await send_embed(feedback_channel, "🔄 Reconnecting...")
            voice_channel = message.author.voice.channel
            vc = await voice_channel.connect()
            voice_clients[gid] = vc
            await send_embed(feedback_channel, "▶️ Melanjutkan...")
            await play_next_song(voice_channel, feedback_channel, message.guild)
        else:
            if message.author.voice is None or message.author.voice.channel is None:
                await send_embed(message.channel, 'Masuk voice channel dulu!')
                return
            voice_channel = message.author.voice.channel
            feedback_channel = client.get_channel(1332111384523309156) or message.channel
            await send_embed(feedback_channel, "🔗 Reconnecting...")
            vc = await voice_channel.connect()
            voice_clients[gid] = vc
            await send_embed(feedback_channel, "▶️ Lanjut lagu...")
            await play_next_song(voice_channel, feedback_channel, message.guild)

    if message.content.startswith('!w2eclear'):
        gid = message.guild.id
        if gid in queues:
            queues[gid].clear()
            await send_embed(message.channel, "Antrean lagu berhasil dihapus (Cleared).")
        else:
            await send_embed(message.channel, "Tidak ada antrean lagu.")

    if message.content.startswith('!w2eshuffle'):
        gid = message.guild.id
        if gid in queues and len(queues[gid]) > 1:
            random.shuffle(queues[gid])
            await send_embed(message.channel, "Antrean lagu berhasil diacak (Shuffled).")
        else:
            await send_embed(message.channel, "Antrean terlalu sedikit untuk diacak.")

    if message.content.startswith('!w2eskip'):
        gid = message.guild.id
        if gid in voice_clients:
            vc = voice_clients[gid]
            if vc.is_playing():
                vc.stop()
                await send_embed(message.channel, "Lagu di-skip.")
            else:
                await send_embed(message.channel, "Tidak ada lagu yang sedang diputar.")
        else:
            await send_embed(message.channel, "Bot tidak berada di voice channel.")

    if message.content.startswith('!w2equeue'):
        gid = message.guild.id
        if gid not in queues or not queues[gid]:
            await send_embed(message.channel, "Antrean lagu kosong.")
            return
        
        q_list = queues[gid][:10]
        res = "**Daftar Antrean (Queue):**\n"
        for i, item in enumerate(q_list):
            res += f"{i+1}. {item['query']}\n"
        
        if len(queues[gid]) > 10:
            res += f"\n...dan {len(queues[gid]) - 10} lagu lainnya."
            
        await message.channel.send(res)


async def play_next_song(voice_channel, feedback_channel, guild):
    gid = guild.id
    if gid not in queues or not queues[gid]:
        await send_embed(feedback_channel, "dikarenakan ga ada queue")
        vc = voice_clients.pop(gid, None)
        if vc:
            await vc.disconnect()
        if gid in session_owners: del session_owners[gid]
        if gid in loop_modes: del loop_modes[gid]
        return
    
    # Handle Loop System
    l_mode = loop_modes.get(gid, 'OFF')
    
    item = queues[gid][0] # peek
    query = item['query']
    requester = item['requester']
    
    await play_music(voice_channel, query, requester, feedback_channel, guild)

async def play_music(voice_channel, query, requester, feedback_channel, guild):
    gid = guild.id
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'default_search': 'ytsearch',
        'quiet': True,
        'cookies': 'SID=g.a000twhngFyAPJ_nQqg-ce-glrlKoTmHAjXYuSTuO-zktHMgU_-PQ7EELFh-3VzfaqaBLGbFSAACgYKAZgSARQSFQHGX2Mih5K5Dk_usSVlDmYjjRsRZxoVAUF8yKpxVmO1AKHZ7bG1Tw-851690076',
    }
    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -c:v mp4v'
    }
    try:
        if "open.spotify.com" in query and "playlist" not in query:
            track_info = sp.track(query)
            query = f"{track_info['name']} {track_info['artists'][0]['name']}"

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            url2 = info['url']
            title = info.get('title', 'Unknown Title')
            duration = info.get('duration', 0)
            current_song_info[gid] = {'url': url2, 'title': title, 'start_time': datetime.now().timestamp(), 'duration': duration}

        if gid in voice_clients:
            vc = voice_clients[gid]
        else:
            vc = await voice_channel.connect(self_deaf=True)
            voice_clients[gid] = vc

        await send_embed(feedback_channel, f"memuterkan lagu: {title}")

        def after_play(error):
            if error:
                logging.error(f"Player error: {error}")
            
            # Handle looping logic after song ends
            l_mode = loop_modes.get(gid, 'OFF')
            if gid in queues and len(queues[gid]) > 0:
                finished_item = queues[gid].pop(0)
                if l_mode == 'TRACK':
                    # Put it back at the front
                    queues[gid].insert(0, finished_item)
                elif l_mode == 'QUEUE':
                    # Put it at the back
                    queues[gid].append(finished_item)
                    
            if gid in queues and len(queues[gid]) > 0:
                asyncio.run_coroutine_threadsafe(play_next_song(voice_channel, feedback_channel, guild), client.loop)
            else:
                asyncio.run_coroutine_threadsafe(afk_timer(gid, vc), client.loop)

        source = FFmpegPCMAudio(url2, **ffmpeg_options)
        volume_float = volumes.get(gid, 0.15)
        volume_source = PCMVolumeTransformer(source, volume=volume_float)
        vc.play(volume_source, after=after_play)

        while vc.is_playing():
            await asyncio.sleep(1)

        logging.info(f"ffmpeg process for {title} successfully terminated")

    except Exception as e:
        logging.error(f"error cok: {str(e)}")
        await send_embed(feedback_channel, f"Error: {str(e)}")
        if gid in queues and len(queues[gid]) > 0:
            queues[gid].pop(0) # Remove failed track
        asyncio.run_coroutine_threadsafe(play_next_song(voice_channel, feedback_channel, guild), client.loop)


client.run(DISCORD_API_KEY)
