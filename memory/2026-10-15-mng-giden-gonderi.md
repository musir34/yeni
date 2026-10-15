# MNG giden gönderi otomasyonu (2026-10-15, yerelde, sandbox doğrulaması + deploy bekliyor)

- Komutan: değişim / manuel sipariş / site siparişi oluşunca Trendyol'daki gibi anında kargo
  referansı üretilsin, "kargoya ver" demeden takip edilsin, teslim/kapıda ödeme otomatik düşsün.
- Tespit: kurye adresi elle giriyordu, panel MNG takip numarasını hiç bilmiyordu (değişim
  `kargo_kodu` yerel 555+7, `musteri_kargo_takip` müşterinin DÖNÜŞ takibi, manuel siparişte takip
  kolonu yok, "Teslim Edildi" 7 gün tahminiyle). Shopify takip numaraları elle kopyalanıyordu.
- API: sunucudaki iade köprüsü (`dhl-kargo/server.js`) MNG ApiZone kullanıyor (token + createReturnOrder +
  checkReturnOrder). Giden yön aynı aile: createOrder → createbarcode (shipmentId, barcodes[].barcode,
  value=ZPL), getshipmentstatus/{ref} (kod 1-8), trackshipment, cancelorder, cbsinfoapi.
  Referans ≤20 BÜYÜK; recipient'ta customerId GÖNDERİLMEZ; cityCode 0 ise cityName zorunlu;
  cevaplar tek elemanlı liste; 20001 "VARIŞ ŞUBESİ" → 5/10 sn bekleyip tekrar; 3002 "ZATEN VAR" → barkoda geç.
- Yapı (panelde, Python; köprüye dokunulmadı):
  `mng_kargo/ayar.py` (.env: MNG_ORTAM=sandbox|prod, MNG_[SANDBOX_]BASE_URL/CLIENT_ID/CLIENT_SECRET/
  CUSTOMER_NUMBER/PASSWORD), `govde.py` (saf gövdeler), `durum.py` (kod→durum), `client.py`,
  `adres.py` (81 il, serbest adresten il/ilçe), `servis.py` (gonderi_ac idempotent, iptal, takip_isi),
  `kaynak.py` (gönderi durumu → Degisim 'Kargoya Verildi'/'Teslim Edildi', YeniSiparis 'Kargoda'/'Teslim
  Edildi', Shopify fulfillment+takip no + Kargoda/Teslim Edildi etiketi; yalnız ileri yön),
  `shopify_tarama.py` (beklemede siparişler, son 7 gün), `routes.py` + `templates/kargo_gonderi.html`
  (/kargo-gonderi: liste, Sorgula, Yeniden Dene + il/ilçe düzeltme, İptal, ZPL indir).
- Tablo `kargo_gonderi` (models.KargoGonderi) — `scripts/create_kargo_gonderi_table.py` RESTART ÖNCESİ.
- Referanslar: değişim DG+kargo_kodu, manuel MN+id, Shopify SH+sipariş no.
- Bağlantılar: degisim.py (kayıt sonrası aç; sil/toplu sil iptal; kartta rozet + etikette MNG barkodu),
  siparisler.py (kayıt sonrası aç, kapıda ödeme tutarıyla; sil iptal; kartta rozet + Etiket düğmesi),
  formlara il/ilçe (opsiyonel, boşsa adresten), app.py job'ları mng_shopify_gonderi (5 dk) + mng_takip (15 dk),
  sayfa_yetki `kargo_gonderi` (YONETIM), _ust_menu, shopify_service get_orders'a phone/zip/provinceCode/email.
- Anahtar: `MNG_OTOMATIK_GONDERI=1` olmadan hiçbir API çağrısı/kayıt yok (eski elle akış aynen).
- Testler: tests/test_mng_kargo.py, test_mng_adres.py, test_kargo_gonderi.py (sahte istemci, sqlite) — 54 geçti.
- AÇIK: (1) `scripts/mng_sandbox_test.py` sandbox kimlikleriyle koşturulup uç/şema doğrulanacak (özellikle
  cityName ile şube çözümü, COD alanı, barkod biçimi, takip URL şablonu MNG_TAKIP_URL_SABLON);
  (2) kuryenin bizim bastığımız Code128 barkodu (barcodes[].barcode) okuttuğu ilk gerçek gönderide
  doğrulanacak, olmazsa ZPL (Zebra) etiket; (3) prod kimlikleri .env'e (köprü config.json mngProd).
- Kod incelemesi sonrası (aynı gün): anahtar kapalıyken kargo_gonderi tablosuna hiç gidilmez + açıkken
  sorgular savepoint'te (tablo betiği restart'tan önce unutulsa silme/liste akışları bozulmaz);
  `kaynak_durum` kolonu: kaynağa başarıyla yazılan son statü → Shopify API hatası sonraki takipte yeniden
  denenir, fulfillment yalnız bir kez açılır (çift mail yok); iptal edilen kaynağa aynı referansla ikinci
  gönderi açılmaz; bilinmeyen elle statü (İade vb.) ezilmez; gönderi kaydı geri gitmez; 3 gün bekleyen → hata.
  Bilinçli kabul: gönderi açma isteği kullanıcı isteği içinde senkron (Trendyol gibi anında referans; MNG
  yavaşsa kayıt 'bekliyor'a düşer, kayıt bloklanmaz); Shopify get_orders'a eklenen phone/zip/provinceCode/email
  alanları canlı mağazada bir kez doğrulanmalı. 62 test geçti.
- Sandbox provası (aynı gün): token OK, createOrder OK (cityCode 0 + cityName/districtName ile şube çözüldü:
  shipperBranchCode döndü), cancelorder OK. recipient.taxNumber boş kabul edilmiyor (26056) → yer tutucu
  11111111111 (govde.VARSAYILAN_TC). createbarcode / getshipmentstatus / cbsinfoapi 401 "Cannot find valid
  subscription": ne sandbox ne prod uygulaması bu ürünlere abone değildi.
- ApiZone portalında (apizone.mngkargo.com.tr, Komutan onayıyla tarayıcıdan) GulluShoesShopifyReturn
  uygulaması Barcode Command + Standard Query + CBS Info ürünlerine abone edildi → "Onay bekliyor",
  MNG onaylayınca e-posta gelecek. Sandbox anahtarı (800169398) bu portalda görünmüyor (ayrı test hesabı);
  gerçek doğrulama onay sonrası CANLIDA iptal edilecek deneme gönderisiyle yapılacak.
- .env (yerel): MNG_SANDBOX_* + MNG_* kimlikleri köprü config.json'dan kopyalandı, MNG_ORTAM=sandbox,
  MNG_OTOMATIK_GONDERI=0. Sunucu .env'e aynı satırlar deploy'da girilecek.
- Abonelikler MNG tarafından onaylandı (API kontrolü: Standard Query 404=abone, CBS Info 82 il, Barcode 400=abone).
  CANLI prova (GSTEST92062782, iptal edildi): createOrder OK (shipperBranchCode 03412900), cancelorder OK,
  createbarcode → 500 [20011] "<IP> IP adresi için tek barkod yetkiniz yoktur". Yani barkod üretimi
  müşteri hesabında "tek barkod yetkisi" + IP beyaz listesi ister; portaldan değil MNG müşteri temsilcisinden
  açılır. Sunucu IP'si 138.199.218.72 (panel buradan çağıracak). AÇIK: temsilciye talep → yetki gelince prova tekrar.
- Yetki açıldı (MNG, aynı gün): sunucudan canlı prova TAM BAŞARILI — createOrder → getorder (isTransformedToShipment 0)
  → createbarcode ilk 15 sn'de 20001 "VARIŞ ŞUBESİ BULUNAMADI, DAHA SONRA TEKRAR DENEYİN", ~31-46 sn sonra OK:
  shipmentId 195991365254, invoiceId RZ880714, barcodes[0].barcode "D@53BH21RZ13CKAAA6J", value = ZPL 2560 kr
  (^PW831 ^LL959 → 104x120 mm) → getshipmentstatus kod 1 "Gönderi_Hazırlandı", trackingUrl
  https://kargotakip.dhlecommerce.com.tr/?takipNo=<shipmentId> → cancelshipment {referenceId, shipmentId} 200 →
  cancelorder 200. getshipment/trackshipment hareket yokken 404. Kapıda ödeme alt sınırı 20 TL (20001 ile red).
- MNG entegrasyon yazısı: iki aşama bilinçli (createOrder siparişte, createbarcode paketlemede), ardışık çağrı
  varışsız hatası verir; barkod kalitesi için 10x10 rulo MNG'den ya da lamine; iptal: barkod sonrası cancelshipment.
- Kod buna göre yeniden düzenlendi: durum 'siparis_acildi' (createOrder OK, barkod yok) → takip işi (5 dk,
  BARKOD_BEKLEME 45 sn) barkod_al; etiket basımı anlık barkod_al(bekle=True); 20001 "varış şubesi" geçici
  (client.sube_cozulmedi), diğer 20001'ler kalıcı → hata; kayit_iptal shipment_id varsa cancelshipment + cancelorder;
  KAPIDA_ODEME_MIN 20; TAKIP_URL_SABLON dhlecommerce; `mng_kargo/etiket.py` ZPL → PNG (Labelary, önbellekli) +
  `/kargo-gonderi/<id>/etiket` 104x120 mm yazdırma sayfası (templates/kargo_gonderi_etiket.html) + ZPL indirme;
  değişim/manuel kartlarında "MNG Etiket" düğmesi. 68 test geçti. Deneme kayıtları MNG'de iptal edildi.
- Canlı Shopify adres verisi (son 50 sipariş): province sık BOŞ ya da çöp ("Bir seçenek belirleyin…"), city serbest
  ("EyÜpsultan", "İZMİT/KOCAELİ", "Bursa yenişehir", "Tr.03416", "39afyonkarahisar"), zip bazen telefon. Çözüm:
  adres.alici_kur il sırası province → city'de il adı → posta kodu plakası (PLAKA) → adres metni; `mng_kargo/cbs.py`
  MNG getcities/getdistricts önbelleği (uploads/mng_cbs.json, 7 gün) ile ilçeyi MNG listesinden eşler ve kodları
  doldurur (_istek_kur içinde, başarısızsa adlarla devam). MNG il adları farklı (AFYON, İÇEL yok → MERSİN).
- Shopify kapıda ödeme: yalnız gateway COD VE displayFinancialStatus != PAID ise tutar gönderilir
  (shopify_tarama.kapida_odeme_mi; 'manual' sayılmaz). Ödenmemiş ve COD olmayan sipariş kargoya açılmaz.
