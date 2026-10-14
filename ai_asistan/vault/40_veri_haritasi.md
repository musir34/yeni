# Veri Haritası — "Hangi bilgi nerede?" (2026-10-14)

Bu not, panelin geliştirme hafızasından süzüldü. Bir soruya cevap ararken ÖNCE buraya,
sonra sistem promptunun sonundaki **Canlı Şema Özeti** ve **Proje Notları Dizini**ne bak.
Tablo adını tahmin etme; burada yoksa şema özetinden bul.

## Ürün ve model
- `products` — satır = BARKOD (varyant: model + renk + beden). Model kodu `product_main_id`
  (ör. '032', '0121', '259'), `color`, `size`, `title`, `sale_price`, `list_price`,
  `cost_usd`/`cost_try` (maliyet), `tedarikci_kodu`/`tedarikci_adi` (üretici), `hidden`,
  `archived`, `on_sale`, `platforms`. Model başına toplama: `GROUP BY product_main_id`.
- Model maliyeti: `model_maliyet` (kalem bazlı, `kalem_id` → `maliyet_kalem`) ve
  `model_direk_maliyet` (model başına tek değer, `birim`).
- `barcode_aliases` — alias barkod → `main_barcode`. Sipariş kalemindeki barkod `products`'ta
  yoksa burada ara. Türkçe karakterli barkodlar ASCII hâliyle de eşleşebilir.
- Tedarikçi listesi: `tedarikcilar` (kod, adi).

## Stok
- Merkezi stok: `central_stock` (barcode, qty). "Elde kaç çift?" = bu tablo.
  Model stoğu: `products` ⋈ `central_stock` ON barcode, `GROUP BY product_main_id`.
- Raf stoğu: `raf_urunleri` (raf_kodu, urun_barkodu, adet); raf tanımı `raflar` (kod, ana, ikincil, kat).
  Merkezi stok ile raf toplamı normalde eşittir; fark = hayalet stok şüphesi.
- Stok hareket defteri (ledger): `stock_movement` (barcode, shelf_code, delta ±, reason, order_number,
  idempotency_key, source, created_at). Fiziksel düşüm kargolamada (Shipped) ve raf okutmada yazılır.
- Pazaryerine gönderilen listeleme tamponu: `stock_listing_policy` (barcode, extra_buffer, cancel_count).
- Shopify stok eşlemesi: `shopify_mappings` (barcode ↔ shopify_variant_id, last_stock_sent).
  Eşlemesi olmayan barkoda Shopify'a stok gitmez.
- Günlük satış serisi (öneri motoru için): `daily_sales` (barcode, date, qty).

## Siparişler
- Siparişler için TEK kaynak `ai_orders_all` view'i (bkz. 20_tablolar). Ham tablolar statüye göre
  ayrıdır: `orders_created` → `orders_hazirlaniyor` → `orders_picking` → `orders_shipped` →
  `orders_delivered`; ayrıca `orders_cancelled`, `orders_archived`. Sipariş statü değiştikçe
  satır tablolar arası TAŞINIR (aynı anda tek tabloda bulunur).
- Ortak kolonlar: `order_number`, `order_date`, `status`, `customer_name/surname`, `product_barcode`,
  `product_main_id`, `quantity`, `amount` (sipariş toplamı), `discount`, `commission`,
  `cargo_tracking_number`, `cargo_provider_name`, `agreed_delivery_date` (kargo son günü), `source`.
- `details` (text, JSON liste) — siparişin KALEMLERİ: her eleman `{barcode, quantity, unit_price,
  line_total_price, color, size, sku, productName, product_main_id, commissionFee}`.
  Kalem birim fiyatı YALNIZ burada: `jsonb_array_elements(details::jsonb)` ile aç,
  `(d->>'unit_price')::numeric`. Bozuk JSON olabilir → `details ~ '^\s*\['` ile süz.
  Tuzak: `details` içindeki `product_main_id` Trendyol contentId'dir, model kodu DEĞİLDİR;
  model kodu için barkodla `products.product_main_id`'ye git.
- `orders_archived` kolon adları diğerleriyle birebir değil (`stockCode`/`stockcode`); yalnız
  gereken kolonları seç, `SELECT *` yazma.
- Site (Shopify) siparişleri sipariş tablolarına inmez; `source ILIKE '%SHOPIFY%'` olanlar
  senkron kopyalarıdır. `SH-<id>` biçimli numaralar site siparişinin iç kimliğidir.
- Sipariş notu: `siparis_notu` (order_number, note). Trendyol müşteri kimliği köprüsü:
  `trendyol_siparis_musteri` (order_number, customer_id) → soru soran müşterinin siparişleri.
- Sipariş olay izi: `order_audit_logs`; kullanıcı işlem kayıtları: `user_logs` (action, details, timestamp).
- Manuel/elle açılan siparişler: `yeni_siparisler` + `siparis_urunler`.

## Üretim modu (ön sipariş)
- Üretim modundaki model listesi: `platform_configs` satırı `platform = 'uretim_ayar'`,
  `extra_config->'models'` (JSON dizi, model kodları). Sorgu:
  `SELECT jsonb_array_elements_text(extra_config::jsonb->'models') FROM platform_configs WHERE platform='uretim_ayar';`
- Üretim siparişleri: `uretim_siparis` — satır = üretime düşen sipariş. `order_number`, `order_date`,
  `product_main_id` (virgüllü model kodları), `details` (JSON: üretilecek kalemler `{barcode, quantity}`),
  durum bayrakları `isleme_alindi` → `uretildi` → `paketlendi` (+ `_at` tarihleri), `hazirlayan`,
  `arsivlendi_at`, iptal bildirimi `iptal_mail_at`. "Bekleyen üretim" = `paketlendi = false AND arsivlendi_at IS NULL`.
- Üretim siparişinin FİYATI bu tabloda YOKTUR: `order_number` ile sipariş tablolarına gidip
  `details` kalemindeki `unit_price` okunur (barkod eşleşmezse tek kalemli siparişte tek fiyatı al).
- Rafta stoğu yeten kalem üretime yazılmaz (raf önceliği); `DG-<no>` numaralı kayıtlar
  değişimden açılan üretim kayıtlarıdır, `SH-` site siparişidir (fiyatı sipariş tablolarında yok).
- Paketlemede doğrulama okutması: `uretim_dogrulama` (order_number, barcode, adet_no, okutan).
- Üretim önerisi/plan: `uretim_plan`, `uretim_oneri_watchlist`, `uretim_oneri_defaults`, `uretim_secim_preset`.

## İade ve değişim
- Trendyol iadeleri: `returns` (claim_id, order_number, status, reason, barcode, quantity, create_date).
  Site iadeleri: `return_orders` + `return_products` (return_to_stock, product_condition).
- Değişimler: `degisim` (degisim_no, siparis_no, degisim_durumu, kargo_kodu, degisim_tarihi,
  `urunler_json`: `{barkod, adet, model_kodu, renk, beden}` listesi).

## Finans ve kasa
- Yeni kasa (/finans): hesaplar `finans_hesap` (kod: Beyazıt/Elde/Banka/kredi kartı, bakiye),
  hareketler `finans_islem` (hesap_id, tur, yon ±1, tutar, tarih, kategori_id, iptal),
  kategoriler `finans_kategori`, gider adları `finans_gider_adi`, düzenli ödeme planı `finans_ana_gider_kalem`.
- Cari hesaplar: `finans_cari` (ad, tur, para_birimi TL/USD, bakiye), hareketleri `finans_cari_hareket`
  (yon, tutar, kur, hakedis_id), mal giriş kalemleri `finans_cari_kalem`, çalışan hak edişi `finans_calisan_hakedis`.
- Eski kasa: `ana_kasa`, `ana_kasa_islemler`, `kasa_kategoriler`; eski giderler `expenses`.
- Fiyat motoru önerileri: `motor_oneri_log` (model_kodu, renk, aksiyon, mevcut/onerilen fiyat, skor, strateji).
- Alissa (ikinci üretici hesabı): `alissa_siparis`, `alissa_hareket`, `alissa_kargo_kalem`, `alissa_odeme`, `alissa_ayar`.

## Müşteri soruları ve mesajlar
- Trendyol soru-cevap: `trendyol_questions` (text, product_main_id, status, answer_text, ai_draft,
  answered_by, creation_date tz'li). Site soruları: `shopify_questions`. Instagram:
  `instagram_conversations` + `instagram_messages` (direction in/out) + `instagram_comments`.

## Kullanıcılar ve yetki
- `users` (username, role, is_owner, status), sayfa yetkileri `kullanici_sayfa_yetki` (sayfa_kodu, izin).

## Zaman kuralları (özet; ayrıntı 00_asistan_kimligi)
- `ai_orders_all` view'inde her şey TR saatinde, dönüştürme YAPMA.
- Ham tablolarda `order_date`, `created_at`, `uretim_siparis.*_at` naive UTC → TR için
  `AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Istanbul'`. `*_questions` ve instagram tabloları tz'li (tstz).

## Hazır sorgu kalıpları
- Model bazında son 30 gün üretim siparişi + ortalama çift fiyatı:
  `uretim_siparis` kalemlerini aç → `order_number`+barkod ile sipariş tablolarının `details`
  kalemine bağla → `products.product_main_id` ile grupla, `sum(unit_price*qty)/sum(qty)`.
- Model stoğu: `SELECT p.product_main_id, sum(c.qty) FROM products p JOIN central_stock c USING (barcode) GROUP BY 1;`
- Üretim modundaki modeller: yukarıdaki `platform_configs` sorgusu.
