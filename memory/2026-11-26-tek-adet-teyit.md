# Tek Adet Teyit (2026-11-26, commit yok)

Neden: kayıtta 1 görünen ama rafta olmayan ürün satılıp "tedarik edilemedi" oluyordu.

- Kural `stock_sync/tek_adet_teyit.py`: central_stock.qty == 1 → teyitsizse platforma 0,
  teyitliyse max(0, 1 - rezerv) (tampon yok). Teyit geçerli ⇔ teyit_at >= central_stock.updated_at.
  Üretim Modu barkodları muaf. qty != 1 → eski formül.
- Uygulandığı yerler: stock_sync/service.py `_get_all_stocks` + `_get_stocks_by_barcodes`,
  shopify_stock_service `push_stock`, health_monitor `check_sync_staleness`.
- Sayfa `/tek-adet-teyit/` (tek_adet_teyit_routes.py, Ürünler & Stok menüsü, sayfa_yetki kodu
  `tek_adet_teyit`, HERKES). Var → stok_teyit kaydı; Yok → record_movement(manual_adjust, -1,
  source TEK_ADET_TEYIT).
- Yeni tablo `stok_teyit` (models.StokTeyit). Deploy: restart ÖNCESİ
  `cd yeni && DISABLE_JOBS=1 ../venv/bin/python scripts/create_stok_teyit_table.py`.
  Tablo yokken tüm tek adetler 0 gider (güvenli taraf).
