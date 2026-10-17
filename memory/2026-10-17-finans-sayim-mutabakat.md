# 2026-10-17 — Kasa defterinde Sayım / Mutabakat

**Emir:** "Buraya mutabakat butonu ekle; elimdeki fiziksel parayı gireceğim, fazla mı eksik mi söylesin,
açıklamasıyla farkı kaydedeyim."

- `finans_service.sayim_mutabakat(hesap_kodu, sayilan, tarih, aciklama, uid)`: fark = sayılan − defter bakiyesi;
  tek `sayim_farki` satırı (+ fazla / − eksik), bakiye sayılana eşitlenir; fark 0 / açıklama boş / kredi kartı → hata.
  `parse_sayilan` 0'a izin verir (kasa boş). Tür `ISLEM_TURLERI` + etiket "Sayım Farkı"; `donem_ozet` yalnız
  gelir/gider/cari türlerini topladığı için raporlara GİRMEZ (kart_duzeltme gibi).
- Rota `POST /finans/defter/<hesap_kodu>/sayim` (finans.py `defter_sayim`), şablon finans_defter.html:
  başlık kartında "Sayım / Mutabakat" düğmesi (kredi kartı hariç) + modal, yazdıkça canlı fazla/eksik.
- Aynı gün bağlam: "Kredi Borcu" carisi ve 23.999,18 ödeme SQL ile fiziksel silindi (kasa bakiyesine
  dokunulmadı → Elde tutarsızlığı, 28.09 tarihli kasasız 'transfer_cikis' düzeltme satırıyla kapatıldı);
  kart ekstre yüklemesi (97 işlem + 30 şahsi cari satırı) SQL ile geri alındı, kart 0.
- Şema yok. Test tests/test_finans_sayim.py (5). Commit f73b5e7; deploy: git pull + restart.
