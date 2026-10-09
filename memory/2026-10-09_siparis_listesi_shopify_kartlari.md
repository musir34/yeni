# 2026-10-09 — Sipariş listesine Shopify (site) siparişleri kart olarak düşüyor

**Komutan emri:** "Sipariş listesine sadece Trendyol siparişleri düşüyor; aynı şekilde Shopify siparişleri de
düşsün, sipariş nosu 1428 tarzında 4 haneli olmalı."

**Kök durum:** Trendyol siparişleri orders_* tablolarında; site siparişleri DB'de YOK, canlı Shopify API'den
geliyor (siparis_hazirla `_fetch_shopify_beklemede_orders` gibi). Sipariş listesi SQL UNION + sayfalama ile
yalnız DB'ye bakıyordu.

**Ne yapıldı:**
- Yeni `shopify_siparis_listesi.py` (saf dönüşüm + 60 sn önbellek): `get_orders(limit=100, "-tag:Arsivlendi")`
  → kart (SimpleNamespace). `order_number='SH-<iç kimlik>'` (arşivle/not/üretim eylemlerinin anahtarı, mevcut
  panel biçimi), `display_number='1428'` (mağaza adı, `#` atılır — KARTTA GÖSTERİLEN). Durum etiketten:
  etiketsiz→Created, Hazirlaniyor→Hazirlaniyor, Kargoda→Shipped, "Teslim Edildi"→Delivered, cancelledAt→Cancelled
  (templates/shopify/orders.html getOrderStatus ile aynı kural). Panelde Archive 'SH-…' kayıtlı olanlar elenir
  (her istekte taze; önbellek yalnız API yanıtı). Not + üretim rozeti Trendyol kartıyla aynı toplu sorgularla.
  Kargo: ilk fulfillment trackingInfo (company/number). order_date naive UTC'ye çevrilir (`| ist` ile uyumlu).
- `order_list_service.py`: `get_order_list` ve `get_filtered_orders` → yalnız **1. sayfada** Shopify kartları
  DB kartlarına eklenir ve `kartlari_sirala` ile aynı sıralama kuralına (date_desc / deadline_* — tarihi olmayan
  en sona) göre karışır; `total_orders_count` artar. Geciken görünümünde (show_overdue) Shopify yok (teslim
  tarihi yok). Sekmelerde durum kodu eşleşmesiyle süzülür (Yeni/Hazırlanıyor/Kargoda/Teslim/İptal; İşleme Alındı'ya
  Shopify düşmez — site akışında Picking yok).
- `templates/order_list.html`: başlık ve kopyala düğmesi `order.display_number or order.order_number`;
  "Kalan Süre" satırı yalnız teslim tarihi varsa (yoksa JS `new Date('Z')` NaN → yanlış "Süre Doldu" basıyordu).
  Etiket formu/Arşivle/Not `order_number` (SH-…) ile çalışmaya devam eder.
- `shopify_service.get_orders` sorgusuna `shippingAddress.address1/address2` eklendi (kartın etiket formu için).
- Testler: `tests/test_shopify_siparis_listesi.py` (6 saf test; `--noconftest` ile).

**Bilinçli sınırlar:** Shopify kartları 2+ sayfalarda görünmez (son 100 arşivlenmemiş site siparişi 1. sayfada
sıraya girer); etiket değişimi en geç 60 sn gecikmeyle yansır; ödemesi bekleyen (havale) site siparişleri de "Yeni"
görünür (liste bilgi amaçlı, hazırlamaya düşme kuralı siparis_hazirla'da). Shopify rozeti/logosu eklenmedi
("aynı şekilde" emri) — istenirse `_is_shopify` bayrağı hazır.

**Deploy:** `git pull && systemctl restart gullupanel.service` (şema değişikliği yok).
