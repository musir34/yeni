---
name: project-ai-asistan-coklu-sohbet
description: "AI asistanı v2 — çoklu sohbet (yeni sohbet + geçmiş listesi), asenkron cevap (gunicorn 502 fixi), --resume bağlamı, opus; migration + deploy bekliyor"
metadata:
  type: project
---

AI asistanı büyük revizyon (2026-07-10). [[project-ai-asistan]] üzerine.

**Ne değişti:**
- **Çoklu sohbet:** JSON dosya (`gecmis/<uid>.json`) yerine `ai_sohbet` + `ai_mesaj` tabloları
  (models.py sonunda; migration: `migrations/versions/add_ai_sohbet.py`, additive, down_revision=None).
  Eski JSON ilk `/sohbetler` çağrısında "Eski sohbet" olarak DB'ye taşınır (dosya → `.json.imported`).
- **Asenkron cevap:** "Sunucu hatası"nın kök nedeni senkron 90 sn'lik `subprocess.run`
  (gunicorn default 30 sn worker timeout → 502) idi. `/sor` artık mesajı `bekliyor` yazıp
  Claude'u daemon thread'de başlatır, anında döner; frontend 2 sn'de bir `/durum/<mesaj_id>` yoklar.
  Timeout 240 sn'ye çıktı. Worker restart'ında takılı kalan `bekliyor` mesajları
  `_bayat_bekleyenleri_isaretle` ile timeout+60 sn sonra `hata`ya düşer (kilit açılır).
- **Bağlam kalitesi:** geçmişi prompta metin yapıştırma kaldırıldı; sohbet başına
  `claude_session_id` saklanır, `--resume` ile gerçek oturum devam eder. Resume başarısız
  olursa taze oturumla otomatik tek retry. Model: `opus` (kullanıcı premium kalite istedi).
- **UI:** widget + /ai-asistan sayfasında ➕ yeni sohbet, 🕘 geçmiş listesi (tıkla-devam-et, sil),
  çöp = aktif sohbeti sil. Aktif sohbet/bekleyen mesaj localStorage'da (widget `aiw_*`, sayfa `aip_*`);
  sayfa yenilense de polling kaldığı yerden sürer. Eski `/gecmis` ve `/temizle` endpoint'leri kaldırıldı
  (tek tüketicileri bu iki şablondu).
- Kullanıcı başına aynı anda TEK bekleyen soru (429) — Claude süreçleri yığılmasın.

**Test:** scratchpad'de 9 senaryoluk smoke test (sahte Claude, dosya-sqlite) 3/3 geçti.
In-memory sqlite'ta flaky (tek bağlantı paylaşımı artefaktı) — Postgres'te geçerli değil.

**Deploy (kullanıcıda):** `git pull` → migration çalıştır (alembic `add_ai_sohbet`,
diğer additive migration'lar nasıl koşulduysa aynı yol) → `systemctl restart gullupanel.service`.
Spec: `docs/superpowers/specs/2026-07-10-ai-asistan-coklu-sohbet-design.md`.
