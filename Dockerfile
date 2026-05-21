FROM python:3.10-slim

# Install system dependencies (FFmpeg is required for music bots)
RUN apt-get update && apt-get install -y ffmpeg libffi-dev libnacl-dev python3-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install sqlitedict yt-dlp aiohttp spotipy bs4 Pillow

# Copy source code
COPY . .

# Set up runner script
RUN chmod +x start.sh

# Expose Web API ports
EXPOSE 8080
EXPOSE 8082

CMD ["./start.sh"]
