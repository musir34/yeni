# 2026-11-20 — Codex hazır model listesi güncellendi

**Ne:** `ai_asistan/motor_ayar.py` `CODEX_HAZIR_MODELLER` eski listesi (gpt-5.2, gpt-5.1-codex-max/mini)
yerine sunucudaki ChatGPT hesabında çalıştığı doğrulanan modeller:
gpt-6.1-terra, gpt-6.1-sol, gpt-6-astra, gpt-6-sol, gpt-6-luna, gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna.

**Neden:** gpt-5.2 "not supported when using Codex with a ChatGPT account" (400) veriyordu; asistan + Q&A düşüyordu.
Bu tek liste /ai-asistan, sağ alt AI widget'ı ve /soru-cevap model seçicisini besler.

**Nasıl seçildi:** sunucu `~/.codex/models_cache.json` (hesaba göre) + her model `codex exec -m <model>` ile denendi.
gpt-6.2-sol / gpt-6.2-astra listede görünse de hesapta 400 verdi → alınmadı.

**Dokunulmadı:** `templates/urun_yukleme.html` MODEL_ONERILERI (ayrı, serbest metin öneri listesi).
