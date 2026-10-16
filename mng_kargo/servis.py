"""MNG giden gönderi servisi — DB'li katman.

Trendyol'un siparişe otomatik referans üretmesi gibi: değişim / manuel sipariş /
Shopify siparişi oluştuğu anda MNG'de sipariş açılır (referans), kısa süre sonra barkod
alınır (takip no + MNG etiketi), takip işi durumu sorar ve kaynak kaydın statüsünü kendisi
düşürür. "Kargoya ver" demeye gerek kalmaz.

MNG'nin iki aşama kuralı (entegrasyon yazısı + canlı prova 2026-10-15):
  1. createOrder  → sipariş kaydı anında (alıcıya göre varış şubesi MNG'de çözülür)
  2. createbarcode → sipariş İŞLEME ALININCA (değişim "İşleme Al", site siparişi "Hazirlaniyor",
     manuel "Hazırlanıyor/Kargoya Hazır") ya da etiket basılınca: barkod_iste() bayrağı koyar ve dener;
     MNG o anda alıcıya "kargonuz hazırlandı" SMS'i atar (govde.SMS_HAZIRLANDI). Erken istenirse
     20001 "VARIŞ ŞUBESİ BULUNAMADI" → kayıt 'siparis_acildi'de kalır, takip işi (5 dk) tekrar dener.
  İptal: barkod alınmadıysa cancelorder, alındıysa cancelshipment (şube kabulünden önce).
  Kapıda ödeme: MNG alt sınırı 20 TL (altı 20001 ile reddedilir).

Açma/kapama anahtarı: MNG_OTOMATIK_GONDERI=1 (.env). Kapalıyken hiçbir çağrı yapılmaz,
kayıt açılmaz, tabloya gidilmez; eski elle akış aynen çalışır.

Referans biçimi (≤20, BÜYÜK, müşteri bazında tekil):
  değişim  → DG + kargo_kodu (555XXXXXXX)      örn. DG5551234567
  manuel   → MN + yeni_siparisler.id           örn. MN8421
  shopify  → SH + sipariş adı rakamları        örn. SH1428
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal

from models import KargoGonderi, db

from .ayar import MngAyar
from .client import MngClient, MngHata, sube_cozulmedi
from .durum import (
    BILINMIYOR, HAZIRLANDI, IPTAL, KAPANMIS, SIPARIS_ACILDI, TESLIM, YOLDA, GonderiDurumu, geri_mi,
)
from .govde import Alici, GonderiIstegi, parca_adetle, referans_normalize

logger = logging.getLogger(__name__)

KAYNAK_DEGISIM = "degisim"
KAYNAK_MANUEL = "manuel"
KAYNAK_SHOPIFY = "shopify"
DURUM_BEKLIYOR = "bekliyor"     # API'ye henüz gidilmedi / gidemedi (yeniden denenir)
DURUM_HATA = "hata"             # deneme sınırı doldu ya da kalıcı hata, insan bakmalı
MAX_DENEME = 5
YENIDEN_DENEME_PENCERESI = timedelta(days=3)
SORGU_ARALIGI = timedelta(minutes=20)       # aynı gönderi bu süreden sık sorulmaz
KAPIDA_ODEME_MIN = Decimal("20")            # MNG: "Tahsilatlı Kapıda Gönderi Tutar en az 20 TL"
TAKIP_URL_SABLON = os.getenv("MNG_TAKIP_URL_SABLON") or "https://kargotakip.dhlecommerce.com.tr/?takipNo={shipment_id}"


def otomatik_acik() -> bool:
    return (os.getenv("MNG_OTOMATIK_GONDERI") or "0").strip() in ("1", "true", "True", "evet")


_client: MngClient | None = None


def client() -> MngClient:
    global _client
    if _client is None:
        _client = MngClient(MngAyar.from_env())
    return _client


def client_sifirla() -> None:
    """Testler / ayar değişimi için."""
    global _client
    _client = None


# ---------------------------------------------------------------- referans
def degisim_referansi(kargo_kodu: str) -> str:
    return referans_normalize(f"DG{kargo_kodu}")


def manuel_referansi(siparis_id: int) -> str:
    return referans_normalize(f"MN{int(siparis_id)}")


def shopify_referansi(siparis_adi: str) -> str:
    rakamlar = re.sub(r"\D", "", str(siparis_adi or ""))
    if not rakamlar:
        raise ValueError(f"Shopify sipariş adından numara çıkmadı: {siparis_adi!r}")
    return referans_normalize(f"SH{rakamlar}")


# ---------------------------------------------------------------- sorgular
# Anahtar kapalıyken tabloya hiç gidilmez: kod tablo betiğinden önce deploy edilse de
# (kargo_gonderi yokken) silme / liste akışları Postgres'te iptal edilmiş işlemde kalmaz.
# Açıkken sorgular savepoint içinde koşar; tablo hatası yalnız savepoint'i geri alır.

def _savepoint_icinde(sorgu):
    try:
        with db.session.begin_nested():
            return sorgu()
    except Exception:
        logger.warning("[MNG] kargo_gonderi sorgusu başarısız (tablo yok mu?)", exc_info=True)
        return None


def gonderi_bul(kaynak: str, kaynak_ref: str) -> KargoGonderi | None:
    """Aktif (iptal olmayan) gönderi kaydı."""
    if not otomatik_acik():
        return None
    return _savepoint_icinde(lambda: (
        KargoGonderi.query
        .filter_by(kaynak=kaynak, kaynak_ref=str(kaynak_ref))
        .filter(KargoGonderi.durum != IPTAL)
        .order_by(KargoGonderi.id.desc())
        .first()))


def shopify_gonderi_bul(siparis_no: str) -> KargoGonderi | None:
    """Site siparişinin aktif gönderisi; panelde sipariş iki adla dolaşır:
    'SH-<Shopify id>' (sipariş hazırla/listesi, üretim) → kaynak_ref, '#1446' (mağaza adı,
    Shopify Siparişler sayfası ve sipariş hazırla 'Yazdır') → kaynak_ad."""
    ham = str(siparis_no or "").strip()
    if not ham or not otomatik_acik():
        return None
    if ham.upper().startswith("SH-"):
        return gonderi_bul(KAYNAK_SHOPIFY, ham[3:])
    if not ham.startswith("#"):          # Trendyol/manuel numaraları buraya düşmesin
        return None
    return _savepoint_icinde(lambda: (
        KargoGonderi.query
        .filter_by(kaynak=KAYNAK_SHOPIFY, kaynak_ad=ham)
        .filter(KargoGonderi.durum != IPTAL)
        .order_by(KargoGonderi.id.desc())
        .first()))


def etiketi_var(kayit: KargoGonderi | None) -> bool:
    """MNG etiketi basılabilir mi: ZPL alınmış ya da sipariş açık (etiket sayfası barkodu o anda alır)."""
    return bool(kayit) and (bool(kayit.zpl) or kayit.durum == SIPARIS_ACILDI)


def gonderi_kaydi_var(kaynak: str, kaynak_ref: str) -> bool:
    """İptal dahil herhangi bir kayıt var mı (iptal edilen referans MNG'de kullanılmış sayılır,
    aynı kaynağa ikinci kez açılmaz; gerekirse Kargo Gönderileri sayfasından elle)."""
    if not otomatik_acik():
        return False
    return bool(_savepoint_icinde(lambda: (
        KargoGonderi.query.filter_by(kaynak=kaynak, kaynak_ref=str(kaynak_ref)).first())))


def gonderi_haritasi(kaynak: str, kaynak_refler) -> dict[str, KargoGonderi]:
    refler = [str(r) for r in kaynak_refler if r]
    if not refler or not otomatik_acik():
        return {}
    kayitlar = _savepoint_icinde(lambda: (
        KargoGonderi.query
        .filter(KargoGonderi.kaynak == kaynak, KargoGonderi.kaynak_ref.in_(refler))
        .filter(KargoGonderi.durum != IPTAL)
        .order_by(KargoGonderi.id.asc())
        .all())) or []
    return {k.kaynak_ref: k for k in kayitlar}   # aynı ref'te son kayıt kazanır


# ---------------------------------------------------------------- açma
def _kayit_olustur(kaynak, kaynak_ref, kaynak_ad, referans, alici: Alici, kapida_odeme_tutari, adet: int = 1) -> KargoGonderi:
    kayit = KargoGonderi(
        kaynak=kaynak, kaynak_ref=str(kaynak_ref), kaynak_ad=(kaynak_ad or "")[:60],
        referans=referans, ortam=client().ayar.ortam, durum=DURUM_BEKLIYOR, parca_adet=max(1, int(adet or 1)),
        kapida_odeme_tutari=Decimal(str(kapida_odeme_tutari)) if kapida_odeme_tutari else None,
        alici_ad=(alici.ad_soyad or "")[:120], alici_telefon=(alici.telefon or "")[:30],
        alici_adres=alici.adres, il=(alici.il or "")[:40], ilce=(alici.ilce or "")[:40],
    )
    db.session.add(kayit)
    db.session.flush()
    return kayit


def _istek_kur(kayit: KargoGonderi, icerik: str = "Ayakkabi", aciklama: str = "") -> GonderiIstegi:
    alici = Alici(ad_soyad=kayit.alici_ad or "", adres=kayit.alici_adres or "",
                  telefon=kayit.alici_telefon or "", il=kayit.il or "", ilce=kayit.ilce or "")
    # İl/ilçe adlarını MNG'nin listesine oturt + kodları doldur (önbellekli; başarısızsa adlarla devam)
    try:
        from .cbs import alici_tamamla
        alici = alici_tamamla(alici)
        kayit.il = (alici.il or kayit.il or "")[:40]
        kayit.ilce = (alici.ilce or kayit.ilce or "")[:40]
    except Exception:
        logger.warning("[MNG] il/ilçe çözümleme atlandı (%s)", kayit.referans, exc_info=True)
    return GonderiIstegi(
        referans=kayit.referans, alici=alici, parcalar=(parca_adetle(kayit.parca_adet or 1),),
        kapida_odeme_tutari=float(kayit.kapida_odeme_tutari) if kayit.kapida_odeme_tutari else None,
        icerik=icerik, aciklama=aciklama or f"Gullu Shoes {kayit.kaynak_ad or kayit.referans}",
    )


def _hata_yaz(kayit: KargoGonderi, exc: Exception, kalici: bool = False) -> None:
    kayit.hata = str(exc)[:2000]
    kayit.durum = DURUM_HATA if (kalici or kayit.deneme >= MAX_DENEME) else DURUM_BEKLIYOR


def _api_ile_ac(kayit: KargoGonderi, icerik: str = "Ayakkabi", aciklama: str = "") -> bool:
    """1. aşama: createOrder. Başarı → siparis_acildi (barkod takip işinde / etikette alınır)."""
    if kayit.kapida_odeme_tutari and Decimal(kayit.kapida_odeme_tutari) < KAPIDA_ODEME_MIN:
        kayit.hata = f"Kapıda ödeme tutarı MNG alt sınırının ({KAPIDA_ODEME_MIN} TL) altında: {kayit.kapida_odeme_tutari}"
        kayit.durum = DURUM_HATA
        return False
    kayit.deneme = (kayit.deneme or 0) + 1
    try:
        client().siparis_olustur(_istek_kur(kayit, icerik, aciklama))
    except (MngHata, ValueError) as exc:
        _hata_yaz(kayit, exc)
        logger.warning("[MNG] sipariş açılamadı %s (%s. deneme): %s", kayit.referans, kayit.deneme, exc)
        return False
    kayit.durum = SIPARIS_ACILDI
    kayit.hata = None
    kayit.deneme = 0
    logger.info("[MNG] sipariş açıldı %s", kayit.referans)
    return True


def barkod_al(kayit: KargoGonderi, bekle: bool = False) -> bool:
    """2. aşama: createbarcode → takip no + barkod + ZPL. Şube çözülmediyse (20001) kayıt
    siparis_acildi'de kalır, sonraki turda denenir (bekle=True: istemci 5+10 sn bekleyip tekrar dener,
    etiket basımı gibi anlık ihtiyaçta)."""
    if kayit.durum != SIPARIS_ACILDI:
        return False
    try:
        cevap = client().barkod_olustur(_istek_kur(kayit), tekrar=bekle)
    except (MngHata, ValueError) as exc:
        if isinstance(exc, MngHata) and sube_cozulmedi(exc):
            kayit.hata = "MNG varış şubesini henüz çözmedi; barkod sonraki turda alınacak"
            return False
        kayit.deneme = (kayit.deneme or 0) + 1
        _hata_yaz(kayit, exc, kalici=True)       # 20 TL sınırı, adres hatası vb. → insan baksın
        kayit.durum = DURUM_HATA
        logger.warning("[MNG] barkod alınamadı %s: %s", kayit.referans, exc)
        return False
    sonuc = client().barkod_sonucu(_istek_kur(kayit), cevap)
    kayit.shipment_id = sonuc.shipment_id or None
    kayit.fatura_id = sonuc.fatura_id or None
    kayit.barkod = sonuc.barkod or None
    kayit.zpl = sonuc.zpl or None
    kayit.durum = HAZIRLANDI
    kayit.hata = None
    kayit.takip_url = TAKIP_URL_SABLON.format(shipment_id=sonuc.shipment_id) if sonuc.shipment_id else None
    logger.info("[MNG] barkod alındı %s → takip %s", kayit.referans, kayit.shipment_id)
    return True


def barkod_iste(kaynak: str, kaynak_ref: str, commit: bool = True, bekle: bool = False) -> bool:
    """Kaynak işleme alındı → barkod bayrağını koy ve hemen dene. Sipariş MNG'de henüz açılmadıysa
    (bekliyor) bayrak kalır, takip işi açtıktan sonra barkodu alır. Hata yutulur, çağıran akış bozulmaz."""
    if not otomatik_acik():
        return False
    try:
        kayit = gonderi_bul(kaynak, kaynak_ref)
        if not kayit or kayit.barkod or kayit.durum in (IPTAL, TESLIM):
            return False
        kayit.barkod_istendi = True
        basarili = barkod_al(kayit, bekle=bekle) if kayit.durum == SIPARIS_ACILDI else False
        if commit:
            db.session.commit()
        return basarili
    except Exception:
        db.session.rollback()
        logger.exception("[MNG] barkod_iste beklenmeyen hata (%s %s) — yutuldu", kaynak, kaynak_ref)
        return False


def gonderi_ac(kaynak: str, kaynak_ref: str, kaynak_ad: str, referans: str, alici: Alici,
               kapida_odeme_tutari=None, icerik: str = "Ayakkabi", aciklama: str = "",
               commit: bool = True, adet: int = 1) -> KargoGonderi | None:
    """Kaynak kaydı için MNG siparişi aç (idempotent). Otomatik kapalıysa None.

    API hatası kaydı engellemez: kayıt 'bekliyor' kalır, takip işi yeniden dener.
    Çağıran tarafın işlemi (değişim/manuel kayıt) ASLA bu yüzden bozulmaz.
    """
    if not otomatik_acik():
        return None
    try:
        mevcut = gonderi_bul(kaynak, kaynak_ref)
        if mevcut:
            return mevcut
        if gonderi_kaydi_var(kaynak, kaynak_ref):      # iptal edilmiş: aynı referans tekrar açılmaz
            return None
        kayit = _kayit_olustur(kaynak, kaynak_ref, kaynak_ad, referans, alici, kapida_odeme_tutari, adet)
        _api_ile_ac(kayit, icerik, aciklama)
        if commit:
            db.session.commit()
        return kayit
    except Exception:
        db.session.rollback()
        logger.exception("[MNG] gonderi_ac beklenmeyen hata (%s %s) — yutuldu", kaynak, kaynak_ref)
        return None


# ---------------------------------------------------------------- iptal
def gonderi_iptal(kaynak: str, kaynak_ref: str, commit: bool = True) -> bool:
    """Kaynak silindi/iptal edildi → MNG'de de iptal et (şube kabul etmeden)."""
    kayit = gonderi_bul(kaynak, kaynak_ref)
    if not kayit:
        return False
    return kayit_iptal(kayit, commit=commit)


def kayit_iptal(kayit: KargoGonderi, commit: bool = True) -> bool:
    """Barkod alındıysa cancelshipment, yalnız sipariş açıldıysa cancelorder; API'ye gitmemişse yerel."""
    if kayit.durum in (TESLIM, IPTAL):
        return False
    if kayit.durum not in (DURUM_BEKLIYOR, DURUM_HATA):
        try:
            if kayit.shipment_id:
                client().iptal_gonderi(kayit.referans, kayit.shipment_id)
            client().iptal(kayit.referans)
        except MngHata as exc:
            kayit.hata = f"iptal: {exc}"[:2000]
            logger.warning("[MNG] iptal başarısız %s: %s", kayit.referans, exc)
            if commit:
                db.session.commit()
            return False
    kayit.durum = IPTAL
    kayit.iptal_at = datetime.utcnow()
    if commit:
        db.session.commit()
    return True


# ---------------------------------------------------------------- takip
def _durum_uygula(kayit: KargoGonderi, d: GonderiDurumu) -> bool:
    """MNG cevabını kayda yaz; durum değiştiyse True. Kayıt geri gitmez (kargoda → hazırlandı yok)."""
    eski = kayit.durum
    kayit.son_sorgu_at = datetime.utcnow()
    kayit.hata = None                      # başarılı sorgu eski 'sorgu:' hatasını temizler
    kayit.mng_durum_kodu = d.kod
    kayit.mng_durum_metni = d.mng_metni[:80] if d.mng_metni else kayit.mng_durum_metni
    if d.shipment_id and not kayit.shipment_id:
        kayit.shipment_id = d.shipment_id
    if d.takip_url:
        kayit.takip_url = d.takip_url[:255]
    if d.durum == BILINMIYOR or geri_mi(eski, d.durum):
        return False
    kayit.durum = d.durum
    if d.durum in YOLDA and not kayit.kargoda_at:
        kayit.kargoda_at = datetime.utcnow()
    if d.teslim_edildi:
        kayit.teslim_alan = d.teslim_alan[:120] if d.teslim_alan else kayit.teslim_alan
        kayit.teslim_zamani = d.teslim_zamani or kayit.teslim_zamani or datetime.utcnow()
        if kayit.kapida_odeme_tutari:
            kayit.tahsil_edildi = True   # MNG kapıda ödemeli gönderiyi tahsilatsız teslim etmez
    return eski != kayit.durum


def kaydi_sorgula(kayit: KargoGonderi, commit: bool = True) -> bool:
    """Tek gönderinin MNG durumunu çek, değiştiyse kaynak statüsünü düşür."""
    try:
        d = client().durum(kayit.referans)
    except MngHata as exc:
        kayit.son_sorgu_at = datetime.utcnow()
        kayit.hata = f"sorgu: {exc}"[:2000]
        if commit:
            db.session.commit()
        return False
    if d is None:
        kayit.son_sorgu_at = datetime.utcnow()
        if commit:
            db.session.commit()
        return False
    degisti = _durum_uygula(kayit, d)
    # Kaynağa yazma hedefi değiştiyse (ya da önceki yazma başarısız kaldıysa) yeniden dene;
    # başarı kaynak_durum'a işlenir → aynı hedef ikinci kez yazılmaz (çift fulfillment yok).
    from .kaynak import hedef_statu_kaynak, kaynak_guncelle
    if hedef_statu_kaynak(kayit) and hedef_statu_kaynak(kayit) != kayit.kaynak_durum:
        kaynak_guncelle(kayit)
    if commit:
        db.session.commit()
    return degisti


def acik_gonderiler(simdi: datetime | None = None) -> list[KargoGonderi]:
    """MNG'de barkodu alınmış, kapanmamış gönderiler (durum sorgusu bunlara)."""
    simdi = simdi or datetime.utcnow()
    esik = simdi - SORGU_ARALIGI
    return (KargoGonderi.query
            .filter(~KargoGonderi.durum.in_(tuple(KAPANMIS | {DURUM_BEKLIYOR, DURUM_HATA, SIPARIS_ACILDI})))
            .filter((KargoGonderi.son_sorgu_at.is_(None)) | (KargoGonderi.son_sorgu_at <= esik))
            .order_by(KargoGonderi.id.asc())
            .all())


def bekleyen_gonderiler(simdi: datetime | None = None) -> list[KargoGonderi]:
    simdi = simdi or datetime.utcnow()
    return (KargoGonderi.query
            .filter(KargoGonderi.durum == DURUM_BEKLIYOR)
            .filter(KargoGonderi.olusturuldu_at >= simdi - YENIDEN_DENEME_PENCERESI)
            .order_by(KargoGonderi.id.asc())
            .all())


def barkod_bekleyenler() -> list[KargoGonderi]:
    """Siparişi açılmış ve barkodu İSTENMİŞ (işleme alınmış) ama henüz alınamamış kayıtlar."""
    return (KargoGonderi.query
            .filter(KargoGonderi.durum == SIPARIS_ACILDI, KargoGonderi.barkod_istendi.is_(True))
            .order_by(KargoGonderi.id.asc())
            .all())


def takip_isi() -> dict:
    """Zamanlayıcı: bekleyenleri aç, barkodları al, açıkları sorgula. Hata yutulur."""
    ozet = {"acildi": 0, "barkod": 0, "sorgulandi": 0, "degisti": 0}
    if not otomatik_acik():
        return ozet
    try:
        for kayit in bekleyen_gonderiler():
            if _api_ile_ac(kayit):
                ozet["acildi"] += 1
            db.session.commit()
        for kayit in barkod_bekleyenler():
            if barkod_al(kayit):
                ozet["barkod"] += 1
            db.session.commit()
        # Yeniden deneme penceresi dolan 'bekliyor' kayıtlar insan baksın diye 'hata'ya düşer
        esik = datetime.utcnow() - YENIDEN_DENEME_PENCERESI
        for kayit in (KargoGonderi.query.filter(KargoGonderi.durum == DURUM_BEKLIYOR,
                                                KargoGonderi.olusturuldu_at < esik).all()):
            kayit.durum = DURUM_HATA
            kayit.hata = (kayit.hata or "") + " | yeniden deneme süresi doldu"
        db.session.commit()
        for kayit in acik_gonderiler():
            ozet["sorgulandi"] += 1
            if kaydi_sorgula(kayit):
                ozet["degisti"] += 1
    except Exception:
        db.session.rollback()
        logger.exception("[MNG] takip_isi hatası (yutuldu)")
    if ozet["acildi"] or ozet["barkod"] or ozet["degisti"]:
        logger.info("[MNG] takip: %s", ozet)
    return ozet
