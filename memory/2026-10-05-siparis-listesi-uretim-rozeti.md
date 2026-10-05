# Sipariş listesinde üretim siparişi rozeti (2026-10-05, yerelde, commit/deploy yok)

- Komutan: sipariş listesinde normal ve üretim siparişleri karışık görünüyor; üretim siparişi olduğu kartta belli olsun.
- "Üretim siparişi" = `uretim_siparis` tablosunda kaydı olan sipariş (order_number).
- `uretim_modu.uretim_durum_haritasi(order_numbers)` → {sipariş no: bekliyor|uretimde|uretildi|paketlendi}
  (tek toplu sorgu; hata → boş sözlük, liste rozetsiz çalışır). Etiketler `URETIM_DURUM_ETIKETI`.
- `order_list_service._merge_order_rows` her karta `uretim_durumu` + `uretim_etiketi` iliştirir (notlarla aynı yerde).
- `templates/order_list.html` `order_card` makrosu: üretim kartında mor sol kenar (`.uretim-karti`) + başlıkta
  fabrika ikonlu rozet (`.uretim-rozeti`; üretildi/paketlendi yeşil). Gece modu karşılığı var.
- Şema değişikliği yok. Test: `tests/test_uretim_rozeti.py` (yalıtılmış). Kart önizlemede dört haliyle görüldü;
  canlı veriyle denenmedi.
