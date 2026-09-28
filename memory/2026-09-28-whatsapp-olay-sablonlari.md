# 2026-09-28 — WhatsApp olay bazlı şablonlar

## Meta tarafı (test WABA 1491753382972145)
Beş şablon açıldı; hepsi Utility, dil `tr`, footer "Güllü Panel otomatik bildirimi".
| Şablon | Header | Değişkenler | Durum (28 Eyl) |
|---|---|---|---|
| musteri_sorusu | yok | kaynak, ürün, soru | Aktif |
| gecikme_uyarisi | yok | sipariş sayısı, kalan süre, sipariş listesi | Aktif |
| uretim_siparisi | GÖRSEL (zorunlu) | sipariş no, ürün, adet | İncelemede |
| uretim_iptal | yok | sipariş no, ürün, adet | İncelemede |
| geciken_siparis | yok | sipariş sayısı, sipariş listesi | İncelemede |
Genel şablon `gullu_bildirim` (dil `en`, 2 değişken) duyuru sayfası ve yedek için duruyor.

## Kod
- `whatsapp_notify.notify_staff_template(template, params, lang="tr", image_url=None, fallback=None)`
  + `_async` hali. Şablon yok/onaysızsa (132001, eşzamanlı döner) ve `fallback=(başlık, detay)`
  verildiyse genel şablona düşer → incelemedeki şablonlar bağlanınca mesaj kaybolmaz.
- Shopify + Trendyol soru bildirimleri `musteri_sorusu` şablonuna geçirildi.
- Canlı deneme: `musteri_sorusu` iki alıcı için Meta tarafından kabul edildi.

## Bağlanmayanlar ve neden
- uretim_siparisi / uretim_iptal: şablon incelemede + alıcı kararı + yedek görsel bekleniyor.
  Görsel başlıklı şablonda görsel her gönderimde zorunlu; fotoğrafsız ürün için yedek görsel şart.
- gecikme_uyarisi / geciken_siparis: eşik (kaç saat kala) ve sıklık kararı bekleniyor.
