# Panelden DHL eCommerce iade kodu oluşturma

- Site İade Yönetimi ekranına admin/manager rollerine görünen `İade Kodu Oluştur` akışı eklendi.
- Form kaynak (`degisim`, `trendyol`, `shopify`, `manuel`), sipariş no, isteğe bağlı müşteri/e-posta ve neden alıyor. Trendyol siparişlerinde e-posta zorunlu değil.
- Panelin `/iade-yonetimi/olustur` ucu oturum, rol, AJAX başlığı ve alan doğrulamasından sonra admin anahtarını yalnızca backend'den köprüye gönderiyor.
- Köprü servise admin anahtarlı `POST /api/admin/iadeler` eklendi. Müşteriye açık `/api/iade` ucunun Shopify sipariş/e-posta doğrulaması değiştirilmedi.
- Her form açılışında UUID işlem kimliği üretiliyor. Köprü hem kayıtlı hem devam eden aynı kimliği algılayarak ağ zaman aşımı/tekrar tıklamada çift DHL eCommerce kodunu engelliyor.
- Köprü kaydına `customerName`, `source`, `createdBy` ve `panelRequestId` eklendi; liste ve detay ekranında kaynak/oluşturan bilgisi gösteriliyor.
- VPS köprü kodu yedeklendi (`server.js.bak-20260811-admin-create`), sözdizimi kontrol edildi ve servis yeniden başlatıldı. Anahtarsız POST 401, anahtarlı geçersiz form 400 döndü; test sırasında gerçek DHL eCommerce kodu oluşturulmadı.
- Panel testleri ve ana regresyon paketi başarılı: 162/162 (`test_listing_policy.py` dosyasındaki bilinen bağımsız toplama sorunu hariç).

## Değişim ekranı bağlantısı

- Değişim Talepleri listesindeki her karta admin/manager için `DHL İade Kodu Oluştur` düğmesi eklendi.
- Yeni `/degisim/<degisim_no>/iade-kodu-olustur` ucu sipariş, müşteri ve neden alanlarını istemciden kabul etmek yerine değişim kaydını veritabanından okuyup merkezi köprüye gönderiyor.
- Değişim numarası sabit `requestId` olarak kullanılıyor; aynı kartta tekrar tıklama veya sayfa yenileme ikinci bir DHL eCommerce kodu üretmiyor, mevcut kodu döndürüyor.
- Değişim tablosundaki `kargo_kodu` alanı giden değişim etiketi için aynen korundu; yeni kod müşterinin ürünü geri göndereceği dönüş kodudur.
- Uygulama başlangıcında tam `DATABASE_URL` yazdıran eski debug çıktısı kaldırıldı; log artık yalnızca ayarın mevcut olup olmadığını bildiriyor.
- Yeni route testleri merkezi iade testleriyle birlikte 13/13 geçti; Python, Jinja, render edilmiş JavaScript ve diff kontrolleri başarılı. Test sırasında gerçek DHL eCommerce kodu oluşturulmadı.

## Siparişsiz manuel değişim

- `Yeni Değişim Talebi` ekranı başlangıçta iki seçenek gösteriyor: varsayılan `Sipariş Numarasıyla` ve `Manuel / Siparişsiz`.
- Sipariş numaralı akış mevcut siparişi bulup müşteri ve ürünleri doldurmaya devam ediyor.
- Manuel akış sipariş numarası istemeden alıcı bilgilerini ve yeni ürün alanını açıyor.
- Backend istemciden boş sipariş no kaydetmiyor; kullanıcıya sipariş numarası sormadan `MANUEL-<rastgele>` dahili referansı üretiyor. Böylece liste, stok hareketi, log ve DHL kodu akışları çalışmaya devam ediyor.
- Değişim listesinde bu kayıtlar dahili referans yerine öncelikle `Manuel / Siparişsiz` etiketiyle gösteriliyor.
- Manuel/siparişli hedef testleri dahil ilgili paket 16/16, ana regresyon paketi 168/168 geçti; render edilmiş JavaScript ve Jinja kontrolleri başarılı.

## Değişim kartında canlı DHL dönüş durumu

- Köprü admin listesinin her kaydına mevcut `panelRequestId` alanı eklendi ve canlıya alındı; yedek `server.js.bak-20260811-return-status` olarak bırakıldı. Böylece DHL kaydı değişim UUID'siyle birebir eşleşiyor.
- `/degisim/iade-durumlari?sync=1` panel ucu DHL kayıtlarını anlık senkronlayıp yalnızca değişim kartlarının ihtiyaç duyduğu durum alanlarını döndürüyor.
- Her kartta dört kullanıcı durumu gösteriliyor: kod oluşturulmadı, müşteri henüz vermedi, müşteri kargoya verdi, geri gelen ürün bize ulaştı. Ayrıca manuel `DHL Durumlarını Yenile` düğmesi var.
- Ürün ulaşmadan `İşleme Al` veya `Etiket` seçilirse Chrome `confirm()` yerine tasarımla uyumlu, duruma özel bir Bootstrap onay modalı açılıyor.
- Kullanıcı erken `İşleme Al` işlemini özel modalda onaylarsa backend `return_check_confirmed=1` ile takip numarası olmadan kontrollü şekilde devam ediyor ve bu onay kullanıcı loguna yazılıyor.
- Ürün ulaşmadan erken etiket yazdırma açıkça onaylanabiliyor; ürün ulaşmışsa mevcut `İşleme Alındı` iş kuralı korunuyor.
- Köprü sağlık kontrolü başarılı (`kayitSayisi: 10`); canlı admin cevabında değişim kaydı için `panelRequestId` alanı gizli anahtar/veri gösterilmeden doğrulandı.
- Durum eşleme ve erken işlem testleriyle ilgili paket 19/19, ana regresyon paketi 171/171 geçti; Jinja ve render edilmiş JavaScript sözdizimi doğrulandı. Testlerde gerçek DHL kodu oluşturulmadı.
