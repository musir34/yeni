---
type: community
cohesion: 0.09
members: 37
---

# Sipariş Yaşam Döngüsü & Arşiv

**Cohesion:** 0.09 - loosely connected
**Members:** 37 nodes

## Members
- [[ANLIK terfi edilemeyen (stoksuz) siparişlerden HENÜZ bildirilmemiş olanlar için]] - rationale - stock_alert_service.py
- [[Belirli bir olay için bildirim açık olan kullanıcıların emaillerini döner.]] - rationale - mail_service.py
- [[Belirli bir olay için bildirim gönderir (arka planda).     Sadece o olayı seçmiş]] - rationale - mail_service.py
- [[Gmail SMTP üzerinden mail gönderir.]] - rationale - mail_service.py
- [[Hazırlanıyor'da söz verilmiş (fiziksel taahhüt) barkod - toplam adet.]] - rationale - promotion_service.py
- [[O an stoksuz bekleyen (fiziksel karşılanamayan) orders_created siparişleri.]] - rationale - stock_alert_service.py
- [[OrderCreated kaydını OrderHazirlaniyor'a taşır (id autoincrement, atanan_raf kor]] - rationale - promotion_service.py
- [[OrderCreated → mail için sipariş bilgisi (sipariş no, müşteri, ürünler).]] - rationale - stock_alert_service.py
- [[PERİYODİK o an stoksuz bekleyen tüm siparişlerin hatırlatma özeti (günlük).]] - rationale - stock_alert_service.py
- [[Siparişin TÜM kalemleri 'available' (kalan müsait) stoktan karşılanabiliyor mu]] - rationale - promotion_service.py
- [[Stok yetersizliğinden hazırlanamayan siparişler için sipariş-bazlı HTML email.]] - rationale - mail_service.py
- [[Stoğu müsait olan Yeni siparişleri Hazırlanıyor'a terfi ettirir.     Dönüş {'pr]] - rationale - promotion_service.py
- [[Trendyol API'ye PUT isteği atarak belirtilen package_id'yi 'Picking' statüsüne ç]] - rationale - update_service.py
- [[_build_product_rows()]] - code - mail_service.py
- [[_build_trendyol_lines()]] - code - promotion_service.py
- [[_committed_in_hazirlaniyor()]] - code - promotion_service.py
- [[_currently_uncovered()]] - code - stock_alert_service.py
- [[_get_recipients_for_event()]] - code - mail_service.py
- [[_move_created_to_hazirlaniyor()]] - code - promotion_service.py
- [[_order_can_be_covered()]] - code - promotion_service.py
- [[_order_to_info()]] - code - stock_alert_service.py
- [[_parse_details()_2]] - code - promotion_service.py
- [[_physical_central()]] - code - promotion_service.py
- [[alert_uncovered_orders()]] - code - stock_alert_service.py
- [[barkod(canonical) - fiziksel merkez stok adedi.]] - rationale - promotion_service.py
- [[build_stock_shortage_email()]] - code - mail_service.py
- [[confirm_packing ile aynı mantık paket(shipmentPackageId) - {lineId, quantity}]] - rationale - promotion_service.py
- [[details (JSON string ya da list) - listdict.]] - rationale - promotion_service.py
- [[mail_service.py]] - code - mail_service.py
- [[notify()]] - code - mail_service.py
- [[promote_eligible_orders()]] - code - promotion_service.py
- [[promotion_service.py]] - code - promotion_service.py
- [[send_email()]] - code - mail_service.py
- [[send_periodic_reminder()]] - code - stock_alert_service.py
- [[stock_alert_service.py]] - code - stock_alert_service.py
- [[update_order_status_to_picking()]] - code - update_service.py
- [[Ürünler için HTML tablo satırları oluşturur.]] - rationale - mail_service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Sipari_Yaam_Dngs__Ariv
SORT file.name ASC
```

## Connections to other communities
- 9 edges to [[_COMMUNITY_Community 41]]
- 4 edges to [[_COMMUNITY_Değişim  İade Talepleri]]
- 4 edges to [[_COMMUNITY_Community 70]]
- 4 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 3 edges to [[_COMMUNITY_E-posta Bildirimleri]]
- 2 edges to [[_COMMUNITY_Stok Senkron API]]
- 2 edges to [[_COMMUNITY_Community 46]]
- 2 edges to [[_COMMUNITY_Community 66]]
- 2 edges to [[_COMMUNITY_Stok Fix Testleri & Yardımcılar]]
- 1 edge to [[_COMMUNITY_Community 57]]
- 1 edge to [[_COMMUNITY_Community 76]]
- 1 edge to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]

## Top bridge nodes
- [[promotion_service.py]] - degree 16, connects to 6 communities
- [[notify()]] - degree 14, connects to 4 communities
- [[mail_service.py]] - degree 11, connects to 3 communities
- [[promote_eligible_orders()]] - degree 12, connects to 2 communities
- [[stock_alert_service.py]] - degree 12, connects to 2 communities