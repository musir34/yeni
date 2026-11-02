# 2026-11-02 — Şahsi cari: "Kasaya Borç Verdim"

- Komutan emri (agentation, /finans/cari/9): şahsi hesapta yalnız "Kasadan Borç Aldım" vardı; ters yön eklensin.
- Kararlar (Komutan): para her seferinde seçilen hesaba girer (Beyazıt/Elde/Banka); geri almak için ayrı düğme YOK,
  mevcut "Kasadan Borç Aldım" kullanılır (önce kasanın borcundan düşer, aşan kısım kasaya borç olur).
- finans_cari_service: yeni hareket türü `borc_verme` (+1, etiket "Kasaya borç verdim"), SAHSI_BORC_TURLERI'ne eklendi
  (sahsi_kasa_borcu net hesaplar), `_sahsi_kontrol` izinli, `tahsilat_al(tur='borc_verme', hesap_kodu=...)` →
  seçilen hesaba `cari_tahsilat`. SAHSI_GIRIS_HESAPLARI = beyazit/elde/banka (kredi kartı yok).
- finans_cari.py: POST /finans/cari/<id>/borc-verme (cari_borc_verme). Şablon: düğme + fnBorcVermeModal; pozitif
  şahsi bakiye "kasanın size borcu"; cari listesinde şahsi grup etiketi artık bakiyeye göre (eskiden hep "kasaya borcum").
- DB: tur String(20) → yeni değer additive, migration yok.
- Rapor etkisi: mevcut "Borcumu Ödedim" gibi kasa tarafı `cari_tahsilat` → aylık özette "Giren/Cari tahsilat"a girer.
- Testler: tests/test_finans_cari_sahsi.py +5 test; finans testleri 166/166 (Windows'ta PYTHONUTF8=1 gerekir:
  test_finans_iptal_dugmesi read_text() kodlamasız — önceden var olan, ortam kaynaklı).
