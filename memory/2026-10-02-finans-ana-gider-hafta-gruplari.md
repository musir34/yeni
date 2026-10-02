# 2026-10-02 — Düzenli Ödemeler: Aylıkçılar / Haftalıkçılar + açılır-kapanır hafta grupları

Kullanıcı (ekran görüntüsüyle): Ekim listesinde aylık ve haftalık ödemeler karışık, her haftalıkçı 4-5 kez
alt alta. İstek: önce "Aylıkçılar" ve "Haftalıkçılar" iki başlık; haftalıkçılar 1./2./3./4. hafta olarak
gruplu; her haftanın yanında ok, basınca açılır, tekrar basınca kapanır.

## Ne değişti
- finans_service.ana_gider_gruplari(durum, bugun): saf fonksiyon. `aylik` (donem YYYY-MM) ve `haftalar`
  (donem YYYY-MM-DD, vade gününe göre sıralı, no=1..n, etiket, satırlar, ara toplam odenen/kalan,
  belirsiz_adet/bekleyen_adet, `acik`). Varsayılan açık hafta: bugünü kapsayan (son geçen vade); ay
  gelecekteyse 1. hafta; ay geçmişteyse hepsi kapalı. Satırların kendisi/sırası değişmedi.
- finans.py ana_gider: `gruplar` şablona geçer; tfoot toplamları eskisi gibi düz `durum` üzerinden.
- templates/finans_ana_gider.html: satır işaretlemesi aynen `satir(d, sinif)` makrosuna taşındı
  (makro içinde `include '_finans_calisan_buton.html'` d'yi görüyor — render ile doğrulandı); "📅 Aylıkçılar"
  ve "🗓️ Haftalıkçılar" başlık satırları; hafta başlığı `<tr role=button data-bs-toggle=collapse
  data-bs-target=".fn-hafta-N">` + satırlar `collapse fn-hafta-N [show]`. Ok (▶) aria-expanded ile döner.
- templates/_finans_nav.html: .fn-grup / .fn-hafta / .fn-ok stilleri + `tr.collapse:not(.show){display:none}`.
- DB/şema değişikliği yok.

## Doğrulama
- Önce test (4 kırmızı) → tests/test_finans_ana_gider_gruplari.py (ayrım, sıra, ara toplam, açık hafta
  kuralları, boş liste). Finans testleri 58 OK (`unittest discover`, pytest DEĞİL).
- Şablon stub base.html + sahte global'lerle render edildi: 2 başlık, 2 hafta, show sınıfı yalnız bugünün
  haftasında, çalışan butonları 3/3, Öde butonları 2/2. Gerçek tarayıcıda görülmedi; canlı/deploy YAPILMADI.

## Yayına alma
`git pull && systemctl restart gullupanel.service` (şema adımı yok).

## İnceleme sonrası (aynı gün)
- Kod inceleme: kritik yok. Uygulanan notlar: `tr.collapsing { height:auto; transition:none }` (tr üzerinde
  yükseklik animasyonu titriyordu, artık anında aç/kapa), hafta başlığına `tabindex="0"` (klavye erişimi).
