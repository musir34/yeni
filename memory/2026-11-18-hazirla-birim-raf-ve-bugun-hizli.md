# Sipariş hazırla: kutu başına raf + Bugün Hazırlananlar hız/ürün adedi (2026-11-18)

## 1) Bugün Hazırlananlar
- Rozet: `50 (63 ürün)`; modal başlığı `… · 50 sipariş · 63 ürün`. Adet = paketleme logundaki
  `Toplam Adet` (confirm_packing `toplam_adet`). Eski kayıtta yoksa `63+ ürün`.
- Yavaşlık kök nedeni: `/api/bugun-hazirlananlar` her satır için `_hazirlanan_yazdir_bilgisi`
  çağırıyordu (Shopify'da sırayla `get_order` API + Trendyol'da tablo taraması).
  Artık liste: Shopify görünen no (#1428) TEK `nodes(ids:)` GraphQL ile (`_shopify_siparis_adlari`);
  yazdır alanları yeni `POST /api/bugun-hazirlananlar/yazdir` ile arka planda (Shopify 6 paralel thread,
  app_context içinde). Yazdır düğmesi yüklenene kadar spinner; bulunamazsa "sipariş bulunamadı".

## 2) Kutu başına raf okutma (sıralı mod)
- Şablon: raf alanı kartta tek değil, her kutu barkodunun ÜSTÜNDE: `raf_{barcode}_{q}`,
  `data-quantity-index=q`. Raf Enter → aynı q'nun kutu barkodu; kutu onayı → sonraki kutunun boş rafı.
- confirm_packing (update_service.py ~260): birim raflar Counter ile raf bazında gruplanır, her
  gruptan ayrı düşülür. Ledger anahtarı: ilk grup klasik `{order}:pick:{bc}` (üretim/kargo
  has_movement kontrolleri buna bakar), ek raflar `{order}:pick:{bc}:{raf}`. Eski `raf_{barcode}` /
  `pick_` alanları fallback olarak duruyor. Birim raflardan biri boşsa "Raf seçilmedi".
- Telefon eşlik: PC payload'a `raf_kutular` [{q,...}] eklendi (`raf` = ilk), `uygula` raf okutmasını
  `o.adet` sırasına yazar; telefon her kutunun üstünde ayrı raf alanı çizer. Sürümler: pc v4, telefon v5.

## Bilinen (dokunulmadı)
- Şablonda kutu barkodu `data-product-index`/id'si iç döngünün `loop.index0`'ını (q) kullanıyor →
  2. üründe id `barkodInput-right-0-0` olur; telefon `#barkodInput-right-<kalem>-<q>` ile 2.+ ürünün
  kutusunu bulamayabilir. Önceden var olan hata.
