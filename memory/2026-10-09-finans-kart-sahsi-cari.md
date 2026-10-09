# 2026-10-09 — Kredi kartı ekstresi: şahsi harcama seçilen şahsi cariye düşer

Kullanıcı: "Şahsi harcama seçtiğimde sağda kategori değil cari hesaplar açılsın, hangisini seçersem o cariye düşsün."
Netleştirme cevabı: listede YALNIZ şahsi hesaplar (cari türü 'sahsi'), tüm cariler değil.

## Ne değişti
- finans_kart.py: `sahsi_cariler()` (aktif + TL + tur='sahsi'), `hafiza_cari()`, `_sahsi_cari_getir()` (kilitli,
  şahsi/aktif/TL değilse FinansHata). satirlari_kaydet: şahsi satırda cari seçiliyse kart_sahsi işlemine bağlı
  (`islem_id`) `borc_alma` cari hareketi yazılır → kişinin kasaya borcu artar, kart borcu da artar (eskisi gibi).
  Cari isteğe bağlı: "— cari yok —" eski davranış. Form alanları `cari_<sıra>` ve elle satırda `ek_cari`.
  Satıcı hafızası şahsi satıcıda `cari_id` de saklar (gider kayıtlarının biçimi değişmedi); önizleme ön-seçer.
- templates/finans_kart_ekstre.html: "Kategori / Cari" sütunu; tür Şahsi iken kategori gizlenir, şahsi cari
  listesi görünür (gizli select disabled → post edilmez); aynı satıcıya yayma cari'yi de taşır; elle satıra cari listesi.
- İptal: kart defterinden de cari defterinden de iki taraf birlikte geri alınır (mevcut islem_iptal bağı).
- Şema değişikliği yok.

## Doğrulama
- Önce test (7, 5 kırmızı) → tests/test_finans_kart_sahsi_cari.py: cariye düşme, carisiz eski davranış,
  tedarikçi/dolar/kapalı/yok cari reddi, gider satırında cari yok sayılır, iki yönlü iptal, hafıza, form okuma.
- Mevcut kart testi hafıza biçimi değişikliğini yakaladı → cari_id yalnız şahsi kayıtlara yazılacak şekilde düzeltildi.
- İnceleme temiz (kritik/orta yok); mükerrer-atlama ve eski hafıza biçimi için 2 güvence testi eklendi.
- Finans testleri 94 OK (`unittest discover`, pytest DEĞİL). Tarayıcıda görülmedi, canlı/deploy YOK.

## Yayına alma
`git pull && systemctl restart gullupanel.service` (şema adımı yok). Önce şahsi cari hesabı(ları) Cari sayfasından
"Şahsi (kasadan borç)" türüyle açılmış olmalı; yoksa liste yalnız "— cari yok —" gösterir.
