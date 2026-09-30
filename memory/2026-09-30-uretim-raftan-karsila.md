# Üretim siparişi: sonradan rafa giren stok (Raftan Karşıla) + kargo düşüm koruması

Tarih: 2026-09-30 · Durum: yerelde, 19 test geçti, commit/deploy bekliyor · Şema değişikliği yok

## Neden
Canlı vaka 11657096149 (095-39 Lacivert): sipariş üretimdeyken aynı üründen iade rafa girdi (L-B-01).
Personel ürünü üretim ekranında doğrulama okutmasıyla (stok DÜŞMEDEN) paketleyip etiketi bastı; sonra
"Üretildi" denince terfi muafiyeti kalktı, sistem rafta stok görüp siparişi tekrar Hazırlanıyor'a aldı.

## Ne değişti
1. `promotion_service.py` — üretim kaydı olan sipariş "Üretildi" sonrası da otomatik terfi etmez
   (muafiyet artık `uretildi=False` değil, kaydın varlığı). Sipariş üretim ekranından yürür.
2. `uretim_routes.raftan_karsila` (`/uretim/api/raftan-karsila/<id>`) — üretilecek kalem, ürün + raf
   okutmasıyla raftan karşılanır: kalem kayıt `details`'inden çıkar (artık "raftan"), düşümü mevcut
   `raf_okut` yapar (aynı pick anahtarı), düşüm başarısızsa `details` geri yüklenir. Üretimden doğrulanmış
   kalem ve `uretildi` kayıt reddedilir. Üretilecek kalem kalmazsa kayıt `uretildi=True` olur.
   Bildirim: `uretim_modu.raftan_karsilandi_bildir` → `uretim_iptal` abonelerine mail + WhatsApp
   ("ÜRETMEYİN"); mail başlığı için `mail_service` EVENT_TITLES/COLORS'a `uretim_raftan` eklendi
   (abonelik olayı DEĞİL).
3. `stock_ledger.apply_lifecycle_effect` — üretim kaydı olan sipariş kargolanırken (ship_out)
   `uretim_modu.kargoda_raftan_dusulmeyecekler` kalemleri atlanır: üretimden gelen kalem (rafa hiç
   girmedi) + üretim ekranında rafı okutulmuş kalem (zaten düşüldü; önceden ÇİFT düşüyordu).
   Üretim kaydı olmayan siparişte davranış aynı.
4. `uretim_routes._hareket_logla` — Üretime Al / Üretildi / Paketlendi / Raftan Karşıla kullanıcı
   hareketlerine yazılır (önceden kimin bastığı bulunamıyordu).
5. `templates/uretim.html` — üretilecek kalemde rafta stok varsa "Rafta stok var" rozeti + "Raftan
   Karşıla" okutma kutusu (yalnız hiç doğrulanmamış kalem ve üretildi olmayan kayıt).

## Bilinen sınırlar
- Personel raftaki ürünü yine doğrulama kutusundan okutabilir (sistem ürünün nereden geldiğini bilemez);
  rozet ve kutu metni yönlendirir, engellemez.
- Otomatik çevirme yok (bilinçli): karar ürünü elinde tutan kişide.
- Terfi muafiyeti ve şablon (JS) test edilmedi; terfi async + Trendyol API'li.
- Üretim siparişi artık Trendyol'a "Picking" bildirmez (stoksuz üretim siparişlerinde zaten böyleydi).
- İptal iadesi (Picking→Cancelled cancel_return) üretim kalemini ayırt etmez — incelenmedi.
