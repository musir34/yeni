"""MNG shipmentStatusCode → panel gönderi durumu (saf, DB'siz).

Standard Query sözleşmesi:
  1 Gönderi Hazırlandı          → hazirlandi   (barkod alındı, kurye henüz almadı)
  2 Transfer Aşamasında         → kargoda
  3 Teslimat Birimine Ulaştı    → kargoda
  4 Alıcı Adresine Yönlendirildi→ dagitimda
  5 Teslim Edildi               → teslim
  6 Teslim Edilemedi            → teslim_edilemedi
  7 Geri Geliyor                → geri
  8 Destek Gerekiyor            → destek
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .govde import tek_kayit

SIPARIS_ACILDI = "siparis_acildi"   # createOrder OK, barkod (createbarcode) henüz alınmadı — MNG şubeyi çözüyor
HAZIRLANDI = "hazirlandi"
KARGODA = "kargoda"
DAGITIMDA = "dagitimda"
TESLIM = "teslim"
TESLIM_EDILEMEDI = "teslim_edilemedi"
GERI = "geri"
DESTEK = "destek"
IPTAL = "iptal"
BILINMIYOR = "bilinmiyor"

KOD_HARITASI = {
    1: HAZIRLANDI,
    2: KARGODA,
    3: KARGODA,
    4: DAGITIMDA,
    5: TESLIM,
    6: TESLIM_EDILEMEDI,
    7: GERI,
    8: DESTEK,
}

# Kargo yola çıktı sayılan durumlar (kaynak kaydı "Kargoda / Kargoya Verildi" olur)
YOLDA = frozenset({KARGODA, DAGITIMDA, TESLIM_EDILEMEDI, GERI, DESTEK})
# Takibi biten durumlar (job bir daha sormaz)
KAPANMIS = frozenset({TESLIM, IPTAL})
# İlerleme sırası: MNG arada eski kodu döndürse de kayıt geri gitmez
SIRA = {SIPARIS_ACILDI: 1, HAZIRLANDI: 2, KARGODA: 3, DAGITIMDA: 4, TESLIM_EDILEMEDI: 4, GERI: 4, DESTEK: 4, TESLIM: 5}


def geri_mi(eski: str, yeni: str) -> bool:
    """yeni, eski'den geride mi (ikisi de sıralı durumsa)."""
    return SIRA.get(eski, 0) > SIRA.get(yeni, 0) > 0

ETIKETLER = {
    SIPARIS_ACILDI: "Sipariş MNG'de, barkod bekliyor",
    HAZIRLANDI: "Gönderi Hazırlandı",
    KARGODA: "Kargoda",
    DAGITIMDA: "Dağıtımda",
    TESLIM: "Teslim Edildi",
    TESLIM_EDILEMEDI: "Teslim Edilemedi",
    GERI: "Geri Geliyor",
    DESTEK: "Destek Gerekiyor",
    IPTAL: "İptal Edildi",
    BILINMIYOR: "Bilinmiyor",
}

_TARIH_BICIMLERI = ("%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y")


@dataclass(frozen=True)
class GonderiDurumu:
    kod: int | None
    durum: str
    mng_metni: str
    shipment_id: str
    teslim_edildi: bool
    teslim_alan: str
    teslim_zamani: datetime | None
    takip_url: str

    @property
    def etiket(self) -> str:
        return ETIKETLER.get(self.durum, ETIKETLER[BILINMIYOR])

    @property
    def yolda(self) -> bool:
        return self.durum in YOLDA

    @property
    def kapanmis(self) -> bool:
        return self.durum in KAPANMIS


def kod_cevir(kod) -> str:
    try:
        return KOD_HARITASI.get(int(kod), BILINMIYOR)
    except (TypeError, ValueError):
        return BILINMIYOR


def tarih_cevir(deger) -> datetime | None:
    if not deger or not isinstance(deger, str):
        return None
    for bicim in _TARIH_BICIMLERI:
        try:
            return datetime.strptime(deger.strip(), bicim)
        except ValueError:
            continue
    return None


def durum_cozumle(govde) -> GonderiDurumu:
    """getshipmentstatus cevabı (tek nesne ya da tek elemanlı liste) → GonderiDurumu."""
    kayit = tek_kayit(govde)
    kod = kayit.get("shipmentStatusCode")
    try:
        kod = int(kod) if kod is not None else None
    except (TypeError, ValueError):
        kod = None
    durum = kod_cevir(kod)
    teslim = kayit.get("isDelivered") in (1, True, "1") or durum == TESLIM
    return GonderiDurumu(
        kod=kod,
        durum=TESLIM if teslim else durum,
        mng_metni=str(kayit.get("shipmentStatus") or ""),
        shipment_id=str(kayit.get("shipmentId") or ""),
        teslim_edildi=teslim,
        teslim_alan=str(kayit.get("deliveryTo") or "").strip(),
        teslim_zamani=tarih_cevir(kayit.get("deliveryDateTime")),
        takip_url=str(kayit.get("trackingUrl") or "").strip(),
    )
