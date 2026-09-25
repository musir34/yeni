# 2026-09-25 — Finans hareketlerini temizleme isteği

Kullanıcı veritabanı yedeğini aldığını belirterek Finans hareketlerinin tamamını silip sıfırdan başlamayı istedi.
(Codex oturumu kota sınırında yarım kaldı; Claude tamamladı.)

- `scripts/reset_finans_hareketler.py`: bayraksız çalıştırılınca yalnız SAYIM yapar (silmez); `--confirm` ile
  finans_cari_kalem → finans_cari_hareket → finans_calisan_hakedis → finans_islem sırasıyla (FK sırası) tek
  transaction içinde siler; finans_hesap ve finans_cari bakiyelerini 0 yapar. Yalnız PostgreSQL'de çalışır.
- Korunanlar: hesaplar, kategoriler, gider adları, cari/çalışan kayıtları, düzenli ödeme planı tanımları.
- Çalışan planları (calisan_cari_id dolu) yeniden tahakkuk üretmesin diye başlangıcı ileri alınır:
  haftalık → ilk_odeme_tarihi bugünden sonraki ilk aynı-haftagünü (haftagünü korunur), baslangic_donem o ay;
  aylık → baslangic_donem gelecek ay. Mantık örnek tarihlerle yerelde doğrulandı (25.09.2026 için:
  Pzt 03.08 → Pzt 28.09; Cuma 25.09 → Cuma 02.10; aylık → 2026-10).
- Normal (çalışan olmayan) planlara dokunulmaz: geçmiş aylarda "bekliyor" görünür, tahakkuk/cari borç üretmez.
- Excel gelir yükleme mükerrer koruması finans_islem'e bakar; sıfırlama sonrası aynı ekstre tekrar yüklenebilir.
- Sıfırlama sırasında finans tabloları ACCESS EXCLUSIVE kilitlenir; saatlik hakediş job'ı bekler. Eski `/kasa` kapsam dışı.
- Lokal: `.env` localhost:5433 tüneline bakıyor, tünel kapalı; Claude'un ssh tüneli açması izinle reddedildi → canlıda ÇALIŞTIRILMADI.
- Sunucuda `~/gullupanel/yeni` dizininden:
  `DISABLE_JOBS=1 ../venv/bin/python scripts/reset_finans_hareketler.py` (sayım) →
  `DISABLE_JOBS=1 ../venv/bin/python scripts/reset_finans_hareketler.py --confirm` (silme). Önce yedek.
