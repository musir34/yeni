#!/bin/bash

git add .
git commit -m "Otomatik güncelleme: $(date +'%Y-%m-%d %H:%M:%S')" || echo "Değişiklik yok, commit atlanıyor"
git push origin main || echo "Push başarısız!"

#shell de güncelle
#git config user.name "Musir" && git config user.email "musir@example.com" && git add . && git commit -m "Güncelleme: $(date +'%Y-%m-%d %H:%M:%S')" && git push
