# 2026-10-20 — Sipariş Hazırla: Telefon Eşlik (QR ile canlı ayna)

## Neden
Sipariş hazırla ekranı PC'de (yazıcı PC'ye bağlı); raf uzakta, çalışan raf kodunu ve ürünü
aklında tutarak gidiyor, karışıyor/unutuyor. Telefon PC ekranının canlı aynası + kablosuz
okuyucusu olsun istendi; ekran paylaşımı gibi dinamik, QR ile eşleşme, 10 dk hareketsizlikte
otomatik kopma, worker yalnız kendi hesabına, yönetim herkese bağlanabilsin.

## Ne değişti
- `models.py`: `HazirlaEslesme` (hazirla_eslesme: token, pc/telefon user, durum
  bekliyor|bagli|kapandi|suresi_doldu, aktif_payload JSON, surum, son_islem_at,
  pc_son_gorulme_at) + `HazirlaOkutma` (hazirla_okutma: telefondan gelen raf/urun olayı,
  kalem/adet sırası, islendi_at). Additive; `scripts/add_hazirla_telefon.py` RESTART ÖNCESİ.
- `hazirla_telefon.py` (blueprint `/hazirla-telefon`): `/pc/baslat` (QR, jeton tek kullanımlık
  120 sn), `/pc/senkron` (PC görüntüyü yazar, değişince sürüm artar; telefon okutmalarını çeker,
  islendi damgalar), `/pc/kes`; `/bagla` (kural `baglanabilir_mi`: aynı hesap → her rol,
  farklı hesap → admin/manager/sahip), `/telefon/senkron`, `/telefon/okut`, `/telefon/kes`.
  Zaman aşımı her istekte sunucuda: hareketsizlik 600 sn → suresi_doldu; PC 60 sn sormazsa
  → kapandi(pc_kapandi); QR 120 sn → kapandi(qr_suresi). Giriş+2FA kalkanı, POST yalnız
  `X-Requested-With: fetch`, sahiplik denetimi (PC rotaları pc_user, telefon rotaları telefon_user).
- `templates/hazirla_telefon.html` + `static/js/hazirla-telefon.js`: telefon sayfası. QR
  kamera (html5-qrcode cdnjs) veya Zebra kutusu; bağlanınca PC'nin kartları tam boy (görsel,
  sku, barkod, adet, raf çipleri, raf+kutu okutma alanları). ~1 sn senkron; yapı değişince kart
  yeniden, yoksa yalnız durum (odak kaybolmaz). Okutma Enter/Tab ile → olay; PC doğrulayınca
  yeşil (📱/🖥️ kaynağı), yanlışsa kırmızı. Kamera ile barkod okutma düğmesi. sessionStorage ile
  yenilemede devam. Kapandı kaplaması (sebep metni) + Yeniden Bağlan.
- `static/js/hazirla-telefon-pc.js` + `siparis_hazirla.html`: üst çubukta "📱 Telefon" düğmesi
  + rozet (Bağlı değil / QR bekleniyor / 📱 ad · kalan süre), QR penceresi (Bootstrap modal:
  QR, kod, adres, Yeni QR, Bağlantıyı Kes). Görüntü DOM'dan okunur (kartlar, .raf-kodu-input,
  .barkod-input dataset.confirmed) ve yalnız değişince gönderilir. Telefondan gelen okutma
  GERÇEK kutuya yazılır + input/Enter olayı tetiklenir → mevcut raf doğrulama ve
  /confirm_packing akışı değişmedi (karma okutma: telefonda raf, PC'de ürün vb.). Kutuya
  `.tel-okutma` mavi çerçeve. Eşleşme sessionStorage'da: sıralı mod geçişi/yenileme koparmaz.
  Sipariş İşlemleri menüsüne "Telefon Eşlik (telefonda aç)" bağlantısı.
- `sayfa_yetki.py`: `hazirla_telefon` kataloğa (ebeveyn siparis_hazirla, menude=False) →
  sipariş hazırlaya giren herkes sayfaya girer; KİME bağlanacağı eşleşme kuralı.
- `routes/__init__.py`: blueprint kaydı. `tests/test_hazirla_telefon.py` (15 test, izole sqlite).

## Cihaz anahtarı (aynı gün ek)
Komutan: "QR yalnız okuyan ve okutulan cihazları etkilesin." Hesap bazlı denetim aynı hesabın
başka sekmesine/telefonuna açıktı → `pc_anahtar` (QR üretilirken PC'ye) ve `telefon_anahtar`
(QR okutulurken telefona) rastgele 24 bayt; her istek hesap + anahtar (compare_digest) ister,
yeni QR'ın eski oturumu kapatması da anahtar ister. Anahtar sessionStorage'da (sekmeye özel).

## Tuzaklar
- Testte app context'i test boyunca açık tutma: test_client istekleri paylaşır, flask-login
  current_user'ı g'de önbellekler (ilk isteğin kullanıcısı sonrakilere sızar).
- Telefon kamerası HTTPS ister; Zebra klavye modunda sorun yok. QR adresi ters vekil arkasında
  X-Forwarded-Proto ile https'e çevrilir.
- PC görüntüsü DOM'a bağlı: siparis_hazirla.html'de kart/kutu sınıfları (.product-card,
  .raf-kodu-input, .barkod-input, #productBarcode-N, .raf-bilgi-list) değişirse PC JS güncellenmeli.

## Deploy
pip değişikliği yok. `cd yeni && DISABLE_JOBS=1 ../venv/bin/python scripts/add_hazirla_telefon.py`
→ `git pull && systemctl restart gullupanel.service`.

## 2026-10-21 — Telefon klavyesi kendi kendine açılmasın
- Sorun: telefonda her güncellemede (`odakla`) ve her gönderimden sonra sıradaki alana otomatik
  focus veriliyordu → klavye sürekli açılıp ekranı bozuyordu; kapatınca yine açılıyordu.
- Çözüm (`static/js/hazirla-telefon.js`, `templates/hazirla_telefon.html`):
  - `odakla()` artık focus vermez, yalnız aktif kartı vurgular.
  - Sağ altta yuvarlak **⌨️** düğmesi (`#klavyeBtn`): basılınca sıradaki boş alana odaklanır
    (dokunma içinde eşzamanlı focus → klavye açılır). Okutulacak alan kalmayınca gizlenir.
  - Enter/Tab ile gönderimde (klavye zaten açık ya da Zebra okuyucu soneki) sıradaki alana geçilir;
    ➤ düğmesi / alandan çıkışla gönderimde geçilmez (`okut(a, ileri)`).
  - Script sürümü `?v=4`.
