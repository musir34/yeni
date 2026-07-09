---
type: community
cohesion: 0.10
members: 29
---

# Uygulama Çekirdeği & Zamanlı İşler

**Cohesion:** 0.10 - loosely connected
**Members:** 29 nodes

## Members
- [[AI Asistanı sohbet sayfası]] - concept - templates/ai_asistan.html
- [[AI Asistanı sunucu kurulumu (headless Claude Code)]] - document - ai_asistan/KURULUM.md
- [[Amazon Ayarlar Sayfası]] - concept - templates/amazon/ayarlar.html
- [[Amazon Entegrasyon Panosu]] - concept - templates/amazon/index.html
- [[Amazon Yapılandırma Hatası Sayfası]] - concept - templates/amazon/config_error.html
- [[Amazon Ürün Eşleştirme Sayfası]] - concept - templates/amazon/eslestirme.html
- [[Gizli özellikler sayfası]] - concept - templates/gizli_ozellikler.html
- [[Haftalık Üretim Önerisi Sayfası]] - concept - templates/uretim_oneri_haftalik.html
- [[Notification Popup Include]] - concept - templates/siparis_fisi_detay.html
- [[Python bağımlılıkları (FlaskSQLAlchemyopenaiprophet)]] - document - requirements.txt
- [[Salt-okunur Postgres MCP (gulludb query)]] - concept - ai_asistan/KURULUM.md
- [[Sipariş Fişi Detayı Sayfası]] - concept - templates/siparis_fisi_detay.html
- [[Sipariş Fişi Oluştur Sayfası]] - concept - templates/siparis_fisi_olustur.html
- [[Sipariş Fişi Yazdırma Sayfası]] - concept - templates/siparis_fisi_print.html
- [[Soru-Cevap (Trendyol Q&A) Sayfası]] - concept - templates/soru_cevap.html
- [[Soru-Cevap AI Taslak API]] - code - templates/soru_cevap.html
- [[Stok Ekleme Ekranı]] - concept - templates/stock_addition.html
- [[Stok Raporu Sayfası]] - concept - templates/stock_report.html
- [[Tedarikçi & Model Maliyet API]] - code - templates/tedarikci_yonetimi.html
- [[Tedarikçi Yönetimi Sayfası]] - concept - templates/tedarikci_yonetimi.html
- [[Toplu Sipariş Fişi Yazdırma Sayfası]] - concept - templates/siparis_fisi_toplu_print.html
- [[ai_readonly salt-okunur DB rolü]] - concept - ai_asistan/KURULUM.md
- [[amazon Blueprint (SP-API Entegrasyonu)]] - code - templates/amazon/index.html
- [[base.html taban şablonu]] - concept - templates/ai_asistan.html
- [[siparis_fisi_bp Blueprint (Tedarik Fişi)]] - code - templates/siparis_fisi_detay.html
- [[stock-addition  barcode lookup Endpoint]] - code - templates/stock_addition.html
- [[Üretim Planı Yazdırma Sayfası]] - concept - templates/uretim_plan_print.html
- [[Üretim Önerisi & Plan API]] - code - templates/uretim_oneri_haftalik.html
- [[Üretim Önerisi Sayfası]] - concept - templates/uretim_oneri.html

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Uygulama_ekirdei__Zamanl_ler
SORT file.name ASC
```
