# Sipariş Hazırla — not görünürlüğü

- Sorun: `templates/siparis_hazirla.html:60` içindeki barkod geri bildirimine ait `.alert` kuralı sipariş notunu da `opacity:0` / `visibility:hidden` ile gizliyordu. Not mevcut olduğunda Not Ekle düğmesi de normal akış gereği gizlendiğinden not alanı tamamen kayboluyordu.
- Not kutusu ayrı `siparis-notu-banner` sınıfına taşındı; gündüz/gece renkleri, çok satırlı metin ve dar ekranda satır kırılması eklendi. Mevcut not, Düzenle düğmesiyle birlikte görünür.
- Sayfanın genel `.btn` kuralı beyaz yazı ve kenarlıksız görünüm verdiğinden açık zemindeki Not Ekle, Düzenle ve Vazgeç düğmeleri dolu `btn-dark` olarak değiştirildi.
- Notun kaydetme, vazgeçme ve sipariş geçişi akışları incelendi. JavaScript, API, veritabanı ve barkod bildirimleri değiştirilmedi.
- Doğrulama: Jinja sözdizimi kontrolü ve `git diff --check` geçti; bağımsız kod incelemesi yapıldı. Yerel örnek sayfa tarayıcıdan erişilemediği için görsel doğrulama tamamlanamadı. Canlı siparişlere test notu yazılmadı.
- Değişiklikler yerel dosyalarda; deploy kullanıcıda.
