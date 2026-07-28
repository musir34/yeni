---
name: project-uretim-modu
description: "Üretim Modu (ön sipariş): seçili modeller stok 0 olsa da Trendyol'a sabit 5 stok, gelen sipariş /uretim sayfası + tek adrese mail, üretilene dek terfi bekletme; deploy bekliyor"
metadata:
  node_type: memory
  type: project
  originSessionId: 8028395c-ed16-4aaf-98c7-72ae76c2e6b6
---

Üretim Modu özelliği eklendi (2026-07-28). Kod hazır, deploy kullanıcıda.

**Ne:** Admin ürün listesinden (model kartı ⋮ menüsü) veya `/uretim` sayfasından bir modeli
(product_main_id) üretim moduna alır → o modelin TÜM barkodları Trendyol'a **daima sabit 5**
stok gider (fiziksel stok/rezerv/tampon/raf-yok-sıfırlama ezilir). Bu modele sipariş gelince
`uretim_siparis` kaydı + panelden ayarlanan tek adrese anlık mail; sipariş orders_created'da
kalır ama "Üretildi" işaretlenene dek otomatik terfi ETMEZ ve stok-yok maillerine GİRMEZ.

**Nerede:**
- `uretim_modu.py` — ayarlar (PlatformConfig `uretim_ayar` torbası, migration'sız:
  `{"models": [...], "mail_to": "..."}`), `get_uretim_barcodes()` (hata→boş set, senkron asla
  durmaz), `isle_yeni_siparisler()` (ingest yakalama + mail, `URETIM_SABIT_ADET=5`)
- `stock_sync/service.py` — `_get_all_stocks` / `_get_stocks_by_barcodes` içinde
  `platform == "trendyol"` kapılı override (Idefix/Amazon/HB/Shopify etkilenmez);
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

İlgili: [[project-listing-buffer-cancel-prone]], [[project-stock-ledger]]
