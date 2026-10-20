# 2026-10-20 — Stok Ekle ve Raflar gece modu

- Sorun: Ortak gece modu yazıları açarken bu iki bağımsız şablonun özel kartları, raf başlıkları ve pencereleri beyaz kalıyordu; metinler okunamıyordu.
- `templates/stock_addition.html`: Ana kart, barkod listesi/ürün kartları, yardımcı metinler, işlem durumları, kardeş barkod uyarısı ve düğme renklerine koyu tema eklendi.
- `templates/raf_olustur.html`: Raf grupları/katları, stok listesi, bilgi/onay pencereleri, sekmeler, rozetler ve bildirimler koyu temaya uyarlandı. Dinamik barkod sonuçlarının inline açık zemin/hover renkleri yalnız gece modunda eziliyor.
- Kurallar sayfaların kendi stil bloklarında `@media screen` + `html.gs-dark` kapsamında. Açık mod, yazdırma ve ortak CSS değiştirilmedi; HTML/JavaScript, backend, stok/ledger akışı ve DB şeması aynı.
- Doğrulama: Jinja parse ve stil bloğu dışının git sürümüyle birebir aynı olduğu kontrol edildi; diff incelemesi başarılı. Ayrı geçici tarayıcı sekmelerinde yeni CSS ile stok formu, raf grupları/katları ve bilgi penceresi görsel olarak kontrol edildi. Önizleme sekmeleri kapatıldı; canlı siteye kalıcı değişiklik/stoğa yazma yapılmadı.
- Deploy kullanıcıda: `git pull && systemctl restart gullupanel.service` (önce commit/push gerekir).
