# 2026-09-23 — Finans Kasası (üç hesaplı yeni kasa, /finans)

**Ne:** Mevcut kasaya (kasa.py, /kasa, AnaKasa/Kasa/KasaKategori) DOKUNMADAN sıfırdan
yeni bir kasa: `finans.py` (blueprint `finans`, url_prefix `/finans`) + `finans_service.py`
(iş kuralları) + 5 yeni tablo (`finans_hesap`, `finans_kategori`, `finans_gider_adi`,
`finans_ana_gider_kalem`, `finans_islem`) + 9 şablon (`templates/finans_*.html`, `_finans_*.html`).
Menü: Finans grubunda "Finans" (admin), eski "Kasa" linki duruyor.

**Neden:** Kullanıcı üç bakiye (Beyazıt / Elde / Banka), kendi tanımladığı kategoriler ve
iki tür gider (tek seferlik küçük gider + aylık tekrar eden ana gider) istedi.

**Kurallar (sunucu tarafında zorlanır):**
- Gelir → yalnızca Beyazıt. Gider → yalnızca Elde/Banka (Beyazıt'tan gider yasak).
- Transfer hesaplar arası serbest; iki bacak `transfer_grup` UUID ile bağlı.
- Bakiyenin tek kaynağı `finans_hesap.bakiye` (FOR UPDATE). `finans_islem` satırı silinmez,
  `iptal=true` + ters delta. Düzeltme = eski iptal + yeni kayıt. Negatif bakiye hiçbir yolla oluşmaz.
- Ana gider: kalem (ad, aylık tutar, dönem aralığı) → her ay "Öde" (partial unique index:
  aynı kalem aynı ay iki kez ödenemez; iptal edilince tekrar ödenebilir).
- Kullanımda olan kategori/gider adı silinmez, pasife alınır; aynı adla eklenince yeniden aktif.
- Tutarlılık: `bakiye == SUM(yon*tutar) WHERE iptal=false` — rapor sayfası her açılışta kontrol eder.

**Deploy:** `git pull && DISABLE_JOBS=1 venv/bin/python scripts/create_finans_tables.py && systemctl restart gullupanel.service`
(script additive + idempotent; 3 hesabı seed eder).

## Ek (aynı gün): Cari Hesaplar (/finans/cari)
**Ne:** Tedarikçi/müşteri cari defteri: `finans_cari`, `finans_cari_hareket`, `finans_cari_kalem`
(scripts/create_finans_cari_tables.py, additive). Kod: `finans_cari_service.py` + `finans_cari.py`
(aynı `finans_bp`, finans.py sonunda import). Şablon: finans_cari.html, finans_cari_detay.html.
**Neden:** "Her mal geldiğinde ne aldığımızı giriyorum, hesapları tutabileyim" — kalem dökümlü borç takibi.
**Kurallar:** bakiye = bizim borcumuz (+ borç / − alacak). Mal girişi & satış kalemli, kasaya dokunmaz.
Ödeme → Elde/Banka'dan `cari_odeme` gideri + borç ↓; Tahsilat → Beyazıt'a `cari_tahsilat` + alacak ↓;
ikisi tek transaction, `islem_id` bağı. İptal iki yönden de iki tarafı geri alır. Bakiyeli hesap kapatılamaz.
Rapor/panel'de cari ödeme & tahsilat ayrı kolon.
**Deploy:** `DISABLE_JOBS=1 ../venv/bin/python scripts/create_finans_cari_tables.py` + restart.
