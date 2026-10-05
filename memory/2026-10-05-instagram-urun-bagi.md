# Instagram yorumlarında AI ürün tespiti + fiyat/bağlantı (2026-10-05, yerelde, commit/deploy yok)

Komutan isteği: "fiyat nedir" gibi yorumlarda yapay zekâ ürünü tespit edip fiyatı ve bağlantıyı hazırlasın;
gönderimi kendisi onaylayacak ("ben onaylarım, o düzgün hazırlasın yeter").

- Sorun: yorum ürünü söylemez, gönderi açıklaması da model kodu içermez. Çözüm: GÖNDERİ bir kez site
  ürününe + rengine bağlanır (`InstagramMediaProduct`, tablo `instagram_media_products`, additive).
- `trendyol_qna/instagram_urun.py` (yeni): Shopify'dan `urun_ara`, `urun_getir`, `katalog` (176 aktif ürün,
  10 dk bellek); `bagla` / `bagi_kaldir`; `urun_baglami` (taslak istemine canlı fiyat + stoktaki numaralar +
  ürün sayfası); `oner` (AI, gönderi açıklaması + katalogdan ürün/renk seçer, ONAYSIZ kaydeder).
- Fiyat kaynağı: SİTE (Shopify varyant fiyatı), bağlantı gullushoes.com ürün sayfası. Shopify'da varyant başlığı
  "Renk / Beden"; aynı üründe renkler farklı fiyatlı olabiliyor → bağ renk de taşır ('' = tüm renkler).
- Kural: onaysız AI önerisi taslağa fiyat olarak GİRMEZ; istem "fiyat/bağlantı yazma, netleştir" der.
  Kullanıcının onayladığı bağ sonraki AI önerisiyle ezilmez.
- Akış: yeni yorum düşen gönderi bağsızsa AI öneri üretir (gönderi başına süreçte tek deneme); kartta
  "AI önerisi … [Doğru, onayla]". Onaylanınca o gönderinin bekleyen yorumlarının taslakları (en çok 15)
  yeniden üretilir; sonraki yeni yorumlara taslak kendiliğinden gelir.
- `qna_routes.py`: `/soru-cevap/api/instagram-yorum/urun-ara` (GET), `/urun-bagla` (POST; `kaldir` ile siler).
- `soru_cevap.html`: karta ürün şeridi (bağsız / AI önerisi / onaylı) + ürün arama paneli.
- Doğrulama: 36 test (yalıtılmış), ürün arama + katalog gerçek Shopify verisiyle salt-okunur denendi, kart
  üç haliyle önizlemede görüldü. AI önerisinin isabeti ve taslak kalitesi CANLIDA DENENMEDİ.
- Kapsam dışı: DM'lerde ürün tespiti (düz "fiyat?" mesajında AI hâlâ hangi ürün olduğunu sorar).
