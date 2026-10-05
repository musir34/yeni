# Shopify Siparişler sayfası stil kodu yeniden yazıldı (2026-10-05)

- Emir: `/shopify/orders` tasarımında ciddi sıkıntılar var; aynı görünüm korunarak tasarım kodu baştan yazılsın.
- Dosya: `templates/shopify/orders.html` — `<style>` bloğu tamamen yeniden yazıldı, betik mantığına dokunulmadı.
- Eski kodun sorunları:
  - Kurallar kapsamsızdı (`.btn`, `.card`, `.dropdown-menu`, `.form-control`, `.modal`, kaydırma çubuğu) → üst menü dahil her şeyi eziyordu;
    `.btn::after` açılır düğmelerin ok işaretini görünmez yapıyordu.
  - Tablo açılır menüleri `position:fixed !important` + satırlarda kalıcı transform ile yanlış yerde açılıyordu;
    `table-responsive` `overflow:visible` yapıldığı için dar ekranda tablo sayfadan taşıyordu.
  - `gullu-common.css:135` `.modal-dialog{margin:10px}` pencereleri sol üst köşeye yapıştırıyordu (ortak kural, başka sayfaları da etkiliyor olabilir).
  - Gece modunda sabit açık renkler (sekmeler, kargo/iade kutuları), odakta büyüyen form alanları, 20+ kullanılmayan animasyon.
- Yeni düzen: tüm kurallar `.shopify-orders` altında, renkler `--so-*` değişkenlerinde (gece modu `html.gs-dark`),
  giriş animasyonları `backwards` (kalıcı transform yok), tablo açılır menüleri
  `data-bs-popper-config='{"strategy":"fixed"}'`, tablo kendi içinde yatay kayar, pencereler ortalı, `prefers-reduced-motion`.
- `countUp` animasyon adı betikten çağrılıyor (animateValue) — adı değiştirme.
- Doğrulama: canlı sisteme dokunmadan Jinja + sahte veriyle önizleme; aydınlık, gece, 390px genişlik, açılır menü konumu,
  toplu seçim çubuğu, iptal penceresi tarayıcıda görüldü. Gerçek veriyle canlıda denenmedi. Deploy bekliyor.
- Dokunulmadı: sayfadaki Türkçe karaktersiz metinler ("Siparis Yonetimi" vb.).
