# Way 2 Eternal Bot (W2E) 🤖✨

Way 2 Eternal Bot adalah Discord bot serbaguna yang dilengkapi dengan kecerdasan buatan (Gemini AI), sistem ekonomi RPG, mini-games, hingga berbagai fitur manajemen server yang unik.

## 🌟 Fitur Utama

### 🧠 Gemini AI Integration
- `w2e <query>` atau `!ai <query>`: Ngobrol langsung dengan Gemini AI.
- **Auto Moderation**: AI akan mendeteksi pesan toxic, rasisme, atau NSFW ekstrim secara otomatis dan menghapusnya.
- **Voice Listener** (`!w2elisten`): Bot bisa masuk ke Voice Channel, merekam suara percakapan, mengubahnya menjadi teks (transkripsi), dan membalasnya dengan gaya santai menggunakan AI!

### 💰 RPG & Economy System
- **Leveling & XP**: Dapatkan XP dengan aktif di server.
- **Daily Rewards**: Klaim koin harianmu dengan `!w2edaily`.
- **Mini Games & Casino**: Main slot (`!w2eslot`), coin flip, atau gacha gelar (`!w2egacha`).
- **Toko & Item**: Beli item seperti *Shield* (anti curi/kutukan), *Double XP*, atau *Lucky Charm*.
- **Sistem Quest**: Selesaikan quest harian untuk mendapatkan hadiah tambahan.

### 🎮 Hiburan & Sosial
- **Music Bot**: Putar dan nikmati lagu bersama teman-teman di voice channel.
- **Radar & Voice Tracker**: Lacak di mana temanmu nongkrong dengan `!find @user` atau pantau lewat radar web API.
- **Family Tree**: Bangun silsilah keluarga virtual di server dan lihat grafis silsilah keluargamu!
- **Ulang Tahun**: Bot akan mengucapkan dan memberikan kado koin otomatis saat anggota server berulang tahun.

### 👑 Eksklusif Server Booster
- **Notifikasi Sultan**: Saat booster masuk ke Voice Channel, bot akan memberikan sambutan megah!
- **Custom Role**: Booster dapat membuat custom role mereka sendiri (beserta icon) secara langsung via bot.
- **Bonus Koin**: Multiplier koin tambahan saat mengklaim *daily reward*.

### 🌐 Web API & Broadcast
- Dilengkapi dengan web server bawaan (berjalan di port 8081).
- **Radar API**: Menampilkan data real-time siapa saja yang sedang di Voice Channel.
- **Broadcast API**: Kirim pesan langsung ke berbagai channel Discord dari sistem eksternal.

## ⚙️ Persyaratan (Requirements)
Pastikan kamu telah menginstal semua dependensi yang dibutuhkan:
```bash
pip install -r requirements.txt
```

## 🚀 Cara Menjalankan
1. Siapkan `.env` atau atur token Discord dan Gemini AI pada file utama.
2. Jalankan bot utama:
```bash
python bot.py
```
*(Catatan: Jangan lupa siapkan juga file-file `.json` seperti `family.json`, `items.json`, dsb. jika memulai ulang database).*
