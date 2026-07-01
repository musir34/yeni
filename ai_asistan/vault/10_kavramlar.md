# Önemli İş Kavramları

- **Geciken siparişler:** Mantık `overdue_orders.py`'de; teslim tarihi UTC ile kıyaslanır.
  Geciken = teslim tarihi geçmiş VE statü Shipped/teslim değil.
- **Akıllı motor beyaz liste:** `/akilli-motor`'da "Sadece Bu Modellere İndirim Uygula"
  açıksa yalnızca listedeki modeller fiyat günceller, gerisi dokunulmaz.
- **Stok hareket defteri (ledger):** Merkezi `stock_ledger.py` + idempotency. Fiziksel stok
  düşümü Shipped geçişinde yapılır. Kronik hayalet stok kök nedeni buydu.
- **Manuel toplama:** Otomatik raf ataması yok; stok okutulan raftan düşülür (picking_service).
- **Barkod önek çakışması:** Önek-çakışmalı barkodlar hayalet raf stoğu üretebilir; sibling
  uyarısı + barkod loglama mevcut.
- **Arşiv statüleri:** Arşiv rozeti pazaryeri statülerini (Picking/Delivered) order_list ile
  tutarlı çevirir; Shopify için sabit "Archived".

> Yeni bir iş kuralı çıktıkça bu dosyaya madde ekle — AI otomatik "öğrenir".
