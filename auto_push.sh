#!/bin/bash

git add .
git commit -m "Otomatik güncelleme: $(date +'%Y-%m-%d %H:%M:%S')" || echo "Değişiklik yok, commit atlanıyor"
git push origin main || echo "Push başarısız!"
