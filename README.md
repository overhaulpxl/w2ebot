# Way 2 Eternal Bot (W2E) 🤖✨

Way 2 Eternal Bot adalah Discord Bot modern berskala *Enterprise/Cloud-Ready* yang memadukan **Kecerdasan Buatan (Gemini 2.5 Flash)**, **Sistem Game RPG & Ekonomi Sultan (Market 3.0)**, dan **Visualisasi Gambar Dinamis menggunakan Pillow**, yang tersimpan aman di database relasional **SQLite**.

Bot ini menggunakan arsitektur **Modular Cogs (discord.py)** untuk skalabilitas maksimum, mengelola puluhan command secara terstruktur (RPG, AI, Utils) dengan performa tinggi berkat optimasi query asynchronous menggunakan `aiosqlite`.

---

## 🌟 Project Overview

Proyek ini dibangun untuk komunitas Discord yang menginginkan fitur lengkap dalam satu bot tanpa perlu mengundang banyak bot berbeda. Fitur unggulannya meliputi:
1. **AI Chat & Persona**: Mengobrol layaknya manusia dengan gaya bahasa kustom (Gen-Z, Wibu, dll). Memori chat tersimpan secara permanen.
2. **RPG & Ekonomi**: Simulasi bursa saham (Market), tambang kripto (Mining Rigs), Boss Raid, Judi Casino, dan Manajemen Inventori.
3. **Sosial & Visual**: Pernikahan virtual, adopsi anak, hingga pembuatan silsilah keluarga (Family Tree) dan Kartu Profil bergambar yang di-*generate* secara dinamis menggunakan Pillow.
4. **Sistem Hibrida Command**: Mendukung **Slash Commands** (`/`) dari Discord secara bawaan, dan secara ajaib juga mendukung **Prefix Commands** (`w!`) berkat sistem `FakeInteraction` internal yang menerjemahkan pesan teks biasa ke eksekusi sistem Slash Command.

---

## 🛠️ Setup & Installation Steps

### Persyaratan Sistem (Prerequisites)
* **Python 3.10** ke atas
* **FFmpeg** (Untuk voice listener/music) ter-install di PATH OS Anda
* Token Bot Discord & API Key Gemini

### Instalasi Lokal
1. **Kloning Repositori & Install Dependensi**:
   ```bash
   git clone https://github.com/overhaulpxl/w2ebot.git
   cd w2ebot
   pip install -r requirements.txt
   ```

2. **Konfigurasi Lingkungan (`.env`)**:
   Buat file `.env` di folder utama:
   ```env
   DISCORD_TOKEN=TOKEN_BOT_DISCORD_ANDA
   GEMINI_API_KEY=KEY_GEMINI_AI_ANDA
   ALLOWED_SERVER_ID=887968847842402355
   BOT_PREFIX=w!
   ```

3. **Menjalankan Bot**:
   Windows: Klik dua kali `run_all.bat` atau ketik:
   ```bash
   python main.py
   ```

### Instalasi dengan Docker (Production)
Bot ini telah dikonfigurasi untuk langsung jalan di Docker menggunakan `docker-compose.yml`.
```bash
# Buat file database kosong terlebih dahulu
touch w2ebot.db

# Jalankan container di background
docker compose up -d --build
```

---

## 🏗️ How Each Function / Core Component Works

Arsitektur W2E Bot dibagi menjadi beberapa komponen utama untuk memisahkan logika dan memudahkan pemeliharaan:

1. **`main.py` (Entry Point)**: 
   File peluncur utama. Memuat modul konfigurasi dasar dan mengimpor file `core.py`, serta meregistrasi seluruh sub-modul (Cogs) dari folder `cogs/` (seperti `rpg`, `ai`, dan `utils`).
2. **`core.py` (Core Library & Database)**: 
   Jantung dari bot. File ini mengelola koneksi `aiosqlite` ke database, fungsi manipulasi JSON/Dictionary (load_json, save_json dengan cache memory `_json_cache` O(1) time complexity), pengaturan Intent (termasuk `message_content`), serta *event listener* utama seperti `on_ready` dan `on_message`.
3. **`FakeInteraction` (Prefix Wrapper)**:
   Berada di `core.py`, kelas ini memotong (intercept) pesan masuk dari `on_message` yang diawali dengan `BOT_PREFIX`. Kelas ini "berpura-pura" menjadi `discord.Interaction` untuk mengelabui argumen slash command, sehingga member dapat memanggil fungsi Slash Command menggunakan teks biasa.
4. **`cogs/rpg.py`**:
   Menangani seluruh game, matematika, perjudian, toko, boss raid, dan mining kripto.
5. **`cogs/ai.py`**:
   Menangani permintaan API ke Google Gemini 2.5 Flash, manajemen sejarah (memory) percakapan, perintah persona, dan analisis sentimen (*roasting*, *rate*, *shipper*).
6. **`cogs/utils.py`**:
   Utilitas harian seperti cek latency (`ping`), pemungutan suara (`poll`), giveaway, pengingat (`remindme`), serta radar bot dan player (`find`, `checkbots`).

---

## 📘 List of All Features / Commands

Berikut adalah daftar lengkap ke-54 command yang tersedia. Semua command bisa dipanggil menggunakan **Prefix** (contoh: `w!help`) atau **Slash** (contoh: `/help`).

### Kategori A: RPG & Ekonomi
* **`daily`** - Klaim koin dan XP harian.
* **`weekly`** - Klaim jatah mingguan koin.
* **`work`** - Bekerja menambang koin.
* **`profile`** - Menampilkan gambar kartu profil lengkap dengan level dan aset.
* **`shop`** - Membuka UI toko W2E.
* **`buy <item>`** / **`sell <item>`** - Transaksi item.
* **`inventory`** - Mengecek tas dan buff aktif.
* **`rob @user`** - Mencuri koin member lain.
* **`transfer @user <jumlah>`** - Mengirim koin secara aman.
* **`top`** - Menampilkan Leaderboard (Orang Terkaya & Level Tertinggi).
* **`buyrig <tier>`** - Membeli mesin mining penghasil pasif income.
* **`miner`** - Cek efisiensi mesin mining.
* **`market`** - Cek grafik naik turun mata uang kripto fiktif.
* **`portfolio`** - Mengecek total aset investasi kripto.
* **`quest`** - Melihat progres misi harian/mingguan.
* **`attack`** - Serang bos Raid bersama-sama.
* **`buypet <pet>`** - Beli peliharaan untuk menambah daya serang.

### Kategori B: Judi & Kasino
* **`cf <pilihan> <bet>`** - Tebak koin kepala/ekor (Heads/Tails).
* **`flip`** - Lempar koin biasa.
* **`slot`** - Putar mesin slot buah.
* **`blackjack <bet>`** - Judi kartu remi klasik melawan bandar AI.
* **`tebak <angka>`** - Judi tebak angka (1-10).
* **`crash <bet>`** - Taruhan grafik naik sebelum hancur!
* **`gacha`** - Buka gulungan gacha item waifu berbayar.
* **`box`** - Buka Mystery Loot Box.
* **`rps`** - Main batu gunting kertas.

### Kategori C: AI & Sosial
* **`ai <pesan>`** - Ngobrol pintar dengan Gemini.
* **`chat <pesan>`** - Ngobrol santai tanpa embel-embel AI.
* **`setpersona <sifat>`** - Mengubah kepribadian balasan AI (Galak, Wibu, Bijak, dll).
* **`listen`** - AI merekam dan membalas obrolan Voice Channel Anda.
* **`roast @user`** - AI menghina target secara sarkas dan lucu.
* **`rate @user`** - AI menilai seberapa menarik seseorang dari skala 1-10.
* **`image`** - AI membuatkan gambar berdasarkan teks (*Prompt*).
* **`shipper @user1 @user2`** - Meramal kecocokan jodoh (Gambar Love Card).
* **`marry @user`** / **`divorce`** - Hubungan pernikahan virtual server.
* **`adopt @user`** / **`family`** - Hubungan anak angkat dan visualisasi bagan keluarga.

### Kategori D: Utilitas
* **`help`** - Membuka menu panduan interaktif ini.
* **`ping`** - Cek ping (latensi) bot.
* **`poll <tanya>;<opsi>`** - Buat sistem voting / poling untuk komunitas.
* **`giveaway`** - Selenggarakan Giveaway berbatas waktu (Khusus Admin).
* **`find @user`** - Mencari tahu target sedang nongkrong di Voice Channel mana.
* **`checkbots`** - Mengecek semua bot musik yang sedang memutar lagu di server.
* **`remindme <menit> <pesan>`** - Alarm pengingat dari bot.
* **`birthday <tanggal>`** - Atur ulang tahun Anda untuk kejutan.
* **`bg <url>`** - Ubah gambar background (banner) Profile Card RPG Anda.
* **`kas`** - Mengecek saldo pajak brankas admin server.
* **`valo`** - Mem-ping kawan se-server untuk mabar Valorant.

---

## 🎮 Example Usage

Berikut adalah contoh skenario seru yang bisa Anda lakukan menggunakan Bot W2E:

**Skenario 1: Menjadi Kaya dari Kripto Fiktif**
> **Player:** `w!buyrig 2` *(Membeli mesin Mining Rig Tier 2 seharga koin mahal)*
> **Player:** `w!miner` *(Mengecek kecepatan hashing mesin tersebut, dan menunggu jam gajian)*
> **Player:** `w!market` *(Menunggu harga ETHR turun merah, lalu membelinya dalam jumlah besar)*
> **Player:** `w!portfolio` *(Menikmati grafik hijau saat harga ETHR melonjak naik dan menjualnya!)*

**Skenario 2: Interaksi Emosional dengan AI**
> **User:** `w!setpersona Pembantu rumah tangga galak bernama Inem`
> *(AI mengubah karakternya di memori database)*
> **User:** `w!chat buatin kopi dong nem`
> **Bot:** *(Membalas dengan marah-marah)* "Bikin sendiri dong, lu kira gue babu robot gratisan? Kopi di laci, air panas di dispenser, ngapain nunggu gue, bos malas!"
> **User:** `w!roast @Joko`
> **Bot:** "Joko? Muka lu mirip kuli bangunan salah alamat, mending lu kuli di pelabuhan aja wkwk."

**Skenario 3: Bertahan Hidup Lewat Perjudian Berbahaya**
> **Player:** `w!crash 10000` *(Mempertaruhkan 10 Ribu Koin)*
> *(Grafik mulai naik: 1.2x... 1.5x... 1.8x)*
> *(Player mengeklik tombol Stop)*
> *(Grafik hancur di 1.9x)*
> **Bot:** "Selamat! Anda berhasil kabur di 1.8x dan memenangkan 18,000 Koin!"

---

*Hak Cipta © Way 2 Eternal Community. Developed with ♥ by the W2E Dev Team.*
