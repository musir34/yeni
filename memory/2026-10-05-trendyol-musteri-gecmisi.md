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

## 2026-10-06: "sıra karışık / tarih tutmuyor" incelemesi — hata bulunmadı, değişiklik YOK
- Komutan soldaki yazışmanın sırasının karışık olduğunu, sonra da Trendyol'daki tarihle tutmadığını söyledi.
- İlk tepkim (cevabı kendi tarihine göre yerleştirme) YANLIŞ teşhisti; yayınlanmadan `git checkout` ile geri alındı.
  Komutan açıkça "soru-cevap-soru-cevap olmalı" dedi → cevap her zaman kendi sorusunun hemen altında kalır.
- Doğrulama: Trendyol API'sinden müşteri 913938'in 4 sorusu salt-okunur çekildi. `creationDate` ve
  `answer.creationDate` İstanbul'a çevrilince Trendyol panelindeki saatlerle birebir aynı (ör. soru 03.10 15:40,
  cevap 04.10 20:00). Yayındaki `_to_dict` aynı veriyle çalıştırıldı: sıra en eski üstte, çiftler bozulmadan.
- Komutanın iki ekran görüntüsü aynı müşterinin FARKLI sorularını gösteriyordu (Trendyol: 3. soru; panel: ilk iki soru).
- Komutan sıra yönünü seçti: en eski üstte (mevcut davranış). Kod değişmedi.
- Ders: "karışık/tutmuyor" şikâyetinde kod değiştirmeden önce gerçek veriyle karşılaştır.
