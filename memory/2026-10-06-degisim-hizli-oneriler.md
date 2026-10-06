# Değişim formunda hızlı öneriler (2026-10-06, yerelde, commit/deploy yok)

- Komutan: değişim oluştururken sipariş no girince öneri çıksın — bir küçük, bir büyük numara, farklı renk —
  ürünü barkod arayarak değil tek tıkla seçebilsin.
- `degisim.degisim_onerileri(barcode)`: sipariş edilen ürünün (Product: model, renk, numara) aynı model+rengindeki
  bir küçük ve bir büyük numarası + aynı numaranın diğer renkleri; her biri barkod ve `CentralStock` adediyle.
  Buçuklu numara ("38,5") sayıya çevrilip sıralanır; arşivli ürün önerilmez; aynı renk+numara iki barkoddaysa
  stoğu çok olan gösterilir; numarası sayı olmayan üründe (STD) numara önerisi yok.
- `/get_order_details` cevabındaki her kaleme `oneriler` eklenir (`_onerileri_ekle`; Trendyol ve site siparişi).
  Site siparişinde Shopify barkodu panel barkoduyla eşleşmezse öneri çıkmaz (form eskisi gibi çalışır).
- `templates/yeni_degisim_talebi.html`: sipariş edilen ürün kartının altında "Aldığı: renk · numara", yeşil
  öneri düğmeleri (stok adediyle; stok yoksa gri ama seçilebilir). Tıklayınca değişim formu açılır, barkod boş
  ürün alanına yazılır ve ürün bilgisi kendiliğinden getirilir; alan doluysa yeni ürün alanı eklenir.
- Kayıt akışı (`/degisim-kaydet`) değişmedi. Şema değişikliği yok.
- Test: `tests/test_degisim_oneri.py` (5, yalıtılmış). Önizlemede sahte siparişle düğmeler ve tıklama akışı denendi;
  canlı veriyle denenmedi.
