# Trendyol kartında müşterinin önceki soruları (2026-10-05, yerelde, commit/deploy yok)

- Komutan: aynı müşteri birden çok soru soruyor, bazen eski sorusuyla ilgili yazıyor; Trendyol panelinde görünüyor,
  bizim panelde görünmüyordu. İstek: Instagram DM kartındaki balonlu yazışma tasarımının aynısı.
- Kaynak yerel tablo: `TrendyolQuestion.customer_id` (API'nin `customerId` alanı) zaten saklanıyordu;
  Trendyol'dan ek istek yok, şema değişikliği yok.
- `qna_service.musteri_gecmisi(customer_ids)`: müşteri başına en çok 12 soru, eskiden yeniye, tek sorgu.
- `qna_routes._trendyol_yazisma` → kart sözlüğüne `mesajlar` (soru = gelen balon, cevabımız = giden balon;
  şimdiki soru `simdiki`, başka ürüne sorulmuş soruda ürün adı). Müşterinin başka sorusu yoksa boş liste →
  kart eskisi gibi tek soruyu gösterir.
- `soru_cevap.html` `cardHtml`: `mesajlar` varsa "Müşterinin soruları" başlığıyla `.qna-thread` balonları
  (Instagram kartıyla aynı sınıflar), şimdiki soru turuncu çerçeveli (`.qna-bubble--now`).
- AI taslağı: `_draft_prompt(..., gecmis=)` son 5 önceki soru-cevabı isteme ekler ("yeni soru bunlara atıf yapıyor olabilir").
- Sınır: yalnız panele düşmüş sorular görünür (entegrasyon öncesi ve hiç senkronlanmamış eski sorular yok).
- 45 test; kart önizlemede geçmişli ve geçmişsiz haliyle görüldü. Canlı veriyle denenmedi.
