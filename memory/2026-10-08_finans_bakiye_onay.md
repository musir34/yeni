# 2026-10-08 — Finans: "Yetersiz bakiye" sert hata yerine "Emin misin?" onayı

**Komutan emri:** Finans bölümünde "Yetersiz bakiye: Banka Hesabı hesabında 3492.96 ₺ var, 3600.00 ₺ çıkılamaz."
gibi engelleyici hatalar istenmiyor; yalnız "emin misin?" diye sorulsun, onaylanınca işlem yapılsın.

**Ne değişti:**
- `finans_service.py`: `YetersizBakiye(FinansHata)` alt sınıfı + `bakiye_asimi_onayli()` (istek formu/JSON'unda
  `bakiye_onay=1` var mı; istek bağlamı yoksa False). `_hareket` ve `islem_iptal` eksiye düşerken onay yoksa
  YetersizBakiye fırlatır, onay varsa devam eder ve **bakiye eksiye düşer** (servis imzaları değişmedi).
- `finans.py`: `_hata_flash(e)` — YetersizBakiye'de orijinal formu (`request.form.lists()`) ve yolu session'a
  (`finans_bakiye_onay`) koyar, 'bakiye_onay' kategorisiyle flash'lar; diğer hatalar eskisi gibi 'danger'.
  finans.py/finans_cari.py/finans_calisan.py'deki tüm `flash(str(e),'danger')` → `_hata_flash(e)` (26 yer).
- `_finans_nav.html`: 'bakiye_onay' flash'ı sarı "⚠️ Emin misiniz?" kutusu; gizli alanlarla aynı forma
  `bakiye_onay=1` ekleyip "Evet, eminim — yine de kaydet" ile yeniden POST eder; "Vazgeç" kapatır.
- Kapsam: Finans kasası (/finans). Eski /kasa modülü ve finans_excel (gelir, bakiye düşmez) dokunulmadı.

**Tuzak:** `_hata_flash` içindeki `flash(str(e),'danger')` toplu değiştirmede kendine dönüşüp özyineleme
oldu, elle geri alındı. Testler: tests/test_finans_bakiye_onay.py (4) — tüm finans testleri 74/74
(`DISABLE_JOBS=1 .venv/bin/python -m unittest discover -s tests -p "test_finans_*.py"`). Şema yok; deploy bekliyor.
