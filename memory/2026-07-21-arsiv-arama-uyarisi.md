# Arama: "bu sipariş arşivde" uyarısı + arşivde arama (2026-07-21)

**Sorun:** Sipariş listesinde arama yapılınca arşivlenmiş sipariş hiç çıkmıyordu
(arşivleme siparişi statü tablosundan SİLİP `archive` tablosuna taşıyor), kullanıcı
"sipariş kayboldu" sanıyordu. Arşiv sayfasında da arama yoktu — sadece tarihe göre
sayfalı liste (20/sayfa), yani elle bulmak pratikte imkânsızdı.

**Değişiklik:**
1. `archive.py::display_archive` — `?search=` desteği (order_number, customer_name,
   customer_surname, ad+soyad birleşimi; ilike). `search_query` şablona geçiyor.
   `sqlalchemy.or_` importu eklendi.
2. `templates/archive.html` — üst barda arama kutusu + "temizle" butonu; 5 sayfalama
   linkine `search=search_query or None` eklendi (arama sayfa değişince kaybolmasın).
3. `order_list_service._archived_search_matches(search_query, limit=5)` — arama varsa
   Archive'ta eşleşenleri döner (order_number, müşteri, arşiv tarihi, sebep).
   Hata durumunda [] döner; liste bozulmaz. `Archive` modeli import edildi.
4. Her iki listeleme yolu (`get_order_list`, `get_filtered_orders`) şablona
   `archived_matches` geçiyor.
5. `templates/order_list.html` — arama araç çubuğunun altında sarı uyarı bandı:
   her eşleşme `/archive?search=<order_number>` linki. `archived_matches|default([])`
   kullanıldığı için bu şablonu render eden diğer rotalar (order_service.py,
   processed_orders_service.py) etkilenmez.

**Kullanıcı kararları:** Uyarı HER aramada çıkar (ana listede sonuç olsa bile);
arama alanları sipariş no + müşteri adı (liste ile aynı).

DB/migration yok. Deploy: git pull && systemctl restart gullupanel.service
