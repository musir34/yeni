# DHL iade kodu 9 haneye indirildi (2026-10-05)

- Şikâyet: müşteriler "iade kodu çalışmıyor" diyor, kodlar çok uzun.
- İade kodu panelde değil, sunucudaki köprü serviste üretilir:
  `/home/musir/shopify-uygulamalari/dhl-kargo/server.js` (`createReturn`). Bu repo dışındadır.
  Servis systemd değil; `start.sh` + crontab (@reboot ve 5 dk'da bir) ile ayakta tutulur, kayıt `app.log`,
  veri `iadeler.json`.
- Eski formül: `sipariş no + "-" + Date.now()` → 18–30 karakter, tireli.
- İnceleme (52 kayıt): DHL 52 kodun hepsini kabul etmiş, oluşturma hatası yok; kullanılmayan kodları da
  DHL tanıyor ("İade Gönderi İşlemi Yapılmadı"). Yani "sistem onaysız kod veriyor" şüphesi doğru değil.
  En tutarlı açıklama: uzun/tireli kodun şubeye aktarılırken bozulması (kanıtlanmadı).
- Değişiklik: kod artık 9 haneli, yalnız rakam, tiresiz, `iadeler.json` içinde benzersiz
  (`crypto.randomInt`). İç parça barkodu `kod-P1` aynen kaldı. Eski kodlar geçerli. Panelde değişiklik yok.
- Canlıya 2026-10-05 07:43'te alındı (komutan betiği kendisi çalıştırdı). Yedekler:
  `server.js.bak-20261005-9hane`, `iadeler.json.bak-20261005`. Geri dönüş: yedeği server.js üzerine
  kopyala, node sürecini öldür, `./start.sh`.
- AÇIK: DHL'in 9 haneli salt rakam kodu kabul ettiği ilk gerçek kodla doğrulanacak.
- Tuzak: uzak kabukta `ssh host '... pkill -f "node.*dhl-kargo/server.js" ...'` yazılırsa desen kendi
  kabuğunu da eşleştirir; komutları `bash -s` ile stdin'den ver.
