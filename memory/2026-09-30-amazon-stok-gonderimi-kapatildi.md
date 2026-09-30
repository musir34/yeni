# 2026-09-30 — Amazon stok gönderimi kapatıldı

**Neden:** Komutan emri: Amazon'da satış istenmiyor. Stoklar bir kez 0 gönderilecek, sonra gönderim duracak.

**Değişen:**
- `stock_sync/service.py`: `DISABLED_PLATFORMS = {"amazon"}` eklendi.
  - `sync_platform` başında kalkan → otomatik, manuel düğme, barkod bazlı, arka plan: hiçbir yoldan Amazon'a stok gitmez.
  - `get_configured_platforms` Amazon'u listelemez ("tümüne gönder" atlar).
  - `auto_sync_platforms_except_idefix`: `platforms_to_sync` listesinden amazon çıkarıldı (3 dk'lık job).
- `scripts/amazon_stok_sifirla.py` (yeni): `products.amazon_sku` dolu 692 ürüne 0 gönderir. Varsayılan kuru çalıştırma, `--gonder` ile gerçek. Panel DB'sine yazmaz.

**Sıra önemli:** önce deploy (pull + restart), SONRA betik. Eski kod çalışırken 0 gönderilirse 3 dk'lık senkron gerçek stoğu geri yazar.

**Dokunulmayan:** Amazon sipariş/ürün/eşleştirme sayfaları, adapter, `amazon_asin/amazon_sku` kolonları. Geri açmak için `DISABLED_PLATFORMS`'tan çıkar + listeye geri ekle.

**Durum:** yerelde; kuru çalıştırma doğrulandı (692 SKU). Commit/deploy yok, gerçek 0 gönderimi henüz yapılmadı.

## Güncelleme (aynı gün): 0 gönderimi BAŞARISIZ — LWA client secret süresi dolmuş

- Betik sunucuda çalıştırıldı: 692/692 HTTP 403. Amazon yanıtı: "The LWA secret token you provided has expired."
- Salt-okunur çağrılar (sellers, listings GET, orders) da aynı 403 → sorun izin/rol değil, `AMAZON_LWA_CLIENT_SECRET` eskimiş.
- `sync_sessions` kanıtı: Amazon'a son başarılı gönderim 2026-06-22. Temmuz–Eylül arası her oturum %100 hatalı (ayda ~3,2 milyon hata), kimse fark etmemiş.
- Yani Amazon'daki stok 22 Haziran'daki değerlerde donuk: o son oturumda 605 ürün, 455'i stoklu, toplam 4748 adet gönderilmişti.
- Çözüm: Seller Central > Develop Apps > LWA credentials'tan yeni secret üret → sunucu `.env` `AMAZON_LWA_CLIENT_SECRET` güncelle → betiği `--gonder` ile tekrar çalıştır. Hızlı önlem: Seller Central tatil modu / listelemeleri kapatma (API gerektirmez).
