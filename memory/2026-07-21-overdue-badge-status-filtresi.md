# Geciken rozeti artık sadece hazırlık statülerinde (2026-07-21)

**Sorun:** Sipariş listesinde Kargoda / Teslim Edildi kartlarında da kırmızı
"Süresi Doldu" (ve "Acil") rozeti çıkıyordu — teslim son tarihi geçmiş olduğu
için. Oysa kargoya verilmiş/teslim edilmiş sipariş gecikmiş sayılmaz.

**Kök neden:** `order_list_service._decorate_order_priority` sadece teslim
tarihine bakıyordu, statüye bakmıyordu. (Sunucu tarafı geciken SAYIMI zaten
doğruydu: `overdue_orders.py:20` yalnız Created/Hazirlaniyor/Picking;
`templates/order_list.html:349` "Kalan Süre" satırı da zaten statüye bağlıydı.)

**Değişiklik (cerrahi, 2 nokta, order_list_service.py):**
- `PRIORITY_STATUS_CODES = frozenset(STATUS_CODE.values())` sabiti eklendi
  (Created/Hazirlaniyor/Picking — overdue_orders ile tek kaynak).
- `_decorate_order_priority` içinde statü bu kümede değilse `is_overdue` /
  `is_urgent` False bırakılıp atlanıyor.

Şablon/DB değişikliği yok. Deploy: git pull && systemctl restart gullupanel.service
