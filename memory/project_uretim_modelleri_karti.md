# Anasayfa "Üretim Modelleri: Sipariş ve Fiyat" kartı (2026-10-14)

**Ne değişti**
- Yeni modül `uretim_gorevi.py` (eritme_gorevi.py deseninin üretim modu eşleniği):
  üretim modundaki her model için son 30 günde (kayan pencere, takvim ayı değil)
  gelen üretim siparişi sayısı, çift, son sipariş fiyatı, adet ağırlıklı ortalama
  fiyat, son sipariş tarihi ve canlı merkezi stok.
- `home.py`: `uretim=uretim_ozeti()` şablona geçer. `templates/home.html`: eritme
  kartının altına yeni kart (4 özet kutusu + yapışkan başlıklı, kaydırmalı tablo,
  sipariş çubuğu, son fiyat − ortalama farkı yeşil/kırmızı rozet, gece modu).

**Veri kaynağı ve tuzaklar**
- Model listesi: `uretim_modu.get_uretim_models()` (PlatformConfig 'uretim_ayar').
- Sipariş sayısı: `uretim_siparis` (order_date naive UTC → kesim `utcnow()-30g`).
- Fiyat: 7 sipariş tablosunun `details` JSON'undaki `unit_price` (Trendyol indirim
  sonrası satır fiyatı). `orders_archived` için tam entity ÇEKİLMEZ, `with_entities`.
- Site (SH-) ve değişim (DG-) kayıtları sayıma girer, fiyata girmez (sipariş
  tablolarında yok).
- Barkod eşleşmezse `normalize_barcode` ile alias çözülür (barkod başına bir kez,
  DB'ye gider); `_hesapla` saf tutuldu, normalize dışarıdan enjekte edilir.
- Sonuç 5 dk süreç içi önbellekte (`_ONBELLEK`); hata → son geçerli veri / None,
  anasayfa düşmez. Üretim modunda model yoksa kart basılmaz.

**Doğrulama:** saf hesap + şablon render testi scratchpad'de koşturuldu (DB'siz,
HESAP_OK / SABLON_OK). Canlı veriyle görsel kontrol deploy sonrası.

**Durum:** yerelde, commit/deploy bekliyor. Deploy: `git pull && systemctl restart gullupanel.service`
(şema değişikliği yok).

**İnceleme (code-reviewer, 2026-10-14):** kritik yok. Düzeltildi: alias barkodlu siparişte fiyat kaçırma (tek barkodlu siparişte `(order_number, "*")` geri düşüşü) ve özet kutusunda "— ₺". Bilinçli bırakıldı: kısmi sonuç 5 dk önbelleklenir, kilit yok (eritme kartında önbellek bile yok); raftan karşılanan kalemler üretim sayısına girmez (kart "üretim siparişi" der, doğru).
