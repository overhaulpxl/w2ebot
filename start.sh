#!/bin/bash
echo "Menyiapkan W2E Main Bot..."

# Pastikan database ada
touch w2ebot.db

# Jalankan RPG & AI Bot di background sementara untuk memicu inisialisasi tabel
echo "Memulai inisialisasi skema bot..."
python main.py &
BOT_PID=$!

# Tunggu 10 detik agar bot selesai membuat tabel SQLite dasar
sleep 10

# Matikan bot sementaranya
kill $BOT_PID
wait $BOT_PID 2>/dev/null

echo "Menyuntikkan Kunci Keamanan Dashboard..."
python setup_my_dashboard.py

echo "Menjalankan W2E Main Bot secara permanen..."
# Jalankan bot di foreground agar Docker tetap hidup
exec python main.py