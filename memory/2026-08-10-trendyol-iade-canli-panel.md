# Trendyol iade ekranı canlı veri yenilemesi

- Trendyol'un güncel resmi `getClaims` sözleşmesi ve gerçek üretim yanıtı doğrulandı. Son 30 günde 443 iade paketi / 478 iade kalemi mevcut; kişisel veri test çıktısına yazdırılmadı.
- Eski `/iade-listesi` DB tablosu render etmek yerine oturum korumalı `/iade-listesi/veri` ucundan canlı Trendyol verisini kullanıyor.
- API sayfa boyutu resmi maksimum olan 200'e çıkarıldı; sayfalar en fazla 4 worker ile paralel alınıyor. User-Agent, bağlantı/okuma zaman aşımı ve mevcut 500 kayıt pencere bölme/dedupe koruması birlikte çalışıyor.
- Canlı veri 55 saniye process cache'inde tutuluyor. Tarayıcı 60 saniyede bir otomatik yeniliyor; `Şimdi Yenile` `sync=1` ile cache'i atlayıp Trendyol'u doğrudan çağırıyor.
- Trendyol geçici hata verirse son başarılı cache; cache yoksa son 30 günlük DB arşivi uyarıyla gösteriliyor. Veri hiç alınamazsa kullanıcıya kontrollü 503 mesajı dönüyor.
- Yeni ekranda durum sayaçları/filtreleri, arama, 50'lik tarayıcı sayfalaması, kargo takibi, iade detayı, ürün nedeni ve müşteri notu bulunuyor. Eski şablondaki boş `return_request_number`, var olmayan `model_number` ve `customer_explanation` kullanımları kaldırıldı.
- `TRENDYOL_RETURN_LOOKBACK_DAYS` ile canlı pencere 7–180 gün arasında ayarlanabilir; varsayılan aktif pencere 30 gündür.
- Doğrulama: gerçek Trendyol üretim çekimi, Python/Jinja/JavaScript derleme kontrolleri ve proje ana test paketi (`test_listing_policy.py` dosyasındaki bilinen bağımsız toplama sorunu hariç) 158/158 başarılı.
