import re

def main():
    with open('bot.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Inject send_embed function just before SLASH COMMANDS section
    embed_func = """
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
"""
    content = content.replace("# ============================================================================\n# SLASH COMMANDS (APP COMMANDS)", embed_func)

    # We only want to replace inside slash commands, so let's split
    parts = content.split("# SLASH COMMANDS (APP COMMANDS)")
    if len(parts) < 2:
        print("Could not find slash commands section")
        return
        
    head = parts[0]
    slash_body = "# SLASH COMMANDS (APP COMMANDS)" + parts[1]

    # Regex to replace await interaction.followup.send("text") or (f"text") or (msg)
    # Be careful not to replace embed=, file=, view=, etc.
    
    # 1. Replace await interaction.followup.send(msg)
    slash_body = re.sub(r'await interaction\.followup\.send\(\s*([a-zA-Z0-9_]+)\s*\)', r'await send_embed(interaction, \1)', slash_body)
    
    # 2. Replace await interaction.followup.send(f"...") or ("...")
    slash_body = re.sub(r'await interaction\.followup\.send\(\s*(f?"[^"]+"|f?\'[^\']+\')\s*\)', r'await send_embed(interaction, \1)', slash_body)
    
    # 3. Handle cases with view=view
    slash_body = re.sub(r'await interaction\.followup\.send\(\s*(f?"[^"]+"|f?\'[^\']+\')\s*,\s*view=([a-zA-Z0-9_]+)\s*,\s*wait=True\s*\)', r'await send_embed(interaction, \1, view=\2)', slash_body)

    # 4. Handle await interaction.response.send_message
    slash_body = re.sub(r'await interaction\.response\.send_message\(\s*([a-zA-Z0-9_]+)\s*\)', r'await send_embed(interaction, \1)', slash_body)
    slash_body = re.sub(r'await interaction\.response\.send_message\(\s*(f?"[^"]+"|f?\'[^\']+\')\s*\)', r'await send_embed(interaction, \1)', slash_body)
    slash_body = re.sub(r'await interaction\.response\.send_message\(\s*(f?"[^"]+"|f?\'[^\']+\')\s*,\s*ephemeral=True\s*\)', r'await send_embed(interaction, \1, ephemeral=True)', slash_body)

    # 5. Handle await msg.edit(content=...)
    slash_body = re.sub(r'await msg\.edit\(content=(f?"[^"]+"|f?\'[^\']+\'),\s*view=None\)', r'await msg.edit(embed=discord.Embed(description=\1, color=discord.Color.blurple()).set_footer(text="W2E Official Bot"), view=None)', slash_body)

    # Exception: slash_radar should have a specific rewrite
    # Let's completely rewrite slash_radar
    radar_new = '''@tree.command(name="checkbots", description="Pantau aktivitas semua bot di server")
async def slash_radar(interaction: discord.Interaction):
    await interaction.response.defer()
    guild = interaction.guild
    if not guild:
        await send_embed(interaction, "Command ini hanya bisa digunakan di dalam server.")
        return
        
    bot_members = [m for m in guild.members if m.bot]
    active_bots = []
    idle_bots = []
    
    for member in bot_members:
        if member.voice and member.voice.channel:
            channel = member.voice.channel
            status = f"🤖 **{member.display_name}** sedang di 🔊 **{channel.name}**"
            active_bots.append(status)
        else:
            if member.bot and member.id != client.user.id:
                idle_bots.append(member.display_name)
                
    embed = discord.Embed(title="📡 W2E Bot & Music Radar", color=discord.Color.blurple())
    
    if active_bots:
        embed.add_field(name="🟢 Sedang Aktif (Di Dalam Voice)", value="\\n".join(active_bots), inline=False)
    else:
        embed.add_field(name="🟢 Sedang Aktif (Di Dalam Voice)", value="-", inline=False)
        
    if idle_bots:
        idle_str = ", ".join(idle_bots[:15])
        if len(idle_bots) > 15:
            idle_str += f" ... dan {len(idle_bots)-15} lainnya."
        embed.add_field(name="💤 Idle (Tidur)", value=idle_str, inline=False)
    else:
        embed.add_field(name="💤 Idle (Tidur)", value="-", inline=False)
        
    embed.set_footer(text="W2E Official Bot")
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    
    await interaction.followup.send(embed=embed)'''
    
    # Replace the old radar
    slash_body = re.sub(r'@tree\.command\(name="checkbots".*?await interaction\.followup\.send\(res\)', radar_new, slash_body, flags=re.DOTALL)

    # Write back to bot.py
    with open('bot.py', 'w', encoding='utf-8') as f:
        f.write(head + slash_body)

if __name__ == "__main__":
    main()
