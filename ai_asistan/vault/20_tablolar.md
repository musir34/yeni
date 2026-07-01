# Veritabanı Tabloları (ipucu)

> Kesin tablo/kolon adlarını her zaman şemadan doğrula (information_schema veya \d).

- **Siparişler:** `orders`, `orders_picking`, arşiv tabloları
- **Stok:** stok/ledger tabloları (`stock_ledger.py` modeline bak)
- **Ürün/model:** ürün ve model maliyet tabloları
- **Kasa/kâr:** kasa ve profit ile ilgili tablolar

## Şema keşfi için örnek sorgular
- Tüm tablolar: `SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1;`
- Bir tablonun kolonları: `SELECT column_name, data_type FROM information_schema.columns WHERE table_name='orders';`
