#!/bin/bash
echo "Menjalankan W2E Bots Cluster..."

# Jalankan RPG Bot di background
python bot.py &

# Jalankan Music Bot Biasa di background
# python music_bot.py &

# Jalankan Custom Premium Music Bot di foreground (agar container tetap hidup)
python w2e_custom_music_bot.py
