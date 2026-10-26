"""Sipariş Hazırla — Bugün Hazırlananlar: saf derleme mantığı testleri (DB yok).

user_logs satırları confirm_packing / order_label / kargo_kodu_verildi biçiminde JSON
details taşır; derleme sırayı, başarısız paketlemeyi, mükerrer kaydı ve etiket izlerini
doğru ayıklamalı.
Çalıştırma: DISABLE_JOBS=1 python -m pytest tests/test_bugun_hazirlananlar.py --noconftest -q
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from siparis_hazirla import bugun_hazirlananlari_derle  # noqa: E402

T0 = datetime(2026, 10, 26, 6, 0, 0)  # naive UTC → 09:00 İstanbul


def _satir(ts, **detay):
    return SimpleNamespace(timestamp=ts, details=json.dumps(detay, ensure_ascii=False))


def test_sira_korunur_basarisiz_ve_mukerrer_elenir():
    rows = [
        _satir(T0, **{"Işlem Açıklaması": "Sipariş hazırlandı — 111 (Created → Picking)",
                      "Sipariş No": "111", "Müşteri": "Ayşe Yılmaz", "Kaynak": "TRENDYOL", "Kullanıcı": "nurcan"}),
        _satir(T0 + timedelta(minutes=1), **{"Işlem Açıklaması": "Paketleme BAŞARISIZ — 222 (stok yetersiz)",
                                             "Sipariş No": "222", "Durum": "BASARISIZ"}),
        _satir(T0 + timedelta(minutes=2), **{"Işlem Açıklaması": "Shopify sipariş hazırlandı — SH-9 (Created → Hazirlaniyor)",
                                             "Sipariş No": "SH-9", "Müşteri": "Ali Kaya", "Kaynak": "SHOPIFY", "Kullanıcı": "nurcan"}),
        _satir(T0 + timedelta(minutes=3), **{"Işlem Açıklaması": "Sipariş hazırlandı — 111 (Created → Picking)",
                                             "Sipariş No": "111"}),
        SimpleNamespace(timestamp=T0, details="bozuk json"),
    ]
    siparisler, _ = bugun_hazirlananlari_derle(rows)
    assert [s["order_number"] for s in siparisler] == ["111", "SH-9"]
    assert siparisler[0]["saat"] == "09:00" and siparisler[0]["musteri"] == "Ayşe Yılmaz"
    assert siparisler[1]["kaynak"] == "SHOPIFY" and siparisler[1]["hazirlayan"] == "nurcan"


def test_etiket_izleri_ilk_kayit_kalir_ve_ture_gore_ayrilir():
    rows = [
        _satir(T0, **{"Işlem Açıklaması": "Kargo etiketi yazdırıldı — 111"}),
        _satir(T0 + timedelta(seconds=30), **{"Işlem Açıklaması": "Otomatik gönderim — kargo kodu verildi — 111"}),
        _satir(T0 + timedelta(minutes=1), **{"Işlem Açıklaması": "Otomatik gönderim — kargo kodu verildi — 333"}),
        _satir(T0 + timedelta(minutes=2), **{"Işlem Açıklaması": "Kargo etiketi yazdırıldı — #1428"}),
    ]
    _, etiketler = bugun_hazirlananlari_derle(rows)
    assert etiketler["111"] == {"tur": "yazdirildi", "saat": "09:00"}
    assert etiketler["333"]["tur"] == "oto"
    assert etiketler["#1428"]["tur"] == "yazdirildi"   # Shopify yazdırma izi mağaza adıyla


def test_siparis_no_alani_yoksa_aciklamadan_cikarilir():
    rows = [_satir(T0, **{"İşlem Açıklaması": "Sipariş hazırlandı — 555 (Created → Picking)"})]
    siparisler, _ = bugun_hazirlananlari_derle(rows)
    assert siparisler[0]["order_number"] == "555" and siparisler[0]["kaynak"] == "TRENDYOL"
