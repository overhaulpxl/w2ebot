# Way 2 Eternal Bot (W2E) 🤖✨

Way 2 Eternal Bot adalah Discord Bot modern berskala *Enterprise/Cloud-Ready* yang memadukan **Kecerdasan Buatan (Gemini 2.5 Flash)**, **Sistem Game RPG & Ekonomi Sultan (Market 3.0)**, dan **Visualisasi Gambar Dinamis menggunakan Pillow**, yang tersimpan aman di database relasional **SQLite**.

Bot ini hadir dengan arsitektur tunggal yang disederhanakan dan antarmuka **Discord UI Components** (Buttons, Select Menus, & Rich Embeds) yang diaplikasikan secara global ke semua perintah untuk menghadirkan pengalaman visual terbaik bagi komunitas Discord Anda.

---

## 🌟 Fitur Utama Lengkap

### 1. 🤖 Kecerdasan Buatan (Gemini 2.5 Flash)
* **Chat Pintar Berbasis Database**: Mengobrol langsung dengan AI menggunakan perintah `/chat <pesan>`. Memori percakapan (*Chat History*) disimpan secara efisien di dalam database **SQLite** (tabel `ChatMemory`) agar performa respons sangat cepat dan ringan di VPS!
* **Gen-Z Native Personality**: W2E diprogram menggunakan instruksi sistem ketat agar berinteraksi memakai bahasa gaul Gen-Z Indonesia (lo, gue, bro, cuy, wkwk) secara alami, tanpa basa-basi kaku khas AI robot.
* **Sistem Persona Kustom (`/setpersona`)**: Atur sifat atau gaya roleplay AI secara kustom per pengguna. Data persona tersimpan permanen di database lokal (`personas.json`).
* **Voice Listener (`w!listen`)**: Bot dapat bergabung ke Voice Channel, merekam suara percakapan, mentranskripsinya via API Gemini, dan membalas dengan respons AI berbentuk suara (gTTS).
* **Saringan Toksisitas**: Pengecekan toxic chat otomatis di background menggunakan Gemini API untuk mendeteksi ujaran kebencian parah demi menjaga keharmonisan server.

### 2. 🎮 Sistem RPG & Ekonomi Sultan (Market 3.0)
* **Visual Premium Profile Card (`/profile`)**: Menampilkan Kartu Profil RPG dinamis berbentuk gambar (Pillow) beresolusi tinggi (`1600x400` px) lengkap dengan panel navigasi interaktif (**🎒 Inventory**, **⛏️ Miner Rigs**, **👪 Silsilah Keluarga**, & **🛒 Buka Toko**).
* **Sultan Shop (`/shop`)**: Beli item-item RPG seperti Shield 🛡️, Double XP ⚡, dan Lucky Charm 🍀 langsung menggunakan tombol sekali klik di chat.
* **Pasif Income / Mining Rigs (`/buyrig` / `/miner`)**: Beli mesin tambang kripto fiktif (Tier 1-3) untuk menghasilkan pasif koin secara otomatis setiap jam.
* **Simulasi Bursa Kripto (`/market` & `/portfolio`)**: Dinamika bursa dengan grafik *Sparklines* (Unicode bar) dan event volatilitas mendadak (Pump & Dump) lengkap dengan tombol Refresh Harga.
* **Game Judi & Hiburan**: Coinflip (`w!cf`), Slot (`w!slot`), Blackjack (`/blackjack`), Crash (`/crash`), dan Gacha (`/gacha`) yang memacu adrenalin.

### 3. 👪 Hubungan Sosial & Silsilah Keluarga
* **Bagan Silsilah Keluarga (`/family`)**: Bagan silsilah keluarga interaktif yang digambar otomatis oleh Pillow menjadi gambar PNG.
* **Pernikahan Virtual (`/marry` & `/divorce`)**: Hubungan asmara resmi antar-member di server lengkap dengan status pasangan di profile.
* **Premium Shipper Card (`/shipper`)**: Kartu kecocokan jodoh beresolusi tinggi (`660x175` px) yang menampilkan avatar kedua pengguna secara simetris, berlatar gradien rose lembut, dengan bentuk hati yang terisi warna gradien asmara secara dinamis sesuai persentase kecocokan.

### 4. 📡 Radar & Utilitas Keamanan
* **Voice Channel Farming**: Dapatkan pasif XP dan Koin hanya dengan nongkrong di Voice Channel (minimal 2 orang untuk mencegah farming AFK solo).
* **Radar Bot (`/checkbots`)** & **Voice Radar (`/find`)**: Pantau durasi nongkrong teman di VC secara real-time dan lacak status bot di server.
* **Web API Dashboard (Port 8081)**: Endpoint `/api/radar` untuk status Voice Channel, `/api/config` untuk konfigurasi dashboard web, dan `/api/broadcast` untuk mengirim pesan dari luar.

---

## ⚙️ Persyaratan Sistem (Prerequisites)

Sebelum menjalankan bot, pastikan sistem Anda telah memenuhi persyaratan berikut:

* **Python 3.10** ke atas.
* **FFmpeg** ter-install di PATH OS Anda (Wajib untuk fitur mendengarkan/merekam suara di Voice Channel).
* Koneksi internet stabil untuk mengakses Discord API dan Google Gemini API.

---

## 🛠️ Panduan Instalasi & Konfigurasi

### 1. Kloning Repositori & Install Dependensi
```bash
git clone https://github.com/overhaulpxl/w2ebot.git
cd w2ebot
pip install -r requirements.txt
```

### 2. Konfigurasi Variabel Lingkungan (`.env`)
Buat file bernama `.env` di folder utama proyek dan isi variabel berikut:
```env
# Token Bot Utama (Discord Developer Portal)
DISCORD_TOKEN=TOKEN_BOT_DISCORD_ANDA

# API Key Google Gemini (Google AI Studio)
GEMINI_API_KEY=KEY_GEMINI_AI_ANDA

# ID Server Discord Utama
ALLOWED_SERVER_ID=887968847842402355

# Konfigurasi Prefix Bot (Default: w!)
BOT_PREFIX=w!
```

### 3. Konfigurasi Server Booster & Kategori Kustom (Opsional)
Bot ini memiliki fitur kustomisasi role otomatis untuk **Server Booster**. Konfigurasikan ID channel target kustomisasi role langsung di dalam file `bot.py` jika diperlukan.

---

## 🚀 Cara Menjalankan Bot (Execution)

### Cara A: Windows (Local / Server)
Cukup klik ganda (double-click) file `run_all.bat` untuk meluncurkan bot utama secara otomatis. 
Atau Anda dapat membukanya melalui PowerShell/CMD:
```powershell
python bot.py
```

### Cara B: Docker & Docker Compose (VPS / Linux / Production Hosting)

Menggunakan Docker adalah metode deployment terbaik untuk server VPS/Linux karena Docker otomatis membundel runtime Python 3.10-slim dan dependensi sistem (seperti FFmpeg dan Node.js) tanpa mengotori server host Anda. Selain itu, jika bot mengalami crash, Docker akan otomatis menyalakannya kembali.

#### 1. Persiapan File Database
Sebelum menjalankan Docker Compose, Anda **wajib** membuat file database kosong `w2ebot.db` secara lokal di folder yang sama. Jika tidak dibuat terlebih dahulu, Docker akan menduga `w2ebot.db` adalah sebuah folder/direktori saat di-mount, yang akan memicu kegagalan sistem.

* **Linux / macOS**:
  ```bash
  touch w2ebot.db
  ```
* **Windows (PowerShell)**:
  ```powershell
  New-Item -Path "w2ebot.db" -ItemType File
  ```

#### 2. Menjalankan Container
Jalankan bot secara otomatis di latar belakang (background/detached mode):
```bash
docker compose up -d --build
```
*(Catatan: Anda dapat menggunakan `docker-compose` jika sistem Anda menggunakan Docker Compose versi lama).*

#### 3. Perintah Manajemen Container
* **Melihat Logs Real-Time (Penting untuk debugging)**:
  ```bash
  docker compose logs -f
  # atau melacak kontainer secara langsung:
  docker logs -f w2ebot-main
  ```
* **Menghentikan Bot**:
  ```bash
  docker compose down
  ```
* **Menyalakan Ulang Bot (Restart)**:
  ```bash
  docker compose restart
  ```
* **Memeriksa Status Running**:
  ```bash
  docker compose ps
  ```
* **Masuk ke dalam Terminal Container (Interactive Bash)**:
  ```bash
  docker exec -it w2ebot-main bash
  ```

#### 4. Persistensi Data Aman
Seluruh data dinamis RPG bot (seperti saldo koin, level, inventori, perkawinan, quests harian, tanggal lahir, silsilah keluarga, dan riwayat chat AI) disimpan di dalam file database `w2ebot.db` (termasuk penyimpanan JSON virtual di dalam tabel `json_store`). 

Karena file `w2ebot.db` telah dipetakan ke server host melalui volume (`./w2ebot.db:/app/w2ebot.db`), **seluruh progres permainan dan obrolan AI Anda 100% aman** dan tidak akan hilang meskipun kontainer di-rebuild, diperbarui, atau dimatikan.


---

## 📘 Panduan Penggunaan Lengkap (Command List)

Semua perintah bot dapat dipanggil menggunakan prefix `w!` (contoh: `w!daily`) atau melalui **Slash Commands** (`/`) Discord.

### Kategori A: RPG & Ekonomi Sultan
| Command Prefix | Command Slash | Deskripsi | Contoh Penggunaan |
| :--- | :--- | :--- | :--- |
| `w!daily` | `/daily` | Ambil jatah koin harian (Booster dapat bonus 2x). | `w!daily` |
| `w!weekly` | `/weekly` | Ambil jatah koin mingguan gratis. | `w!weekly` |
| `w!work` | `/work` | Bekerja menghasilkan koin acak setiap beberapa menit. | `w!work` |
| `w!rob @user` | `/rob @user` | Mencuri koin dari member lain (ada peluang ditangkap polisi). | `w!rob @Equiv` |
| `w!transfer @user <jumlah>` | `/transfer` | Mengirim koin secara aman ke member lain. | `w!transfer @Equiv 500` |
| `w!shop` | `/shop` | Buka menu Sultan Shop berformat UI interaktif. | `w!shop` |
| `w!buy <item>` | `/buy <item>` | Membeli item langsung (shield, double_xp, lucky_charm). | `w!buy shield` |
| `w!inventory` | `/inventory` | Cek isi tas inventory, status efek aktif, dan durasi item. | `w!inventory` |
| `w!sell <item>` | `/sell <item>` | Menjual kembali item ke toko dengan harga setengah koin. | `w!sell shield` |
| `w!buyrig <tier>` | `/buyrig` | Membeli mining rig pasif (tier 1, 2, atau 3). | `w!buyrig 2` |
| `w!miner` | `/miner` | Memantau status, efisiensi, dan klaim koin hasil mining. | `w!miner` |
| `w!market` | `/market` | Memantau tren harga kripto fiktif terupdate. | `w!market` |
| `w!portfolio` | `/portfolio` | Lacak nilai aset kripto fiktif Anda (ETHR, dsb). | `w!portfolio` |
| `w!tebak <angka>` | `/tebak` | Menebak angka (1-10) berhadiah koin. | `w!tebak 7` |
| `w!cf <pilihan> <bet>`| `/coinflip` | Judi lempar koin (pilihan: heads / tails). | `w!cf heads 100` |
| `w!blackjack <bet>` | `/blackjack` | Judi kartu blackjack melawan dealer AI. | `w!blackjack 200` |
| `w!crash <bet>` | `/crash` | Judi grafik naik, klaim sebelum grafik crash/meledak! | `w!crash 150` |
| `w!attack` | `/attack` | Menyerang Raid Boss aktif di server bersama-sama. | `w!attack` |
| `w!buypet <pet>` | `/buypet` | Membeli pet pembantu (slime, wolf, dragon) untuk buff attack. | `w!buypet wolf` |
| `w!box` | `/box` | Membuka Mystery Box untuk mendapatkan koin atau item langka. | `w!box` |

### Kategori B: Gemini AI & Sosial
| Command Prefix | Command Slash | Deskripsi | Contoh Penggunaan |
| :--- | :--- | :--- | :--- |
| `w!ai <pesan>` | `/ai` | Mengobrol atau bertanya apa saja dengan Gemini AI. | `w!ai jelaskan apa itu black hole` |
| `w!listen` | `/listen` | Panggil bot ke voice channel untuk merekam & membalas suara. | `w!listen` |
| `w!setpersona <sifat>`| `/setpersona` | Mengubah sifat AI (contoh: galak, tsundere, wibu). | `w!setpersona wibu` |
| `w!chat <pesan>` | `/chat` | Mengobrol dengan bot tanpa perlu mengetik prefix lagi. | `w!chat halo bro` |
| `w!roast @user` | `/roast` | AI me-roast profil Discord pengguna secara sarkas & lucu. | `w!roast @Equiv` |
| `w!rate @user` | `/rate` | AI menilai pesona member (skala 1-10) dengan analisis kocak. | `w!rate @Equiv` |
| `w!shipper @u1 @u2` | `/shipper` | Menggambar Love Card & meramal kecocokan cinta. | `w!shipper @u1 @u2` |
| `w!marry @user` | `/marry` | Mengajak member lain untuk bertunangan/menikah virtual. | `w!marry @Equiv` |
| `w!divorce` | `/divorce` | Menceraikan pasangan nikah virtual saat ini. | `w!divorce` |
| `w!adopt @user` | `/adopt` | Mengadopsi member lain sebagai anak angkat. | `w!adopt @Equiv` |
| `w!family` | `/family` | Menghasilkan gambar bagan silsilah keluarga (Pillow PNG). | `w!family` |
| `w!quiz` | `/quiz` | Mengikuti kuis kognitif trivia berhadiah koin dari AI. | `w!quiz` |

### Kategori C: Utilitas & Keamanan
| Command Prefix | Command Slash | Deskripsi | Contoh Penggunaan |
| :--- | :--- | :--- | :--- |
| `w!checkbots` | `/checkbots` | Memeriksa bot mana saja yang aktif dan latensinya. | `w!checkbots` |
| `w!find @user` | `/find` | Melacak status durasi user nongkrong di Voice Channel. | `w!find @Equiv` |
| `w!ping` | `/ping` | Menampilkan latensi koneksi API Discord ke server bot. | `w!ping` |
| `w!poll <tanya>;<o1>;<o2>`| `/poll` | Membuat pemungutan suara interaktif (maks 5 opsi). | `w!poll Mabar?;Ya;Tidak` |
| `w!giveaway` | `/giveaway` | Mengadakan pembagian koin dengan pengundian otomatis. | `w!giveaway` |
| `w!birthday set <tgl-bln>`| `/birthday` | Mendaftarkan ulang hari ulang tahun (format: DD-MM). | `w!birthday set 26-05` |
| `w!kas` | `/kas` | Memeriksa total saldo pajak brankas server. | `w!kas` |

---

## 🛠️ Panduan Pemeliharaan & Administrasi (Maintenance Guide)

Untuk menjaga performa W2E Bot tetap prima dan bebas dari gangguan, ikuti petunjuk pengelolaan administrasi sistem berikut ini.

### 1. Struktur Basis Data (Database Schema)
Seluruh data utama disimpan di dalam file database SQLite tunggal (`w2ebot.db`). Struktur tabelnya adalah sebagai berikut:

#### Tabel `DiscordStat`
Menyimpan status ekonomi, level, koin, dan waktu klaim harian pemain:
* `id` (TEXT, PRIMARY KEY): ID Saluran/Pengguna Discord unik.
* `displayName` (TEXT): Nama tampilan terakhir pengguna.
* `coins` (INTEGER): Jumlah koin saat ini.
* `xp` (INTEGER): XP saat ini dalam level yang berjalan (0 hingga `level * 100`).
* `level` (INTEGER): Tingkat Level RPG saat ini.
* `lastDaily` (TEXT): Waktu ISO-8601 pengambilan bonus harian terakhir.
* `updatedAt` (TEXT): Waktu pembaruan data terakhir.

#### Tabel `ChatMemory`
Menyimpan memori obrolan teks pengguna dengan AI `/chat` atau `/ai`:
* `id` (INTEGER, PRIMARY KEY AUTOINCREMENT): ID unik baris memori.
* `timestamp` (TEXT): Waktu percakapan dilakukan.
* `content` (TEXT): Konten teks obrolan berbentuk JSON terformat (menyimpan role `user` dan `model` untuk konteks berkelanjutan).

#### Tabel `json_store`
Menyimpan data cadangan JSON secara internal ke database.

### 2. Backup & Pemulihan (Backup & Disaster Recovery)
Sangat direkomendasikan untuk melakukan backup berkala secara harian (Daily Backup) pada file-file berikut untuk menghindari kehilangan progres database pemain:
* **`w2ebot.db`** (Database SQLite utama)
* **`users.json`** (Menyimpan data perkawinan, adopsi, inventory, dan pencapaian)
* **`quests.json`** (Menyimpan riwayat quests harian user)
* **`birthdays.json`** (Menyimpan tanggal lahir user)
* **`config.json`** (File konfigurasi server)

#### Perintah Backup Otomatis di Linux (Cronjob)
Tambahkan cronjob di VPS Anda untuk menyalin database ke folder backup setiap malam jam 12:
```bash
0 0 * * * cp /path/to/w2ebot/w2ebot.db /path/to/backup/w2ebot_$(date +\%F).db
```

### 3. Mekanisme Self-Healing Level-Up
Bot ini dilengkapi dengan logika penyembuhan mandiri (*Self-Healing Leveling System*). 
* **Masalah**: Jika ada modul background task (seperti penambahan XP otomatis saat masuk Voice Channel) memperbarui database langsung tanpa memicu pemberitahuan level up, XP pengguna bisa menumpuk melebihi kapasitas levelnya (misalnya `260 / 100 XP`).
* **Solusi**: Logika internal di dalam `get_discord_stat` secara otomatis mendeteksi ketidaksesuaian ini saat data dibaca (misalnya saat membuka `/profile`), menghitung ulang level yang benar secara berulang (*looping*), memperbarui database SQLite ke nilai yang benar, dan menampilkan informasi level terbaru dengan instan. Admin tidak perlu melakukan sinkronisasi database manual jika terjadi ketidaksesuaian XP.

### 4. Pengelolaan Font & Tampilan UI Gambar
Gambar Profile Card dan Love Card digambar menggunakan **Pillow**.
* Font yang digunakan adalah **Poppins (Bold, Medium, Regular, Light)**.
* Bot akan memeriksa keberadaan font di folder `./fonts` pada saat startup. Jika font tidak ditemukan, bot akan secara otomatis mengunduhnya langsung dari repositori Google Fonts ke direktori lokal Anda.
* **Troubleshooting Font**: Jika teks pada profile tumpang tindih atau rusak, hapus folder `./fonts` dan restart bot untuk memicu pengunduhan ulang font yang bersih.

---

## 🔍 Troubleshooting (Pemecahan Masalah)

#### ❓ Masalah 1: Bot Offline atau Tidak Merespon
1. **Pemeriksaan Proses**: Jalankan perintah berikut di PowerShell (Windows) untuk memastikan apakah proses python bot sedang berjalan:
   ```powershell
   Get-CimInstance Win32_Process -Filter "name = 'python.exe'" | Select-Object ProcessId, CommandLine
   ```
2. **Crash Loop**: Periksa logs konsol. Jika terjadi crash berulang karena error token, periksa apakah file `.env` sudah diisi dengan benar dan token Discord tidak kedaluwarsa.

#### ❓ Masalah 2: Fitur Merekam Suara (`w!listen`) Gagal / Error Voice Channel
1. Pastikan Anda sudah mengunduh **FFmpeg** dan meletakkan folder bin-nya ke dalam *System Environment Variables PATH* sistem operasi Anda. Ketik `ffmpeg -version` di command prompt untuk memverifikasi.
2. Pastikan pustaka binding suara Python telah ter-install:
   ```bash
   pip install PyNaCl
   ```
3. Pastikan bot memiliki izin untuk menghubungkan diri (*Connect*) dan berbicara (*Speak*) pada Voice Channel target di Discord Server Anda.

#### ❓ Masalah 3: Bot API Dashboard Gagal Diakses
* Bot menjalankan web server terintegrasi berbasis `aiohttp` pada port `8081`. Pastikan port `8081` tidak sedang digunakan oleh aplikasi lain di VPS/Server Anda. 
* Jika Anda meng-host menggunakan Docker, pastikan port mapping pada file `docker-compose.yml` diarahkan dengan benar (`8081:8081`).

---

## 👥 Kontribusi & Lisensi
Proyek ini dikembangkan secara eksklusif untuk ekosistem **Way 2 Eternal (W2E)**. Segala bentuk kontribusi kode silakan diajukan melalui mekanisme *Pull Request* pada repositori GitHub resmi.

* **Lisensi**: Hak cipta dilindungi undang-undang. Hanya untuk penggunaan internal komunitas Way 2 Eternal.
