# 2026-10-12 — Finans Panel sayfası sade yeniden tasarım

Kullanıcı: "Panel sayfasını güzel, basit ve anlaşılır şekilde yeniden tasarla, çok karışık."
Yalnız templates/finans_panel.html değişti (route/veri aynı, şema yok). Sıra:
1. Hızlı düğmeler: Gelir ekle · Harcama ekle · Para aktar (Hızlı Transfer formu aynı alanlarla pencereye taşındı) · Düzenli ödemeler.
2. "Param nerede?": 4 hesap kutucuğu (tıklayınca defter), kredi kartı "kart borcu" olarak mutlak değer + kırmızı kenar;
   sağ üstte "Toplam nakit" (kredi kartı hariç hesaplar toplamı).
3. Bu ay kartı: Giren (gelir + cari tahsilat) / Çıkan (toplam_gider) / Kalan (net) büyük; altında kalem kalem döküm;
   cari özeti (borcumuz/alacağımız/kasadan aldığım borç/dolar) aynı kartta, yalnız sıfır olmayanlar.
4. Ödenmeyi bekleyenler: başlıkta adet + toplam, Öde / çalışan düğmeleri aynen.
5. Son işlemler: 10 satır, açıklama + "hesap · tür · kategori" alt satırı, tutar, iptal ✕ (tek tırnaklı onclick korundu).
Doğrulama: finans testleri 112 OK (HTTP render dahil); örnek verilerle önizleme tarayıcıda ekran görüntüsüyle kontrol
edildi (masaüstü). Mobil genişlik görülemedi (pencere küçültme işlemedi). Deploy bekliyor.

## Düzeltme (aynı gün, canlı ekran görüntüsü sonrası)
- Kullanıcı: "son işlemlerin yeri doğru mu" — bekleyen listesi ayın tüm gelecek haftalarıyla 22 satıra uzuyor, son
  işlemler en alta itilip sol taraf boş kalıyordu.
- Son işlemler sol sütuna (aylık özetin altına) taşındı; satırda tarih alt satıra indi.
- Bekleyenler: yalnız vadesi gelenler (aylık YYYY-MM + haftası ≤ bugün + geçmiş borçlar); gelecek haftalar tek satır
  "Sonraki haftalar: N ödeme · X ₺ › Düzenli Ödemeler". Başlık sayısı/toplamı vadesi gelenlerden.
- Önizleme: 12.10 itibarıyla 7 vadesi gelen + 9 sonraki doğrulandı; dar ekran ekran görüntüsü düzgün. Finans 112 OK.
