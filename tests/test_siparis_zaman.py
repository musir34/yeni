"""Sipariş Zaman Çizgisi — saf mantık testleri (DB yok).

Kaynaklar naive UTC saklar; sayfa İstanbul gösterir. Aynı adım (ör. Paketlendi) hem audit
hem user_log hem tablo kaydından saniyeler arayla gelir → tek satıra inmeli, kullanıcı adı
hangisinde varsa oradan alınmalı.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from siparis_zaman import (  # noqa: E402
    Olay,
    olaylari_birlestir,
    ozet_adimlar,
    sure_metni,
    user_log_adimi,
)

T0 = datetime(2026, 10, 7, 7, 37, 6)  # naive UTC → 10:37:06 İstanbul


def test_ayni_adim_saniyeler_icinde_tek_satira_iner_ve_kim_dolar():
    olaylar = [
        Olay(T0 + timedelta(milliseconds=2), "hazirlandi", "Paketlendi", detay="Raf I-I-02", kaynak="Kullanıcı"),
        Olay(T0, "hazirlandi", "Sipariş hazırlandı — 1 (Created → Picking)", kim="nurcan", kaynak="Kullanıcı"),
        Olay(T0 + timedelta(seconds=1), "hazirlandi", "Paketlendi (Picking)", kim="nurcan"),
    ]
    sonuc = olaylari_birlestir(olaylar)
    assert len(sonuc) == 1
    assert sonuc[0].kim == "nurcan"
    assert sonuc[0].detay == "Raf I-I-02"


def test_farkli_adimlar_birlesmez_ve_kronolojik():
    olaylar = [
        Olay(T0 + timedelta(hours=5), "kargoda", "Kargoya verildi"),
        Olay(T0, "hazirlandi", "Paketlendi"),
        Olay(T0 + timedelta(seconds=2), "etiket", "Kargo etiketi yazdırıldı"),
    ]
    assert [o.adim for o in olaylari_birlestir(olaylar)] == ["hazirlandi", "etiket", "kargoda"]


def test_stok_hareketleri_ayni_detayla_birlesir_farkliyla_birlesmez():
    olaylar = [
        Olay(T0, "stok", "Raftan düşüldü", detay="111 · A-A-01 · -1"),
        Olay(T0 + timedelta(seconds=1), "stok", "Paketlemede raftan düşüldü", detay="111 · A-A-01 · -1"),
        Olay(T0 + timedelta(seconds=1), "stok", "Paketlemede raftan düşüldü", detay="222 · B-B-02 · -1"),
    ]
    assert len(olaylari_birlestir(olaylar)) == 2


def test_ozet_istanbul_saati_ve_ilk_zaman():
    olaylar = [
        Olay(datetime(2026, 10, 6, 14, 34, 20), "siparis", "Sipariş verildi"),
        Olay(T0 + timedelta(minutes=10), "hazirlandi", "Paketlendi"),
        Olay(T0, "paketlendi", "Paketlendi — bekliyor"),   # paketlendi → aynı özet kutusu, daha erken
        Olay(datetime(2026, 10, 7, 13, 4, 35), "kargoda", "Kargoya verildi"),
    ]
    ozet = {a["anahtar"]: a for a in ozet_adimlar(olaylar)}
    assert ozet["siparis"]["saat"] == "17:34" and ozet["siparis"]["tarih"] == "06.10.2026"
    assert ozet["hazirlandi"]["saat"] == "10:37"
    assert ozet["kargoda"]["saat"] == "16:04"
    assert ozet["teslim"]["var"] is False
    assert "uretim_basladi" not in ozet and "iptal" not in ozet  # yalnız varsa gösterilir


def test_ozet_uretim_adimi_varsa_gorunur():
    ozet = {a["anahtar"] for a in ozet_adimlar([Olay(T0, "uretim_basladi", "Üretim başladı")])}
    assert "uretim_basladi" in ozet


def test_user_log_metni_adima_eslenir():
    assert user_log_adimi("Kargo etiketi yazdırıldı — 11678528052") == "etiket"
    assert user_log_adimi("Sipariş hazırlandı — 11680029013 (Created → Picking)") == "hazirlandi"
    assert user_log_adimi("Üretim siparişi: İşleme alındı — üretim başladı — 1") == "uretim_basladi"
    assert user_log_adimi("Üretim siparişi: Üretildi olarak işaretlendi — 1") == "uretildi"
    assert user_log_adimi("Üretim siparişi: Paketlendi — kargoya verilmeyi bekliyor — 1") == "paketlendi"
    assert user_log_adimi("Shopify sipariş durumu güncellendi — 1 → Kargoda") == "kargoda"
    assert user_log_adimi("Paketleme BAŞARISIZ — 1 (stok yetersiz)") == "hata"
    assert user_log_adimi("Stok eklendi — A-A-01, 1 ürün") == "diger"


def test_sure_metni():
    assert sure_metni(T0, T0 + timedelta(days=1, hours=2, minutes=5)) == "1 gün 2 sa 5 dk"
    assert sure_metni(T0, T0 + timedelta(minutes=3)) == "3 dk"
    assert sure_metni(T0 + timedelta(hours=1), T0) == ""
    assert sure_metni(None, T0) == ""


def test_panele_dusme_teslim_aninden_sonra_gosterilmez():
    """Audit öncesi eski sipariş: tek aday teslim satırının created_at'i → 'Panele düştü' üretilmemeli."""
    from types import SimpleNamespace

    from siparis_zaman import _panele_dusme
    import siparis_zaman as sz

    sz.db = SimpleNamespace(session=SimpleNamespace(query=lambda *a, **k: (_ for _ in ()).throw(RuntimeError()), rollback=lambda: None))
    teslim = Olay(T0, "teslim", "Teslim edildi")
    satir = SimpleNamespace(created_at=T0)
    assert _panele_dusme("1", [(satir, "Teslim Edildi")], [teslim]) == []
    erken = SimpleNamespace(created_at=T0 - timedelta(days=2))
    sonuc = _panele_dusme("1", [(erken, "Teslim Edildi")], [teslim])
    assert len(sonuc) == 1 and sonuc[0].ts == T0 - timedelta(days=2)


def test_otomatik_gonderim_metni_etiket_adimina_eslenir():
    assert user_log_adimi("Otomatik gönderim — kargo kodu verildi — 11680029013") == "etiket"


def test_kargo_kodu_verildi_rotasi_print_logu_yazar(monkeypatch):
    """Otomatik Gönderim anı /order-label PRINT kaydıyla aynı biçimde iz bırakmalı."""
    from flask import Flask

    import siparis_zaman as sz

    yazilan = []
    monkeypatch.setattr(sz, "log_user_action", lambda action, details=None, **kw: yazilan.append((action, details)))
    app = Flask(__name__)
    app.register_blueprint(sz.siparis_zaman_bp)
    c = app.test_client()
    r = c.post("/siparis-zaman/kargo-kodu-verildi", json={
        "order_number": "11680029013", "shipping_barcode": "7340000123456",
        "cargo_provider": "DHL eCommerce Marketplace", "sayfa": "Üretim Siparişleri"})
    assert r.status_code == 200 and r.get_json()["success"] is True
    assert yazilan[0][0] == "PRINT"
    assert yazilan[0][1]["işlem_açıklaması"] == "Otomatik gönderim — kargo kodu verildi — 11680029013"
    assert yazilan[0][1]["kargo_firması"] == "DHL eCommerce Marketplace"
    assert c.post("/siparis-zaman/kargo-kodu-verildi", json={}).status_code == 400
