---
name: project-trendyol-qna-taslak-revizyon
description: "Q&A AI taslakları opus'a geçti + panele 'düzeltme talimatı' alanı (Düzelttir) eklendi — mevcut taslak + talimatla revizyon"
metadata:
  type: project
---

Trendyol Soru-Cevap taslak kalitesi revizyonu (2026-07-10). [[project-trendyol-qna]] üzerine.

**Belirti:** Kullanıcı taslak kalitesini yetersiz buldu ve yanlış yazan taslağı
AI'a "şunu düzelt" diyebileceği bir alan yoktu (elle düzeltmek zorundaydı).

**Ne değişti:**
- `qna_ai.py`: `_run_claude`'a `--model CLAUDE_MODEL` eklendi (ai_asistan.blueprint'ten
  import, "opus") — önceden model belirtilmiyordu, sunucu varsayılanıyla üretiyordu.
- `generate_draft`/`generate_drafts_async`/`_draft_prompt` artık opsiyonel
  `talimat` + `mevcut_metin` alıyor; talimat varsa prompt "mevcut taslağı bu
  talimata göre düzelt, dokunmadığı kısımları koru" şeklinde kurulur.
- `qna_routes.py` `/api/taslak/<qid>`: JSON gövdeden `talimat` (max 500) ve
  `metin` (max 2000, panelde o an görünen/elle düzenlenen metin) okur.
- `soru_cevap.html`: cevap kutusunun altına talimat input'u + "Düzelttir" butonu
  (Enter da tetikler); mevcut tetikle-yokla akışı aynen kullanılır, DB değişikliği YOK.

**Deploy:** `git pull && systemctl restart gullupanel.service` (migration yok).
