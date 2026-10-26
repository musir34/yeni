# 2026-10-26 — Sipariş Hazırla: Shopify siparişi paketlenince aynı sipariş yeniden geliyordu

## Şikâyet
Komutan: "Shopify siparişini hazırlayıp okutuyorum, yeni sipariş yerine eski sipariş geliyor; ekranı
yenilediğimde gidiyor."

## Teşhis
- confirm_packing Shopify siparişine "Hazirlaniyor" etiketini yazar (update_service.py), ardından JS
  ~1.4-2.3 sn sonra refreshOrderContent ile /siparis-hazirla'yı yeniden çeker.
- get_home sıradaki siparişi `_fetch_shopify_beklemede_orders` ile Shopify **arama sorgusu**
  (`-tag:Hazirlaniyor ...`) üzerinden seçer. Shopify arama dizini etiket değişikliğini birkaç saniye
  geç yansıtır → az önce paketlenen sipariş listede hâlâ dönüyor ve yine açılıyordu; elle yenileyince
  dizin güncellenmiş oluyordu.

## Düzeltme (`siparis_hazirla.py`, tek fonksiyon)
`_fetch_shopify_beklemede_orders` dönen kayıtların KENDİ `tags` alanına bakar (kayıt güncel, dizin
değil); `_SHOPIFY_KAPALI_TAGLAR` = {Hazirlaniyor, Kargoda, Teslim Edildi, Arsivlendi} taşıyanlar
yerelde elenir. get_home, get_queue_orders (kuyruk) ve uretim_modu site siparişi taraması aynı
fonksiyonu kullandığından üçü de tutarlı. Şema yok; deploy: pull + restart.
