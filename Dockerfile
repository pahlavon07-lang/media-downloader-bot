# Media Downloader Telegram Bot uchun Docker image.
FROM python:3.11-slim

# yt-dlp video+audio birlashtirish va audio konvertatsiya qilish uchun
# ffmpeg'ga muhtoj.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bot HTTP port tinglamaydi (polling rejimida ishlaydi), shuning uchun
# EXPOSE shart emas. Hosting'da uni "Background Worker" sifatida ishga
# tushiring.
CMD ["python", "main.py"]
