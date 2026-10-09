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
