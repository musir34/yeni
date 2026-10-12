# 2026-10-09 — Şahsi cari hesaba haftalık maaş planı

Kullanıcı: Cari'de kendi şahsi hesabı var; her hafta 15.000 ₺ maaşı Düzenli Ödemeler'den bu hesaba bağlamak
istiyor. Sorun: plan formunda yalnız çalışan carileri listeleniyordu, "Yeni çalışan ekle" yeni cari açıyordu.

## Çözüm
- finans_calisan_service: `MAAS_CARI_TURLERI = ('calisan','sahsi')`, `maas_carileri()` (açık + TL, çalışan ve
  şahsi). `cari_bagla` artık şahsi TL hesabı da kabul eder (dolar/kapalı/tedarikçi reddedilir).
- Plan formu (finans_ana_gider.html, ekle + düzenle): listede şahsi hesap "(şahsi)" etiketiyle çıkar.
- Cari detay: şahsi hesapta hak ediş varsa "Hak edişler ve ödemeler" kartı + ödeme penceresi görünür;
  şahsi düğmeleri (Kasadan Borç Aldım / Borcumu Ödedim) yerinde kalır. "Cebinden Para Verdi" yalnız çalışanda.
- Muhasebe: haftalık hak ediş şahsi hesaba +15.000 (işletme sahibine borçlu) yazılır, kasadan alınan borçla
  (borc_alma −) aynı hesapta mahsuplaşır. Ödeme eskisi gibi Düzenli Ödemeler'den "Ödeme ekle".
- Korumalar: plan bağlı şahsi hesap kapatılamaz (cari_pasif), türü/para birimi değiştirilemez (cari_guncelle).
- Şema değişikliği yok.

## Doğrulama
- Önce test (4 kırmızı) → tests/test_finans_sahsi_maas.py (6 test: bağlama/yeni cari yok, mahsuplaşma + ödeme,
  listeleme + hak ediş satırları, red durumları, korumalar, çalışan akışı değişmedi).
- Finans testleri 100 OK (`unittest discover`, pytest DEĞİL). Tarayıcıda görülmedi, canlı/deploy YOK.

## Kullanım
Düzenli Ödemeler → Düzenli Ödeme Ekle → "Çalışan ödemesi" → listeden "<adınız> (şahsi)" → Haftalık,
ilk ödeme günü, 15.000 sabit → Ekle. Yayın: `git pull && systemctl restart gullupanel.service`.

## İnceleme sonrası (aynı gün)
- Kritik yok. Uygulanan küçük düzeltmeler: şahsi hesapta "Borcumu Ödedim" yalnız kasaya borç varken (bakiye < 0)
  görünür; defter sütunu hak ediş varken "Ödediğim / Hak ediş".
- İnceleme bulgusu (orta): mahsuplaşma yalnız bakiyedeydi, hafta "kalan"ı gerçek ödeme olmadan kapanmıyordu.
  Komutan kararı: "Borçtan mahsup seçeneği eklensin".

## Borçtan mahsup (aynı gün)
- Maaş ödeme penceresinde, yalnız şahsi hesapta görünen "Kasa borcundan düş" seçeneği (hesap='mahsup').
- hakedis_ve_odeme: iki kasasız cari satırı, aynı hakedis_id/tutar/tarih: `odeme` (−1, odeme_anahtari, haftayı
  kapatır) + `mahsup` (+1, kasa borcunu düşer). Net bakiye değişmez, kasadan para çıkmaz.
  Sınır: haftanın kalanı ve `sahsi_kasa_borcu` (borc_alma/borc_odeme/mahsup toplamı). Çift tıklama anahtarı korunur.
- İptal: herhangi biri iptal edilince `_mahsup_ciftini_iptal` ikisini birden geri alır; defterde iptal düğmesi görünür.
- Testler: tests/test_finans_sahsi_maas.py +5 (kapanış, sınır, yalnız şahsi, iki yönlü iptal, çift tıklama).
  Finans testleri 105 OK.

## Mahsup incelemesi sonrası (aynı gün)
- Orta bulgu düzeltildi: mahsup edilmiş kasa borcunun (borc_alma) iptali engellendi (finans_service.cari_hareket_geri_al;
  cari ve kasa defteri iptal yollarının ortak noktası). Mahsup yoksa iptal eskisi gibi serbest. Önce mahsup iptal edilir.
- Küçükler: mahsup çiftinin iki satırı iptalde id sırasıyla önce kilitlenir (eşzamanlı iptalde kilitlenme yok);
  "Borcumu Ödedim" düğmesi artık gerçek kasa borcuna (sahsi_kasa_borcu > 0) göre görünür; yorum satırı düzeltildi.
- +2 test; finans testleri 107 OK.

## 2026-10-12 — "Kasa borcundan düş" → "Hesabıma yaz"
- Kullanıcı haftalığını almadı, seçeneği kullandı: "Kasa borcundan en çok 0.00 ₺ düşülebilir" hatası (borcu yoktu).
  İstek: "hesabıma eklesin". Seçenek anlamı genişletildi: maaş nakit alınmadan hesaba yazılır, hafta kapanır.
- Borç sınırı kaldırıldı (tek sınır haftanın kalanı); önce kasa borcunu kapatır, artanı alacak olarak kalır,
  sonraki kasadan alımlar (borc_alma) bu alacaktan düşer. sahsi_kasa_borcu en az 0 olduğu için tutarlı.
- Mahsup edilmiş borc_alma iptal engeli kaldırıldı: yeni anlamda borç iptali yalnız alacağı büyütür, tutarsızlık yok.
- Etiketler: seçenek "Hesabıma yaz (kasadan para çıkmaz)", defter "Maaş hesaba yazıldı", açıklama "… maaşı hesaba yazıldı".
- Testler güncellendi (borçsuz hesaba yazma + sonraki alım, kalan sınırı, borç iptali serbest); finans 110 OK.
- 2026-10-12 (sonra): Kullanıcı "neden 2 defa görünüyor" → defterde tek satır istendi. cs.hareketler() artık
  "Hesabıma yaz" ikilisinin kasasız `odeme` bacağını (tur=odeme, islem_id NULL, hakedis_id dolu) listelemez;
  `mahsup` satırı tutarı açıklamada "· X ₺ · kasadan para çıkmadı" olarak gösterir, tutar sütunu boş, bakiye sütunu doğru.
  Hesaplama/iptal değişmedi (iptal yine ikiliyi birlikte geri alır). Test +1; finans 111 OK.
- 2026-10-12 (sonra 2): Kullanıcı "neden 2 ayrı satır, tek satır olsun" — hak ediş (09.10) + "Maaş hesaba yazıldı" (12.10).
  Şimdi ikilinin İKİ bacağı da defterden gizli (tur odeme|mahsup, islem_id NULL, hakedis_id dolu); haftanın hak ediş
  satırına "Hesaba yazıldı · X ₺ · kasadan para çıkmadı" notu + geri al ✕ (son mahsup satırını iptal eder → ikili iptal).
  cs.hesaba_yazilanlar(cari_id) → {hakedis_id: {tutar, iptal_id}}. Sayfa render testi eklendi; finans 112 OK.
