# 2026-11-20 — Soru-cevap taslakları Sonnet'e alındı

**Ne:** `trendyol_qna/qna_ai.py` artık `ai_asistan.blueprint.CLAUDE_MODEL` ("opus") yerine yerel
`QNA_CLAUDE_MODEL = "sonnet"` kullanıyor (kullanılmayan CLAUDE_MODEL importu kaldırıldı).
Kapsam: Trendyol + Shopify + Instagram DM/yorum taslakları ve Düzelttir (hepsi `_run_claude`'dan geçer).
Asistan (/ai-asistan + widget) ve ürün yükleme opus'ta kaldı.

**Neden:** Komutan: abonelik (Max 5x) limiti hızlı tükeniyor; Q&A her soru için otomatik ayrı Opus oturumu açıyordu.

**⚠️ Tespit:** Sunucu Claude Code CLI 2.1.119 (güncel 2.1.329). Takma adlar CLI sürümüne göre çözülüyor:
`opus` → claude-opus-4-7, `sonnet` → claude-sonnet-4-6 (5.5 değil). CLI güncellenince takma adlar yeni modellere geçer.
