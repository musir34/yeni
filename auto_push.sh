#!/bin/bash

git add .
git commit -m "Otomatik güncelleme: $(date +'%Y-%m-%d %H:%M:%S')" || echo "Değişiklik yok, commit atlanıyor"
git push origin main || echo "Push başarısız!"

#shell de güncelle
#git config user.name "Musir" && git config user.email "musir@example.com" && git add . && git commit -m "Güncelleme (TR): $(TZ=Europe/Istanbul date +'%Y-%m-%d %H:%M:%S')" && git push
# "git pull origin main" komutu ile githubda ki dosyaları alabilirsin
# "git reset --hard origin/main" komutu ile replitte ki tüm değişiklikleri siler ve githubda ki dosyaları alır.