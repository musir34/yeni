# 2026-09-25 — Çalışan carisi, hak ediş ve kısmi ödeme

İstek: Her eklenen çalışana otomatik cari açılsın; haftalık hak edişler ve eksik/tam ödemeler orada biriksin.

## Kullanım
- Düzenli Ödemeler planında "Çalışan ödemesi" seçilir. Yeni çalışan adıyla cari otomatik açılır; mevcut çalışan carisi de seçilebilir. Kira/reklam gibi diğer planlar cari oluşturmaz.
- Sabit hak edişler başlangıç takviminden bugüne kadar vadesi geldikçe bir defa cariye borç yazılır. Saatlik scheduler görevi (finans_calisan_hakedis) ve panel/düzenli ödeme/cari ekranları kaçırılmış dönemleri tamamlar. Gelecek dönemler yalnız plan olarak gösterilir.
- Değişken hak edişte borç tutarı varsayılmaz; kullanıcı dönemin hak edişini girer. Hak edişi belirlenmemiş dönem ayrı görünür. Sonradan varsayılanı değiştirmek geçmiş hak edişleri değiştirmez.
- Hak ediş ve "şimdi verilen para" ayrı alanlardır. Ödeme alanı boşsa yalnız borç kaydedilir. Örnek: 5000 hak ediş − 3000 ödeme = 2000 kalan. Sonraki hafta başlasa da cari ve panelde borç kalır.
- Aynı döneme birden çok kısmi ödeme yapılabilir. Ödeme istek anahtarı çift gönderimde ikinci kasa çıkışını önler. Ödeme toplamı hak edişi aşamaz. Hak ediş ödenenden aşağı indirilemez; önce hatalı ödeme iptal edilir.
- Hak ediş tutarı değişince cari fark hareketi yazılır; kasa etkilenmez. Doğrudan hak ediş hareketini iptal etmek engellenir. Ödeme iptali kasa ve cari etkisini birlikte geri alır.
- Çalışan carisinden de ilgili döneme ödeme yapılır; dönemsiz genel cari ödeme/alış/satış yolları çalışan için kapalıdır.
- Eski düzenli planın çalışan olduğu bir kez işaretlenebilir. Önceden ödenmiş kayıtlar ödenen tutar kadar hak ediş+ödeme olarak bağlanır, kasadan tekrar para çıkmaz. Geçmişte eksik ödendiği bilinen bir dönemde toplam hak ediş kullanıcı tarafından düzeltilebilir. Diğer eski giderleri adlarından çalışan varsayarak otomatik dönüştürmedik.

## Teknik
- Yeni finans_calisan_service.py + finans_calisan.py ve çalışan modal/buton şablonları.
- FinansAnaGiderKalem.calisan_cari_id; FinansCalisanHakedis (kalem/dönem unique, nullable tutar); FinansCariHareket.hakedis_id ve unique odeme_anahtari.
- Yeni çalışan nakit ödemeleri cari_odeme olarak kaydedilir; plan/dönem ve cari hareketiyle bağlıdır. Kasa raporlarında bir kez sayılır. Hak ediş nakit gider değildir.
- Plan → eski işlem (varsa) → kasa (varsa) → cari kilit sırası. Otomatik tahakkuk ve elle ödeme aynı plan kilidini paylaşır. Cari kapanışı aktif plan/bekleyen hak ediş/borç varken engellenir.

## Doğrulama
- `.venv/bin/python -W ignore -m unittest discover -s tests -p 'test_finans_*.py'`: 28 test geçti (izole SQLite).
- Sabit/değişken hak ediş, kısmi ödeme, sonraki haftaya/aya borç taşıma, tekrar istek, yetersiz bakiye rollback, iptal, hak ediş düzeltme, stale form, eski ödeme aktarımı, ortak çalışan carisi, raporların çift saymaması ve HTTP route/admin yetki kontrolü test edildi.
- Chromium: çalışan alanları, mevcut çalışan seçimi/düzenleme, hak ediş ve ödeme tutarlarının ayrılığı, yalnız hak ediş kaydetme, cari/panelden ödeme modalı ve mobil görünüm genişliği kontrol edildi. JS hatası yok.
- Python/Jinja sözdizimi, tam migration import/önkoşulları ve git diff --check geçti. PostgreSQL DDL gerçek veritabanında çalıştırılmadı.

## Güncel dağıtım
Önceki haftalık ödeme güncellemesinin yerine tam güncelleme:
`DISABLE_JOBS=1 python scripts/update_finans_calisan.py`
Ardından servis yeniden başlatılır. Script temel finans+cari+haftalık önkoşulları içerir; mevcut kayıtları silmez/değiştirmez, tekrar çalıştırılabilir.
Önceki `update_finans_haftalik.py` ve `create_finans_tables.py` çalıştırma girişleri de tam şemaya yönlendirildi.
Canlı veritabanı güncellemesi ve deploy yapılmadı.
