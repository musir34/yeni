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

## 2026-10-07: site siparişi adıyla (1423) kabul edilir
- Komutan: değişim formuna Shopify sipariş no 1423 yazınca kabul etmiyor.
- Sebep: form site siparişini yalnız `SH-<Shopify iç kimlik>` (uzun sayı) biçiminde tanıyordu; 1423 sipariş ADI.
  Düz sayı Trendyol tablolarında aranıp "bulunamadı" dönüyordu.
- `degisim.shopify_siparis_bilgisi(girdi)` → (bilgi, kanonik "SH-<id>"): '1423', '#1423', 'SH-1423', 'sh 1423'
  kabul; kısa sayı Shopify'da adla aranır (`_shopify_id_adla_bul`, GraphQL `orders(query:"name:#1423")`),
  10+ haneli sayı iç kimlik sayılır. `/get_order_details` düz sayıda önce Trendyol, bulunamazsa site adı dener;
  cevaba `siparis_no` (kanonik) eklendi, form gizli alanı onu yazar → kayıt yine `SH-<id>` adıyla (liste, DHL
  kodu, değişim akışları değişmedi). Yinelenen POST yolu da aynı çözücüyü kullanır.
- Gerçek Shopify'da 1423 adla bulundu, müşteri adı/adresi geldi (yerel sqlite denemesinde ürün listesi boş kaldı: eşleme tablosu boştu — canlıda eski SH- akışıyla aynı kod). Sipariş adı araması sırasında `read_customers` yetkisi eksik uyarısı önceden de vardı. 6 test (test_degisim_oneri.py). Canlıda denenmedi.

## 2026-10-07: site siparişinde ürünler hiç gelmiyordu (eski hata, düzeltildi)
- Komutan: "ürün bilgisini neden getirmedi?" — `_fetch_shopify_order_info` kalemleri ham `lineItems.edges`'den
  okuyordu; `shopify_service.get_order` ise kalemleri `line_items` listesine çevirip `lineItems`'ı siliyor
  (shopify_service.py ~723). Sonuç: SH- siparişlerinde değişim formu ürün listesi HER ZAMAN boştu.
- Düzeltme: `line_items` okunur (yoksa `lineItems.edges`'e düşer); barkod olarak önce `resolved_barcode`
  (eşleme tablosundan panel barkodu), yoksa Shopify varyant barkodu → hızlı öneriler site siparişinde de çıkar.
- Gerçek 1423 siparişi: müşteri + 1 ürün geldi. 7 test. Aynı deseni kullanan başka yer var mı bakılmadı.
