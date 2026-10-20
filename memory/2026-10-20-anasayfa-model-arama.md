# 2026-10-20 — Anasayfa model araması

- İstek: Görev ve Üretim Modelleri kartlarında model kodunu yazarak hızlı bulma.
- `templates/home.html`: Her karta bağımsız arama kutusu eklendi. Yazdıkça model kodları metin olarak filtrelenir; baştaki sıfırlar korunur, harf büyüklüğü önemsenmez. Arama temizlenince tüm modeller görünür.
- Görev araması iki grubu birlikte süzer ve kapalı listeleri açar. Eşleşme yoksa ilgili grupta veya üretim tablosunda mesaj gösterilir. Aramada liste kaydırması başa döner.
- Kart toplamları ve Kopyala düğmelerinin tüm listeyi kopyalama davranışı korunur. Backend, stok, sipariş ve DB şeması değişmedi; migration yok.
- Doğrulama: Jinja derleme, örnek verilerle iki kartın var/yok olduğu dört durumda izole şablon render, tüm inline JavaScript için `node --check` ve diff incelemesi başarılı. Canlı uygulama/DB çalıştırılmadı; tarayıcıda görsel kontrol yapılmadı.
- Deploy kullanıcıda: `git pull && systemctl restart gullupanel.service` (önce değişikliklerin commit/push edilmesi gerekir).
