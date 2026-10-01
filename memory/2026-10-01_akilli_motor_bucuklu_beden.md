# 2026-10-01 — Akıllı motor: buçuklu beden ("39,5") çökmesi

**Hata:** `akilli_motor_moduller._extract_color_from_tariff` tarife BEDEN hücresini
`str(int(beden))` ile çeviriyordu; Trendyol komisyon tarifesinde "39,5" (metin) /
39.5 (sayı) gelince `ValueError: invalid literal for int()` → analiz tamamlanmıyordu.

**Değişiklik (yalnız akilli_motor_moduller.py):**
- `_beden_to_str(beden)` eklendi: 36/36.0/"36" → "36", 39.5/"39,5"/"39.5" → "39,5",
  NaN/None/boş → "", sayı olmayan değer olduğu gibi döner.
- Renk çıkarımı buçuklu bedende SKU'daki "39,5" ve "39.5" yazımlarının ikisini de dener.
- Tam sayı bedenlerde davranış değişmedi (mevcut testler aynen geçiyor).
- Test: tests/test_akilli_motor.py::test_extract_color_from_tariff_bucuklu_beden

**Deploy:** `git pull && systemctl restart gullupanel.service`
