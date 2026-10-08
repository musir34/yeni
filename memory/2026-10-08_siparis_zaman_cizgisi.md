# 2026-10-08 — Sipariş Zaman Çizgisi (/siparis-zaman)

**Ne:** Eski /siparis-iz sayfası tüm audit kayıtlarını ham döktüğü için okunmuyordu (en büyük gürültü:
4 dakikada bir tekrarlayan AUTO_HEAL `order_received`/`warning` çiftleri; canlıda 35k+25k satır).
Yeni sayfa `siparis_zaman.py` + `templates/siparis_zaman.html`: sipariş/paket no ile arama, üstte
"Tek bakışta" şeridi (Sipariş verildi → Panele düştü → Hazırlanıyor → [Üretim başladı → Üretildi] →
Paketlendi → Etiket basıldı → Kargoya verildi → Teslim [→ İptal/Arşiv]) ve altta gün gruplu kronolojik akış.
Menüde "Sipariş Zaman Çizgisi" (eski sayfa kaldı; yeni sayfadaki "Ayrıntı" düğmesi oraya gider).

**Kaynaklar (hepsi naive UTC, gösterim fmt_ist = İstanbul):** orders_* tabloları (order_date,
hazirlaniyor_since, toplandi_at, picking_start_time, shipping_time, cancellation_date, archive_date),
uretim_siparis (isleme_alindi_at / uretildi_at / paketlendi_at + hazirlayan), order_audit_logs (gürültü
hariç: status_changed, order_picked, order_archived, order_cancelled, raf_assigned(ilk), manual_note),
user_logs (Işlem Açıklaması + Kullanıcı; PAGE_VIEW hariç), stock_movement, siparis_notu.

**Tuzaklar / kararlar:**
- Aynı adım 3 kaynaktan saniyeler arayla gelir → 5 sn penceresinde tek satır; boş kim/detay diğerinden dolar.
- `str.lower()` Türkçe "İ"yi noktalı i̇ yapar, "işleme alındı" eşleşmiyordu → `kucuk()` (İ→i, I→ı).
- orders_archived'a tam entity select YASAK (prod'da stockCode kolonu yok) → kolon bazlı seçim.
- "Panele düştü" = satır created_at + ilk audit kaydı + diğer panel olaylarının en erkeni
  (satırlar tablo değiştirirken created_at yenileniyor; üretim siparişinde ilk audit 1 gün geç olabiliyor).
- hazirlayan damgası yalnız üretildi/paketlendi adımına; işleme alan farklı kişi olabiliyor (canlıda görüldü).
- Shopify siparişleri orders_* tablolarında yok (source=SHOPIFY 0 satır); yalnız user_logs metinleriyle görünür.
- Kargoda zamanı Trendyol senkronunun tespit anıdır (gerçek teslim anı değil).

**Doğrulama:** 7 saf-mantık testi (tests/test_siparis_zaman.py, --noconftest) + canlı DB'ye salt-okunur
render (normal sipariş 11680029013, üretim siparişi 11678528052, bulunamayan) + headless Chrome görüntü.
Şema değişikliği yok; deploy bekliyor.

## Ek — geçmiş siparişler kapsamı (aynı gün, komutan sorusu)
- Sayfa tüm tablolara bakar (teslim 38.5k, iptal 1.7k satır, 2024'e kadar); ama adım kaynakları farklı tarihlerde başlıyor:
  "Sipariş hazırlandı" user_log 2026-03-29, audit (Hazırlanıyor/Kargoda/Teslim/raf) 2026-05-07, ledger 2026-06-10,
  üretim 2026-07-28, etiket yazdırma logu 2026-08-07. Mayıs 2026 öncesi siparişte yalnız "Sipariş verildi" + "Teslim edildi"
  (teslim = senkron satırının taşınma anı) görünür.
- Düzeltme: audit öncesi siparişte "Panele düştü" olarak teslim satırının created_at'i basılıyordu → kargoda/teslim/iptal/arşiv
  anından geç/eşit ise "Panele düştü" üretilmez (test eklendi, 8 test geçiyor).

## Ek — "son 1 ayın her adımı görünsün" (aynı gün, komutan emri)
- Ölçüm (son 30 gün, sipariş tarihine göre; teslim 1040 / kargoda 116 / iptal 66): Kargoda+Teslim %100, Paketlendi
  (hazırlandı logu 657 + üretim 344) ≈ %96, ledger %92, Hazırlanıyor %68 (üretim siparişi bu adımı atlar, normal),
  **Etiket yalnız %40** (414/1040).
- Kök neden: "Otomatik Gönderim" modunda (sipariş hazırla `autoShipToggle`, üretim `urKargoOtomatik`) etiket panelden
  basılmaz, kargo kodu ekranda gösterilip kuryenin terminalinden basılır; bu an hiçbir yerde loglanmıyordu.
- Çözüm: `POST /siparis-zaman/kargo-kodu-verildi` (siparis_zaman.py) → /order-label ile aynı biçimde PRINT user_log
  ("Otomatik gönderim — kargo kodu verildi — N", sayfa, kargo firması, kargo kodu). Her iki ekran otomatik gönderim anında
  bu rotayı çağırır (sipariş hazırla: sipariş başına tek kayıt, updateButtons tekrarına karşı). Özet kutusu "Etiket / Kargo kodu".
- user_log'da "Kullanıcı" yoksa user_id'den ad çözülür. 10 test geçiyor.
- Geçmişe dönük: deploy öncesi otomatik gönderimle çıkan siparişlerde bu adım geri kazanılamaz (veri yok); o siparişlerde
  aynı anın izi "Sipariş hazırlandı" (paketlendi) kaydıdır.

## Ek — ad değişikliği (aynı gün)
- Komutan emri: sayfanın adı "Sipariş Takip" (menü, başlık, sipariş hazırla menüsü); URL /siparis-zaman korundu.
- Sipariş listesindeki "Sipariş İzi Sür" düğmesi kaldırıldı, yerine "Sipariş Takip" (yeni sayfa) konuldu; eski /siparis-iz yalnız menüden ve yeni sayfadaki "Ayrıntı" düğmesinden ulaşılır.
