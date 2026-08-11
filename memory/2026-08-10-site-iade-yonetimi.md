# Site iade yönetimi entegrasyonu

- MNG/DHL iade köprüsünün admin liste ucu VPS'e yüklendi ve servis yeniden başlatıldı. Sağlık ucu 9 kayıt döndürdü; `panel.key` boşken admin ucunun 401 ile kapalı kaldığı doğrulandı.
- `iade_yonetimi.py` ile oturum koruması altında `/iade-yonetimi` ekranı ve `/iade-yonetimi/veri` backend proxy'si eklendi. `X-Admin-Key` yalnızca backend'den köprüye gider; tarayıcıya aktarılmaz.
- Panelde Bekleyenler, Kargoda ve Elime Ulaştı sayaç/filtreleri; yerel arama; detay; barkod ve Shopify sipariş aksiyonları; `sync=1` ile anık MNG yenileme bulunur.
- Mevcut Trendyol iade listesi korunarak ana menüde ayrı adlandırıldı.
- Site İade Yönetimi bağlantısı, Shopify akışıyla birlikte bulunması için Anasayfa > Paneller menüsünde Shopify Siparişler'in hemen altına yerleştirildi.
- Yapılandırma: VPS panel `.env` dosyasında `IADE_PANEL_KEY` zorunludur. `IADE_API_URL` verilmezse aynı sunucudaki `http://localhost:3434` kullanılır.
- Doğrulama: iade proxy ve oturum koruması testleri, sağlık testi, Python derleme, Jinja derleme, JavaScript parse ve Flask route kayıt kontrolü başarılı. Projenin `tests/` paketi (bilinen bağlamsız `test_listing_policy.py` toplama hatası hariç) 150/150 geçti.
