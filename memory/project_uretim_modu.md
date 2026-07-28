---
name: project-uretim-modu
description: "Üretim Modu (ön sipariş): seçili modeller stok 0 olsa da Trendyol'a sabit 5 stok, gelen sipariş /uretim sayfası + abone kullanıcılara mail, üretilene dek terfi bekletme; deploy bekliyor"
metadata:
  node_type: memory
  type: project
  originSessionId: 8028395c-ed16-4aaf-98c7-72ae76c2e6b6
---

Üretim Modu özelliği eklendi (2026-07-28). Kod hazır, deploy kullanıcıda.

**Ne:** Admin ürün listesinden (model kartı ⋮ menüsü) veya `/uretim` sayfasından bir modeli
(product_main_id) üretim moduna alır → o modelin TÜM barkodları Trendyol'a **daima sabit 5**
stok gider (fiziksel stok/rezerv/tampon/raf-yok-sıfırlama ezilir). Bu modele sipariş gelince
`uretim_siparis` kaydı + bildirimi açık kullanıcılara anlık mail; sipariş orders_created'da
kalır ama "Üretildi" işaretlenene dek otomatik terfi ETMEZ ve stok-yok maillerine GİRMEZ.

**Nerede:**
- `uretim_modu.py` — ayarlar (PlatformConfig `uretim_ayar` torbası, migration'sız:
  `{"models": [...]}`; mail alıcıları User.notify_events `uretim_siparis` olayı (kullanıcı yönetimi → Bildirimler)), `get_uretim_barcodes()` (hata→boş set, senkron asla
  durmaz), `isle_yeni_siparisler()` (ingest yakalama + mail, `URETIM_SABIT_ADET=5`)
- `stock_sync/service.py` — `_get_all_stocks` / `_get_stocks_by_barcodes` içinde
  `platform == "trendyol"` kapılı override (Idefix/Amazon/HB etkilenmez);
  CentralStock satırı olmayan üretim barkodu da listeye eklenir
- `order_service.py` `_process_sync_orders_bulk` — commit SONRASI kanca
- `promotion_service.py` + `stock_alert_service.py` — üretim bekleyen hariç tutma
- Raf tarafı: ingest'te üretim barkoduna kritik "Raf bulunamadı!" audit'i yerine info
  "raf=ÜRETİM MODU" yazılır (`order_service.py` raf döngüsü); `raf_recovery.recover_missing_raf`
  (AUTO_HEAL/BACKFILL) üretim bekleyenleri tarama dışı bırakır — üretildi işaretlenince
  sonraki turda normal raf ataması kendiliğinden yapılır
- `uretim_routes.py` + `templates/uretim.html` — `/uretim` sayfası (qna tarzı 2FA kalkanı)
- `models.py` `UretimSiparis` (`uretim_siparis` tablosu) — order_number unique (resync koruması),
  uretildi/uretildi_at/mail_sent_at

**Kritik bilgi:** Sipariş `details`'indeki `product_main_id` Trendyol **contentId**'dir, panel
model kodu DEĞİL → eşleşme barkod üzerinden yapılır (barkod → Product.product_main_id).

**Deploy:** `git pull` → `venv/bin/python scripts/create_uretim_tables.py` (bir kez, idempotent)
→ `systemctl restart gullupanel.service`. Tablo açılmadan restart olursa tüm kancalar hatayı
yutar, mevcut davranış korunur. Rollback: modeli üretim modundan çıkar → ilk senkronla gerçek stok.

- Shopify (2026-07-28 ek): `shopify_stock_service.push_stock` de sabit adedi uygular; `health_monitor.check_oversell_risk` üretim barkodlarını sahte oversell alarmından hariç tutar. ⚠️ Shopify siparişleri DB'ye inmediği için (canlı GraphQL görünüm) Shopify'dan gelen üretim siparişi /uretim listesine DÜŞMEZ ve mail TETİKLEMEZ — sadece stok 5 gider; sipariş yakalama Trendyol'a özgü.

- Sayfa v2 (2026-07-28): 3 statü — Bekleyen → **İşleme Alındı** (`isleme_alindi(+_at)` kolonları, `/uretim/api/isleme-al/<id>`) → Üretildi; her karta 'Ürün Özellikleri' paneli (liste API'si Product'tan görsel/başlık/model zenginleştirir, sipariş listesi detay düzeniyle aynı). İşlemde olanlar da terfiden hariç (uretildi=False filtresi kapsıyor). Kolonlar `scripts/create_uretim_tables.py` ile additive eklenir (idempotent ALTER).

- Kargo çıktısı (2026-07-28): Üretildi tıklanınca (ve her karttaki 🖨 ile) kargo diyaloğu — 'Yazdır (normal akış)' `/order-label` formuna POST (sipariş hazırla ile birebir alanlar), 'Otomatik Gönderim' kodu kopyalar+overlay gösterir (sipariş hazırladaki autoShip karşılığı). Liste API'si kargo verisini orders_created/hazirlaniyor/picking/shipped'den canlı çeker; cargo_tracking_number sipariş Yeni'yken zaten mevcut, /order-label statü kontrolü yapmaz. Not: 'Otomatik Gönderim' backend'de ayrı akış DEĞİL, yalnız istemci tarafı yazdırma tercihi.

İlgili: [[project-listing-buffer-cancel-prone]], [[project-stock-ledger]]
