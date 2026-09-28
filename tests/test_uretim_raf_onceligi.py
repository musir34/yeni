"""Üretim modu raf önceliği — izole sqlite kanıt testi.

Senaryo (Komutan tarifi, 2026-09-24):
  * Model üretim modunda; bir bedeni rafta var, diğeri yok.
  * Sipariş gelince rafta olan beden ÜRETİME YAZILMAZ (normal yol),
    rafta olmayan beden üretime yazılır (kayıt + mail).
  * Üretilip gönderilen ürün iade gelip rafa okutulunca, aynı barkoda
    yeni sipariş artık üretime düşmez.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_uretim_raf_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"
os.environ["WERKZEUG_RUN_MAIN"] = "false"

from flask import Flask  # noqa: E402

from models import (  # noqa: E402
    db, Raf, RafUrun, Product, BarcodeAlias, PlatformConfig, UretimSiparis,
    OrderCreated, OrderHazirlaniyor, StockMovement,
    OrderPicking, OrderShipped, OrderDelivered, OrderArchived, OrderCancelled,
    UretimDogrulama,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

_NEEDED = (Raf, RafUrun, Product, BarcodeAlias, PlatformConfig, UretimSiparis,
           OrderCreated, OrderHazirlaniyor, StockMovement,
           OrderPicking, OrderShipped, OrderDelivered, OrderArchived,
           OrderCancelled, UretimDogrulama)

with app.app_context():
    for _m in _NEEDED:
        _m.__table__.create(bind=db.engine, checkfirst=True)

MODEL = "0121"
BC_RAFTA = "079950000036"   # 36 numara — rafta var
BC_YOK = "079950000037"     # 37 numara — rafta yok


@pytest.fixture(autouse=True)
def _ctx_clean(monkeypatch):
    with app.app_context():
        for m in (UretimSiparis, RafUrun, Raf, Product, PlatformConfig,
                  OrderCreated, OrderHazirlaniyor, StockMovement, OrderShipped):
            m.query.delete()
        db.session.commit()
        # Model üretim modunda
        db.session.add(PlatformConfig(platform="uretim_ayar", is_active=True,
                                      extra_config={"models": [MODEL]}))
        db.session.add(Product(barcode=BC_RAFTA, product_main_id=MODEL))
        db.session.add(Product(barcode=BC_YOK, product_main_id=MODEL))
        db.session.add(Raf(kod="A1", ana="A", ikincil="1", kat="1"))
        db.session.add(RafUrun(raf_kodu="A1", urun_barkodu=BC_RAFTA, adet=1))
        db.session.commit()
        # Mail/WhatsApp dışarı çıkmasın — sadece çağrı sayılsın
        import mail_service
        import whatsapp_service
        gonderilen = []
        monkeypatch.setattr(mail_service, "notify",
                            lambda ev, **kw: gonderilen.append(ev))
        monkeypatch.setattr(whatsapp_service, "notify_whatsapp",
                            lambda *a, **kw: None)
        # Çalışan WhatsApp hattı: dağılım okunamazsa HERKESE gönderir — testte kapalı
        import uretim_modu
        monkeypatch.setattr(uretim_modu, "_wa_personel_bildirimi",
                            lambda *a, **kw: None)
        yield gonderilen
        db.session.rollback()


def _siparis(no, kalemler):
    return {
        "order_number": no,
        "package_number": None,
        "customer_name": "Test",
        "customer_surname": "Müşteri",
        "order_date": None,
        "details": json.dumps([
            {"barcode": bc, "quantity": q, "sku": "", "color": "", "size": ""}
            for bc, q in kalemler
        ]),
    }


def test_rafta_olan_beden_uretime_yazilmaz_olmayan_yazilir(_ctx_clean):
    from uretim_modu import isle_yeni_siparisler

    eklenen = isle_yeni_siparisler([_siparis("TY-1", [(BC_RAFTA, 1), (BC_YOK, 1)])])

    assert eklenen == 1
    kayit = UretimSiparis.query.filter_by(order_number="TY-1").one()
    uretilecek = {u["barcode"] for u in json.loads(kayit.details)}
    assert uretilecek == {BC_YOK}, "yalnız rafta olmayan beden üretime girmeli"
    assert _ctx_clean == ["uretim_siparis"], "tek mail gitmeli"


def test_tum_kalemler_raftaysa_kayit_ve_mail_yok(_ctx_clean):
    from uretim_modu import isle_yeni_siparisler

    eklenen = isle_yeni_siparisler([_siparis("TY-2", [(BC_RAFTA, 1)])])

    assert eklenen == 0
    assert UretimSiparis.query.count() == 0
    assert _ctx_clean == []


def test_iade_rafa_girince_yeni_siparis_uretime_dusmez(_ctx_clean):
    from uretim_modu import isle_yeni_siparisler

    # 1) Rafta yok → üretime düşer
    assert isle_yeni_siparisler([_siparis("TY-3", [(BC_YOK, 1)])]) == 1

    # 2) Üretildi, gönderildi, iade geldi, rafa okutuldu (raf_sistemi ile aynı yazım)
    db.session.add(RafUrun(raf_kodu="A1", urun_barkodu=BC_YOK, adet=1))
    db.session.commit()

    # 3) Aynı barkoda yeni sipariş → artık normal yol
    assert isle_yeni_siparisler([_siparis("TY-4", [(BC_YOK, 1)])]) == 0
    assert UretimSiparis.query.filter_by(order_number="TY-4").first() is None
    assert _ctx_clean == ["uretim_siparis"], "ikinci siparişe mail gitmemeli"


def test_rafta_adet_yetmiyorsa_kalem_uretime_girer(_ctx_clean):
    from uretim_modu import isle_yeni_siparisler

    # Rafta 1 var, sipariş 2 istiyor → kalem üretime yazılır
    assert isle_yeni_siparisler([_siparis("TY-5", [(BC_RAFTA, 2)])]) == 1


# ── Rezerv + sahipsiz sipariş taraması (2026-09-28) ──────────────────────────
# Canlı vaka: rafta 1 adet vardı, o adet eski siparişe aitti; sonradan gelen
# siparişler "rafta var" sayılıp üretime yazılmadı, adet paketlenince sahipsiz kaldı.

def _yeni_siparis_db(no, kalemler, tarih):
    """Siparişi orders_created'a yazar (ingest commit'i gibi) + dict'ini döner."""
    d = _siparis(no, kalemler)
    d["order_date"] = tarih
    db.session.add(OrderCreated(order_number=no, order_date=tarih,
                                details=d["details"]))
    db.session.commit()
    return d


def test_tek_adede_uc_siparis_yaslanamaz(_ctx_clean):
    from datetime import datetime
    from uretim_modu import isle_yeni_siparisler

    s1 = _yeni_siparis_db("TY-10", [(BC_RAFTA, 1)], datetime(2026, 9, 26, 4, 0))
    s2 = _yeni_siparis_db("TY-11", [(BC_RAFTA, 1)], datetime(2026, 9, 26, 5, 0))
    s3 = _yeni_siparis_db("TY-12", [(BC_RAFTA, 1)], datetime(2026, 9, 26, 20, 0))

    assert isle_yeni_siparisler([s1, s2, s3]) == 2
    yazilan = {k.order_number for k in UretimSiparis.query.all()}
    assert yazilan == {"TY-11", "TY-12"}, "raftaki tek adet en eski siparişin"


def test_uretime_yazilan_kalem_rezerv_sayilmaz(_ctx_clean):
    from datetime import datetime
    from uretim_modu import isle_yeni_siparisler

    # Eski sipariş 2 adet istiyor, rafta 1 var → üretime yazılır, rafı tutmaz.
    s1 = _yeni_siparis_db("TY-13", [(BC_RAFTA, 2)], datetime(2026, 9, 26, 4, 0))
    assert isle_yeni_siparisler([s1]) == 1
    # Yeni sipariş 1 adet → raftaki adet boşta, normal yol.
    s2 = _yeni_siparis_db("TY-14", [(BC_RAFTA, 1)], datetime(2026, 9, 26, 5, 0))
    assert isle_yeni_siparisler([s2]) == 0


def test_sahipsiz_siparis_taramada_uretime_yazilir(_ctx_clean):
    from datetime import datetime
    from uretim_modu import isle_yeni_siparisler, isle_sahipsiz_siparisler

    # İndiği an rafta 1 adet var → üretime yazılmadı.
    s1 = _yeni_siparis_db("TY-15", [(BC_RAFTA, 1)], datetime(2026, 9, 26, 4, 0))
    assert isle_yeni_siparisler([s1]) == 0
    assert isle_sahipsiz_siparisler() == 0, "raf hâlâ karşılıyor"

    # Adet başka yere gitti → raf boş.
    RafUrun.query.filter_by(urun_barkodu=BC_RAFTA).update({"adet": 0})
    db.session.commit()

    assert isle_sahipsiz_siparisler() == 1
    assert UretimSiparis.query.filter_by(order_number="TY-15").first() is not None
    assert isle_sahipsiz_siparisler() == 0, "ikinci tur yeniden yazmaz"
    assert _ctx_clean == ["uretim_siparis"], "tek mail gitmeli"


def test_rafi_okutulmus_kalem_taramada_uretime_yazilmaz(_ctx_clean):
    from datetime import datetime
    from uretim_modu import isle_sahipsiz_siparisler, pick_key

    _yeni_siparis_db("TY-16", [(BC_RAFTA, 1)], datetime(2026, 9, 26, 4, 0))
    # Ürün raftan okutuldu: raf 0'a düştü + pick hareketi yazıldı.
    RafUrun.query.filter_by(urun_barkodu=BC_RAFTA).update({"adet": 0})
    db.session.add(StockMovement(barcode=BC_RAFTA, shelf_code="A1", delta=-1,
                                 reason="pack_out", order_number="TY-16",
                                 idempotency_key=pick_key("TY-16", BC_RAFTA)))
    db.session.commit()

    assert isle_sahipsiz_siparisler() == 0
    assert UretimSiparis.query.count() == 0


# ── Liste 500 sınırı (2026-09-28) ────────────────────────────────────────────
# Canlı vaka: üretilmiş kayıt 527 olunca "Üretildi"ye basılan sipariş kayboldu —
# limit(500) kargolanan elemesinden ÖNCE uygulanıyordu.

def test_uretilen_sekmesi_500_kargolanmis_kayit_arkasinda_kaybolmaz(_ctx_clean):
    from datetime import datetime, timedelta
    import uretim_routes

    eski = datetime(2026, 8, 1)
    for i in range(505):
        no = f"ESKI-{i}"
        db.session.add(UretimSiparis(order_number=no, details="[]", uretildi=True,
                                     order_date=eski + timedelta(minutes=i)))
        db.session.add(OrderShipped(order_number=no, details="[]"))
    db.session.add(UretimSiparis(order_number="YENI-1", details="[]", uretildi=True,
                                 order_date=datetime(2026, 9, 26)))
    db.session.add(UretimSiparis(order_number="YENI-2", details="[]", uretildi=True,
                                 paketlendi=True, order_date=datetime(2026, 9, 27)))
    db.session.commit()

    def _liste(durum):
        with app.test_request_context(f"/uretim/api/liste?durum={durum}"):
            return [r["order_number"] for r in uretim_routes.liste().get_json()["rows"]]

    assert _liste("uretilen") == ["YENI-1"]
    assert _liste("paketlenen") == ["YENI-2"]
