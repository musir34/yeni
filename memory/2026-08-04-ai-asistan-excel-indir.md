# AI asistanı: cevaptan Excel indirme (2026-08-04)

## Sorun
Codex motorundan "excel tablosu ver" istendiğinde "veri analizi aracım yok" diyordu.
Sebep kurulum değil, YETKİ: Codex alt süreci salt-okunur kum havuzunda çalışıyor
(`ai_asistan/blueprint.py` — `sandbox_mode="read-only"`, `approval_policy="never"`)
ve `sql_kopru.py` başlığında yazdığı gibi shell/ağ yetkisi yok → dosya yazamaz.
Claude motorunda da tek izinli araç `mcp__gulludb__query` (blueprint.py:71).
Ayrıca modele beslenen sonuç 200 satır / 12.000 karakterle kırpılıyor.

## Çözüm (Excel'i asistan değil PANEL üretir)
- `AiMesaj.son_sql` (yeni nullable Text kolonu): Codex döngüsünde BAŞARIYLA çalışan
  son SELECT saklanır (`_codex_sql_dongusu`, hata/red dönen sorgular sayılmaz).
- Yeni endpoint `GET /ai-asistan/excel/<mesaj_id>`: sahiplik kontrolü → `sql_dogrula`
  (salt-okunur tek SELECT) → ai_readonly ile YENİDEN çalıştırılır → openpyxl ile
  .xlsx. Satır tavanı `AZAMI_EXCEL_SATIR = 50.000` (sohbetin 200 satır sınırı yok).
- `/durum` ve `/sohbet/<id>` cevaplarına `excel: bool(son_sql)` bayrağı; sayfa
  (`ai_asistan.html`) ve widget (`includes/ai_widget.html`) cevabın altına
  "Excel indir" butonu koyar (fetch + blob; hata JSON'u sohbete hata balonu olur).
- `CODEX_SQL_TALIMATI`'na "Excel istenirse yapamam deme" bölümü eklendi — model
  tüm sütunları içeren tek SELECT yazıp butonu tarif ediyor.
- Formül enjeksiyonu: '=' ile başlayan metin hücreleri `data_type='s'` ile metne
  sabitlendi; Decimal→float, jsonb/list→str (`_excel_deger`).

## Not / sınır
- Sorgu indirme ANINDA yeniden çalışır → veri o anki hâlini yansıtır (cevap
  anındaki değil). Kasıtlı: tam ve güncel veri.
- Claude motorunda SQL MCP içinde kaldığı için `son_sql` boş → buton çıkmaz.
  Excel isteyen Codex motorunu kullanmalı.

## Deploy
Kolon additive; prod'da alembic koşulmuyor:
`DISABLE_JOBS=1 /home/musir/gullupanel/venv/bin/python scripts/add_ai_mesaj_son_sql.py`
(idempotent) → sonra `git pull && systemctl restart gullupanel.service`.
Alembic kullananlar için: `migrations/versions/add_ai_mesaj_son_sql.py`.
