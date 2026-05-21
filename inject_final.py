import re

file_path = r'C:\Users\blur\Downloads\ABDM\bot\w2ebot\bot.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()
    
# 1. Update blackjack logic for 'gambler_king'
blackjack_pattern = r"(users\[uid\]\['balance'\] \+= win\s*\n\s*save_json\(USER_FILE, users\))"
blackjack_hook = """\g<1>
        if win >= 1000000 and 'gambler_king' not in users[uid].get('achievements', []):
            if 'achievements' not in users[uid]: users[uid]['achievements'] = []
            users[uid]['achievements'].append('gambler_king')
            save_json(USER_FILE, users)
            await ctx.send(f"🏆 **ACHIEVEMENT UNLOCKED!** {ctx.author.mention} menang besar dan mendapatkan gelar **👑 Sang Raja Judi**!")"""

content = re.sub(blackjack_pattern, blackjack_hook, content, count=1)

# 2. Update hunt logic for 'hitman'
hunt_pattern = r"(users\[uid\]\['balance'\] \+= reward\s*\n\s*bounties\[tid\] = 0)"
hunt_hook = """\g<1>
        users[uid]['hunt_success'] = users[uid].get('hunt_success', 0) + 1
        if users[uid]['hunt_success'] >= 5 and 'hitman' not in users[uid].get('achievements', []):
            if 'achievements' not in users[uid]: users[uid]['achievements'] = []
            users[uid]['achievements'].append('hitman')
            await ctx.send(f"🏆 **ACHIEVEMENT UNLOCKED!** {ctx.author.mention} membunuh 5 target dan mendapatkan gelar **🔪 Hitman**!")"""

content = re.sub(hunt_pattern, hunt_hook, content, count=1)

# 3. Update profile logic to show achievements
profile_pattern = r"(embed\.add_field\(name=\"Level\", value=f\"{stat\['level'\]}\", inline=True\))"
profile_hook = """\g<1>
    
    users = load_json(USER_FILE)
    achievements = users.get(uid, {}).get('achievements', [])
    if achievements:
        ach_emojis = {
            'gambler_king': '👑 Sang Raja Judi',
            'no_lifer': '🧟‍♂️ No-Lifer',
            'hitman': '🔪 Hitman',
            'boss_slayer': '🛡️ Boss Slayer'
        }
        ach_text = "\\n".join([f"- {ach_emojis.get(a, a)}" for a in achievements])
        embed.add_field(name="🏆 Achievements", value=ach_text, inline=False)"""

content = re.sub(profile_pattern, profile_hook, content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
