# Shopify 0023 ve 259 Ekim kampanyaları — 2026-10-23

- Kullanıcı isteği üzerine Güllü Shoes (www.gullushoes.com, TRY) canlı mağazasında uygulandı.
- 0023 / gid://shopify/Product/8814245445810: 56 varyantın satış fiyatı 1549.00 TL; tüm ürüne %40 otomatik indirim. İndirim sonrası 929.40 TL.
- 259 / gid://shopify/Product/8814244593842: 56 varyantin satis fiyati 1999.90 TL; Bej, Beyaz, Bordo, Gri, Kirmizi, Mavi ve Siyah Suet renklerinin toplam 49 varyantina %25 otomatik indirim.
- 259 yalniz Siyah (7 varyant) indirim disinda. Kullanici duzeltmesiyle Siyah Suet dahil: mevcut indirime Siyah Suet 35-41 bedenlerinin 7 varyanti eklendi; baslik "259 - Siyah Haric Ekim Sonuna Kadar %25" olarak duzeltildi.
- İndirimler sepette/ödemede otomatik uygulanır. Bitiş: 2026-11-01 00:00:00 Europe/Istanbul = 2026-10-31T21:00:00Z; 31 Ekim gün sonuna kadar.
- İndirim kimlikleri: gid://shopify/DiscountAutomaticNode/1542068764850 (0023), gid://shopify/DiscountAutomaticNode/1542068994226 (259). İkisi de ACTIVE olarak yeniden sorgulanıp doğrulandı.
- İki ürünün aynı sepette indirim alabilmesi için productDiscounts birleşimi açık; orderDiscounts ve shippingDiscounts birleşimi kapalı. Başka kampanya değiştirilmedi.
- Başlangıç fiyatları ve hedef kapsam: 2026-10-23-shopify-0023-259-kampanya-oncesi.jsonl.
- Güncellemeden sonra 112 varyant fiyatı, yüzdeler, 0023 ürün kapsamı, 259'un 42 varyantlık kapsamı ve bitiş tarihleri canlı API'den tekrar doğrulandı. Üstü çizili fiyatlara dokunulmadı.
- Shopify Admin API: https://shopify.dev/docs/api/admin-graphql/latest/mutations/discountAutomaticBasicCreate

- Siyah Suet duzeltmesi mevcut gid://shopify/DiscountAutomaticNode/1542068994226 uzerinde discountAutomaticBasicUpdate / productVariantsToAdd ile uygulandi; yeni indirim olusturulmadi.
- 2026-10-23 21:50:04 Europe/Istanbul: Kullanici istegiyle IKINCI100 (1331051954354) ve test (1335734796466) kodlari discountCodeDeactivate ile kapatildi. Iki kod da canli API ile EXPIRED dogrulandi; silinmedi. Aktif kalanlar: HOSGELDIN100, 1D39Z43PB72K, 0023 %40 ve 259 %25 (Siyah Suet dahil, yalniz Siyah haric).
