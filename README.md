# Way 2 Eternal Bot (W2E) 🤖✨

Way 2 Eternal Bot adalah Discord bot super canggih yang memadukan Kecerdasan Buatan (Gemini AI), Sistem Game/RPG (Ekonomi), alat pemantauan Voice Channel, serta Web API bawaan.

## 🌟 Fitur Utama Lengkap

### 1. 🤖 Kecerdasan Buatan (Gemini AI 1.5 Pro)
- **Chat Pintar**: Ngobrol langsung dengan AI menggunakan command `!ai <pesan>` atau `w2e <pesan>`. AI akan merespons layaknya asisten virtual sungguhan.
- **Auto-Moderator AI**: Bot secara otomatis memonitor seluruh obrolan. Jika mendeteksi pesan yang berisi ujaran kebencian, rasisme, atau NSFW ekstrim, bot akan langsung menghapus pesan tersebut dan memberikan peringatan kepada pelakunya.
- **Voice Listener (`!w2elisten`)**: Bot bisa bergabung ke Voice Channel (VC) untuk merekam obrolan kalian, lalu hasil rekaman tersebut ditranskripsi ke dalam teks dan dijawab dengan balasan AI yang lucu dan santai!

### 2. 💰 Sistem Ekonomi & RPG
Bot ini memiliki sistem progresi dengan penyimpanan menggunakan *SQLite* (dev.db):
- **Leveling System**: Dapatkan XP setiap kali kamu aktif mengobrol di server. Saat akumulasi XP cukup, level kamu akan otomatis naik!
- **Koin Harian (`!w2edaily`)**: Klaim koin gratis setiap hari.
- **Sistem Quest (`!quest`)**: Misi harian yang di-generate otomatis (misalnya: kirim 5 pesan, main slot 1x, dll).
- **Mini Games & Casino**:
  - `!w2eslot <taruhan>`: Main tebak slot (kasino mini).
  - `!w2egacha`: Gacha seharga 200 koin untuk mendapatkan gelar lucu (contoh: *Raja Skip Lagu*, *Kuli Discord*).
- **Shop Item**: Koin bisa ditukar dengan *buff* seperti **Shield** (kebal kutukan), **Double XP**, atau **Lucky Charm**.
- **Profile Banner**: Pengguna bisa melihat statistik mereka (Avatar, Level, XP, Koin) dalam bentuk gambar banner keren menggunakan command profile.

### 3. 👑 Eksklusif Server Booster (VIP)
Fitur spesial untuk menghargai member yang nge-boost server:
- **Intro Kedatangan (Voice Announcer)**: Setiap kali booster masuk ke Voice Channel, bot akan otomatis mengirim pengumuman megah di chat umum (contoh: *"🌟 Sultan server baru saja join VC! Selawat dulu dong~"*).
- **Custom Role Creator**: Booster bisa mengirimkan gambar ke channel khusus `#custom-role` untuk menyuruh bot otomatis membuatkan Custom Role lengkap dengan icon, lalu memberikannya langsung ke mereka.
- **Bonus Sultan**: Booster mendapat **2x lipat Koin** saat klaim *daily* dan dapat Gacha title yang lebih eksklusif/langka.

### 4. 📡 Radar & Alat Pantau
- **Voice Radar (`!find @user`)**: Cari tahu temanmu sedang asyik nongkrong di Voice Channel mana dan sudah berapa lama mereka di sana.
- **Web API Bawaan (Port 8081)**:
  - **Radar API** (`/api/radar`): Menampilkan data real-time (JSON) siapa saja yang berada di VC.
  - **Broadcast API** (`/api/broadcast`): Memungkinkan sistem luar (website) mengirim pesan ke Discord.
  - Command internal `w2e1`, `w2e2`, `w2e3` untuk broadcast ke channel spesifik.

### 5. 🎉 Interaksi Sosial & Hiburan
- **Ulang Tahun Otomatis**: Bot mendeteksi tanggal lahir member (dari `birthdays.json`). Di hari H, bot akan mengucapkan selamat dan otomatis memberikan kado 1000 Koin!
- **Silsilah Keluarga (Family Tree)**: Sistem unik di mana pengguna bisa membentuk keluarga (pasangan & anak). Bot bisa membuat gambar grafis silsilah yang menyatukan semua avatar anggota keluarga dalam satu gambar *Family Tree*!

---

### 6. 🎵 Sistem Music Bot (Basic & Premium)
Bot ini memiliki dua sistem music bot terpisah yang saling melengkapi untuk menemani nongkrong di Voice Channel.

#### 🎧 Basic Music Bot (`music_bot.py`)
Bot musik reguler untuk publik tanpa batasan khusus:
- **Pemrosesan Super Cepat**: Mengekstrak metadata dari playlist Spotify & YouTube dalam sekejap tanpa menyebabkan lag server.
- **Sistem Session & Ownership**: Orang pertama yang memutar lagu menjadi *Session Owner* untuk mencegah sabotase antrean. Owner bisa mentransfer hak dengan `w2etransfer` atau direbut dengan `w2eclaim` jika owner AFK.
- **Interactive Now Playing (`!np`)**: Menampilkan *Progress Bar* visual (contoh: `[▬▬▬▬▬▬🔘▬▬▬▬▬▬▬] 2:30 / 4:00`) disertai tombol kontrol Discord UI (Pause/Skip/Stop) yang bisa diklik.
- **Sistem Looping Lengkap (`w2eloop`)**: Bisa mengulang satu lagu (TRACK), mengulang seluruh antrean (QUEUE), atau mati (OFF).
- **Web API Server (Port 8080)**: Mengizinkan kontrol musik secara remote dari web dashboard lewat endpoint API (`/api/status`, `/api/pause`, `/api/skip`).

#### 💎 Custom/Premium Music Bot (`w2e_custom_music_bot.py`)
Bot musik tingkat lanjut bergaya VIP dengan *Quality of Life* dan analitik ekstrem:
- **Sistem Security Whitelist**: Sangat eksklusif! Semua pesan akan diabaikan jika pengguna tidak terdaftar di *whitelist* (diatur via `!whitelist @user`).
- **Sistem Tracking & Profiling Musik (`!profile`)**: Melacak secara diam-diam tiap detik lagu yang kamu dengarkan! Mencatat Total Play, Total Menit Mendengarkan, Sumber Favorit (Spotify/YT), Top 3 Tracks favorit, dan mencatat teman VC-mu ke dalam `premium_music_stats.json`.
- **Scraping Lirik Cerdas (`!lyrics`)**: Secara otomatis mencari lirik ke API Genius.com untuk lagu yang sedang diputar tanpa perlu menulis ulang judul lagunya.
- **Autoplay Machine Logic**: Musik tak akan pernah mati. Jika antrean kosong, bot mengecek Histori Lagu dan mencari lagu rekomendasi selanjutnya menggunakan algoritma *Autoplay*.
- **Rich Embed Player**: Memunculkan status pemutar yang sangat rapi dilengkapi Thumbnail Album asli yang ditarik dari Spotify/YouTube.
- **Premium Web API Server (Port 8082)**: Server API independen untuk memantau status premium dan mengatur whitelist melalui jaringan luar.

---

## ⚙️ Persyaratan (Requirements)
Pastikan kamu telah menginstal semua library Python yang dibutuhkan:
```bash
pip install -r requirements.txt
```

## 🚀 Cara Menjalankan
1. Siapkan environment file atau masukkan `DISCORD_API_KEY` dan `GEMINI_API_KEY` pada kode utama.
2. Atur path database dan channel ID pada variabel di `bot.py` jika perlu disesuaikan dengan servermu.
3. Jalankan bot utama:
```bash
python bot.py
```
