"""
Botning barcha xabar va tugma (callback) ishlovchilari (handlerlari).

Ishlash tartibi:

1. Foydalanuvchi ``https://`` bilan boshlanuvchi havola yuboradi.
2. Bot "Tekshirilmoqda..." xabarini ko'rsatib, ``extract_info()`` orqali
   post haqida ma'lumot oladi va mavjud sifatlar bilan tugmalar chiqaradi.
3. Foydalanuvchi bitta sifat tugmasini bosadi.
4. Bot "Yuklanmoqda..." xabarini ko'rsatib, ``download_media()`` orqali
   faylni yuklab oladi va uni Telegram orqali yuboradi.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.cache import olish, saqlash
from bot.downloader import (
    MAX_FAYL_HAJMI_BAYT,
    MediaMalumot,
    YuklabOlishXatosi,
    download_media,
    extract_info,
)

logger = logging.getLogger(__name__)
router = Router(name="asosiy")

_LINK_REGEX = re.compile(r"https?://\S+")

_XUSH_KELIBSIZ_MATNI = (
    "👋 Salom! Men ijtimoiy tarmoqlardagi ochiq (public) rasm, video va "
    "audiolarni yuklab beruvchi botman.\n\n"
    "Quyidagi tarmoqlardan havola yuborsangiz bo'ldi:\n"
    "• Instagram\n"
    "• Facebook\n"
    "• TikTok\n"
    "• YouTube\n"
    "• Twitter / X\n"
    "• Pinterest\n"
    "• va yana ko'plab boshqa saytlar\n\n"
    "Shunchaki havolani menga yuboring — men sizga mavjud sifatlarni "
    "ko'rsataman! /help orqali batafsil qo'llanmani ko'rishingiz mumkin."
)

_YORDAM_MATNI = (
    "📖 <b>Qo'llanma</b>\n\n"
    "1️⃣ Ijtimoiy tarmoqdagi (Instagram, Facebook, TikTok, YouTube va h.k.) "
    "ochiq postning havolasini nusxalab, menga yuboring.\n"
    "2️⃣ Men post haqida ma'lumot olib, mavjud sifatlarni tugmalar orqali "
    "ko'rsataman (masalan 1080p, 720p, faqat audio).\n"
    "3️⃣ Kerakli tugmani bosing — men faylni yuklab, sizga yuboraman.\n\n"
    "⚠️ <b>Muhim cheklovlar:</b>\n"
    "• Telegram orqali maksimal ~50 MB hajmdagi fayl yuborish mumkin.\n"
    "• Faqat ochiq (public) postlarni yuklab olish mumkin, shaxsiy "
    "(private) akkauntlardagi kontentni emas.\n\n"
    "⚖️ Botdan faqat o'zingizga tegishli yoki ochiq litsenziyali "
    "kontent uchun foydalaning — boshqalarning mualliflik huquqidagi "
    "postlarini ruxsatsiz tarqatmang."
)


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    """/start buyrug'i — xush kelibsiz xabari."""
    await message.answer(_XUSH_KELIBSIZ_MATNI)


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    """/help buyrug'i — qisqa qo'llanma."""
    await message.answer(_YORDAM_MATNI, parse_mode="HTML")


def _sifatlar_klaviaturasi(malumot: MediaMalumot) -> InlineKeyboardMarkup:
    """MediaMalumot asosida sifat tanlash uchun inline klaviatura quradi."""
    url_kaliti = saqlash(malumot.url)
    tugmalar = [
        [
            InlineKeyboardButton(
                text=variant.matn,
                callback_data=f"dl:{url_kaliti}:{variant.kalit}",
            )
        ]
        for variant in malumot.sifatlar
    ]
    return InlineKeyboardMarkup(inline_keyboard=tugmalar)


def _malumot_matni(malumot: MediaMalumot) -> str:
    """Post haqida foydalanuvchiga ko'rsatiladigan qisqa ma'lumot matnini quradi."""
    qatorlar = [f"📌 <b>{malumot.sarlavha}</b>"]
    if malumot.muallif:
        qatorlar.append(f"👤 Muallif: {malumot.muallif}")
    if malumot.davomiylik_soniya:
        daqiqa, soniya = divmod(int(malumot.davomiylik_soniya), 60)
        qatorlar.append(f"⏱ Davomiyligi: {daqiqa:02d}:{soniya:02d}")
    qatorlar.append("\nKerakli sifatni tanlang 👇")
    return "\n".join(qatorlar)


@router.message(F.text.regexp(_LINK_REGEX))
async def link_handler(message: Message) -> None:
    """Xabar tarkibidan https:// bilan boshlanuvchi havola topilsa ishga tushadi."""
    match = _LINK_REGEX.search(message.text or "")
    if not match:
        return
    url = match.group(0)

    holat_xabari = await message.answer("🔎 Tekshirilmoqda, biroz kuting...")

    try:
        malumot = await extract_info(url)
    except YuklabOlishXatosi as exc:
        await holat_xabari.edit_text(f"❌ {exc}")
        return
    except Exception:  # noqa: BLE001
        logger.exception("link_handler kutilmagan xato: %s", url)
        await holat_xabari.edit_text(
            "❌ Kutilmagan xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
        )
        return

    matn = _malumot_matni(malumot)
    klaviatura = _sifatlar_klaviaturasi(malumot)

    await holat_xabari.delete()

    if malumot.thumbnail_url:
        try:
            await message.answer_photo(
                photo=malumot.thumbnail_url,
                caption=matn,
                parse_mode="HTML",
                reply_markup=klaviatura,
            )
            return
        except Exception:  # noqa: BLE001
            # Preview-rasmni yuborib bo'lmasa, oddiy matn bilan davom etamiz.
            logger.warning("Preview-rasmni yuborib bo'lmadi: %s", url)

    await message.answer(matn, parse_mode="HTML", reply_markup=klaviatura)


@router.callback_query(F.data.startswith("dl:"))
async def yuklab_olish_callback(callback: CallbackQuery) -> None:
    """Foydalanuvchi sifat tugmasini bosganda ishga tushadi."""
    if not callback.data or not callback.message:
        await callback.answer()
        return

    qismlar = callback.data.split(":", 2)
    if len(qismlar) != 3:
        await callback.answer("❌ Noto'g'ri so'rov.", show_alert=True)
        return

    _, url_kaliti, sifat_kaliti = qismlar
    url = olish(url_kaliti)

    if url is None:
        await callback.answer(
            "⌛ Bu havola uchun so'rov muddati tugagan. Iltimos, linkni "
            "qaytadan yuboring.",
            show_alert=True,
        )
        return

    await callback.answer("⬇️ Yuklanmoqda...")
    holat_xabari = await callback.message.answer("⬇️ Yuklanmoqda, biroz kuting...")

    fayl_yoli: Path | None = None
    try:
        fayl_yoli = await download_media(url, sifat_kaliti)

        hajm = fayl_yoli.stat().st_size
        if hajm > MAX_FAYL_HAJMI_BAYT:
            await holat_xabari.edit_text(
                "❌ Fayl hajmi 50 MB dan katta bo'lgani uchun Telegram "
                "orqali yuborib bo'lmaydi. Iltimos, pastroq sifatni "
                "tanlab ko'ring."
            )
            return

        kirish_fayli = FSInputFile(fayl_yoli)

        if sifat_kaliti == "audio":
            await callback.message.answer_audio(kirish_fayli)
        elif sifat_kaliti == "image":
            await callback.message.answer_photo(kirish_fayli)
        else:
            await callback.message.answer_video(kirish_fayli)

        await holat_xabari.delete()

    except YuklabOlishXatosi as exc:
        await holat_xabari.edit_text(f"❌ {exc}")
    except Exception:  # noqa: BLE001
        logger.exception(
            "yuklab_olish_callback kutilmagan xato: %s (%s)", url, sifat_kaliti
        )
        await holat_xabari.edit_text(
            "❌ Faylni yuborishda kutilmagan xatolik yuz berdi. Iltimos, "
            "qayta urinib ko'ring."
        )
    finally:
        if fayl_yoli is not None:
            fayl_yoli.unlink(missing_ok=True)


@router.message(F.text)
async def boshqa_xabarlar(message: Message) -> None:
    """Havola topilmagan har qanday boshqa matnli xabarga javob."""
    await message.answer(
        "🤔 Men faqat ijtimoiy tarmoqlardagi havolalarni tushunaman.\n"
        "Iltimos, Instagram, Facebook, TikTok, YouTube va h.k. saytlardan "
        "https:// bilan boshlanuvchi to'g'ri havolani yuboring.\n\n"
        "Yordam uchun /help buyrug'ini yuboring."
    )
