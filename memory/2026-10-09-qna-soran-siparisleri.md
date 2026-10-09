---
name: project-qna-soran-siparisleri
description: Soru-Cevap Trendyol kartında soruyu soranın siparişleri (customerId köprüsü, trendyol_siparis_musteri tablosu); 2026-10-09 yerelde, deploy bekliyor
metadata:
  type: project
---

2026-10-09: Q&A API sipariş no vermiyor; ortak anahtar customerId (sipariş v2 paketinde de var, paket seviyesinde).
- Yeni tablo `trendyol_siparis_musteri` (order_number PK → customer_id, order_date); açılışta qna_service.ensure_table_exists ile checkfirst kurulur (migration yok).
- order_service.process_all_orders başında `trendyol_qna/siparis_musteri.musteri_siparislerini_kaydet` (ayrı bağlantı, ON CONFLICT DO NOTHING, hata senkronu durdurmaz; arşivdekiler dahil).
- Kart: "Siparişleri: #no" düğmeleri (sorulan modeli içeren yeşil "bu ürün", başta) → Bootstrap modal: görsel, model kodu, renk, beden, barkod, alıcı ad-soyad, adres.
- Model kodu barkoddan products.product_main_id (sipariş satırındaki product_main_id = contentId tuzağı). Arşiv tablolarına yalnız kolon select.
- Geçmiş: `scripts/backfill_trendyol_siparis_musteri.py` (~90 gün, 14 günlük pencere), deploy sonrası bir kez.
- Test: tests/test_qna_siparis_musteri.py (sqlite, --noconftest). Ekran görüntüyle doğrulanmadı.
İlgili: [[project-trendyol-qna]]
