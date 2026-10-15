"""MNG Kargo (DHL eCommerce Türkiye) ApiZone istemcisi — giden gönderiler.

Köprü servis (sunucudaki dhl-kargo/server.js) yalnız İADE kodlarını üretir;
bu paket GİDEN gönderiler içindir: değişim, manuel sipariş ve Shopify siparişi
oluşturulduğu anda MNG'de gönderi açılır, barkod alınır, takip edilir.

Alt modüller:
  ayar.py   — .env'den kimlik/ortam (sandbox | prod)
  client.py — HTTP istemcisi (token, createOrder, createbarcode, durum, iptal, il/ilçe)
  durum.py  — MNG durum kodu → panel durumu (saf, DB'siz, test edilebilir)
  govde.py  — istek gövdeleri (saf fonksiyonlar, test edilebilir)
"""
