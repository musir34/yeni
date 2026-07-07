---
type: community
cohesion: 0.06
members: 53
---

# E-posta Bildirimleri

**Cohesion:** 0.06 - loosely connected
**Members:** 53 nodes

## Members
- [[ANLIK terfi edilemeyen (stoksuz) siparişlerden HENÜZ bildirilmemiş olanlar için]] - rationale - stock_alert_service.py
- [[Any_12]] - code
- [[Belirli bir olay için bildirim açık olan kullanıcıların emaillerini döner.]] - rationale - mail_service.py
- [[Belirli bir olay için bildirim gönderir (arka planda).     Sadece o olayı seçmiş]] - rationale - mail_service.py
- [[Donmuş veya tutarsız mapping'leri tespit et, eşik aşılırsa mail gönder.]] - rationale - stock_sync/health_monitor.py
- [[Gmail SMTP üzerinden mail gönderir.]] - rationale - mail_service.py
- [[Hazırlanıyor'da söz verilmiş (fiziksel taahhüt) barkod - toplam adet.]] - rationale - promotion_service.py
- [[Health monitor'ı lokal test et — kimse abone değilse mail atmaz, sadece loglar.]] - rationale - scripts/test_health_monitor.py
- [[O an stoksuz bekleyen (fiziksel karşılanamayan) orders_created siparişleri.]] - rationale - stock_alert_service.py
- [[OrderCreated kaydını OrderHazirlaniyor'a taşır (id autoincrement, atanan_raf kor]] - rationale - promotion_service.py
- [[OrderCreated → mail için sipariş bilgisi (sipariş no, müşteri, ürünler).]] - rationale - stock_alert_service.py
- [[PERİYODİK o an stoksuz bekleyen tüm siparişlerin hatırlatma özeti (günlük).]] - rationale - stock_alert_service.py
- [[Panel stoğu 0 ama Shopify'a son 'var' olarak gönderilmiş ürünleri tespit et.]] - rationale - stock_sync/health_monitor.py
- [[Shopify stok senkronizasyon sağlık izleme.  İki ayrı kontrol   1. check_sync_st]] - rationale - stock_sync/health_monitor.py
- [[Siparişin TÜM kalemleri 'available' (kalan müsait) stoktan karşılanabiliyor mu]] - rationale - promotion_service.py
- [[Stok yetersizliğinden hazırlanamayan siparişler için sipariş-bazlı HTML email.]] - rationale - mail_service.py
- [[Stoksistem uyarıları için jenerik HTML email oluşturur.      summary_rows (et]] - rationale - mail_service.py
- [[Stoğu müsait olan Yeni siparişleri Hazırlanıyor'a terfi ettirir.     Dönüş {'pr]] - rationale - promotion_service.py
- [[Trendyol API'ye PUT isteği atarak belirtilen package_id'yi 'Picking' statüsüne ç]] - rationale - update_service.py
- [[Tüm kontrolleri sıra ile çalıştır. Scheduler bunu çağırır.]] - rationale - stock_sync/health_monitor.py
- [[Tüm platformlara gönderilen stoktan düşülecek güvenlik tamponu.      Env değişke]] - rationale - stock_sync/service.py
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
- [[build_alert_email_html()]] - code - mail_service.py
- [[build_stock_shortage_email()]] - code - mail_service.py
- [[check_oversell_risk()]] - code - stock_sync/health_monitor.py
- [[check_sync_staleness()]] - code - stock_sync/health_monitor.py
- [[confirm_packing ile aynı mantık paket(shipmentPackageId) - {lineId, quantity}]] - rationale - promotion_service.py
- [[details (JSON string ya da list) - listdict.]] - rationale - promotion_service.py
- [[get_safety_stock_buffer()]] - code - stock_sync/service.py
- [[health_monitor.py]] - code - stock_sync/health_monitor.py
- [[mail_service.py]] - code - mail_service.py
- [[main()_26]] - code - scripts/test_health_monitor.py
- [[notify()]] - code - mail_service.py
- [[promote_eligible_orders()]] - code - promotion_service.py
- [[promotion_service.py]] - code - promotion_service.py
- [[run_all_checks()]] - code - stock_sync/health_monitor.py
- [[send_email()]] - code - mail_service.py
- [[send_periodic_reminder()]] - code - stock_alert_service.py
- [[stock_alert_service.py]] - code - stock_alert_service.py
- [[test_health_monitor.py]] - code - scripts/test_health_monitor.py
- [[update_order_status_to_picking()]] - code - update_service.py
- [[Ürünler için HTML tablo satırları oluşturur.]] - rationale - mail_service.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/E-posta_Bildirimleri
SORT file.name ASC
```

## Connections to other communities
- 14 edges to [[_COMMUNITY_Sipariş Yaşam Döngüsü & Arşiv]]
- 6 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 5 edges to [[_COMMUNITY_Uygulama Çekirdeği & Zamanlı İşler]]
- 4 edges to [[_COMMUNITY_Raf Yönetimi & Barkod Çakışması]]
- 4 edges to [[_COMMUNITY_Community 38]]
- 2 edges to [[_COMMUNITY_Community 37]]
- 2 edges to [[_COMMUNITY_Sipariş Denetim Kaydı (Audit Log)]]
- 2 edges to [[_COMMUNITY_Trendyol Sipariş Çekme & Komisyon]]
- 2 edges to [[_COMMUNITY_Merkezi Stok Senkronizasyonu]]
- 1 edge to [[_COMMUNITY_Barkod Alias Yardımcıları]]
- 1 edge to [[_COMMUNITY_Community 59]]
- 1 edge to [[_COMMUNITY_Community 35]]
- 1 edge to [[_COMMUNITY_Community 65]]

## Top bridge nodes
- [[promotion_service.py]] - degree 16, connects to 6 communities
- [[get_safety_stock_buffer()]] - degree 8, connects to 4 communities
- [[notify()]] - degree 14, connects to 2 communities
- [[promote_eligible_orders()]] - degree 12, connects to 2 communities
- [[stock_alert_service.py]] - degree 12, connects to 2 communities