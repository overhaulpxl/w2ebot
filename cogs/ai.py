import discord
from core import *
import random, asyncio, sqlite3
from datetime import datetime

def setup(tree, client):
    @tree.command(name="ai", description="Ngobrol langsung dengan Gemini AI")
    async def slash_ai(interaction: discord.Interaction, pertanyaan: str):
        await interaction.response.defer()
        nick = getattr(interaction.user, 'nick', None) or interaction.user.display_name
        response = await get_gemini_response(pertanyaan, interaction.user.id, nick)
        # Handle long messages since discord limits embeds to 4096 and messages to 2000
        if len(response) > 2000:
            for i in range(0, len(response), 2000):
                await interaction.followup.send(response[i:i+2000])
        else:
            await send_embed(interaction, response)
        await write_to_memory(f'User: {pertanyaan}\nBot: {response}')
    
    @tree.command(name="setpersona", description="Ubah sifat/persona AI untuk chat selanjutnya")
    async def slash_setpersona(interaction: discord.Interaction, persona: str = None):
        await interaction.response.defer()
        uid = str(interaction.user.id)
        personas = await load_json(PERSONAS_FILE)
        if not persona:
            if uid in personas:
                del personas[uid]
                await save_json(PERSONAS_FILE, personas)
            await send_embed(interaction, "✅ Persona AI kamu telah direset ke default.")
            return
        personas[uid] = persona
        await save_json(PERSONAS_FILE, personas)
        await send_embed(interaction, f"✅ Persona AI kamu telah diubah menjadi:\n> *{persona}*")
    
    @tree.command(name="chat", description="Chat santai tanpa prefix AI")
    async def slash_chat(interaction: discord.Interaction, message: str):
        await interaction.response.defer()
        response = await get_gemini_response(message, interaction.user.id)
        await send_embed(interaction, response)
    
    @tree.command(name="roast", description="Minta AI meroasting kamu atau orang lain")
    async def slash_roast(interaction: discord.Interaction, target: discord.Member = None):
        await interaction.response.defer()
        t = target.display_name if target else interaction.user.display_name
        query = f"Roast (hina dengan lucu dan savage tapi jangan terlalu kasar) orang yang bernama {t}. Gunakan bahasa gaul tongkrongan Indonesia (lo-gue), pedas tapi lucu. JANGAN ada basa-basi pembuka/penutup khas AI. Langsung tembak dengan kalimat roasting-nya."
        response = await get_gemini_response(query, interaction.user.id)
        await send_embed(interaction, response)
    
    @tree.command(name="rate", description="AI akan memberikan rating (1-10) untuk orang ini")
    async def slash_rate(interaction: discord.Interaction, target: discord.Member = None):
        await interaction.response.defer()
        t = target.display_name if target else interaction.user.display_name
        query = f"Berikan rating 1 sampai 10 seberapa keren/cantik/ganteng orang yang bernama {t}, lalu berikan alasan kocak/absurd kenapa kamu memberi nilai tersebut. Gunakan bahasa gaul santai, JANGAN formal, JANGAN ada basa-basi khas AI. Langsung sebut nilainya di awal."
        response = await get_gemini_response(query, interaction.user.id)
        await send_embed(interaction, response)
    
    @tree.command(name="shipper", description="AI akan mencocokkan dua orang")
    async def slash_shipper(interaction: discord.Interaction, orang1: discord.Member, orang2: discord.Member):
        await interaction.response.defer()
        
        if orang1 == orang2:
            await send_embed(interaction, "❌ Jomblo ngenes banget nge-ship diri sendiri...")
            return
            
        # Consistent random based on ID
        seed = int(orang1.id) + int(orang2.id)
        random.seed(seed)
        match_pct = random.randint(0, 100)
        random.seed() # reset
        
        prompt = f"Buatkan ramalan cinta super singkat dan lucu (bisa sarkas atau romantis) untuk dua orang dengan tingkat kecocokan {match_pct}%. Gunakan bahasa gaul anak discord Indonesia (lo-gue, santai, kocak). JANGAN ada basa-basi khas AI seperti 'Ini dia...' atau 'Semoga...'. Langsung ke ramalannya secara natural."
        try:
            response = await asyncio.to_thread(gemini_client.models.generate_content, model='gemini-2.5-flash', contents=prompt)
            desc = response.text.strip()
        except Exception:
            desc = f"Tingkat kecocokan kalian adalah {match_pct}%, tapi ramalan AI sedang error."
    
        if PILLOW_AVAILABLE:
            img_buf = await generate_love_image(orang1, orang2, match_pct)
            if img_buf:
                file = discord.File(fp=img_buf, filename="love.png")
                embed = discord.Embed(title="💖 W2E Shipper 💖", description=f"**{orang1.display_name}** x **{orang2.display_name}**\n\n{desc}", color=discord.Color.brand_red())
                embed.set_image(url="attachment://love.png")
                await interaction.followup.send(embed=embed, file=file)
                return
    
        embed = discord.Embed(title="💖 W2E Shipper 💖", description=f"**{orang1.display_name}** x **{orang2.display_name}**\n\n**Kecocokan: {match_pct}%**\n\n{desc}", color=discord.Color.brand_red())
        await interaction.followup.send(embed=embed)
    
    
    @tree.command(name="image", description="Buat gambar menggunakan AI")
    async def slash_image(interaction: discord.Interaction, prompt: str):
        await interaction.response.defer()
        # Mocking image generation for now since Gemini free tier might not support image gen in discord bot
        await send_embed(interaction, f"🎨 **Membuat gambar:** *{prompt}*\n(Maaf, fitur generate gambar sedang dalam perbaikan karena limitasi API)")
    
    @tree.command(name="quiz", description="AI akan memberikan pertanyaan kuis")
    async def slash_quiz(interaction: discord.Interaction, topik: str = "Pengetahuan Umum"):
        await interaction.response.defer()
        query = f"Berikan satu pertanyaan kuis trivia tentang {topik}. Jangan beri tahu jawabannya dulu."
        response = await get_gemini_response(query, interaction.user.id)
        await send_embed(interaction, f"🧠 **KUIS W2E:**\n{response}\n*(Silakan jawab di chat biasa!)*")
    
    @tree.command(name="listen", description="Bot akan masuk ke VC dan mentranskrip suaramu via AI")
    async def slash_listen(interaction: discord.Interaction):
        await send_embed(interaction, "🎧 Fitur transkripsi suara sedang dinonaktifkan sementara untuk optimalisasi server.", ephemeral=True)
    
