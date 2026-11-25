---
name: uretim-arama
description: /uretim sayfasına sekmeden bağımsız sipariş araması (sipariş no / müşteri adı-soyadı / kargo kodu) + sonuçta üretim sekmesi ve pazaryeri statüsü (2026-11-25)
metadata:
  type: project
---

Ne değişti:
- `uretim_routes.py` yeni `GET /uretim/api/ara?q=` (en az 2 karakter, ilk 50 sonuç). Tüm
  `uretim_siparis` kayıtlarında arar (arşivlenen/kargolanan/iptal dahil). Kargo kodu ve soyad
  üretim kaydında yok → sipariş tablolarından alt sorguyla: orders_* `cargo_tracking_number`,
  panel `archive.shipping_barcode`, değişimde `degisim.kargo_kodu` (DG-<no>). Sipariş listesi
  araması (commit b1330e1) ile aynı kolonlar.
- Sonuç: `sekme` (liste() ile aynı kurallar: iptal → sekmede yok; üretilmemiş + elle arşiv →
  sekmede yok; teslim/arşiv → Teslim; Shipped/Değişim Kargoya Verildi → Kargoya Verilen;
  paketlendi → Paketlenen; yoksa Üretilen/Üretiliyor/Bekleyen) + `pazaryeri_statu` (ilk
  bulunan tablo etiketi + ham status, ör. "Kargoda (Shipped)", "Panel arşivi (Picking)").
- `templates/uretim.html`: sekmelerin üstünde arama kutusu + sonuç paneli, "Sekmeye git"
  mevcut sekme düğmesini tıklatır. Liste/sıralama davranışı değişmedi.

Sınır: Shopify (SH-) siparişinin MNG takip noyla araması yok (site siparişi DB'ye inmez);
SH- kayıtları no ve müşteri adıyla bulunur.

Neden: Komutan, siparişin hangi sekmede/aşamada olduğunu tek tek sekme gezmeden bulmak istedi.
