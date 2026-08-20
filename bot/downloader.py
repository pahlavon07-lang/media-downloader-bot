"""
yt-dlp bilan ishlash uchun yordamchi modul.

Bu modulda ikkita asosiy funksiya bor:

- :func:`extract_info`  — link haqida ma'lumot oladi (sarlavha, muallif,
  davomiylik, preview-rasm, mavjud sifatlar ro'yxati), lekin hech narsa
  yuklab olmaydi.
- :func:`download_media` — foydalanuvchi tanlagan sifatda faylni
  vaqtinchalik papkaga yuklab oladi va uning yo'lini qaytaradi.

yt-dlp o'zi sinxron (blocking) kutubxona bo'lgani uchun, botning asosiy
event-loop'ini band qilib qo'ymasligi uchun barcha chaqiruvlar
``asyncio.to_thread`` orqali alohida oqimda (thread) bajariladi.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yt_dlp

logger = logging.getLogger(__name__)

# Yuklab olingan vaqtinchalik fayllar shu papkada saqlanadi.
YUKLAB_OLISH_PAPKASI = Path(tempfile.gettempdir()) / "media_downloader_bot"
YUKLAB_OLISH_PAPKASI.mkdir(parents=True, exist_ok=True)

# Telegram Bot API orqali yuborish mumkin bo'lgan maksimal fayl hajmi.
MAX_FAYL_HAJMI_BAYT = 50 * 1024 * 1024  # 50 MB


class YuklabOlishXatosi(Exception):
    """Foydalanuvchiga tushunarli xato ko'rsatish uchun umumiy istisno."""


@dataclass
class SifatVarianti:
    """Foydalanuvchiga tugma sifatida ko'rsatiladigan bitta sifat varianti."""

    kalit: str  # masalan: "1080", "720", "audio", "image"
    matn: str  # tugmada ko'rinadigan matn, masalan: "1080p"


@dataclass
class MediaMalumot:
    """extract_info() natijasi — postni yuklab olishdan oldingi ma'lumot."""

    url: str
    sarlavha: str
    muallif: str | None
    davomiylik_soniya: int | None
    thumbnail_url: str | None
    sifatlar: list[SifatVarianti] = field(default_factory=list)
    # Agar True bo'lsa — bu video emas, oddiy rasm-post (masalan
    # Instagram/Facebook'dagi rasm), va yagona variant "image" bo'ladi.
    faqat_rasm: bool = False


# Barcha ehtimoliy sifat presetlari, kattadan kichikkacha tartibda.
_BARCHA_SIFATLAR = [
    SifatVarianti("best", "🎬 Eng yaxshi sifat"),
    SifatVarianti("1080", "1080p"),
    SifatVarianti("720", "720p"),
    SifatVarianti("480", "480p"),
    SifatVarianti("audio", "🎵 Faqat audio (MP3)"),
]

_YTDLP_ASOSIY_SOZLAMALAR: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    # Ba'zi saytlar (Instagram, Facebook) uchun oddiy User-Agent kerak bo'ladi.
    "extractor_args": {"generic": {"impersonate": ["chrome"]}},
}


def _formatlar_orasidan_balandliklarni_topish(info: dict[str, Any]) -> set[int]:
    """info['formats'] ichidan mavjud video balandliklarini (height) yig'adi."""
    balandliklar: set[int] = set()
    for fmt in info.get("formats") or []:
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")
        if height and vcodec and vcodec != "none":
            balandliklar.add(int(height))
    return balandliklar


def _sifatlar_royxatini_tuzish(info: dict[str, Any]) -> tuple[list[SifatVarianti], bool]:
    """Ma'lumot asosida foydalanuvchiga ko'rsatiladigan sifat tugmalarini tanlaydi."""
    balandliklar = _formatlar_orasidan_balandliklarni_topish(info)

    if not balandliklar:
        # Video format topilmadi — demak bu rasm-post (Instagram/Facebook'da
        # ko'p uchraydi) yoki audio-only kontent bo'lishi mumkin.
        if info.get("thumbnail") or info.get("thumbnails"):
            return [SifatVarianti("image", "🖼 Rasmni yuklash")], True
        # Video ham, rasm ham topilmasa — faqat audio variantini taklif qilamiz.
        return [SifatVarianti("audio", "🎵 Faqat audio (MP3)")], False

    natija: list[SifatVarianti] = [_BARCHA_SIFATLAR[0]]  # "best" doim mavjud
    for variant in _BARCHA_SIFATLAR[1:-1]:  # 1080/720/480
        chegara = int(variant.kalit)
        if any(h >= chegara - 40 for h in balandliklar):  # kichik tolerantlik
            natija.append(variant)
    natija.append(_BARCHA_SIFATLAR[-1])  # audio doim mavjud
    return natija, False


def _eng_katta_thumbnail(info: dict[str, Any]) -> str | None:
    """info ichidan eng sifatli preview-rasm URL'ini tanlaydi."""
    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        # yt-dlp odatda thumbnails'ni kichikdan kattaga saralaydi.
        return thumbnails[-1].get("url")
    return info.get("thumbnail")


def _malumotni_sinxron_olish(url: str) -> dict[str, Any]:
    """yt-dlp orqali linkni tekshiradi (bloklovchi chaqiruv, alohida oqimda ishlatiladi)."""
    sozlamalar = dict(_YTDLP_ASOSIY_SOZLAMALAR)
    with yt_dlp.YoutubeDL(sozlamalar) as ydl:
        return ydl.extract_info(url, download=False)


async def extract_info(url: str) -> MediaMalumot:
    """Berilgan link haqida ma'lumot qaytaradi (yuklab olmasdan).

    Xato yuz bersa (link noto'g'ri, kontent topilmadi, tarmoq xatosi va
    h.k.), :class:`YuklabOlishXatosi` ko'tariladi — undagi matn
    foydalanuvchiga to'g'ridan-to'g'ri ko'rsatilishi mumkin.
    """
    try:
        info = await asyncio.to_thread(_malumotni_sinxron_olish, url)
    except yt_dlp.utils.DownloadError as exc:
        raise YuklabOlishXatosi(_xatoni_ozbek_tiliga_ogirish(str(exc))) from exc
    except Exception as exc:  # noqa: BLE001 — foydalanuvchiga umumiy xabar beramiz
        logger.exception("extract_info kutilmagan xato: %s", url)
        raise YuklabOlishXatosi(
            "Havolani tekshirishda kutilmagan xatolik yuz berdi. "
            "Iltimos, biroz vaqtdan so'ng qayta urinib ko'ring."
        ) from exc

    if info is None:
        raise YuklabOlishXatosi("Bu havoladan ma'lumot topilmadi.")

    # Ba'zida playlist/karusel qaytishi mumkin — birinchi elementini olamiz.
    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        if not entries:
            raise YuklabOlishXatosi(
                "Bu havolada yuklab olish mumkin bo'lgan kontent topilmadi."
            )
        info = entries[0]

    sifatlar, faqat_rasm = _sifatlar_royxatini_tuzish(info)

    return MediaMalumot(
        url=url,
        sarlavha=(info.get("title") or "Nomsiz post").strip()[:200],
        muallif=info.get("uploader") or info.get("channel") or info.get("uploader_id"),
        davomiylik_soniya=info.get("duration"),
        thumbnail_url=_eng_katta_thumbnail(info),
        sifatlar=sifatlar,
        faqat_rasm=faqat_rasm,
    )


def _format_tanlash_qatori(sifat_kaliti: str) -> str:
    """Berilgan sifat kaliti uchun yt-dlp'ning `format` parametrini quradi."""
    if sifat_kaliti == "best":
        return "bestvideo+bestaudio/best"
    if sifat_kaliti in {"1080", "720", "480"}:
        balandlik = sifat_kaliti
        return (
            f"bestvideo[height<={balandlik}]+bestaudio/best[height<={balandlik}]/best"
        )
    # audio va image uchun format tanlash kerak emas (alohida ishlanadi).
    return "bestvideo+bestaudio/best"


def _sinxron_yuklab_olish(url: str, sifat_kaliti: str, maqsad_papka: Path) -> Path:
    """Faylni haqiqatda diskka yuklaydi (bloklovchi, alohida oqimda ishlatiladi)."""
    fayl_nomi_shabloni = str(maqsad_papka / "%(id)s.%(ext)s")

    sozlamalar: dict[str, Any] = dict(_YTDLP_ASOSIY_SOZLAMALAR)
    sozlamalar["outtmpl"] = fayl_nomi_shabloni

    if sifat_kaliti == "image":
        # Video/audio o'rniga faqat eng katta preview-rasmni yuklaymiz.
        with yt_dlp.YoutubeDL(dict(_YTDLP_ASOSIY_SOZLAMALAR)) as ydl:
            info = ydl.extract_info(url, download=False)
        thumb_url = _eng_katta_thumbnail(info)
        if not thumb_url:
            raise YuklabOlishXatosi("Bu posttan rasm topilmadi.")
        import urllib.request

        nom = f"{uuid.uuid4().hex}.jpg"
        yol = maqsad_papka / nom
        urllib.request.urlretrieve(thumb_url, yol)  # noqa: S310 — ishonchli manba (yt-dlp bergan URL)
        return yol

    if sifat_kaliti == "audio":
        sozlamalar["format"] = "bestaudio/best"
        sozlamalar["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        sozlamalar["format"] = _format_tanlash_qatori(sifat_kaliti)
        sozlamalar["merge_output_format"] = "mp4"

    with yt_dlp.YoutubeDL(sozlamalar) as ydl:
        info = ydl.extract_info(url, download=True)
        if info.get("_type") == "playlist":
            info = (info.get("entries") or [info])[0]
        yakuniy_yol = Path(ydl.prepare_filename(info))

    # Audio uchun kengaytma mp3'ga o'zgargan bo'lishi mumkin.
    if sifat_kaliti == "audio" and not yakuniy_yol.exists():
        yakuniy_yol = yakuniy_yol.with_suffix(".mp3")

    if not yakuniy_yol.exists():
        # Ba'zida yt-dlp fayl nomini biroz boshqacha yozadi — papkadan qidiramiz.
        nomzodlar = sorted(
            maqsad_papka.glob(f"{yakuniy_yol.stem}.*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if nomzodlar:
            yakuniy_yol = nomzodlar[0]
        else:
            raise YuklabOlishXatosi(
                "Fayl yuklab olindi, lekin uni diskdan topib bo'lmadi. "
                "Iltimos, qayta urinib ko'ring."
            )

    return yakuniy_yol


async def download_media(url: str, sifat_kaliti: str) -> Path:
    """Media faylni vaqtinchalik papkaga yuklab, uning to'liq yo'lini qaytaradi.

    Chaqiruvchi (handler) faylni yuborib bo'lgach, uni o'chirib tashlashi
    kerak (masalan ``path.unlink(missing_ok=True)``).
    """
    # Har bir yuklab olish uchun alohida vaqtinchalik papka — fayllar
    # bir-biriga aralashmasligi va tozalash osonroq bo'lishi uchun.
    maqsad_papka = YUKLAB_OLISH_PAPKASI / uuid.uuid4().hex
    maqsad_papka.mkdir(parents=True, exist_ok=True)

    try:
        return await asyncio.to_thread(
            _sinxron_yuklab_olish, url, sifat_kaliti, maqsad_papka
        )
    except YuklabOlishXatosi:
        raise
    except yt_dlp.utils.DownloadError as exc:
        raise YuklabOlishXatosi(_xatoni_ozbek_tiliga_ogirish(str(exc))) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("download_media kutilmagan xato: %s (%s)", url, sifat_kaliti)
        raise YuklabOlishXatosi(
            "Faylni yuklab olishda kutilmagan xatolik yuz berdi. "
            "Iltimos, biroz vaqtdan so'ng qayta urinib ko'ring."
        ) from exc


def _xatoni_ozbek_tiliga_ogirish(xato_matni: str) -> str:
    """yt-dlp'ning ingliz tilidagi xato xabarini foydalanuvchiga tushunarli qilib beradi."""
    matn = xato_matni.lower()

    if "private" in matn or "login" in matn:
        return (
            "Bu kontent shaxsiy (private) akkauntga tegishli yoki tizimga "
            "kirishni talab qiladi. Faqat ochiq (public) postlarni yuklab "
            "olish mumkin."
        )
    if "unsupported url" in matn or "no extractor" in matn:
        return "Bu havola qo'llab-quvvatlanmaydi. Iltimos, boshqa link yuboring."
    if "404" in matn or "not found" in matn:
        return "Post topilmadi. Havola noto'g'ri yoki o'chirilgan bo'lishi mumkin."
    if "unable to download webpage" in matn or "network" in matn or "timed out" in matn:
        return "Tarmoq xatosi yuz berdi. Iltimos, birozdan so'ng qayta urinib ko'ring."

    return (
        "Havolani qayta ishlashda xatolik yuz berdi. Havola to'g'ri va "
        "ochiq (public) ekanligiga ishonch hosil qiling, so'ng qayta "
        "urinib ko'ring."
    )
