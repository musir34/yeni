"""Gönderi durumu → kaynak kaydın statüsü (değişim / manuel sipariş / Shopify).

Kurallar:
- Yalnız İLERİ yön: 'Teslim Edildi' olan kayıt 'Kargoda'ya geri alınmaz.
- Yalnız bilinen statülerden ilerlenir; elle verilmiş başka bir statü (İade, İptal...) ezilmez.
- Başarıyla yazılan hedef KargoGonderi.kaynak_durum'a işlenir; takip işi hedef != kaynak_durum
  olduğu sürece yeniden dener (Shopify API hatası kaybolmaz), aynı hedefi ikinci kez yazmaz.
- Shopify fulfillment yalnız bir kez açılır (kaynak_durum boşken, ilk ileri hareket); sonraki
  geçişler yalnız etiket değiştirir → müşteriye çift kargo maili gitmez.
"""
from __future__ import annotations

import logging

from models import Degisim, KargoGonderi, YeniSiparis

from .durum import TESLIM, YOLDA

logger = logging.getLogger(__name__)

# değişim statüleri (degisim_talep.html)
DEGISIM_KARGODA = "Kargoya Verildi"
DEGISIM_TESLIM = "Teslim Edildi"
DEGISIM_BILINEN = {None, "", "Oluşturuldu", "Beklemede", "İşleme Alındı", DEGISIM_KARGODA, DEGISIM_TESLIM}
# manuel sipariş statüleri (yeni_siparis.html)
MANUEL_KARGODA = "Kargoda"
MANUEL_TESLIM = "Teslim Edildi"
MANUEL_BILINEN = {None, "", "Yeni Sipariş", "Yeni", "Onaylandı", "Hazırlanıyor", "Kargoya Hazır",
                  "Kargoya Verildi", MANUEL_KARGODA, MANUEL_TESLIM}
# Shopify etiketleri (shopify_service.ORDER_STATUSES)
SHOPIFY_KARGODA = "Kargoda"
SHOPIFY_TESLIM = "Teslim Edildi"

_SIRA = {None: 0, "": 0, "Kargoya Verildi": 1, "Kargoda": 1, "Teslim Edildi": 2}


def _ileri_mi(mevcut: str | None, yeni: str, bilinen: set) -> bool:
    if mevcut not in bilinen:
        return False
    return _SIRA.get(yeni, 0) > _SIRA.get(mevcut, 0)


def hedef_statu(gonderi_durumu: str, kargoda: str, teslim: str) -> str | None:
    if gonderi_durumu == TESLIM:
        return teslim
    if gonderi_durumu in YOLDA:
        return kargoda
    return None


_HEDEFLER = {
    "degisim": (DEGISIM_KARGODA, DEGISIM_TESLIM),
    "manuel": (MANUEL_KARGODA, MANUEL_TESLIM),
    "shopify": (SHOPIFY_KARGODA, SHOPIFY_TESLIM),
}


def hedef_statu_kaynak(kayit: KargoGonderi) -> str | None:
    """Bu gönderi durumunda kaynağa yazılması gereken statü (yoksa None)."""
    ciftler = _HEDEFLER.get(kayit.kaynak)
    return hedef_statu(kayit.durum, *ciftler) if ciftler else None


def _degisim_guncelle(kayit: KargoGonderi, hedef: str) -> bool:
    rec = Degisim.query.filter_by(degisim_no=kayit.kaynak_ref).first()
    if rec and _ileri_mi(rec.degisim_durumu, hedef, DEGISIM_BILINEN):
        rec.degisim_durumu = hedef
        return True
    return False


def _manuel_guncelle(kayit: KargoGonderi, hedef: str) -> bool:
    sip = YeniSiparis.query.filter_by(siparis_no=kayit.kaynak_ref).first()
    if sip and _ileri_mi(sip.durum, hedef, MANUEL_BILINEN):
        sip.durum = hedef
        return True
    return False


def _shopify_guncelle(kayit: KargoGonderi, hedef: str) -> bool:
    """İlk ileri hareket: fulfillment (takip no, müşteriye Shopify maili) + etiket; sonra yalnız etiket.
    Etiket geçişi başarısızsa False → kaynak_durum yazılmaz, takip işi yeniden dener."""
    from shopify_site.shopify_service import shopify_service
    if not kayit.kaynak_durum and kayit.shipment_id:
        sonuc = shopify_service.create_fulfillment(
            order_id=kayit.kaynak_ref, tracking_number=kayit.shipment_id,
            tracking_company="MNG Kargo", tracking_url=kayit.takip_url or None, notify_customer=True,
        )
        if not sonuc.get("success"):
            logger.warning("[MNG] Shopify fulfillment başarısız %s: %s", kayit.kaynak_ad, sonuc.get("error") or sonuc.get("errors"))
            return False
    sonuc = shopify_service.update_order_status(kayit.kaynak_ref, hedef)
    if not sonuc.get("success"):
        logger.warning("[MNG] Shopify etiket geçişi başarısız %s → %s: %s", kayit.kaynak_ad, hedef, sonuc)
        return False
    return True


_GUNCELLEYICILER = {
    "degisim": _degisim_guncelle,
    "manuel": _manuel_guncelle,
    "shopify": _shopify_guncelle,
}


def kaynak_guncelle(kayit: KargoGonderi) -> bool:
    """Hedef statüyü kaynağa yaz; başarıda (ya da kaynak zaten ileride/bilinmeyen statüdeyse)
    kaynak_durum = hedef → aynı hedef bir daha denenmez. Shopify API hatasında kaynak_durum
    yazılmaz, sonraki takipte tekrar denenir."""
    hedef = hedef_statu_kaynak(kayit)
    fn = _GUNCELLEYICILER.get(kayit.kaynak)
    if not hedef or not fn:
        return False
    try:
        degisti = fn(kayit, hedef)
    except Exception:
        # rollback YOK: gönderi kaydındaki durum güncellemesi aynı oturumda, kaybolmasın;
        # çağıran (takip_isi) commit eder, DB hatası oradaki rollback'e düşer.
        logger.exception("[MNG] kaynak güncelleme hatası %s %s (yutuldu)", kayit.kaynak, kayit.kaynak_ref)
        return False
    if kayit.kaynak == "shopify" and not degisti:
        return False                    # API hatası → yeniden denensin
    kayit.kaynak_durum = hedef
    if degisti:
        logger.info("[MNG] kaynak statüsü güncellendi: %s %s → %s", kayit.kaynak, kayit.kaynak_ad, hedef)
    return degisti
