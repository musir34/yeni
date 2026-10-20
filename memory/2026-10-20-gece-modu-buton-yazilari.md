# 2026-10-20 — Gece modunda mavileşen buton yazıları

- Sorun: `static/css/dark-mode.css` içindeki genel `html.gs-dark a` ve `a:hover` kuralları, bağlantı olarak oluşturulan butonların beyaz yazılarını maviye çeviriyordu.
- Bu iki kuraldan standart `.btn` ve etkilenen `.ss-btn`, `.btn-home`, `.btn-print`, `.btn-detail`, `.qna-send-btn`, `.search-container .clear-btn`, `.header .left-btns a` bağlantıları çıkarıldı. Butonların mevcut beyaz yazı ve etkileşim renkleri yeniden geçerli. Fiş oluşturma sayfasındaki stilsiz Temizle linki kapsam dışı tutuldu.
- Kapsam: Anasayfa/ortak menü ve aynı sorunun bulunduğu stok senkronizasyonu, rapor, tedarik ve soru-cevap bağlantı butonları. Sarı butonların koyu yazısı, açık zeminli butonların hover kontrastı ve normal metin linkleri korunur; tüm bağlantıları zorla beyaza boyayan kural eklenmedi.
- Doğrulama: İlgili sınıfların normal/hover renkleri ve CSS öncelikleri kod üzerinden incelendi; `git diff --check` başarılı. Yalnız ortak CSS değişti; açık mod, yazdırma ve iş mantığı değişmedi.
- Deploy kullanıcıda: `git pull && systemctl restart gullupanel.service` (önce commit/push gerekir).
