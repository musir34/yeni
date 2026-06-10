# Manuel Raf-Okutmalı Toplama — Tasarım Dokümanı

**Tarih:** 2026-06-10
**Durum:** Onaylandı (uygulama planı bekliyor)

## Bağlam ve problem

Mevcut sistem siparişlere **otomatik raf atıyor** (`atanan_raf`). Çalışan fiziksel olarak başka bir raftan ürünü aldığında, sistem otomatik atadığı raftan düşüyor → fiziksel gerçek ile sistem ayrışıyor → **stok kaybı / hayalet stok**. (Bu, yeni kurulan stok hareket defteri / ledger ile aynı kök problemin farklı bir yüzü.)

**Hedef:** Otomatik raf atamasını kaldırmak. Stok düşümü, çalışanın **fiziksel olarak aldığı rafın barkodunu okutmasıyla** (yer-gerçeği) yapılacak. Böylece düşüm tahmine değil, gerçeğe dayanır.

## Hedefler / Hedef olmayanlar

**Hedefler:**
- Otomatik `atanan_raf` ataması kaldırılır; raflar yalnızca *bilgi amaçlı gösterilir*.
- Stok düşümü yalnızca **okutulan raftan** yapılır (toplu toplama veya tekli sıralı-açık).
- Bir sipariş **tam bir kez** düşer; düşülmemiş sipariş paketlenemez (uyarı).
- Paketlemede Trendyol'a API ile statü bildirimi **kaldırılır** (sipariş geldiğinde zaten işleme alınmış sayılıyor).

**Hedef olmayanlar (DOKUNULMAZ):**
- Raf görüntüleme, mal kabul (stok ekleme), CentralStock senkronu, pazaryeri stok push.
- Created→Hazırlanıyor geçişi (`promotion_service`).
- Shopify tag akışı (şimdilik aynı kalır).
- Çok-ürünlü siparişlerin toplu ekranda gösterimi (yalnızca tek-ürünlü; çok-ürünlü tekli sıralı-açıktan).

## Genel akış

```
TOPLU TOPLAMA ekranı (picking istasyonu)
  • Hazırlanıyor tek-ürünlü siparişler, RAF KODUNA göre artan sıralı
  • Otomatik raf ataması YOK — ürünün hangi raflarda olduğu sadece gösterilir
  • Her satırda 2 alan: [RAF BARKODU]  [ÜRÜN BARKODU]
  • İkisi okunur → doğrulama → O RAFTAN düşülür (ledger pack_out) → ürün arabaya
  • Sipariş "toplandı" damgalanır (toplandi_at, toplandi_raf) → listeden düşer
        ↓
TEKLİ ekran (paketleme istasyonu)
  • SIRALI KAPALI: sadece ÜRÜN barkodu okutulur
       - toplandi_at VAR → 3sn sayaç → otomatik yazdır + paketle (statü geçişi). DÜŞME YOK.
       - toplandi_at YOK → 🔴 UYARI "bu sipariş toplanmadı, önce topla" → paketleme BAŞLAMAZ
  • SIRALI AÇIK: ürün barkodu alanının ÜSTÜNE raf kodu alanı; raf radio-seçimi KALDIRILIR
       - raf + ürün okunur → o raftan düşülür → toplandı damgalanır → paketlenir
       - (çok-ürünlü veya topluda toplanmamış siparişler için)
```

## Bileşenler

### 1. Veri modeli (additive)
`OrderHazirlaniyor` tablosuna iki nullable kolon (her iki ekran da bu statüde çalışır):
- `toplandi_at` (DateTime, nullable) — sipariş fiziksel toplandığı (düşüldüğü) an.
- `toplandi_raf` (String, nullable) — okutulan/düşülen raf kodu.

Alembic migration: yalnızca `op.add_column` × 2. DROP/ALTER yok → canlı veri güvende. (`add_stock_movement` deseninin aynısı.) Not: `flask db` yok + multi-head var; tablo/kolon ekleme prod'da `*.__table__` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` ile idempotent script üzerinden yapılır (mevcut `create_stock_movement_table.py` / `db_setup` deseni).

### 2. Toplu Toplama ekranı (yeniden yapılır)
- **Backend:** `new_orders_service.py` — yeni/değişen route. `_build_shelf_groups`'taki **otomatik atama mantığı kaldırılır**; yerine raf koduna göre sıralı, henüz toplanmamış (`toplandi_at IS NULL`) tek-ürünlü Hazırlanıyor siparişleri.
- **Yeni endpoint:** `POST /prepare-new-orders/pick` — `{order_number, raf_barkodu, urun_barkodu}` alır:
  1. Barkodları normalize et (`normalize_barcode`).
  2. Ürün barkodu siparişin ürünüyle eşleşiyor mu? Değilse hata.
  3. Okutulan raf bu ürünü içeriyor ve `adet >= gerekli` mi? Değilse hata ("bu rafta bu üründen yeterli yok").
  4. **O raftan düş:** seçili `RafUrun` satırından `adet -= qty` (with_for_update) + `record_movement(reason=pack_out, shelf_code=okutulan_raf, mutate_shelf=False, idempotency_key="{order}:pick:{barcode}")` + `sync_central_stock`.
  5. `toplandi_at=utcnow`, `toplandi_raf=okutulan_raf` damgala. Audit: `stock_decremented` + `order_picked`.
  6. Commit. Yanıt: sıradaki sipariş.
- **Template:** `bulk_order_prepare.html` yeniden — raf koduna göre dizili, her satırda 2 okutma alanı (raf + ürün), tamamlananlar listeden düşer. (Zebra TC21: keyboard-wedge Enter; etkileşimli öğeleri focus-capture'dan hariç tut — [[project-zebra-tc21]] dersleri.)

### 3. Tekli ekran — sıralı mod AÇIK
- **Template:** `siparis_hazirla.html` — ürün barkodu alanının üstüne **raf kodu** alanı. Raf **radio-seçimi kaldırılır**; `_build_raf_payload` çıktısı yalnızca "şu raflarda var" bilgisi olarak gösterilir.
- **Backend:** `confirm_packing` (`update_service.py`) sıralı-açık dalı: form'dan `pick_{barcode}` (radio) yerine **okutulan raf kodu** gelir. Düşüm o raftan yapılır (mevcut mantık; sadece kaynak radio yerine scan). `toplandi_at/raf` damgalanır.

### 4. Tekli ekran — sıralı mod KAPALI
- **Template/JS:** yalnızca ürün barkodu alanı. Ürün okununca backend'e sorulur.
- **Backend:** yeni hafif kontrol — `order.toplandi_at`:
  - **Doluysa:** düşüm YAPILMAZ. 3sn sayaç (mevcut "onaylama süresi" ayarı) → otomatik yazdır + `confirm_packing` (yalnızca statü geçişi + etiket).
  - **Boşsa:** `{success:false, error:"Bu sipariş henüz toplanmadı (stok düşülmedi). Önce toplu ekranda topla."}` → paketleme başlamaz, sayaç çalışmaz.

### 5. Trendyol API bildiriminin kaldırılması
- `confirm_packing` içindeki `update_order_status_to_picking` (Trendyol API çağrısı) ve ona bağlı rollback **kaldırılır**. Paketleme yalnızca panel-içi `OrderHazirlaniyor → OrderPicking` geçişi + etiket yapar.
- Shopify tag güncellemesi (`shopify_service.update_order_status`) **aynı kalır**.

## Stok düşümü kuralı (tek-düşüm garantisi)
- Düşüm **yalnızca raf okutulduğunda, okutulan raftan** olur (toplu `/pick` veya tekli sıralı-açık).
- Tekli sıralı-kapalı **asla düşmez** — yalnızca daha önce toplanmış siparişi paketler.
- **Yetkili kilit:** HER düşüm yolu (toplu `/pick` ve tekli sıralı-açık) düşümden ÖNCE `order.toplandi_at`'ı kontrol eder; doluysa düşümü atlar (zaten toplanmış). Böylece `toplandi_at` tek-düşümün birincil garantisidir.
- **Backstop:** Tüm pick yollarında ortak idempotency_key `{order}:pick:{barcode}` kullanılır; damga bir şekilde atlansa bile ledger ikinci fiziksel düşümü engeller. (Not: pick yollarının hepsi aynı `pick` anahtar biçimini kullanır — tutarlılık şart.)

## Hata / kenar durumlar
- Yanlış ürün barkodu → "ürün eşleşmedi".
- Okutulan rafta ürün yok / yetersiz → "bu rafta yeterli yok, doğru rafı okut".
- Toplanmamış siparişi sıralı-kapalı paketleme → uyarı, engellenir.
- Aynı sipariş iki kez toplanmaya çalışılırsa → `toplandi_at` zaten dolu → ikinci pick reddedilir / idempotent atlanır.
- Stok 0/eksik rafa düşüm → `RafUrun.adet >= 0` CHECK + negatife düşmez.

## Test stratejisi (TDD)
`tests/` altında, mevcut izole-sqlite deseni ([[project-stock-ledger]] test altyapısı):
1. `pick`: doğru raf+ürün → RafUrun düşer, pack_out yazılır, `toplandi_at/raf` dolar.
2. `pick`: yanlış raf (ürün yok/yetersiz) → reddedilir, düşüm olmaz.
3. Tekli sıralı-kapalı + toplandi_at boş → paketleme reddedilir (uyarı).
4. Tekli sıralı-kapalı + toplandi_at dolu → düşüm OLMADAN statü geçişi.
5. Çift-pick → ikinci düşüm olmaz (idempotency + damga).
6. `confirm_packing` artık Trendyol API çağırmıyor (mock ile doğrula).

## Dokunulan dosyalar
- `models.py` — OrderHazirlaniyor `toplandi_at`, `toplandi_raf` (additive).
- migration/idempotent script — kolon ekleme.
- `new_orders_service.py` — otomatik atama kaldır, `/pick` endpoint, sıralama.
- `templates/bulk_order_prepare.html` — yeniden (2 alanlı tarama UI).
- `update_service.py` `confirm_packing` — Trendyol API kaldır; sıralı-açık raf-scan; sıralı-kapalı toplandi_at kontrolü.
- `siparis_hazirla.py` / `siparis_hazirla.html` — raf kodu alanı, radio-seçimi kaldır, sıralı-kapalı JS akışı.
- `tests/` — yeni testler.

## Açık nokta
- Yok (tüm kararlar netleşti). Shopify tag akışı bu kapsamda aynı kalır; ileride istenirse ayrı ele alınır.
