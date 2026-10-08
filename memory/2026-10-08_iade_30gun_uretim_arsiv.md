# 2026-10-08 — Site iadeleri 30 gün + Üretim Paketlenen "Arşivle"

## 1) Site iadeleri: 30 günü geçen "bekliyor" iadeler listeden düşer
- Veri panelde değil, repo dışı köprü serviste (`/home/musir/shopify-uygulamalari/dhl-kargo/iadeler.json`, server.js).
  Köprüye dokunmadan **panel tarafında** (`iade_yonetimi.eski_bekleyenleri_ele`) elendi: kategori `bekliyor` ve
  `createdAt` 30 günden eskiyse listeden ve sayaçtan düşer; `toplam` yeniden hesaplanır. Tarihi okunamayan kayıt elenmez.
- Kayıt silinmez: müşteri geç de olsa kodu kullanıp kargoya verirse DHL senkronu `kargoda`ya çeker, yeniden görünür.
- Sabit: `BEKLEYEN_IADE_OMRU_GUN = 30`. Testler: tests/test_iade_yonetimi.py (+2; `test_real_panel_routes_require_login`
  conftest fixture'ı ister, --noconftest ile ERROR vermesi normal/eski).

## 2) Üretim: Paketlenen sekmesine "Arşivle" düğmesi
- Neden takılıyordu: kargo tespiti orders_shipped/delivered/archived'a bakar; site siparişi (SH-) bu tablolara hiç inmez,
  bazı eski kayıtların da izi yok → Paketlenen'de sonsuza dek bekler.
- `uretim_siparis.arsivlendi_at` (additive, nullable) — **migration: `scripts/add_uretim_arsiv.py` RESTART'TAN ÖNCE
  çalıştırılmalı**, yoksa /uretim listesi kolon hatası verir (liste sorgusu `arsivlendi_at IS NULL` filtreler).
- `POST /uretim/api/arsivle/<id>` ({geri_al}) — diğer durum rotalarıyla aynı desen (fetch başlığı CSRF, _hareket_logla).
- Arşivlenen kayıt aktif 4 sekmeden düşer, **Teslim** sekmesinde "Arşivlendi: tarih" rozetiyle durur, oradan geri alınır.
- Test: tests/test_uretim_arsiv.py (sqlite, 4 test; db.create_all mükerrer indeks yüzünden çöker → yalnız gerekli tablolar).
