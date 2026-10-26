# 2026-10-26 — Üretim Siparişleri: Otomatik Gönderim kartı sipariş hazırla ile eşitlendi

## Şikâyet
Komutan: "üretim siparişleri ekranında otomatik gönderim doğru gönderilmiyor; sipariş hazırla
ekranında nasıl gönderiliyorsa orada da öyle gitmeli."

## Teşhis (karşılaştırma)
- Sipariş Hazırla (`templates/siparis_hazirla.html` showAutoShip): barkodlar doğrulanınca ekran
  ORTASINDA büyük "Otomatik Gönderim Aktif" kartı (400-500px, mor gradyan, kod 1.5rem) 3 sn
  gösterilir + panoya kopyalanır + Sipariş Takip izi; ayrıca onaylama süresi sonunda
  confirm_packing (Created→Picking) kendiliğinden çalışır.
- Üretim (`templates/uretim.html` urKargoOtomatik): kopyalama + Sipariş Takip izi aynıydı, ama
  kod sağ-altta KÜÇÜK yeşil bildirimde (.85rem) gösteriliyordu; Paketlendi ayrı düğme.

## Karar (Komutan seçimi: "Yalnız görünüm")
Statü/paketleme akışına dokunulmadı. Yalnız kart görünümü sipariş hazırladaki ile birebir
yapıldı: `.ur-autoship` → ekran ortası koyu zemin, `.ur-autoship-card` mor gradyan + shine
animasyonu, `.ur-autoship-head` başlık + "Kargo kodu: X", `.ur-autoship-kod` büyük kod;
mobil (≤680px) ölçüleri de sipariş hazırladaki gibi. JS: `urAutoShipKodUst` ek span dolduruldu,
3 sn gizleme süresi aynı.

Seçilmeyen seçenekler (ileride istenirse): Otomatik Gönderim tıklanınca otomatik "Paketlendi"
işareti; Trendyol siparişini panelde Created→Picking taşıma (ledger/senkrona dokunur).

## Deploy
Şema yok. `git pull && systemctl restart gullupanel.service`.

## Ek (aynı gün) — Ürün Özellikleri: kopyala / yapıştır / onay uyarıları
Şikâyet: barkod kopyala → uyarı, yapıştır+Enter → uyarı, Doğrula → uyarı; hepsi kapatılmak zorunda.
Kök neden: `uretim.html` `gs-dialog.js`'i yüklemiyordu; sayfadaki `toast()` `window.gsToast` yoksa
`alert()`'e düşüyor → her bildirim tarayıcı kutusu (sipariş hazırla/product_list kütüphaneyi yüklüyor).
Düzeltme (yalnız `templates/uretim.html`): 1) `gs-dialog.js` scripts bloğuna eklendi (tüm bildirimler
sağ-alt, kendiliğinden kaybolan toast); 2) "Barkod kopyalandı" başarı bildirimi kaldırıldı (hata kaldı);
3) Doğrula başarı bildirimi kaldırıldı — sayaç/“Doğrulandı” kutusu zaten güncelleniyor; yanlış ürün ve
"tamamı okutuldu" hataları gösterilmeye devam eder. Raf okut / durum düğmeleri dokunulmadı.

Ek: kopyala tuşu başarıda 1,5 sn yeşil tik (.ur-copy-btn--ok, bi-check-lg) olup geri döner — bildirim kutusu yerine tuşun kendisi geri bildirim verir (Komutan uyarısı: bunu kendim akıl etmeliydim).

## Ek (aynı gün) — Otomatik Gönderim'in ASIL çalışmama nedeni: Chrome eklentisi köprüsü
"Otomatik gönderim" = Chrome eklentisi **Güllü Kargo Asist** (`e:\gullu-kargo-asist`, repo dışı, git yok):
panel sayfasında (gullupanel.com) her saniye `#autoShipBarcode` öğesine bakar, 10-20 haneli kodu alıp
background → DHL Online Şube "Gönderi Hazırlık" sekmesine iletir; orada paket tipi (Tekli/İkili... =
ürün adedi), içerik (MODA TAKI / GİYİM EŞYALARI), Parçayı Kaydet, platform kodu, Enter (etiket QZ Tray'den basılır,
ZPL günlük PDF'e Labelary ile eklenir).
- Kök neden: `#autoShipBarcode` yalnız siparis_hazirla.html'de vardı; uretim.html kartı farklı kimlik
  kullanıyordu → eklenti üretim ekranındaki kodu hiç görmedi.
- Panel düzeltmesi (`templates/uretim.html`): üst satırdaki kod span'ı `id="autoShipBarcode"` +
  `data-urun-adet` (kalemListesi uzunluğu = sipariş hazırladaki .product-card sayısı gibi SATIR sayısı).
- Eklenti düzeltmesi (`content-script.js`, sürüm 2.4): adet önce `data-urun-adet`'ten, yoksa product-card
  sayısı; Parçayı Kaydet tek deneme (650 ms) yerine 5 sn'ye kadar 250 ms yoklama
  (`PARCA_KAYDET_BEKLEME_MS`) — görseldeki "Parcayi Kaydet aktif edilemedi" hatası buydu.
- Eklenti yükleme: chrome://extensions → Geliştirici modu → Güncelle (paketlenmemiş). Panel: pull+restart.
- Not: adet "satır" sayısıdır (adet 2 olan tek kalem = 1); sipariş hazırla ile tutarlı, Komutan'a bildirildi.
