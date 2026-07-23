# Trendyol Soru-Cevap mobil arayüz yenilemesi (2026-07-23)

## Ne değişti

- `templates/soru_cevap.html` mobil öncelikli bir çalışma ekranı olarak yeniden
  tasarlandı; backend endpointleri ve veri sözleşmeleri değiştirilmedi.
- Renkli hızlı erişim çubuğu, kompakt marka başlığı + hızlı menüye dönüştürüldü.
- Durum sekmeleri ve arama tek kontrol kartında toplandı.
- Soru kartlarında ürün / müşteri sorusu / cevap alanı bilgi hiyerarşisi ayrıldı.
  Mobilde tek sütun, geniş ekranda soru ve cevap için iki sütun kullanılıyor.
- AI taslak üretimi, AI ile düzenleme, karakter sayacı ve gönderme eylemi dokunmatik
  kullanıma uygun hale getirildi.
- Sayfalama mobilde kısaltıldı; boş, hata ve yükleniyor durumları tasarlandı.
- Kullanıcı cevap yazarken 30 saniyelik otomatik yenilemenin metni silmesi
  engellendi; bu durumda yalnızca bekleyen soru sayısı yenileniyor.
- Sayfaya özel koyu tema ve dar ekran kuralları eklendi.

## Doğrulama

- Jinja parse ve JavaScript `node --check` başarılı.
- Playwright ile 390 px mobil ve 1440 px masaüstü görsel kontrolü yapıldı.
- Mobil genişlikte yatay taşma yok; cevap düzenleme alanının `dirty` koruması
  etkileşim testiyle doğrulandı.

## Deploy

`git pull && systemctl restart gullupanel.service` — migration gerekmez.
