# 2026-09-25 — Finans hareketlerini temizleme isteği

Kullanıcı veritabanı yedeğini aldığını belirterek Finans hareketlerinin tamamını silip sıfırdan başlamayı istedi.
(Codex oturumu kota sınırında yarım kaldı; Claude tamamladı.)

- `scripts/reset_finans_hareketler.py`: bayraksız çalıştırılınca yalnız SAYIM yapar (silmez); `--confirm` ile
  finans_cari_kalem → finans_cari_hareket → finans_calisan_hakedis → finans_islem → finans_ana_gider_kalem
  sırasıyla (FK sırası) tek transaction içinde siler; finans_hesap ve finans_cari bakiyelerini 0 yapar. Yalnız PostgreSQL'de çalışır.
- 2. revizyon (kullanıcı ekran görüntüsüyle "düzenli ödemelerde bulunanlar hâlâ silinmemiş" dedi): Düzenli Ödemeler →
  Kalem Tanımları (finans_ana_gider_kalem: Ahmet/Ali/Kalfa/Nur hüda planları) da silinir. Bu yüzden çalışan planı
  "ileri alma" mantığı gereksizleşti ve kaldırıldı.
- Korunanlar: hesaplar, kategoriler, gider adları, cari/çalışan kayıtları.
- Excel gelir yükleme mükerrer koruması finans_islem'e bakar; sıfırlama sonrası aynı ekstre tekrar yüklenebilir.
- Sıfırlama sırasında finans tabloları ACCESS EXCLUSIVE kilitlenir; saatlik hakediş job'ı bekler. Eski `/kasa` kapsam dışı.
- 2026-09-25 18:50 CANLIDA ÇALIŞTIRILDI (kullanıcı tüneli `!ssh` ile açtı): hareket tabloları zaten 0 idi, 4 plan tanımı silindi, bakiyeler 0; sonraki sayım tüm tablolarda 0 doğruladı.
- Sunucuda `~/gullupanel/yeni` dizininden:
  `DISABLE_JOBS=1 ../venv/bin/python scripts/reset_finans_hareketler.py` (sayım) →
  `DISABLE_JOBS=1 ../venv/bin/python scripts/reset_finans_hareketler.py --confirm` (silme). Önce yedek.
