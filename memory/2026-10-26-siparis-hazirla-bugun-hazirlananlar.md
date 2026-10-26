# 2026-10-26 — Sipariş Hazırla: "Bugün Hazırlananlar" listesi

## İstek
Komutan: etiket çıkmadan sipariş sıradakine geçince hangisi olduğu bulunamıyor; "her gün 00:00'da
yenilenen bir şey olsun, sırayla hazırlanan siparişler çıksın."

## Yapılan
- `siparis_hazirla.py`: `/api/bugun-hazirlananlar` (blueprint siparis_hazirla → sayfa yetkisi
  ebeveynle aynı, katalog girişi gerekmedi). Gün = İstanbul 00:00'dan itibaren (`_bugun_baslangici_utc`,
  naive UTC); ayrı tablo/cron YOK, zaman penceresi. Kaynak user_logs: paketleme kaydı
  ("… hazırlandı — N (…)", confirm_packing; Durum=BASARISIZ elenir, mükerrer ilk kalır) + etiket izleri
  ("Kargo etiketi yazdırıldı — N" PRINT, "Otomatik gönderim — kargo kodu verildi — N").
  Saf derleme `bugun_hazirlananlari_derle(rows)` (testli). Her satır: sıra, saat, sipariş (Shopify'da
  mağaza adı #1428 + SH-id), müşteri, kaynak, hazırlayan, etiket durumu (yazdirildi/oto/yok) ve
  yeniden yazdır alanları (`_hazirlanan_yazdir_bilgisi`: Trendyol find_order_across_tables,
  Shopify uretim_modu.shopify_siparis önbellekli).
- `templates/siparis_hazirla.html`: üst düğme grubunda "Bugün Hazırlananlar" (+ sayı rozeti) →
  modal tablo; etiket izi olmayan satır kırmızı; "Yazdır" gizli formla /order-label'a (yazdirForm ile
  aynı alanlar; Shopify'da MNG etiketine yönlenir). Her açılışta/yenilede taze çekilir.
- Tuzak: Shopify etiket izi iki adla düşer (yazdırma '#1428', oto 'SH-id'); eşleme her ikisine bakar.
- `tests/test_bugun_hazirlananlar.py` (3 test, DB yok; DISABLE_JOBS=1 … --noconftest).

## Deploy
Şema yok. `git pull && systemctl restart gullupanel.service`.
