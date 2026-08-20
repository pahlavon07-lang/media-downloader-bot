"""
Qisqa muddatli in-memory kesh.

Telegram inline tugmalarining ``callback_data`` maydoni 64 baytdan
oshmasligi kerak, shu sababli uzun URL manzillarni to'g'ridan-to'g'ri
tugmaga joylab bo'lmaydi. Buning o'rniga URL (va boshqa kerakli
ma'lumotlar) shu keshda qisqa uuid-kalit bilan saqlanadi, tugmaga esa
faqat o'sha kalit joylashtiriladi.

Kesh butunlay operativ xotirada ishlaydi (bazasiz), shuning uchun bot
qayta ishga tushirilganda tozalanadi. Bu oddiy bot uchun yetarli.
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from typing import Any

# Keshda bir vaqtning o'zida saqlanadigan yozuvlarning maksimal soni.
# Shu sondan oshsa, eng eski yozuvlar avtomatik o'chiriladi (LRU uslubida).
_MAX_HAJM = 500

# Har bir yozuv shu vaqtdan (soniyada) ko'p turib qolsa, eskirgan
# hisoblanadi va so'ralganda ham qaytarilmaydi.
_YASHASH_MUDDATI_SONIYA = 6 * 60 * 60  # 6 soat

# Kalit -> (qiymat, yaratilgan_vaqt) tarzida saqlaymiz.
_kesh: "OrderedDict[str, tuple[Any, float]]" = OrderedDict()


def saqlash(qiymat: Any) -> str:
    """Berilgan qiymatni keshga saqlaydi va unga mos qisqa kalitni qaytaradi."""
    _eskilarni_tozalash()

    # Kesh hajmi chegaradan oshib ketmasligi uchun eng eski
    # (birinchi qo'shilgan) yozuvlarni o'chirib boramiz.
    while len(_kesh) >= _MAX_HAJM:
        _kesh.popitem(last=False)

    kalit = uuid.uuid4().hex[:12]
    _kesh[kalit] = (qiymat, time.monotonic())
    return kalit


def olish(kalit: str) -> Any | None:
    """Kalitga mos qiymatni qaytaradi, topilmasa yoki eskirgan bo'lsa None."""
    _eskilarni_tozalash()
    yozuv = _kesh.get(kalit)
    if yozuv is None:
        return None
    return yozuv[0]


def _eskilarni_tozalash() -> None:
    """Yashash muddati o'tib ketgan yozuvlarni keshdan olib tashlaydi."""
    hozir = time.monotonic()
    eskirgan_kalitlar = [
        kalit
        for kalit, (_, vaqt) in _kesh.items()
        if hozir - vaqt > _YASHASH_MUDDATI_SONIYA
    ]
    for kalit in eskirgan_kalitlar:
        _kesh.pop(kalit, None)
