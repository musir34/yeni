# 2026-10-08 — Sipariş Hazırla: kargo firması renk ayrımı

**Ne değişti:** `templates/siparis_hazirla.html`
- Aktif Sipariş başlığına Trendyol rozetinin yanına kargo rozeti eklendi:
  DHL → mavi (`.badge.kargo-dhl`, #1565c0), Trendyol Express → turuncu (`.badge.kargo-tyex`, #f27a1a).
- "Kargo Bilgileri" kutusunda "Kargo Firması:" adı aynı renklerle kalın basılıyor (`.kargo-firma`), gece modu tonları ayrı.
- Eşleme ada göre, küçük harfe çevrilip alt-dize ile: `dhl` → mavi, `trendyol`/`tyex` → turuncu; tanınmayan ad (ör. "Kargo Firması Yok") renksiz kalır.

**Neden:** Artık iki kargo firması var (canlı veri: "DHL eCommerce Marketplace" ve "Trendyol Express Marketplace"); paketleyen tek bakışta ayırt edebilsin.

**Durum:** yerelde, DB/şema değişikliği yok, deploy bekliyor (`git pull && systemctl restart gullupanel.service`).

## Ek — kargo etiketi (aynı gün)
- `templates/order_label.html`: Trendyol Express etiketinde kargo firması satırı **siyah bant + beyaz büyük harf** (`.cargo-provider.cargo-tyex`), DHL etiketi eskisi gibi düz kalın yazı.
  Termal/siyah-beyaz yazıcıda da ayrım görünsün diye renk değil zemin kullanıldı; 11pt + 0.3px harf aralığı (12pt'te "MARKETPLACE" kırpılıyordu, headless Chrome ile 100×100 mm önizlemede doğrulandı).
- Aynı şablon /order-label (sipariş hazırla + üretim) ve Shopify fiş baskısında kullanılıyor; eşleme ad alt-dizesiyle (`trendyol`/`tyex`), DHL için koşul yok.
