# Değişim sayfası her açılışta DHL'i taramasın (2026-10-06, yerelde, commit/deploy yok)

- Komutan: değişim sayfasına her girişte tüm kargo takip sorguları yeniden taranıyor; daha stabil olsun.
- Sebep: `templates/degisim_talep.html` açılışta `loadReturnStatuses(true)` → `/degisim/iade-durumlari?sync=1`
  → köprü `adminListe` `sync=1` görünce `await syncAll()` çalıştırıyor: teslim edilmemiş HER iade kaydı için
  DHL'e sırayla ayrı istek (sunucudaki server.js satır 276; kayıt sayısı arttıkça onlarca saniye).
  Köprü bu taramayı zaten kendi başına saatte bir yapıyor (`syncIntervalMinutes`).
- Çözüm (yalnız panel şablonu): açılışta `loadReturnStatuses(false)` → köprünün kayıtlı durumları anında gelir,
  DHL'e istek gitmez. Canlı tarama yalnız "DHL Durumlarını Yenile" düğmesiyle. Düğmenin altında
  "Son DHL kontrolü: SS:DD (N dk önce) · saatte bir kendiliğinden yenilenir" yazar (kayıtların en yeni `lastSyncAt`'i).
- Köprü servise ve `degisim.py`'ye dokunulmadı. Durumlar en fazla ~60 dk eski olabilir; anlık gerekiyorsa düğme.
- Doğrulama: şablon ve JS sözdizimi; tarayıcıda denenmedi.
