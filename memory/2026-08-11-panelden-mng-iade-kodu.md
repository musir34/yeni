# Panelden MNG iade kodu oluşturma

- Site İade Yönetimi ekranına admin/manager rollerine görünen `İade Kodu Oluştur` akışı eklendi.
- Form kaynak (`degisim`, `trendyol`, `shopify`, `manuel`), sipariş no, isteğe bağlı müşteri/e-posta ve neden alıyor. Trendyol siparişlerinde e-posta zorunlu değil.
- Panelin `/iade-yonetimi/olustur` ucu oturum, rol, AJAX başlığı ve alan doğrulamasından sonra admin anahtarını yalnızca backend'den köprüye gönderiyor.
- Köprü servise admin anahtarlı `POST /api/admin/iadeler` eklendi. Müşteriye açık `/api/iade` ucunun Shopify sipariş/e-posta doğrulaması değiştirilmedi.
- Her form açılışında UUID işlem kimliği üretiliyor. Köprü hem kayıtlı hem devam eden aynı kimliği algılayarak ağ zaman aşımı/tekrar tıklamada çift MNG kodunu engelliyor.
- Köprü kaydına `customerName`, `source`, `createdBy` ve `panelRequestId` eklendi; liste ve detay ekranında kaynak/oluşturan bilgisi gösteriliyor.
- VPS köprü kodu yedeklendi (`server.js.bak-20260811-admin-create`), sözdizimi kontrol edildi ve servis yeniden başlatıldı. Anahtarsız POST 401, anahtarlı geçersiz form 400 döndü; test sırasında gerçek MNG kodu oluşturulmadı.
- Panel testleri ve ana regresyon paketi başarılı: 162/162 (`test_listing_policy.py` dosyasındaki bilinen bağımsız toplama sorunu hariç).

## Değişim ekranı bağlantısı

- Değişim Talepleri listesindeki her karta admin/manager için `MNG İade Kodu Oluştur` düğmesi eklendi.
- Yeni `/degisim/<degisim_no>/iade-kodu-olustur` ucu sipariş, müşteri ve neden alanlarını istemciden kabul etmek yerine değişim kaydını veritabanından okuyup merkezi köprüye gönderiyor.
- Değişim numarası sabit `requestId` olarak kullanılıyor; aynı kartta tekrar tıklama veya sayfa yenileme ikinci bir MNG kodu üretmiyor, mevcut kodu döndürüyor.
- Değişim tablosundaki `kargo_kodu` alanı giden değişim etiketi için aynen korundu; yeni kod müşterinin ürünü geri göndereceği dönüş kodudur.
- Uygulama başlangıcında tam `DATABASE_URL` yazdıran eski debug çıktısı kaldırıldı; log artık yalnızca ayarın mevcut olup olmadığını bildiriyor.
- Yeni route testleri merkezi iade testleriyle birlikte 13/13, ana regresyon paketi 165/165 geçti; Python, Jinja, render edilmiş JavaScript ve diff kontrolleri başarılı. Test sırasında gerçek MNG kodu oluşturulmadı.
