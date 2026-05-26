import os
import re

ALLOWED_ID = "887968847842402355"

def modify_bot_py():
    with open('bot.py', 'r', encoding='utf-8') as f:
        code = f.read()

    # 1. Add ALLOWED_SERVER_ID
    if "ALLOWED_SERVER_ID" not in code:
        code = code.replace("GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'MMM')",
                            f"GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'MMM')\nALLOWED_SERVER_ID = int(os.getenv('ALLOWED_SERVER_ID', '{ALLOWED_ID}'))")

    # 2. Modify tree.sync
    code = re.sub(r'await tree\.sync\(\)', 'await tree.sync(guild=discord.Object(id=ALLOWED_SERVER_ID))', code)
    code = re.sub(r'await tree\.sync\(\)', 'await tree.sync(guild=discord.Object(id=ALLOWED_SERVER_ID))', code) # just in case

    # 3. Add auto-leave logic to on_ready
    on_ready_logic = """
    # Single Server Lock
    for guild in client.guilds:
        if guild.id != ALLOWED_SERVER_ID:
            logging.warning(f"Leaving unauthorized server: {guild.name}")
            await guild.leave()
"""
    if "Single Server Lock" not in code:
        code = re.sub(r'async def on_ready\(\):', f'async def on_ready():{on_ready_logic}', code)

    # 4. Add on_guild_join logic
    on_guild_join = """
@client.event
async def on_guild_join(guild):
    if guild.id != ALLOWED_SERVER_ID:
        logging.warning(f"Invited to unauthorized server {guild.name}. Leaving automatically.")
        await guild.leave()
"""
    if "def on_guild_join" not in code:
        code += on_guild_join

    # 5. Add /api/server API endpoint
    api_endpoint = """
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
"""
    if "async def get_server_data" not in code:
        code = code.replace("async def get_config_api(request):", api_endpoint + "\nasync def get_config_api(request):")
        code = code.replace("app.router.add_get('/api/config', get_config_api)", "app.router.add_get('/api/config', get_config_api)\n    app.router.add_get('/api/server', get_server_data)")

    with open('bot.py', 'w', encoding='utf-8') as f:
        f.write(code)

def modify_music_bot(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            code = f.read()

        if "ALLOWED_SERVER_ID" not in code:
            code = code.replace("DISCORD_TOKEN = os.getenv('MUSIC_BOT_TOKEN', '')",
                                f"DISCORD_TOKEN = os.getenv('MUSIC_BOT_TOKEN', '')\nALLOWED_SERVER_ID = int(os.getenv('ALLOWED_SERVER_ID', '{ALLOWED_ID}'))")
            code = code.replace("DISCORD_TOKEN = os.getenv('CUSTOM_MUSIC_BOT_TOKEN', '')",
                                f"DISCORD_TOKEN = os.getenv('CUSTOM_MUSIC_BOT_TOKEN', '')\nALLOWED_SERVER_ID = int(os.getenv('ALLOWED_SERVER_ID', '{ALLOWED_ID}'))")

        on_ready_logic = """
    # Single Server Lock
    for guild in bot.guilds:
        if guild.id != ALLOWED_SERVER_ID:
            print(f"Leaving unauthorized server: {guild.name}")
            await guild.leave()
"""
        if "Single Server Lock" not in code:
            code = re.sub(r'async def on_ready\(\):', f'async def on_ready():{on_ready_logic}', code)

        on_guild_join = """
@bot.event
async def on_guild_join(guild):
    if guild.id != ALLOWED_SERVER_ID:
        print(f"Invited to unauthorized server {guild.name}. Leaving automatically.")
        await guild.leave()
"""
        if "def on_guild_join" not in code:
            code += on_guild_join

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(code)
    except Exception as e:
        print(f"Error modifying {filename}: {e}")

if __name__ == "__main__":
    modify_bot_py()
    modify_music_bot('music_bot.py')
    modify_music_bot('w2e_custom_music_bot.py')
