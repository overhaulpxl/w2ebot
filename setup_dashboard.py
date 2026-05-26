import os
import json

def setup_dashboard():
    # 1. Create config.json if not exists
    if not os.path.exists('config.json'):
        with open('config.json', 'w') as f:
            json.dump({'booster_channel_id': ''}, f)

    # 2. Create dashboard.html
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>W2E Bot Control Panel</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #0f172a; color: white; font-family: 'Inter', sans-serif; }
        .glass { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); }
    </style>
</head>
<body class="min-h-screen flex items-center justify-center p-4">
    <div class="glass p-8 rounded-2xl shadow-2xl w-full max-w-md">
        <div class="text-center mb-8">
            <h1 class="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-500">W2E Dashboard</h1>
            <p class="text-slate-400 mt-2">Bot Configuration Panel</p>
        </div>
        
        <form id="configForm" class="space-y-6">
            <div>
                <label class="block text-sm font-medium text-slate-300 mb-2">Booster Notification Channel ID</label>
                <input type="text" id="channelId" class="w-full bg-slate-800 border border-slate-600 rounded-lg p-3 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition" placeholder="e.g. 1332113600894079131">
                <p class="text-xs text-slate-500 mt-2">Biarkan kosong untuk otomatis mencari channel "general".</p>
            </div>
            
            <button type="submit" class="w-full bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white font-bold py-3 px-4 rounded-lg transition transform hover:scale-105 shadow-lg">
                Save Configuration
            </button>
        </form>
        
        <div id="statusMsg" class="mt-4 text-center text-sm font-semibold hidden"></div>
    </div>

    <script>
        // Load initial config
        fetch('/api/config')
            .then(res => res.json())
            .then(data => {
                document.getElementById('channelId').value = data.booster_channel_id || '';
            });

        // Save config
        document.getElementById('configForm').addEventListener('submit', (e) => {
            e.preventDefault();
            const btn = e.target.querySelector('button');
            btn.innerHTML = 'Saving...';
            
            const payload = {
                booster_channel_id: document.getElementById('channelId').value
            };
            
            fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                btn.innerHTML = 'Save Configuration';
                const status = document.getElementById('statusMsg');
                status.classList.remove('hidden');
                if(data.status === 'success') {
                    status.innerText = '✅ Settings saved successfully!';
                    status.classList.add('text-green-400');
                    status.classList.remove('text-red-400');
                } else {
                    status.innerText = '❌ Error saving settings!';
                    status.classList.add('text-red-400');
                    status.classList.remove('text-green-400');
                }
                setTimeout(() => status.classList.add('hidden'), 3000);
            });
        });
    </script>
</body>
</html>
"""
    with open('dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html)

    # 3. Update bot.py
    with open('bot.py', 'r', encoding='utf-8') as f:
        code = f.read()

    dashboard_api = """
async def serve_dashboard(request):
    try:
        with open('dashboard.html', 'r', encoding='utf-8') as f:
            html = f.read()
        return web.Response(text=html, content_type='text/html')
    except:
        return web.Response(text="Dashboard not found.", status=404)

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
    app.router.add_post('/api/config', update_config_api)
    app.router.add_get('/api/radar', api_radar)
"""

    import re
    # Replace the existing start_web_server
    code = re.sub(r'async def start_web_server\(\):.*?app\.router\.add_get\(\'/api/radar\', api_radar\)', dashboard_api.strip(), code, flags=re.DOTALL)

    # 4. Update the booster logic inside on_voice_state_update
    booster_logic = """
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
"""
    code = re.sub(r'        if member\.premium_since and not member\.bot:.*?(?=            if notify_channel:)', booster_logic, code, flags=re.DOTALL)
    
    with open('bot.py', 'w', encoding='utf-8') as f:
        f.write(code)

if __name__ == "__main__":
    setup_dashboard()
