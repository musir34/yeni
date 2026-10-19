# 2026-10-19 — sync_details diski doldurdu (17 Ekim), gece temizliği eklendi

- Kök neden (Komutanın sunucudaki tespit raporu): stock_sync/service.py `_save_sync_details` her senkronda
  barkod × platform satırı yazıyor (~1,9 M/gün), silen iş yoktu → Ocak-Ekim 2026 ~190 M satır, 41 GB
  (satır 33 GB + indeks 8 GB), 75 GB disk %100 → Postgres yazamadı, panel kapandı; iade köprüsünün
  iadeler.json'ı da aynı anda sıfırlandı (bkz. 2026-10-19-iade-koprusu-enospc-kurtarma.md).
- Sunucuda yapılan: son 1 ay (42.373.424 satır) ~/sync_keep.gz (442 MB) olarak dışa alındı, TRUNCATE
  sync_details, disk %44. 2026-10-19 09:00 kontrol: tabloda 3.960.900 satır, en eski 2026-10-17 08:05 →
  "son ayı geri yükledik" adımı GERÇEKLEŞMEMİŞ; sync_keep.gz silinmemeli (karar Komutanda; panel eski kayda
  ihtiyaç duymadığı için geri yüklememek önerildi).
- Panel tarafı: `stock_sync/temizlik.py` sync_detay_temizle (created_at < şimdi−SYNC_DETAY_SAKLAMA_GUN,
  varsayılan 7 gün; 50k'lık partiler, tek koşuda en çok 400 parti) + app.py cron job `sync_detay_temizlik`
  her gece 03:40. Test tests/test_sync_detay_temizlik.py. Postgres boşalan yeri yeniden kullanır, dosya küçülmez.
  Neden 7 gün: 30 gün = ~57 M satır ≈ 12 GB; panel yalnız son senkron durumu + hata listesini okur.
