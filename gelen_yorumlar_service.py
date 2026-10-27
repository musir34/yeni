# gelen_yorumlar_service.py — 💬 Güllü Yorum (Shopify yorum uygulaması) gönderim takibi — SALT OKUNUR
# Güllü Yorum panelle aynı sunucuda ayrı bir uygulamadır; e-posta gönderimlerini kendi SQLite
# dosyasında tutar (requests / submissions). Bu modül o dosyayı yalnızca okur:
#  - Hiçbir tabloya yazılmaz, Güllü Yorum'un .env'i okunmaz, Shopify'a gidilmez.
#  - Bağlantı her çağrıda açılıp kapanır (gunicorn worker'ında tutulmaz).
#  - Dosya yoksa / açılamazsa GelenYorumHata fırlatılır; sayfa "ulaşılamadı" gösterir.
# Flask/DB bağımlılığı yok → saf testlenebilir (tests/test_gelen_yorumlar.py).
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

# Brif §1: /home/musir/shopify-uygulamalari/gullu-yorum/data/gullu_yorum.sqlite3 (sahibi musir, panelle aynı kullanıcı)
VARSAYILAN_DB = "/home/musir/shopify-uygulamalari/gullu-yorum/data/gullu_yorum.sqlite3"
DB_YOLU = os.getenv("GULLU_YORUM_DB", VARSAYILAN_DB)
BAGLANTI_ZAMAN_ASIMI_SN = 5

# Durum kodları (liste satırı): öncelik yorum > baktı > açmadı
DURUM_YORUM = "yorum"
DURUM_BAKTI = "bakti"
DURUM_ACMADI = "acmadi"
DURUM_ETIKETLERI = {
    DURUM_YORUM: ("Yorum yaptı", "success"),
    DURUM_BAKTI: ("Baktı, yazmadı", "warning"),
    DURUM_ACMADI: ("Açmadı", "secondary"),
}

OZET_SQL = """
SELECT
  COUNT(*)                                                     AS gonderilen,
  COALESCE(SUM(first_viewed_at IS NOT NULL), 0)                AS bakan,
  COALESCE(SUM(order_id IN (SELECT order_id FROM submissions)), 0) AS yorum_yapan,
  COALESCE(SUM(reminder_sent_at IS NOT NULL), 0)               AS hatirlatma_giden,
  COALESCE(SUM(incentive_amount > 0 AND refunded_at IS NULL
      AND order_id IN (SELECT order_id FROM submissions)), 0)  AS iade_bekleyen,
  COALESCE(SUM(CASE WHEN incentive_amount > 0 AND refunded_at IS NULL
      AND order_id IN (SELECT order_id FROM submissions)
      THEN incentive_amount ELSE 0 END), 0)                    AS iade_bekleyen_tutar
FROM requests
WHERE delivered = 1
"""

LISTE_SQL = """
SELECT
  r.order_name,
  r.customer_name,
  r.email,
  r.sent_at,
  r.first_viewed_at,
  MIN(s.submitted_at) AS reviewed_at,
  COUNT(s.handle)     AS yorum_sayisi,
  r.incentive_amount,
  r.refunded_at,
  r.reminder_sent_at
FROM requests r
LEFT JOIN submissions s ON s.order_id = r.order_id
WHERE r.delivered = 1
GROUP BY r.order_id
ORDER BY r.sent_at DESC
"""


class GelenYorumHata(Exception):
    """Güllü Yorum verisine ulaşılamadı (dosya yok, açılamadı, şema beklenmedik)."""


@dataclass(frozen=True)
class Ozet:
    gonderilen: int = 0
    bakan: int = 0
    yorum_yapan: int = 0
    hatirlatma_giden: int = 0
    iade_bekleyen: int = 0
    iade_bekleyen_tutar: int = 0

    @property
    def bakan_yuzde(self) -> int:
        return _yuzde(self.bakan, self.gonderilen)

    @property
    def yorum_yuzde(self) -> int:
        return _yuzde(self.yorum_yapan, self.gonderilen)


@dataclass(frozen=True)
class Satir:
    order_name: str
    customer_name: str
    email_maskeli: str
    sent_at: datetime | None
    first_viewed_at: datetime | None
    reviewed_at: datetime | None
    yorum_sayisi: int
    incentive_amount: int
    refunded_at: datetime | None
    reminder_sent_at: datetime | None
    durum: str

    @property
    def durum_etiketi(self) -> str:
        return DURUM_ETIKETLERI[self.durum][0]

    @property
    def durum_renk(self) -> str:
        return DURUM_ETIKETLERI[self.durum][1]

    @property
    def iade_bekliyor(self) -> bool:
        """Teşvikli + yorum yapmış + iade henüz işaretlenmemiş."""
        return self.incentive_amount > 0 and self.durum == DURUM_YORUM and self.refunded_at is None


# ──────────────────────────── Yardımcılar ────────────────────────────

def _yuzde(pay: int, payda: int) -> int:
    return round(pay * 100 / payda) if payda else 0


def utc_parse(deger) -> datetime | None:
    """Güllü Yorum ISO-UTC metni ('2026-10-27T11:41:30Z') → tz-aware UTC datetime.
    Boş/None/bozuk → None (ekranda '—'). Gösterimde `| ist` filtresi İstanbul'a çevirir."""
    if not deger or not isinstance(deger, str):
        return None
    metin = deger.strip()
    if metin.endswith("Z"):
        metin = metin[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(metin)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def email_maskele(email) -> str:
    """Kişisel veri: 'ayse.yilmaz@gmail.com' → 'ay***@gmail.com'. Boş → ''."""
    if not email or "@" not in email:
        return "" if not email else "***"
    yerel, alan = email.rsplit("@", 1)
    gorunen = yerel[:2] if len(yerel) > 2 else yerel[:1]
    return f"{gorunen}***@{alan}"


def _durum(reviewed_at, first_viewed_at) -> str:
    if reviewed_at:
        return DURUM_YORUM
    if first_viewed_at:
        return DURUM_BAKTI
    return DURUM_ACMADI


def _satir_yap(row) -> Satir:
    reviewed_at = utc_parse(row["reviewed_at"])
    first_viewed_at = utc_parse(row["first_viewed_at"])
    return Satir(
        order_name=row["order_name"] or "",
        customer_name=row["customer_name"] or "",
        email_maskeli=email_maskele(row["email"]),
        sent_at=utc_parse(row["sent_at"]),
        first_viewed_at=first_viewed_at,
        reviewed_at=reviewed_at,
        yorum_sayisi=int(row["yorum_sayisi"] or 0),
        incentive_amount=int(row["incentive_amount"] or 0),
        refunded_at=utc_parse(row["refunded_at"]),
        reminder_sent_at=utc_parse(row["reminder_sent_at"]),
        durum=_durum(reviewed_at, first_viewed_at),
    )


# ──────────────────────────── Okuma ────────────────────────────

def _baglan(db_yolu: str) -> sqlite3.Connection:
    """Brif §3: salt okunur URI (mode=ro); WAL yüzünden `immutable` KULLANILMAZ."""
    if not os.path.isfile(db_yolu):
        raise GelenYorumHata(f"Güllü Yorum veri dosyası yok: {db_yolu}")
    try:
        conn = sqlite3.connect(f"file:{db_yolu}?mode=ro", uri=True, timeout=BAGLANTI_ZAMAN_ASIMI_SN)
    except sqlite3.Error as e:
        raise GelenYorumHata(f"Güllü Yorum veri tabanı açılamadı: {e}") from e
    conn.row_factory = sqlite3.Row
    return conn


def oku(db_yolu: str | None = None, sadece_yorum: bool = False) -> tuple[Ozet, list[Satir]]:
    """Özet + liste; her çağrıda aç-kapat. sadece_yorum=True → yalnız yorum yapanlar."""
    yol = db_yolu or DB_YOLU
    conn = _baglan(yol)
    try:
        try:
            ozet_row = conn.execute(OZET_SQL).fetchone()
            rows = conn.execute(LISTE_SQL).fetchall()
        except sqlite3.Error as e:
            raise GelenYorumHata(f"Güllü Yorum sorgusu başarısız: {e}") from e
    finally:
        conn.close()
    ozet = Ozet(**{k: int(ozet_row[k] or 0) for k in ozet_row.keys()})
    satirlar = [_satir_yap(r) for r in rows]
    if sadece_yorum:
        satirlar = [s for s in satirlar if s.durum == DURUM_YORUM]
    return ozet, satirlar
