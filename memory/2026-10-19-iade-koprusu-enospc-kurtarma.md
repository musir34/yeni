# 2026-10-19 — İade köprüsü (dhl-kargo) ENOSPC ile düştü, iadeler.json kurtarma

- Belirti: /iade-yonetimi "İade servisine şu anda ulaşılamıyor"; iade kodu üretilemiyor. MNG giden gönderi
  işiyle ilgisi YOK (o kod bu dizine dokunmaz).
- Kök neden: 2026-10-17 07:43 UTC disk doldu (app.log: "[sync] … ENOSPC: no space left on device, write").
  Köprünün `saveDb` = `fs.writeFileSync(iadeler.json)` yarım kaldı → dosya 0 bayt. Sonraki her açılışta
  (crontab start.sh 5 dk) `JSON.parse("")` → "Unexpected end of JSON input" ile çöküş (588 kez).
  Disk sonra boşalmış (%53); /home/musir/sync_keep.gz (462 MB, 17 Ekim) kaynağı bilinmiyor.
- Veri: son yedek iadeler.json.bak-20261005 (52 kayıt). 5-16 Ekim arası 19 kayıt geri kuruldu:
  app.log "[createReturnOrder] cevap" satırları (referans + returnOrderLabelURL, 19/19 bulundu),
  panel user_logs "DHL eCommerce iade kodu oluşturuldu" (sipariş no, iade kodu, tarih, kullanıcı; 16 kayıt),
  app.log "[webhook] #1421/#1437 iadesi onaylandi" (2 kayıt), 1 kayıt (154808457) kaynaksız.
  Müşteri adı/neden: degisim tablosu, Shopify get_orders, orders_delivered. Durumlar "OLUSTURULDU"
  yazıldı; köprü syncAll (checkReturnOrder) gerçek durumu MNG'den çeker.
- Betikler (müşteri verisi içerdiği için repoda DEĞİL): sunucu ~/tmp/iade_kopru_kurtar_20261019.js
  (kuru prova / --uygula; mevcut iadeler.json doluysa onun üstüne ekler, kopya iadeler.json.kurtarma-20261019)
  ve ~/tmp/iade_kopru_server_patch_20261019.js (server.js: loadDb boş/bozuk dosyada en yeni .bak-*'a düşer;
  saveDb günlük yedek iadeler.json.bak-YYYYMMDD + tmp→rename atomik yazım + 60 gün temizlik;
  yedek server.js.bak-20261019-kurtarma). Otomatik mod canlı dosyayı yazdırmadı → Komutan koşturur.
- Uygulama: `node ~/tmp/iade_kopru_kurtar_20261019.js --uygula && node ~/tmp/iade_kopru_server_patch_20261019.js --uygula
  && ~/shopify-uygulamalari/dhl-kargo/start.sh && sleep 3 && curl -s localhost:3434/api/saglik` (sudo gerekmez).
