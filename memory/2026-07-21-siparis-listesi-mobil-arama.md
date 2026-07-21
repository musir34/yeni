# Sipariş listesi mobil arama düzeni

## Değişiklik

- Mobil sipariş aramasında metin alanı kalan genişliği kullanacak, arama ikon butonu ise 48 px sabit genişlikte kalacak şekilde düzenlendi.
- Arama formunun normal GET submit'i engellenip sonuç alanı `fetch` ile yerinde güncellenir hale getirildi.
- Arama sonucunda kartlar, toplam sipariş sayısı, arşiv eşleşme uyarısı ve sayfalama birlikte yenileniyor.
- Tarayıcı geri/ileri geçmişi `pushState` ve `popstate` ile korunuyor.

## Neden

Araç çubuğundaki genel mobil buton kuralı arama ikonuna da yüzde 100 genişlik vererek giriş alanını sıkıştırıyordu. Normal form submit'i de her aramada tam sayfa yenilenmesine neden oluyordu.
