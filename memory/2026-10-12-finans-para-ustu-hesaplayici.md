# 2026-10-12 — Günlük Harcamalar: para üstü hesaplayıcı

Kullanıcı: "600 verdim 270 geri geldi, ne kadar gittiğini hesaplamakla mı uğraşacağım."
- templates/finans_kucuk_gider.html: Tutar alanının altına "Verdiğim" + "Para üstü" kutuları (name yok → forma
  gönderilmez). Yazdıkça Tutar = verdiğim − para üstü doldurulur, altında "Harcanan: 330 ₺ (600 − 270)" yazar;
  para üstü fazlaysa kırmızı uyarı. Sayılar finans_sayi.js (fnSayi.num/bicimle) ile Türkçe biçimde.
- Yalnız istemci tarafı; sunucu/şema değişmedi. Aritmetik node ile denendi (600−270=330, 1.000−250,50=749,50).
  Finans testleri 112 OK. Tarayıcıda görülmedi.
