# Shopify Siparişleri: arşivdeki sipariş "Beklemede" görünüyordu (2026-11-18)

**Şikâyet:** "Arşivden çıkardığım Shopify siparişi Shopify sayfasında Beklemede duruyor ama sipariş hazırlaya düşmüyor."

**Teşhis (user_logs + archive + Shopify canlı):**
- Arşivden çıkarma (`archive.py:819-831`) düzgün çalışıyor; #1635/#1642 11:05'te çıkarılmış,
  20-27 sn sonra ertas tarafından "Sistem Hatası (Hazırlandı)" ile ELLE yeniden arşivlenmiş.
  #1656 hiç çıkarılmamıştı. Üretim ekranında değiller (uretim_siparis boş).
- Asıl kafa karışıklığı: `templates/shopify/orders.html` Beklemede sekmesi/sayacı `-tag:Arsivlendi`
  dışlamıyordu, `getOrderStatus` Arsivlendi'yi tanımayıp "Beklemede" diyordu. Sipariş hazırla ise
  arşivdekileri doğru eliyor (`siparis_hazirla.py:149,376`).

**Değişiklik (yalnız templates/shopify/orders.html):**
- Beklemede liste filtresi + global sayaç sorgusuna `-tag:Arsivlendi`.
- `getOrderStatus`: statü etiketi yoksa ve `Arsivlendi` varsa → `'Arsivde'` (gri, archive ikonu,
  `STATUS_CONFIG` + `.status-arsivde`). Dropdown seçeneklerine (ORDER_STATUSES) EKLENMEDİ.
- Arsivlendi+Kargoda gibi çift etiketlide statü etiketi önceliklidir (Kargoda görünür).

**Not:** İlk hipotez (remove_order_tags dönüşü kontrol edilmiyor, `archive.py:824`) bu vakada
kök neden DEĞİLDİ; zayıflık hâlâ duruyor ama dokunulmadı.
