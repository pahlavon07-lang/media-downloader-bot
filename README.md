# Media Downloader — Telegram Bot

Instagram, Facebook, TikTok, YouTube, Twitter/X, Pinterest va boshqa ko'plab
ijtimoiy tarmoqlardagi ochiq (public) rasm, video va audiolarni Telegram
orqali yuklab beruvchi bot. **aiogram 3 + yt-dlp** asosida yozilgan.

## Qanday ishlaydi

1. Foydalanuvchi botga havola (link) yuboradi.
2. Bot havoladan ma'lumot oladi (sarlavha, preview-rasm, mavjud sifatlar)
   va sifat tugmalarini ko'rsatadi (masalan 1080p, 720p, faqat audio).
3. Foydalanuvchi tugmani bosadi → bot faylni yuklab, to'g'ridan-to'g'ri
   Telegram orqali yuboradi.

Instagram/Facebook rasm-postlar uchun (video topilmasa) bot avtomatik
ravishda rasmni JPG sifatida yuboradi.

## Loyihaning tuzilishi

```
telegram-bot/
├── bot/
│   ├── __init__.py
│   ├── handlers.py     # /start, /help, link va tugma handlerlari
│   ├── downloader.py   # yt-dlp bilan ishlash logikasi
│   └── cache.py        # tugmalar uchun qisqa URL-kesh
├── main.py              # bot ishga tushirish nuqtasi (polling)
├── requirements.txt
├── Dockerfile
├── .env.example
├── .gitignore
└── .dockerignore
```

## 1-qadam: Bot yaratish va token olish

1. Telegram'da [@BotFather](https://t.me/BotFather) ga yozing.
2. `/newbot` buyrug'ini yuboring, botga nom va username bering
   (username `bot` bilan tugashi kerak, masalan `MyDownloader_bot`).
3. BotFather sizga token beradi, masalan:
   `123456789:AAExampleTokenHereChangeMe`. Uni saqlab qo'ying va hech
   kimga bermang.

## 2-qadam: Lokal ishga tushirish

Talab: Python 3.11+ va **ffmpeg**.

```bash
# ffmpeg o'rnatish (Ubuntu/Debian misolida)
sudo apt-get install -y ffmpeg

# virtual muhit va kutubxonalar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# tokenni sozlash
cp .env.example .env
# .env faylini oching va BOT_TOKEN=... qatoriga o'z tokeningizni yozing

# botni ishga tushirish
python main.py
```

Terminalda "Bot ishga tushmoqda (polling)..." degan xabarni ko'rsangiz,
bot ishlayapti. Endi Telegram'da botingizga o'ting va /start yuboring.

## Docker orqali ishga tushirish

```bash
docker build -t media-downloader-bot .
docker run -d --restart unless-stopped --env-file .env media-downloader-bot
```

## Hosting bo'yicha tavsiya

Bot **polling** rejimida ishlaydi (Telegram serverlariga o'zi so'rov
yuborib turadi), shuning uchun unga tashqi domen yoki SSL sertifikat
shart emas.

### 1) Railway.app yoki Render.com (eng oson)

- Loyihani GitHub'ga push qiling.
- Railway/Render'da "New Project" → "Deploy from GitHub repo".
- **Muhim:** Render'da bu botni "Web Service" emas, **"Background
  Worker"** turi sifatida deploy qiling (chunki bot hech qanday HTTP
  port tinglamaydi). Railway'da oddiy "Service" sifatida ishlayveradi.
- Environment Variables bo'limiga `BOT_TOKEN` ni qo'shing.
- Bepul/arzon tarif kichik botlar uchun yetarli.

### 2) VPS (Timeweb, DigitalOcean, Hetzner va h.k.)

Doimiy ishlashi va uzilib qolmasligi uchun eng ishonchli yo'l:

```bash
git clone <sizning-repo> && cd telegram-bot
docker build -t media-downloader-bot .
docker run -d --restart unless-stopped --env-file .env --name dl-bot media-downloader-bot
```

Yoki Docker'siz, `systemd` xizmati sifatida:

```ini
# /etc/systemd/system/media-downloader-bot.service
[Unit]
Description=Media Downloader Telegram Bot
After=network.target

[Service]
WorkingDirectory=/opt/telegram-bot
ExecStart=/opt/telegram-bot/.venv/bin/python main.py
EnvironmentFile=/opt/telegram-bot/.env
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now media-downloader-bot
```

### Qaysi birini tanlash kerak?

- Tez sinab ko'rish → **Railway** yoki **Render Background Worker**.
- Doimiy, ishonchli, arzon → **Hetzner/Timeweb VPS ($4-5/oy)** + systemd
  yoki Docker.

## Muhim cheklovlar

- **Fayl hajmi**: oddiy Telegram Bot API orqali bot maksimal ~50 MB
  hajmdagi faylni yubora oladi. Kattaroq video/audio uchun xatolik
  ko'rsatiladi. (Buni oshirish uchun o'zingizning Local Bot API Server
  ishga tushirish kerak bo'ladi — bu ilg'or mavzu.)
- **Faqat ochiq kontent**: shaxsiy (private) akkauntlar yoki
  login talab qiluvchi postlarni yuklab bo'lmaydi.

## Muhim eslatma (huquqiy)

Bu bot faqat ochiq (public) va shaxsiy foydalanish uchun mo'ljallangan.
Har bir platforma (Instagram, Facebook va h.k.) o'z Foydalanish
shartlariga ega, va boshqa mualliflarning kontentini ularning ruxsatisiz
yuklab olib qayta tarqatish mualliflik huquqini buzishi mumkin. Botni
faqat o'zingizga tegishli kontent yoki ochiq litsenziyali/ruxsat berilgan
kontent uchun ishlating.

## Kengaytirish g'oyalari

- Guruh chatlarida ishlashini yaxshilash (bot admin bo'lishi kerak
  bo'lgan holatlarni boshqarish).
- Foydalanuvchilar uchun so'rovlar sonini cheklash (rate limiting).
- Webhook rejimiga o'tish (agar server doimiy HTTP portga ega bo'lsa,
  polling'dan tezroq javob beradi).
- Yuklab olishlar statistikasini bazada saqlash.
