# 2026-11-02 — Stok Eritme kartı: model başına bugünkü sipariş

- Komutan emri (agentation, /anasayfa): eritme kartındaki her model kodunun yanında bugün 00:00–23:59 gelen sipariş sayısı.
- Kararlar (Komutan): kart = Stok Eritme; iptaller hariç.
- eritme_gorevi.py: `_bugunku_siparisler` — OrderCreated/Hazirlaniyor/Picking/Shipped/Delivered (anasayfa günlük kutucuğuyla aynı küme;
  cancelled/archived dışarıda), order_date naive UTC → İstanbul günü `ist_to_utc` ile UTC aralığa çevrilir.
  Model bağlama: details barkodu → products.product_main_id, yedek olarak satırın product_main_id kolonu. Sipariş modele 1 kez sayılır.
- home.html: çipte `🛒N` rozeti (0 ise soluk), gece modu rengi, başlıkta açıklama.
- Shopify site siparişleri sayılmaz (DB'de değil, canlı API). DB değişikliği yok. Deploy bekliyor.
- Gözlem (dokunulmadı): home.py `_ist_between` naive-UTC kolonu `timezone('Europe/Istanbul', col)` ile İstanbul saati sayıyor olabilir → günlük kutucuk penceresi ~3 saat kayık olabilir.
- Ek (aynı gün): grup başlıklarına (Çok Satan / Ağır Giden) "🛒 Bugün N sipariş" toplamı. `_bugunku_siparisler` artık
  model → sipariş no kümesi döner; grup toplamı kümelerin birleşimi (iki modelli sipariş bir kez sayılır, bu yüzden
  model rozetlerinin toplamından küçük olabilir). `_grup_stoklari` dönüşüne `bugun_toplam` eklendi.
