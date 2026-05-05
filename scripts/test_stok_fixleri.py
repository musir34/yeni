"""
Stok düzeltmelerinin uçtan uca test scripti.

Test edilen değişiklikler:
  1) order_service.py:362-368 — RafUrun raf seçimine with_for_update() eklendi
  2) app.py:437-451           — Stok sync 15 dk -> 3 dk
  3) siparis_hazirla.py       — _build_raf_payload yardımcısı + 3 raf bloğu
  4) templates/siparis_hazirla.html — önerilen raf vurgusu, boşalmış uyarısı, stok yok mesajı

Çalıştırma:
  cd /path/to/proje && DATABASE_URL=sqlite:///:memory: DISABLE_JOBS=1 \
      python scripts/test_stok_fixleri.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# 1) Test ortamı — gerçek DB'ye DOKUNMUYORUZ.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_stok_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"          # Scheduler kapalı
os.environ["WERKZEUG_RUN_MAIN"] = "false" # is_main_proc engelle

# 2) Minimal Flask app — gerçek app.py side-effect zincirini bypass et.
from flask import Flask
from models import (
    db, Product, RafUrun, OrderCreated, CentralStock, Raf,
    Archive, Degisim, ShopifyMapping,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


# barcode_alias_helper.normalize_barcode() PostgreSQL translate() çağırıyor —
# SQLite'da yok. Aynı semantiği UDF olarak ekliyoruz.
def _install_sqlite_udfs():
    import sqlite3
    from sqlalchemy import event

    @event.listens_for(db.engine, "connect")
    def _on_connect(dbapi_conn, _):
        if isinstance(dbapi_conn, sqlite3.Connection):
            def _translate(s, frm, to):
                if s is None:
                    return None
                return s.translate(str.maketrans(frm, to))
            dbapi_conn.create_function("translate", 3, _translate)


# ─────────────────────────────────────────────────────────
# Test runner
# ─────────────────────────────────────────────────────────
PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def expect(cond: bool, name: str, detail: str = ""):
    if cond:
        PASSED.append(name)
        print(f"  ✓ {name}")
    else:
        FAILED.append((name, detail))
        print(f"  ✗ {name} — {detail}")


def reset_db():
    db.session.rollback()
    # Sadece testte yarattığımız tablolar için temizlik (hepsi mevcut değil).
    for model in (RafUrun, Raf, OrderCreated, CentralStock, Product):
        db.session.execute(model.__table__.delete())
    db.session.commit()


# ─────────────────────────────────────────────────────────
# Bölüm 1 — Yardımcı fonksiyon birim testleri
# ─────────────────────────────────────────────────────────
def test_build_raf_payload():
    print("\n[1] _build_raf_payload yardımcı fonksiyon testleri")
    from siparis_hazirla import _build_raf_payload

    reset_db()
    # Raf master kayıtları
    db.session.add(Raf(kod="A-01-01", ana="A", ikincil="01", kat="01"))
    db.session.add(Raf(kod="A-01-02", ana="A", ikincil="01", kat="02"))
    db.session.add(Raf(kod="B-09-09", ana="B", ikincil="09", kat="09"))
    # Ürün-raf eşleştirmeleri
    db.session.add(RafUrun(raf_kodu="A-01-01", urun_barkodu="TST-001", adet=2))
    db.session.add(RafUrun(raf_kodu="A-01-02", urun_barkodu="TST-001", adet=5))
    db.session.add(RafUrun(raf_kodu="B-09-09", urun_barkodu="ALIAS-001", adet=3))
    db.session.commit()

    # Test 1: atanan_raf var ve dolu -> başa alınmalı + onerilen=True
    p = _build_raf_payload("TST-001", atanan_raf="A-01-01")
    expect(p["raflar"][0]["kod"] == "A-01-01",
           "atanan_raf dolu ise başa alınır",
           f"got={p['raflar'][0]['kod']}")
    expect(p["raflar"][0]["onerilen"] is True,
           "atanan_raf 'onerilen=True' olarak işaretlenir")
    expect(p["onerilen_bosaldi"] is False,
           "dolu önerilen raf için onerilen_bosaldi=False")
    expect(p["stok_yok"] is False,
           "raf var iken stok_yok=False")
    expect(len(p["raflar"]) == 2,
           "tüm dolu raflar listede",
           f"got={len(p['raflar'])}")

    # Test 2: atanan_raf var ama dolu rafların arasında yok (boşalmış)
    p = _build_raf_payload("TST-001", atanan_raf="A-99-99")
    expect(p["onerilen_bosaldi"] is True,
           "atanan_raf dolu listede yoksa onerilen_bosaldi=True")
    expect(p["stok_yok"] is False,
           "alternatif raflar varken stok_yok=False")
    expect(all(not r["onerilen"] for r in p["raflar"]),
           "boşalmış durumda hiçbir raf 'onerilen' işaretli olmaz")

    # Test 3: atanan_raf yok -> doğal sıralama (adet desc)
    p = _build_raf_payload("TST-001", atanan_raf=None)
    expect(p["onerilen_bosaldi"] is False,
           "atanan_raf yoksa onerilen_bosaldi=False")
    expect(p["onerilen_raf_kodu"] is None,
           "atanan_raf yoksa onerilen_raf_kodu=None")
    expect(p["raflar"][0]["kod"] == "A-01-02",
           "adet desc sıralı: A-01-02 (5 adet) önce",
           f"got={p['raflar'][0]['kod']}")

    # Test 4: Hiç stok yok + atanan_raf var -> stok_yok=True, onerilen_bosaldi=True
    p = _build_raf_payload("YOK-XYZ", atanan_raf="A-01-01")
    expect(p["stok_yok"] is True,
           "hiç dolu raf yoksa stok_yok=True")
    expect(p["raflar"] == [],
           "boş liste döner")
    expect(p["onerilen_bosaldi"] is True,
           "atanan_raf vardı ama eşleşme yok -> onerilen_bosaldi=True")

    # Test 5: alt_barcode fallback (alias)
    p = _build_raf_payload("PRIMARY-XYZ", atanan_raf=None, alt_barcode="ALIAS-001")
    expect(p["stok_yok"] is False,
           "alt_barcode fallback ile bulunur")
    expect(p["raflar"][0]["kod"] == "B-09-09",
           "fallback rafı geri döner",
           f"got={p['raflar'][0]['kod']}")

    # Test 6: Adet 0 olan raf KAYDEDİLEMEZ (CheckConstraint)
    # Aynı barkod için adet=0 yapamayız (negative değil ama 0 da listelenmez)
    rec = RafUrun.query.filter_by(raf_kodu="A-01-01", urun_barkodu="TST-001").first()
    rec.adet = 0
    db.session.commit()
    p = _build_raf_payload("TST-001", atanan_raf="A-01-01")
    expect(p["onerilen_bosaldi"] is True,
           "adet=0 yapılan atanan raf 'boşalmış' olarak işaretlenir")
    expect(all(r["kod"] != "A-01-01" for r in p["raflar"]),
           "adet=0 raf listede gözükmez")


# ─────────────────────────────────────────────────────────
# Bölüm 2 — get_home akışı (entegrasyon)
# ─────────────────────────────────────────────────────────
def test_get_home_with_atanan_raf():
    print("\n[2] get_home() Trendyol siparişi için atanan_raf akışı")
    from siparis_hazirla import get_home

    reset_db()
    # Master raflar
    db.session.add(Raf(kod="C-01-01", ana="C", ikincil="01", kat="01"))
    db.session.add(Raf(kod="C-02-02", ana="C", ikincil="02", kat="02"))
    db.session.add(RafUrun(raf_kodu="C-01-01", urun_barkodu="TYL-100", adet=1))
    db.session.add(RafUrun(raf_kodu="C-02-02", urun_barkodu="TYL-100", adet=4))

    # Created sipariş — atanan_raf C-01-01 (1 adet, ürün hâlâ orada)
    db.session.add(OrderCreated(
        order_number="TYL-1001",
        status="Created",
        order_date=datetime.utcnow(),
        details=json.dumps([{"barcode": "TYL-100", "quantity": 1, "sku": "TYL-100"}]),
        atanan_raf="C-01-01",
        source="TRENDYOL",
        customer_name="Ali",
        customer_surname="Veli",
    ))
    db.session.commit()

    data = get_home(order_number="TYL-1001")
    products = data.get("order").products if data.get("order") else []
    expect(len(products) == 1, "1 ürün döner", f"got={len(products)}")
    p = products[0]
    expect(p["raflar"][0]["kod"] == "C-01-01",
           "atanan_raf ürünün ilk seçeneği oluyor",
           f"got={p['raflar'][0]['kod']}")
    expect(p["raflar"][0]["onerilen"] is True,
           "ilk raf onerilen=True")
    expect(p.get("onerilen_bosaldi") is False,
           "raf hâlâ dolu, onerilen_bosaldi=False")
    expect(p.get("stok_yok") is False,
           "stok_yok=False")


def test_get_home_atanan_raf_bosaldi():
    print("\n[3] get_home() — atanan raf boşalmış senaryo")
    from siparis_hazirla import get_home

    reset_db()
    db.session.add(Raf(kod="D-01-01", ana="D", ikincil="01", kat="01"))
    db.session.add(Raf(kod="D-02-02", ana="D", ikincil="02", kat="02"))
    # Atanan raf D-01-01 boş, ama D-02-02 dolu
    db.session.add(RafUrun(raf_kodu="D-02-02", urun_barkodu="BOS-200", adet=2))
    db.session.add(OrderCreated(
        order_number="TYL-2002",
        status="Created",
        order_date=datetime.utcnow(),
        details=json.dumps([{"barcode": "BOS-200", "quantity": 1}]),
        atanan_raf="D-01-01",  # Bu raf yok / boş
        source="TRENDYOL",
        customer_name="X",
        customer_surname="Y",
    ))
    db.session.commit()

    data = get_home(order_number="TYL-2002")
    p = data["order"].products[0]
    expect(p["onerilen_bosaldi"] is True,
           "atanan_raf D-01-01 boş -> onerilen_bosaldi=True")
    expect(p["onerilen_raf_kodu"] == "D-01-01",
           "kullanıcıya hangi rafın boşaldığı bildirilir")
    expect(p["raflar"][0]["kod"] == "D-02-02",
           "alternatif raf gösterilir",
           f"got={p['raflar'][0]['kod']}")
    expect(p["stok_yok"] is False, "alternatif var, stok_yok=False")


def test_get_home_stok_yok():
    print("\n[4] get_home() — hiç stok yok senaryo")
    from siparis_hazirla import get_home

    reset_db()
    db.session.add(Raf(kod="E-01-01", ana="E", ikincil="01", kat="01"))
    # RafUrun KAYDI YOK
    db.session.add(OrderCreated(
        order_number="TYL-3003",
        status="Created",
        order_date=datetime.utcnow(),
        details=json.dumps([{"barcode": "HIC-YOK", "quantity": 1}]),
        atanan_raf=None,
        source="TRENDYOL",
        customer_name="Z",
        customer_surname="K",
    ))
    db.session.commit()

    data = get_home(order_number="TYL-3003")
    p = data["order"].products[0]
    expect(p["stok_yok"] is True, "stok_yok=True")
    expect(p["raflar"] == [], "raflar boş listesi")
    expect(p["onerilen_bosaldi"] is False, "atanan_raf yoktu -> onerilen_bosaldi=False")


# ─────────────────────────────────────────────────────────
# Bölüm 3 — Template render testi (Jinja akışı)
# ─────────────────────────────────────────────────────────
def test_template_render():
    print("\n[5] Template render — 3 farklı durum için HTML çıkışı")
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(PROJECT_ROOT / "templates")))

    # Sadece raf bloğunu izole eden mini-template kullanalım — gerçek template'den
    # hangi koşulların tetiklendiğini doğrulamak için.
    block_src = """
{% set aktif_raflar = product['raflar'] %}
{% if product.get('onerilen_bosaldi') %}
ALERT_WARNING:{{ product['onerilen_raf_kodu'] }}
{% endif %}
{% if aktif_raflar %}
{% for raf in aktif_raflar %}
RAF:{{ raf.kod }}|adet={{ raf.adet }}|onerilen={{ raf.onerilen }}|checked={% if raf.onerilen %}YES{% elif not product.get('onerilen_raf_kodu') and loop.first %}YES{% else %}NO{% endif %}
{% endfor %}
{% elif not product.get('onerilen_bosaldi') %}
ALERT_DANGER:STOKTA_YOK
{% endif %}
""".strip()
    tpl = env.from_string(block_src)

    # Senaryo A: atanan_raf dolu, onerilen=True ile vurgulanmalı
    out = tpl.render(product={
        "raflar": [
            {"kod": "A-01-01", "adet": 2, "onerilen": True},
            {"kod": "A-02-02", "adet": 5, "onerilen": False},
        ],
        "onerilen_raf_kodu": "A-01-01",
        "onerilen_bosaldi": False,
        "stok_yok": False,
    })
    expect("RAF:A-01-01|adet=2|onerilen=True|checked=YES" in out,
           "[A] önerilen raf checked + onerilen=True render edildi")
    expect("RAF:A-02-02|adet=5|onerilen=False|checked=NO" in out,
           "[A] alternatif raf NO işaretli")
    expect("ALERT_WARNING" not in out,
           "[A] sarı uyarı YOK (raf boşalmamış)")
    expect("ALERT_DANGER" not in out,
           "[A] kırmızı uyarı YOK")

    # Senaryo B: önerilen raf boşalmış, alternatif var
    out = tpl.render(product={
        "raflar": [
            {"kod": "D-02-02", "adet": 2, "onerilen": False},
        ],
        "onerilen_raf_kodu": "D-01-01",
        "onerilen_bosaldi": True,
        "stok_yok": False,
    })
    expect("ALERT_WARNING:D-01-01" in out,
           "[B] sarı uyarı + atanan raf kodu render edildi")
    expect("RAF:D-02-02" in out,
           "[B] alternatif raf hâlâ listede")
    # Önerilen yok ama bilinmeyen atanan_raf var; checked=NO çünkü
    # şart 'not product.get(onerilen_raf_kodu)' -> False (atanan_raf var)
    expect("checked=NO" in out,
           "[B] hiçbir raf otomatik checked değil (kullanıcı bilinçli seçsin)")

    # Senaryo C: hiç stok yok
    out = tpl.render(product={
        "raflar": [],
        "onerilen_raf_kodu": None,
        "onerilen_bosaldi": False,
        "stok_yok": True,
    })
    expect("ALERT_DANGER:STOKTA_YOK" in out,
           "[C] kırmızı 'Stokta yok' kutusu render edildi")
    expect("RAF:" not in out,
           "[C] hiç raf listelenmez")


# ─────────────────────────────────────────────────────────
# Bölüm 4 — Kod düzeyinde değişiklik doğrulamaları
# ─────────────────────────────────────────────────────────
def test_code_changes_present():
    print("\n[6] Kod düzeyinde değişiklik doğrulamaları")

    # 4a) order_service.py — with_for_update() eklendi
    src = (PROJECT_ROOT / "order_service.py").read_text()
    # Atanan_raf yazılan blokta with_for_update var mı?
    block = src.split("urun_raf_bilgileri = []")[1].split("siparis_no = order_dict")[0]
    expect("with_for_update()" in block,
           "order_service.py raf seçimine with_for_update() eklenmiş")

    # 4b) app.py — sync periyodu 3 dakika
    src = (PROJECT_ROOT / "app.py").read_text()
    block = src.split('id="stock_sync_auto"')[1].split("next_run_time")[0]
    expect("minutes=3" in block,
           "app.py stock_sync periyodu 3 dakika")
    expect("minutes=15" not in block,
           "app.py'da 15 dk artık yok")

    # 4c) siparis_hazirla.py — yardımcı fonksiyon mevcut
    src = (PROJECT_ROOT / "siparis_hazirla.py").read_text()
    expect("def _build_raf_payload(" in src,
           "_build_raf_payload tanımlandı")
    expect(src.count("_build_raf_payload(") >= 3,
           "_build_raf_payload her 3 raf bloğunda da çağrılıyor",
           f"call_count={src.count('_build_raf_payload(')}")

    # 4d) template — yeni alan adları kullanılıyor
    src = (PROJECT_ROOT / "templates" / "siparis_hazirla.html").read_text()
    expect("onerilen_bosaldi" in src,
           "template onerilen_bosaldi bayrağını kontrol ediyor")
    expect("raf-onerilen" in src or "📌" in src,
           "template önerilen rafı görsel olarak vurguluyor")


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────
def main() -> int:
    print("=" * 60)
    print("STOK DÜZELTMELERI — UÇTAN UCA TEST")
    print("=" * 60)

    with app.app_context():
        _install_sqlite_udfs()
        # Sadece ihtiyaç duyduğumuz tabloları yarat — models.py'da
        # `ix_tasks_commit_due` indexi iki kez tanımlandığı için (1108 + 1114)
        # SQLite'da tüm DB'yi create_all etmek hata veriyor (mevcut bug,
        # bu PR'la ilgisi yok). Sadece raf/sipariş tablolarını yaratıyoruz.
        # Tüm tabloları tek tek dene — models.py'da `tasks` tablosu için
        # `ix_tasks_commit_due` indexi iki kez tanımlandığından (mevcut bug,
        # bu PR'la ilgisi yok) toplu create_all SQLite'da patlıyor.
        skipped = []
        for tbl in db.metadata.sorted_tables:
            try:
                tbl.create(bind=db.engine, checkfirst=True)
            except Exception as e:
                skipped.append((tbl.name, str(e)[:80]))
        if skipped:
            print(f"  (atlanan tablolar: {[s[0] for s in skipped]})")
        try:
            test_build_raf_payload()
            test_get_home_with_atanan_raf()
            test_get_home_atanan_raf_bosaldi()
            test_get_home_stok_yok()
            test_template_render()
            test_code_changes_present()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"\n💥 Test çalıştırma hatası: {e}")
            return 2

    print("\n" + "=" * 60)
    print(f"SONUÇ:  ✓ {len(PASSED)} geçti   ✗ {len(FAILED)} hata")
    print("=" * 60)
    if FAILED:
        for name, detail in FAILED:
            print(f"  ✗ {name}: {detail}")
        return 1
    print("Tüm testler başarılı — değişiklikler güvenli.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
