"""sync_details günlük temizliği.

Stok senkronu her barkod × platform için sync_details'e satır yazar (günde ~1,9 milyon). Silen bir iş
olmadığı için Ocak-Ekim 2026 arasında ~190 milyon satır / 41 GB birikti ve 17 Ekim 2026'da disk doldu
(panel + iade köprüsü düştü). Panel bu tabloyu yalnız son senkron durumu ve hata listesi için okur;
eski kayda ihtiyaç yok. Bu iş her gece SYNC_DETAY_SAKLAMA_GUN (varsayılan 7) günden eski satırları
küçük partilerle siler (uzun kilit yok). Boşalan yer Postgres'te yeniden kullanılır (dosya küçülmez).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

VARSAYILAN_SAKLAMA_GUN = 7
PARTI = 50_000
AZAMI_PARTI = 400            # tek koşuda en çok 20 milyon satır; kalan ertesi gece


def saklama_gun() -> int:
    try:
        return max(1, int(os.getenv("SYNC_DETAY_SAKLAMA_GUN") or VARSAYILAN_SAKLAMA_GUN))
    except ValueError:
        return VARSAYILAN_SAKLAMA_GUN


def sync_detay_temizle(gun: int | None = None, parti: int = PARTI, azami_parti: int = AZAMI_PARTI,
                       simdi: datetime | None = None) -> int:
    """created_at < (şimdi − gün) olan sync_details satırlarını partiler halinde siler; silinen sayıyı döner."""
    esik = (simdi or datetime.utcnow()) - timedelta(days=gun if gun is not None else saklama_gun())
    silinen = 0
    for _ in range(azami_parti):
        sonuc = db.session.execute(
            text("DELETE FROM sync_details WHERE id IN "
                 "(SELECT id FROM sync_details WHERE created_at < :esik ORDER BY id LIMIT :parti)"),
            {"esik": esik, "parti": parti},
        )
        db.session.commit()
        adet = sonuc.rowcount or 0
        silinen += adet
        if adet < parti:
            break
    logger.info("[SYNC TEMİZLİK] sync_details: %s satır silindi (eşik %s)", silinen, esik.strftime("%Y-%m-%d %H:%M"))
    return silinen


def temizlik_isi() -> int:
    """Zamanlayıcı girişi; hata yutulur."""
    try:
        return sync_detay_temizle()
    except Exception:
        db.session.rollback()
        logger.exception("[SYNC TEMİZLİK] sync_details temizliği başarısız (yutuldu)")
        return 0
