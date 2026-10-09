# 2026-10-08 — Finans: Kredi Kartı hesabı + PDF ekstre yükleme + mutabakat

**Komutan emri:** "Kartı nasıl takip edeceğiz?" tartışması → aylık kart ekstresi yüklenerek; "mutabakata manuel
müdahale etme şansım olmalı". Örnek: İşbankası Maximum 5503 kartı PDF ekstreleri (Ocak–Eylül 2026, repo dışı).

**Ne kuruldu:**
- `kredi_karti` hesabı (ad "Kredi Kartı (5503)", sira 4) — `scripts/add_finans_kredi_karti.py` (INSERT … ON CONFLICT DO NOTHING).
  `finans_service`: HESAP_KODLARI/GIDER_HESAPLARI'na eklendi; `BORC_HESAPLARI=('kredi_karti',)` → eksi bakiye normal,
  "Emin misin?" sorulmaz. Yeni işlem türleri: `kart_sahsi` (−, raporlara girmez), `kart_iade` (+), `kart_duzeltme` (±).
- `finans_kart_parser.py` (saf): pypdf metni → satırlar (tarih/açıklama/tutar/taksit/puan; döviz satırında TL son tutar),
  önceki bakiye + hesap özeti borcu + kesim/son ödeme; `ic_tutarlilik_farki` (önceki + Σsatır − borç). Tür önerisi:
  negatif "HESAPTAN AKTARIM"→odeme_banka, negatif "ATMDEN ÖDEME"→odeme_elde, diğer negatif→iade, pozitif "NAKİT"→nakit
  (henüz gerçek ekstrede görülmedi), diğer→gider. Satıcı anahtarı: rakam/kod/ülke-şehir atılır, ilk 2 kelime (İ→I).
- `finans_kart.py`: `/finans/kart` (GET sayfa + POST PDF önizleme), `/finans/kart/kaydet`, `/finans/kart/duzelt`.
  Önizleme: hafıza (PlatformConfig 'finans_kart' torbası, satıcı→tür+kategori) + eşleştirme (aynı tutar, aynı yön,
  ±3 gün, açıklaması aynı olan öncelikli; bir kayıt bir satıra) → eşleşen "kayıtlı" tiksiz. Kaydet tek transaction:
  gider→kucuk_gider_ekle(kredi_karti), şahsi→kart_sahsi, iade→kart_iade, ödeme→transfer_yap(banka/elde→kart),
  nakit→transfer_yap(kart→elde); mükerrer (tutar+yön+açıklama ±3 gün) atlanır; hafıza öğrenir.
  Form `bakiye_onay=1` taşır (Banka ödeme satırlarında eksiye düşebilir; önizleme onayın kendisidir).
- Mutabakat: hedef = −ekstre borcu; sonrası = kart bakiyesi − seçili net; fark canlı (JS) + sunucuda. Manuel müdahale:
  tik/tür/kategori değiştirme, "elle satır ekle" (ek_* alanları), "farkı düzeltme kaydıyla kapat" (kart_duzeltme,
  sunucu farkı yeniden hesaplar), ve ekstreden bağımsız "Elle mutabakat düzeltmesi" formu (neden zorunlu).
  Aynı satıcıya tür/kategori yayma (JS) ilk ayın 100 satırını kolaylaştırır.
- Nav'a "Kredi Kartı" sekmesi; kart defteri /finans/defter/kredi_karti ile zaten çalışır.

**Gerçek ekstre doğrulaması:** Eylül 105 satır, Temmuz 64 satır → iç tutarlılık 0,00; Ağustos'ta PDF'in metninde
tutarı düşmüş 1 satır (255,97) → "okunamayan" uyarısı + elle satır ile kapatılır. Eylül önizlemesinde önceden girilmiş
250.000 ₺ cari ödeme "kayıtlı" eşleşti, fark 0,00. Testler: tests/test_finans_kart.py (11) — tüm finans 97/97.

**Deploy:** prod venv'de pypdf YOK (`requirements.txt` pypdf==5.1.0) → `venv/bin/pip install pypdf==5.1.0`;
`scripts/add_finans_kredi_karti.py` restart'tan önce; şema değişikliği yok (yeni tur değerleri String kolon).
