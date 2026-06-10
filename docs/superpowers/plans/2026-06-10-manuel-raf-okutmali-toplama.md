# Manuel Raf-Okutmalı Toplama — Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Otomatik raf atamasını kaldırıp, stok düşümünü çalışanın okuttuğu raftan (yer-gerçeği) yapmak; düşülmemiş siparişin paketlenmesini engellemek; paketlemeden Trendyol API bildirimini kaldırmak.

**Architecture:** Ortak bir `picking_service.pick_order_from_shelf()` yardımcısı iki ekranın da kullandığı tek düşüm noktası olur (DRY). "Toplandı" durumu `OrderHazirlaniyor.toplandi_at/toplandi_raf` damgasıyla tutulur; ledger `pack_out` idempotency backstop. Toplu ekran raf-sıralı listeler + 2-alanlı tarama (`/pick`); tekli ekran sıralı-açıkta raf okutur, sıralı-kapalıda yalnızca toplanmış siparişi paketler.

**Tech Stack:** Flask, SQLAlchemy, PostgreSQL (prod) / SQLite (test), Alembic (additive), stock_ledger, pytest.

**Spec:** `docs/superpowers/specs/2026-06-10-manuel-raf-okutmali-toplama-design.md`

**Test komutu (her yerde):**
`DATABASE_URL="sqlite:////tmp/pick_test.db" DISABLE_JOBS=1 WERKZEUG_RUN_MAIN=false python -m pytest <path> -v`
(Not: tam `db.create_all()` SQLite'da çift-index bug'ı yüzünden patlar → testlerde yalnızca gerekli tabloları `__table__.create(checkfirst=True)` ile oluştur; `tests/test_stock_ledger.py` desenini izle.)

---

## Dosya Yapısı

| Dosya | Sorumluluk | İşlem |
|------|------------|-------|
| `models.py` | `OrderHazirlaniyor.toplandi_at`, `toplandi_raf` | Modify (additive) |
| `scripts/add_toplandi_columns.py` | Prod'a kolon ekleyen idempotent script | Create |
| `picking_service.py` | Ortak "okutulan raftan düş + toplandı damgala" mantığı | Create |
| `new_orders_service.py` | Toplu ekran: otomatik atama kaldır, `/pick` endpoint | Modify |
| `templates/bulk_order_prepare.html` | 2-alanlı (raf+ürün) tarama UI | Modify |
| `update_service.py` | confirm_packing: Trendyol API kaldır, sıralı-açık raf-scan, sıralı-kapalı toplandı kontrolü | Modify |
| `siparis_hazirla.py` / `templates/siparis_hazirla.html` | Raf kodu alanı, radio kaldır, sıralı-kapalı akış | Modify |
| `tests/test_picking_service.py` | picking_service testleri | Create |
| `tests/test_bulk_pick.py` | /pick endpoint + confirm_packing testleri | Create |

---

## Faz 1 — Veri modeli (toplandı damgası)

### Task 1: OrderHazirlaniyor'a toplandi_at + toplandi_raf

**Files:**
- Modify: `models.py` (OrderHazirlaniyor sınıfı)
- Create: `scripts/add_toplandi_columns.py`

- [ ] **Step 1: Modeli güncelle**

`models.py` içinde `class OrderHazirlaniyor(OrderBase):` gövdesine (mevcut `atanan_raf` / `hazirlaniyor_since` satırlarının yanına) ekle:

```python
    toplandi_at = db.Column(db.DateTime, nullable=True)   # fiziksel toplandığı (düşüldüğü) an
    toplandi_raf = db.Column(db.String, nullable=True)    # okutulan/düşülen raf kodu
```

- [ ] **Step 2: Idempotent prod kolon-ekleme scripti**

Create `scripts/add_toplandi_columns.py`:

```python
#!/usr/bin/env python3
"""orders_hazirlaniyor'a toplandi_at + toplandi_raf kolonlarını ekler.
ADDITIVE, IDEMPOTENT. ALTER TABLE ... ADD COLUMN IF NOT EXISTS (Postgres).
Çalıştırma: DISABLE_JOBS=1 python scripts/add_toplandi_columns.py
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DISABLE_JOBS", "1")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")

def main():
    from app import app
    from models import db
    from sqlalchemy import text
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE orders_hazirlaniyor ADD COLUMN IF NOT EXISTS toplandi_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE orders_hazirlaniyor ADD COLUMN IF NOT EXISTS toplandi_raf VARCHAR"))
        print("✅ toplandi_at + toplandi_raf eklendi (veya zaten vardı).")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Derleme kontrolü**

Run: `python -m py_compile models.py scripts/add_toplandi_columns.py`
Expected: hatasız.

- [ ] **Step 4: Commit**

```bash
git add models.py scripts/add_toplandi_columns.py
git commit -m "feat: OrderHazirlaniyor toplandi_at/toplandi_raf damgası (additive)"
```

---

## Faz 2 — Ortak düşüm yardımcısı (picking_service)

### Task 2: pick_order_from_shelf

**Files:**
- Create: `picking_service.py`
- Test: `tests/test_picking_service.py`

- [ ] **Step 1: Failing test yaz**

Create `tests/test_picking_service.py` (bootstrap'ı `tests/test_stock_ledger.py`'den birebir kopyala: tempfile sqlite, translate UDF, yalnızca gerekli tabloları create, autouse temizleme fixture). Gerekli tablolar: `Raf, RafUrun, CentralStock, StockMovement, Product, BarcodeAlias, OrderHazirlaniyor, OrderAuditLog`. Sonra:

```python
def _mk_order(order_number="O1", barcode="BC1", qty=1):
    o = OrderHazirlaniyor(
        order_number=order_number, status="Hazırlanıyor", source="TRENDYOL",
        product_barcode=barcode, details=f'[{{"barcode":"{barcode}","quantity":{qty}}}]',
        order_date=datetime.utcnow(), package_number="PKG1",
    )
    db.session.add(o); db.session.commit()
    return o

def test_pick_decrements_scanned_shelf_and_stamps():
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    o = _mk_order()
    from picking_service import pick_order_from_shelf
    res = pick_order_from_shelf(order=o, barcode="BC1", raf_kodu="A1", qty=1, source="USER")
    assert res["success"] is True
    assert _shelf_qty("BC1", "A1") == 4
    assert o.toplandi_at is not None and o.toplandi_raf == "A1"
    from models import StockMovement
    assert StockMovement.query.filter_by(reason="pack_out", order_number="O1").count() == 1
```

- [ ] **Step 2: Test fail görülür**

Run: `... pytest tests/test_picking_service.py::test_pick_decrements_scanned_shelf_and_stamps -v`
Expected: FAIL — `ModuleNotFoundError: picking_service`.

- [ ] **Step 3: picking_service.py yaz**

Create `picking_service.py`:

```python
"""Manuel raf-okutmalı toplama — ortak düşüm yardımcısı.

İki ekran (toplu /pick ve tekli sıralı-açık confirm_packing) buradan geçer.
Çalışanın okuttuğu RAFTAN siparişin ürününü fiziksel düşer, ledger'a pack_out
yazar ve siparişi 'toplandı' damgalar. toplandi_at doluysa idempotent atlar.
"""
from __future__ import annotations

import logging
from datetime import datetime

from models import db, RafUrun
from barcode_alias_helper import normalize_barcode
from stock_management import sync_central_stock
from stock_ledger import record_movement, REASON_PACK_OUT

logger = logging.getLogger(__name__)


def pick_order_from_shelf(*, order, barcode: str, raf_kodu: str, qty: int = 1,
                          source: str = "USER", commit: bool = True) -> dict:
    """Okutulan raftan düş + toplandı damgala. Dönüş: {success, error}."""
    bc = normalize_barcode((barcode or "").strip())
    raf_kodu = (raf_kodu or "").strip()
    if not bc:
        return {"success": False, "error": "Geçersiz ürün barkodu."}
    if not raf_kodu:
        return {"success": False, "error": "Raf kodu okutulmadı."}
    if qty <= 0:
        return {"success": False, "error": "Geçersiz adet."}

    # Idempotency: zaten toplanmışsa tekrar düşme.
    if getattr(order, "toplandi_at", None):
        return {"success": True, "error": None, "already": True}

    # Ürün siparişle eşleşiyor mu? (tek-ürünlü; product_barcode normalize ile karşılaştır)
    order_bc = normalize_barcode((getattr(order, "product_barcode", "") or "").split(",")[0].strip())
    if order_bc and order_bc != bc:
        return {"success": False, "error": "Okutulan ürün bu siparişle eşleşmiyor."}

    # Okutulan rafta bu üründen yeterli var mı?
    rec = (RafUrun.query
           .filter_by(raf_kodu=raf_kodu, urun_barkodu=bc)
           .with_for_update()
           .first())
    if not rec or (rec.adet or 0) < qty:
        mevcut = (rec.adet or 0) if rec else 0
        return {"success": False,
                "error": f"{raf_kodu} rafında {bc} ürününden yeterli yok (var: {mevcut}, gerekli: {qty})."}

    # Düş + ledger + damga (aynı transaction)
    rec.adet = (rec.adet or 0) - qty
    db.session.flush()
    record_movement(
        barcode=bc, delta=-qty, reason=REASON_PACK_OUT, shelf_code=raf_kodu,
        order_number=order.order_number, idempotency_key=f"{order.order_number}:pick:{bc}",
        source=source, mutate_shelf=False, commit=False,
    )
    sync_central_stock(bc, commit=False)
    order.toplandi_at = datetime.utcnow()
    order.toplandi_raf = raf_kodu

    if commit:
        db.session.commit()
    return {"success": True, "error": None, "already": False}
```

- [ ] **Step 4: Test pass görülür**

Run: `... pytest tests/test_picking_service.py -v`
Expected: PASS.

- [ ] **Step 5: Negatif + idempotency testleri ekle**

`tests/test_picking_service.py`'ye ekle:

```python
def test_pick_wrong_shelf_rejected():
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    o = _mk_order()
    from picking_service import pick_order_from_shelf
    res = pick_order_from_shelf(order=o, barcode="BC1", raf_kodu="Z9", qty=1)
    assert res["success"] is False and "yeterli yok" in res["error"]
    assert _shelf_qty("BC1", "A1") == 5
    assert o.toplandi_at is None

def test_pick_wrong_product_rejected():
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    o = _mk_order(barcode="BC1")
    from picking_service import pick_order_from_shelf
    res = pick_order_from_shelf(order=o, barcode="BCX", raf_kodu="A1", qty=1)
    assert res["success"] is False

def test_pick_idempotent_no_double_decrement():
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    o = _mk_order()
    from picking_service import pick_order_from_shelf
    pick_order_from_shelf(order=o, barcode="BC1", raf_kodu="A1", qty=1)
    pick_order_from_shelf(order=o, barcode="BC1", raf_kodu="A1", qty=1)
    assert _shelf_qty("BC1", "A1") == 4   # bir kez düştü
```

- [ ] **Step 6: Testler pass + commit**

Run: `... pytest tests/test_picking_service.py -v` → PASS.
```bash
git add picking_service.py tests/test_picking_service.py
git commit -m "feat: picking_service.pick_order_from_shelf (ortak raf-okutmalı düşüm)"
```

---

## Faz 3 — Toplu Toplama ekranı

### Task 3: new_orders_service — otomatik atama kaldır + /pick endpoint

**Files:**
- Modify: `new_orders_service.py:69-172` (`_build_shelf_groups`, `prepare_new_orders`)
- Test: `tests/test_bulk_pick.py`

- [ ] **Step 1: Failing test yaz**

Create `tests/test_bulk_pick.py` (aynı bootstrap; tablolara `Raf, RafUrun, CentralStock, StockMovement, Product, BarcodeAlias, OrderHazirlaniyor, OrderAuditLog, Archive` dahil; ayrıca test client gerekir → minimal app'e `new_orders_service_bp` register et):

```python
def test_pick_endpoint_decrements_and_stamps(client):
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    _mk_hazirlaniyor("O1", "BC1")
    resp = client.post("/prepare-new-orders/pick", json={
        "order_number": "O1", "raf_barkodu": "A1", "urun_barkodu": "BC1"})
    data = resp.get_json()
    assert data["success"] is True
    assert _shelf_qty("BC1", "A1") == 4
```

(NOT: test app'ine blueprint register + bir `client` fixture ekle; `tests/test_stock_ledger.py`'deki app objesini paylaşıp `app.register_blueprint(new_orders_service_bp)` çağır, `client = app.test_client()`.)

- [ ] **Step 2: Test fail görülür**

Run: `... pytest tests/test_bulk_pick.py::test_pick_endpoint_decrements_and_stamps -v`
Expected: FAIL — 404 (endpoint yok).

- [ ] **Step 3: `_build_shelf_groups`'tan otomatik atamayı kaldır**

`new_orders_service.py` `_build_shelf_groups` gövdesini, otomatik tahsis (satır ~116-138, `barcode_rafs` rezerv + `order.atanan_raf = ...`) mantığını KALDIRACAK şekilde sadeleştir. Yeni davranış: yalnızca henüz toplanmamış (`toplandi_at IS NULL`) tek-ürünlü siparişleri, ürünün bulunduğu **ilk raf koduna göre** grupla (bilgi amaçlı). Atama/`atanan_raf` yazma YOK.

`_build_shelf_groups` içindeki sorguyu değiştir:
```python
    new_orders = (PrepModel.query
                  .filter(PrepModel.toplandi_at.is_(None))
                  .order_by(PrepModel.order_date.asc())
                  .all())
```
Rezerv döngüsünü (her order için `for raf_entry in barcode_rafs...` ve `order.atanan_raf = yeni_atanan_raf`) çıkar; bunun yerine her barkodun **ilk (alfabetik) stoklu rafını** sadece görüntü için seç:
```python
        rafs_for_bc = barcode_rafs.get(barcode, [])
        display_raf = rafs_for_bc[0][0] if rafs_for_bc else 'RAF YOK'
        stok_yetersiz = not rafs_for_bc
```
`db.session.commit()` (atama yazımı kalktığı için) çıkarılabilir; gerekiyorsa no-op bırak. `with_for_update(read=True)` raf sorgusundan kaldır (artık rezerv yok).

- [ ] **Step 4: `/pick` endpoint ekle**

`new_orders_service.py` sonuna ekle:

```python
@new_orders_service_bp.route('/prepare-new-orders/pick', methods=['POST'])
def pick_order():
    """Toplu ekranda raf+ürün okutarak o raftan fiziksel düşüm. Tek-ürünlü."""
    try:
        payload = request.get_json(silent=True) or request.form
        order_number = (payload.get('order_number') or '').strip()
        raf_barkodu = (payload.get('raf_barkodu') or '').strip()
        urun_barkodu = (payload.get('urun_barkodu') or '').strip()
        if not order_number:
            return jsonify({"success": False, "error": "Sipariş numarası yok."}), 400

        order = OrderHazirlaniyor.query.filter_by(order_number=order_number).first()
        if not order:
            return jsonify({"success": False, "error": "Sipariş bulunamadı (Hazırlanıyor değil)."}), 404

        from picking_service import pick_order_from_shelf
        items = _parse_details(order)
        qty = int(items[0].get('quantity', 1)) if items else 1
        res = pick_order_from_shelf(order=order, barcode=urun_barkodu,
                                    raf_kodu=raf_barkodu, qty=qty, source="USER")
        if not res["success"]:
            return jsonify(res), 400
        return jsonify({"success": True, "order_number": order_number,
                        "toplandi_raf": order.toplandi_raf}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Hata: {e}"}), 500
```

- [ ] **Step 5: Test pass görülür**

Run: `... pytest tests/test_bulk_pick.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add new_orders_service.py tests/test_bulk_pick.py
git commit -m "feat: toplu ekran /pick endpoint + otomatik raf ataması kaldırıldı"
```

### Task 4: bulk_order_prepare.html — 2-alanlı tarama UI

**Files:**
- Modify: `templates/bulk_order_prepare.html`

- [ ] **Step 1: Mevcut şablonu oku**

`templates/bulk_order_prepare.html`'i tam oku. Raf blokları (`.shelf-block`) ve sipariş satırları (`order_number, model_code, color, size`) yapısını anla.

- [ ] **Step 2: Her sipariş satırına 2 okutma alanı + JS ekle**

Her sipariş satırına iki input ekle (örnek snippet, mevcut markup'a uyarla):
```html
<div class="pick-row" data-order="{{ item.order_number }}" data-barcode="{{ item.barcode }}">
  <span class="raf-bilgi">Raf: {{ raf_kodu }}</span>
  <input class="raf-input" placeholder="RAF BARKODU" autocomplete="off">
  <input class="urun-input" placeholder="ÜRÜN BARKODU" autocomplete="off">
  <span class="pick-status"></span>
</div>
```
JS: her `.pick-row` için, iki input da dolunca (ürün input'unda Enter / Zebra wedge) `POST /prepare-new-orders/pick {order_number, raf_barkodu, urun_barkodu}` çağır; success → satırı yeşil işaretle + DOM'dan kaldır/"toplandı" yaz; error → kırmızı uyarı göster, inputları temizle. Zebra TC21: Enter native buton tetiklemesin ([[project-zebra-tc21]]); etkileşimli öğeleri agresif focus-capture'dan hariç tut.

- [ ] **Step 3: Manuel doğrulama notu**

Otomatik test yok (UI). El terminalinde: raf barkodu + ürün barkodu okut → satır toplandı olur, stok düşer. Yanlış raf → kırmızı uyarı.

- [ ] **Step 4: Commit**

```bash
git add templates/bulk_order_prepare.html
git commit -m "feat: toplu ekran 2-alanlı (raf+ürün) tarama arayüzü"
```

---

## Faz 4 — Tekli ekran

### Task 5: confirm_packing — Trendyol API kaldır + sıralı kontrolü

**Files:**
- Modify: `update_service.py` (confirm_packing, ~110-498)
- Test: `tests/test_bulk_pick.py` (confirm_packing senaryoları ekle)

- [ ] **Step 1: Failing testler yaz**

`tests/test_bulk_pick.py`'ye ekle (update_service_bp register edilmeli; `confirm_packing` async route — `client.post` Flask async desteğiyle çalışır, `flask[async]` kurulu varsay):

```python
def test_confirm_packing_blocks_unpicked_in_sequential_off(client):
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    _mk_hazirlaniyor("O1", "BC1")   # toplandi_at = None
    resp = client.post("/confirm_packing", data={
        "order_number": "O1", "sirali": "0"},
        headers={"X-Requested-With": "XMLHttpRequest"})
    data = resp.get_json()
    assert data["ok"] is False  # toplanmadığı için engellendi
    assert _shelf_qty("BC1", "A1") == 5

def test_confirm_packing_packs_picked_without_decrement(client):
    _seed_shelf(barcode="BC1", shelf="A1", adet=5)
    o = _mk_hazirlaniyor("O2", "BC1")
    from picking_service import pick_order_from_shelf
    pick_order_from_shelf(order=o, barcode="BC1", raf_kodu="A1", qty=1)  # 5→4, toplandı
    resp = client.post("/confirm_packing", data={
        "order_number": "O2", "sirali": "0"},
        headers={"X-Requested-With": "XMLHttpRequest"})
    assert _shelf_qty("BC1", "A1") == 4   # paketleme tekrar düşmedi
    from models import OrderPicking
    assert OrderPicking.query.filter_by(order_number="O2").count() == 1
```

- [ ] **Step 2: Test fail görülür**

Run: `... pytest tests/test_bulk_pick.py -k confirm_packing -v`
Expected: FAIL.

- [ ] **Step 3: Trendyol API bloğunu kaldır**

`update_service.py` confirm_packing Trendyol dalında (satır ~351-421), `update_order_status_to_picking` çağrısını ve `trendyol_success`/rollback bloğunu KALDIR. Yalnızca "OrderHazirlaniyor → OrderPicking taşı" (satır ~423+) kalsın. (`update_order_status_to_picking` fonksiyonu dosyada dursa da artık çağrılmaz; importları kırma.)

- [ ] **Step 4: Sıralı mod kontrolünü ekle**

confirm_packing başına (order kaydı bulunduktan sonra) ekle:
```python
    sirali = request.form.get('sirali', '1') == '1'  # frontend gönderir; default açık
    is_toplandi = bool(getattr(order_created, 'toplandi_at', None))

    if not sirali:
        # Sıralı KAPALI: düşüm yapılmaz; yalnızca toplanmış sipariş paketlenir.
        if not is_toplandi:
            flash('Bu sipariş henüz toplanmadı (stok düşülmedi). Önce toplu ekranda topla.', 'danger')
            return _respond(is_ajax)
        # Düşüm bloğunu (5/6) ATLA → doğrudan statü geçişine git.
```
Sıralı KAPALI ve `is_toplandi` ise: barkod-doğrulama + RAF DÜŞÜM bloğunu (mevcut 200-292 civarı) atla, doğrudan platform dalına (Trendyol taşıma / Shopify tag) geç.

Sıralı AÇIK ise: düşümü artık `pick_{barcode}` radio yerine okutulan raf kodundan yap → `picking_service.pick_order_from_shelf(order=order_created, barcode=bc, raf_kodu=request.form.get(f'raf_{bc}') or request.form.get('raf_kodu'), qty=adet, source="USER", commit=False)` çağır; başarısızsa rollback + uyarı.

(NOT: mevcut elle RafUrun düşüm bloğu sıralı-AÇIK'ta `pick_order_from_shelf` ile değiştirilir; böylece tek düşüm yolu olur.)

- [ ] **Step 5: Testler pass görülür**

Run: `... pytest tests/test_bulk_pick.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add update_service.py tests/test_bulk_pick.py
git commit -m "feat: confirm_packing — Trendyol API kaldırıldı, sıralı-kapalı toplandı kontrolü, raf-scan düşüm"
```

### Task 6: siparis_hazirla.html + siparis_hazirla.py — raf alanı, radio kaldır, sıralı-kapalı akış

**Files:**
- Modify: `templates/siparis_hazirla.html`
- Modify: `siparis_hazirla.py` (`_build_raf_payload` çıktısı yalnızca bilgi)

- [ ] **Step 1: Şablonu oku**

`templates/siparis_hazirla.html` (özellikle ürün kartı/raf radio bölümü ~701-787 ve form/JS ~789-815, ayarlar ~545-562) ve `siparis_hazirla.py:258-301` `_build_raf_payload`'ı oku.

- [ ] **Step 2: Raf radio-seçimini bilgi-gösterimine çevir**

Ürün kartındaki raf radio inputlarını (`name="pick_{barcode}"`) kaldır; yerine "şu raflarda var: A1(3), B2(1)" gibi salt-bilgi listesi göster. Sıralı mod AÇIK ise her ürün için **raf kodu input'u** (`name="raf_{barcode}"`) ürün barkodu input'unun ÜSTÜNE ekle.

- [ ] **Step 3: Sıralı bayrağı + akışı**

Form'a `sirali` hidden input ekle (mevcut "Sıralı Mod" toggle değerinden doldur). JS:
- **Sıralı AÇIK:** raf input + ürün input okutulur; ikisi dolunca paketleme onayı POST edilir (`sirali=1`, `raf_{bc}` dolu).
- **Sıralı KAPALI:** yalnızca ürün barkodu okutulur. Okutunca: önce sunucuya `sirali=0` ile confirm_packing POST et; sunucu toplanmamışsa `ok:false` + uyarı döner (sayaç başlamaz); toplanmışsa mevcut 3sn sayaç → otomatik yazdır + paketleme akışı çalışır.

- [ ] **Step 4: Manuel doğrulama**

El terminalinde: sıralı AÇIK → raf+ürün okut → paketlenir. Sıralı KAPALI + toplanmış → 3sn sonra otomatik. Sıralı KAPALI + toplanmamış → kırmızı uyarı, paketlenmez.

- [ ] **Step 5: Commit**

```bash
git add templates/siparis_hazirla.html siparis_hazirla.py
git commit -m "feat: tekli ekran — raf kodu alanı, radio kaldırıldı, sıralı-kapalı toplandı akışı"
```

---

## Faz 5 — Doğrulama & deploy

### Task 7: Regresyon + deploy

- [ ] **Step 1: Tüm testler**

Run: `DATABASE_URL="sqlite:////tmp/pick_test.db" DISABLE_JOBS=1 WERKZEUG_RUN_MAIN=false python -m pytest tests/ -q`
Expected: tüm testler PASS (ledger testleri dahil regresyon).

- [ ] **Step 2: code-reviewer ajanı**

Değişiklikleri code-reviewer ajanına incelet; CRITICAL/HIGH bulguları düzelt.

- [ ] **Step 3: Commit + push**

```bash
git push origin main
```

- [ ] **Step 4: Prod deploy (sunucuda, kullanıcı)**

```bash
# sunucuda:
git pull origin main
DISABLE_JOBS=1 python scripts/add_toplandi_columns.py   # additive kolon
sudo systemctl restart gullupanel.service
```

- [ ] **Step 5: Manuel uçtan uca test**

Toplu ekranda 1 sipariş raf+ürün okut → stok düşer, toplandı olur. Tekli sıralı-kapalı o siparişi paketle → düşmeden Picking. Toplanmamış başka siparişi sıralı-kapalı paketlemeye çalış → uyarı.

---

## Notlar / riskler
- **Çok-ürünlü siparişler:** Toplu ekran yalnızca tek-ürünlü; çok-ürünlü tekli sıralı-AÇIK'tan (her ürün için raf+ürün). picking_service tek-ürünlü varsayar; çok-ürünlü için confirm_packing her detay için ayrı `pick_order_from_shelf` çağırır.
- **Shopify:** tag akışı aynı kalır; Shopify siparişleri DB'de OrderHazirlaniyor olarak tutulmadığından `toplandi_at` damgası uygulanmaz — Shopify sıralı-kapalı akışı kapsam dışı, mevcut davranışı korunur (gerekirse ayrı ele alınır).
- **Trendyol statüsü:** Artık paketlemede Trendyol'a bildirim yok; siparişin Trendyol'da doğru statüde olduğu varsayılır (kullanıcı kararı).
- **`atanan_raf`:** Kolon kalır ama toplu ekran artık yazmaz; tekli ekran bilgi amaçlı okuyabilir.
