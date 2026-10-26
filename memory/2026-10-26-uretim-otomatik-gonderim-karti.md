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
