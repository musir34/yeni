# Shopify fiyatlarını Trendyol'a eşitleme (2026-10-23)

- İstek: /shopify/fiyat-karsilastir ekranında tüm modelleri veya seçilen modelleri Shopify → Trendyol fiyat eşitliğine getiren butonlar.
- Arayüze model kutucukları, görünenleri seç, Seçilenleri eşitle ve Tümünü eşitle eklendi. Tümü arama/durum/minimum fark filtrelerinin dışındaki eşleşmiş modelleri de kapsar.
- Karşılaştırma yanıtındaki model_codes filtrelenmemiş model listesidir. Tarayıcı modelleri sırayla işler; işlem boyunca sayfa açık kalmalıdır. Sonuçta güncellenen/aynı/atlanan/doğrulanamayan sayıları gösterilir ve karşılaştırma yenilenir.
- Yeni POST /shopify/api/price-compare/sync tek model alır. Fiyat her istekte Product.sale_price üzerinden sunucuda okunur; istemci fiyatına güvenilmez. Kullanıcı girişi, Shopify ayar kontrolü ve shopify_fiyat sayfa yetkisi uygulanır; başarılı güncellemeler kullanıcı günlüğüne yazılır.
- ShopifyMapping kapsamındaki her varyant kendi Trendyol fiyatına eşitlenir; Shopify ürün kimliğine göre en fazla 250'lik gruplarda productVariantsBulkUpdate kullanılır. Yalnız price gönderilir. Aynı fiyat atlanır; geçersiz/sıfır/negatif fiyat veya silinmiş Shopify varyantı gönderilmez. Shopify yanıtındaki id/fiyat doğrulanmadan başarılı sayılmaz; kısmi hatalarda önceki başarı sayıları korunur.
- Trendyol kaynağı paneldeki kayıtlı fiyattır; bu işlem Trendyol'dan fiyat yenilemez. Stok, üstü çizili fiyat ve kampanya alanları değişmez. Şema/migration yok.
- Doğrulama: python -m pytest --noconftest tests/test_shopify_price_sync.py tests/test_sayfa_yetki.py -q → 32 geçti. --noconftest, ana uygulamayı/scheduler'ı başlatmadan bellek içi SQLite ve sahte Shopify yanıtlarıyla test içindir.
- Arayüz: Jinja render + node --check geçti; gerçek sayfa JavaScript'i izole DOM/fetch taklitleriyle çalıştırıldı, 14 kontrol geçti (seçim, filtre dışı tüm modeller, işlem kilidi, kısmi hata, yenileme). Gerçek tarayıcı kontrolü ortamda açılamadı: headless Chrome kapanması ve yerel önizlemede ERR_CONNECTION_TIMED_OUT; görsel QA tamamlanmadı.
- Shopify API 2026-01 sorgu ve mutasyon şema doğrulamaları geçti. Gereken kapsamlar: read_products, write_products. Kaynak: https://shopify.dev/docs/api/admin-graphql/2026-01/mutations/productVariantsBulkUpdate
- Canlı API mutasyonu/deploy yapılmadı. Deploy kullanıcıda; repoya aktarılıp sunucuda alındıktan sonra git pull && systemctl restart gullupanel.service.
