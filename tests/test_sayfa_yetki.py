"""Sayfa yetkileri — saf mantık testleri (DB/Flask yok).

Etkin yetki = rol varsayılanı ± kişiye özel istisna; sahip her şeyi görür. Devreye girince
kimsenin bugünkü erişimi değişmemeli (rol varsayılanları = mevcut roles_required kuralları).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sayfa_yetki import (  # noqa: E402
    SAYFALAR,
    SAYFA_MAP,
    erisebilir,
    etkin_sayfalar,
    gruplu_sayfalar,
    istisna_farki,
    rol_varsayilani,
    sayfa_bul,
)


def test_katalog_kodlari_benzersiz_ve_her_sayfa_bir_kurala_bagli():
    kodlar = [s.kod for s in SAYFALAR]
    assert len(kodlar) == len(set(kodlar))
    for s in SAYFALAR:
        assert s.blueprints or s.endpoints or s.yollar, s.kod
    assert {g for g, _ in gruplu_sayfalar()} == {s.grup for s in SAYFALAR}


def test_endpoint_blueprint_ve_yol_eslemesi():
    assert sayfa_bul("order_list_service.order_list_all").kod == "siparis_listesi"
    assert sayfa_bul("finans.panel", "/finans").kod == "finans"
    # Alt sayfalar yol önekiyle blueprint'ten ÖNCE eşleşir
    assert sayfa_bul("finans.cari_liste", "/finans/cari").kod == "finans_cari"
    assert sayfa_bul("finans.cari_odeme", "/finans/cari/12/odeme").kod == "finans_cari"
    assert sayfa_bul("finans.kart_ekstre", "/finans/kart").kod == "finans_kart"
    assert sayfa_bul("finans.gelir_excel", "/finans/gelir/excel").kod == "finans_excel"
    assert sayfa_bul("finans.panel", "/finans/kartlar").kod == "finans"       # 'kart' öneki '/finans/kartlar'ı yutmaz
    # Endpoint bazlı ayrım blueprint'ten önce
    assert sayfa_bul("shopify.price_compare_api", "/shopify/api/price-compare").kod == "shopify_fiyat"
    assert sayfa_bul("shopify.orders_dashboard", "/shopify/orders").kod == "shopify_siparisler"
    assert sayfa_bul("login_logout.approve_users", "/approve_users").kod == "kullanici_yonetimi"
    # Katalog dışı → None (eski kurallar)
    assert sayfa_bul("login_logout.cihazlarim", "/cihazlarim") is None
    assert sayfa_bul("home.home", "/home") is None
    assert sayfa_bul(None, "/") is None


def test_rol_varsayilanlari_bugunku_erisimi_korur():
    admin, manager, worker = rol_varsayilani("admin"), rol_varsayilani("manager"), rol_varsayilani("worker")
    assert admin == set(SAYFA_MAP)                                   # admin her sayfa
    assert worker <= manager <= admin
    for kod in ("finans", "finans_cari", "kasa", "kullanici_yonetimi", "urun_yukleme", "kargo_mutabakat", "alissa"):
        assert kod not in worker and kod not in manager
    for kod in ("siparis_takip", "siparis_iz", "kullanici_hareketleri"):
        assert kod in manager and kod not in worker
    for kod in ("siparis_hazirla", "siparis_listesi", "urun_listesi", "raf", "ai_asistan", "soru_cevap"):
        assert kod in worker


def test_istisna_ekler_kaldirir_sahip_her_seyi_gorur():
    assert not erisebilir("finans", "worker")
    assert erisebilir("finans", "worker", {"finans": True})           # personele finans açıldı
    assert erisebilir("raf", "admin")
    assert not erisebilir("raf", "admin", {"raf": False})             # yöneticiden raf kaldırıldı
    assert erisebilir("finans", "worker", {"finans": False}, sahip=True)
    assert erisebilir("bilinmeyen_kod", "worker")                     # katalog dışı kod kısıtsız
    assert "finans" in etkin_sayfalar("worker", {"finans": True})
    assert etkin_sayfalar("worker", {"finans": False}, sahip=True) == set(SAYFA_MAP)


def test_istisna_farki_yalniz_varsayilandan_sapmayi_saklar():
    varsayilan = rol_varsayilani("worker")
    assert istisna_farki("worker", set(varsayilan)) == {}
    assert istisna_farki("worker", varsayilan | {"finans", "finans_cari"}) == {"finans": True, "finans_cari": True}
    assert istisna_farki("admin", set(SAYFA_MAP) - {"raf"}) == {"raf": False}
    # Bilinmeyen kod yok sayılır, varsayılanda olan sayfa işaretlenmezse kaldırma olur
    fark = istisna_farki("worker", (varsayilan - {"raf"}) | {"yok_boyle_sayfa"})
    assert fark == {"raf": False}
