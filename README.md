# Way 2 Eternal Bot (W2E) 🤖✨

Way 2 Eternal Bot adalah sekumpulan Discord bot berskala *Enterprise/Cloud-Ready* yang memadukan Kecerdasan Buatan (Gemini AI), Sistem Game/RPG & Ekonomi (Market 3.0), Pemutar Musik Premium (DJ & Filters), serta arsitektur yang kuat menggunakan **SQLite** dan **Docker**.

## 🌟 Fitur Utama Lengkap

### 1. 🤖 Kecerdasan Buatan (Gemini AI 1.5 Pro)
- **Chat Pintar**: Ngobrol langsung dengan AI menggunakan command `!ai <pesan>` atau `w2e <pesan>`.
- **Voice Listener (`!w2elisten`)**: Bergabung ke VC, merekam obrolan, mengubahnya menjadi teks, dan membalas dengan respon AI yang santai!

### 2. 💰 Market 3.0 & Ekonomi Sultan
Sistem ekonomi super lengkap yang tersimpan aman di database **SQLite (`w2ebot.db`)**:
- **Sistem Sultan (Mining Rigs)**: Beli mesin tambang seharga jutaan koin (`/buyrig`) untuk mendapatkan pasif *income* otomatis setiap jam.
- **Pajak & Treasury (`/kas`)**: Setiap penjualan koin kripto di pasar dikenakan pajak 2% yang masuk ke kas server. Hadiah Boss Raid diambil dari uang pajak ini! (Hanya bisa diakses oleh Admin).
- **Simulasi Kripto (`/market`)**: Pasar saham/kripto yang sangat dinamis lengkap dengan grafik *Sparklines* (Unicode bar) dan event volatilitas acak (Pump & Dump mendadak).
- **Tebak Harga / Binomo (`/tebak`)**: Fitur judi menebak arah harga pasar (Naik/Turun) dalam 10 menit ke depan untuk menggandakan uang.
- **Portfolio & PnL**: Lacak modal awal dan *Profit & Loss* secara real-time.

### 3. 🃏 RPG The Underworld (Ekspansi Kegelapan)
Selain fitur *Quest*, *Slot*, dan *Gacha*, kini ada area "Bawah Tanah":
- **Blackjack (`/blackjack <taruhan>`)**: Bermain kartu melawan AI Dealer langsung di chat Discord.
- **Sistem Pet (`/buypet`)**: Adopsi peliharaan (Slime, Serigala, Naga) yang memberikan bonus *Damage* besar-besaran saat melakukan `/attack` ke Boss Raid.
- **Bounty Hunter (`/bounty` & `/hunt`)**: Sayembara nyawa! Pasang uang untuk kepala member lain, dan biarkan member lain mencoba memburunya dengan risiko denda/kematian.
- **Sistem Gelar (Trophy Room)**: Lakukan pencapaian ekstrem (seperti menang judi jutaan koin atau sukses membunuh buronan 5x) untuk memajang piala 👑 **Sang Raja Judi** atau 🔪 **Hitman** secara permanen di profil (`/profile`).

### 4. 🎮 Modernisasi & Leveling
- **Slash Commands (`/`)**: 100% kompatibel dengan *Slash Commands* bawaan UI Discord untuk navigasi mudah tanpa perlu menghafal command. Daftar Slash Command yang tersedia:
  - `/profile`, `/market`, `/tebak`, `/blackjack`, `/shop`, `/buy`, `/inventory`, `/daily`, `/slot`, `/attack`, `/buypet`, `/bounty`, `/hunt`, `/kas`, `/radar`, `/find`.
  - *Catatan: Command klasik (menggunakan `!`) tetap tersedia sebagai alternatif!*
- **Voice Channel Farming (VC Leveling)**: Dapatkan pasif XP dan Koin hanya dengan nongkrong di Voice Channel! (Raih piala **🧟‍♂️ No-Lifer** jika nongkrong total 24 jam).

### 5. 👑 Eksklusif Server Booster (VIP)
- **Voice Announcer**: Pengumuman Sultan saat bergabung ke VC.
- **Custom Role Creator**: Pembuatan Role otomatis dari gambar.
- **Bonus Sultan**: Diskon 20% di `/shop` dan 2x lipat Koin saat klaim `/daily`.

### 6. 📡 Radar & Alat Pantau
- **Voice Radar (`/find @user`)**: Lacak durasi teman nongkrong di VC.
- **Bot Radar (`/checkbots`)**: Pantau status dan lokasi seluruh bot di server secara *real-time*.
- **Web API Bawaan**: Endpoint `/api/radar` (Status VC) dan `/api/broadcast` (Kirim pesan dari luar).

---

### 7. 🎵 Sistem Music Bot (Basic & Premium)

#### 🎧 Basic Music Bot (`music_bot.py`)
- Ekstraksi *playlist* super cepat dari YouTube/Spotify.
- **Session Ownership**: Orang pertama yang memutar lagu mengunci kontrol (bisa direbut jika AFK dengan `w2eclaim`).
- **Interactive `!np`**: Progress bar visual dan tombol kontrol UI interaktif.
- **Web API (Port 8080)**: Endpoint kontrol musik remote.

#### 💎 Custom Premium Music Bot (`w2e_custom_music_bot.py`)
Pemutar musik tingkat dewa eksklusif untuk member *Whitelist*:
- **Audio Filters (DJ Mode)**: Ubah suara dengan FFmpeg `!filter` (Bassboost, Nightcore, Vaporwave, 8D, Clear).
- **Smooth Fading**: Transisi antar lagu sangat mulus dengan efek *Fade-In* dan *Fade-Out* otomatis.
- **Advanced Controls**: Fitur `!seek <waktu>` untuk melompat ke detik lagu tertentu instan, `!volume`, dan `!loop`.
- **Smart Autoplay**: Ketika antrean kosong, `yt-dlp` otomatis merekomendasikan dan memutar lagu terkait.
- **Personal Playlists**: Member bisa menggunakan `!playlist save/play` untuk mengarsipkan daftar lagu favorit mereka sendiri.
- **Aesthetic UI & `!quote`**: Tampilan Now Playing dilengkapi dengan Visualizer gelombang musik buatan. Command `!quote <teks>` men-generate **Lyric Card berbentuk gambar/poster** (menggunakan Pillow) dari teks dan sampul album lagu, mirip fitur share lirik Spotify/Instagram.
- **Music Profiling (`!profile`)**: Lacak lagu teratasmu dan waktu mendengarkan.
- **Auto-Lyrics (`!lyrics`)**: Tarik lirik langsung dari Genius API.

---

## ⚙️ Persyaratan (Requirements)
```bash
pip install -r requirements.txt
```
*Catatan: FFmpeg wajib ter-install di sistem OS (Linux/Windows) untuk memutar musik.*

## 🚀 Infrastruktur Cloud-Ready (Deployment)
Bot ini siap di-host 24/7 di layanan Cloud (VPS, Railway, Render, AWS) menggunakan arsitektur modern dengan Docker.

### 🐳 Tutorial Deploy Otomatis di VPS (Ubuntu)

Langkah-langkah berikut akan membimbingmu menjalankan bot ini 24/7 di VPS Ubuntu secara otomatis.

**1. Install Docker & Docker Compose di Ubuntu**
Buka terminal VPS kamu dan jalankan perintah ini:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install docker.io docker-compose -y
sudo systemctl enable docker
sudo systemctl start docker
```

**2. Clone Repository Bot & Masuk ke Folder**
```bash
git clone <URL_GITHUB_KAMU> w2ebot
cd w2ebot
```

**3. Konfigurasi Bot**
Buat file `.env` untuk menyimpan token rahasia:
```bash
nano .env
```
*(Isi dengan `DISCORD_TOKEN`, `GEMINI_API_KEY`, dsb. Simpan dengan `Ctrl+X`, tekan `Y`, lalu `Enter`)*

Pancing file database SQLite agar tidak menjadi error folder saat di-*mount* oleh Docker:
```bash
touch w2ebot.db
```

**4. Jalankan Bot (Auto-Restart 24/7)**
Jalankan bot di *background*. Konfigurasi di dalam `docker-compose.yml` akan otomatis mengatur bot agar selalu *restart* (unless-stopped) jika VPS mati atau bot *crash*.
```bash
sudo docker-compose up -d --build
```

**✅ Command Docker Berguna Lainnya:**
- **Melihat aktivitas/log live:** `sudo docker logs -f w2ebot-cluster`
- **Mematikan bot:** `sudo docker-compose down`
- **Restart bot manual:** `sudo docker-compose restart`

---

**Database Migration Note:** 
Untuk migrasi dari *legacy json* (lama) ke SQLite baru, jalankan `python migrate_db.py` sekali saja sebelum menggunakan Docker, atau jalankan di dalam container.
