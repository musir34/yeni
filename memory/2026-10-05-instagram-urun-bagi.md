# Instagram yorumlarında AI ürün tespiti + fiyat/bağlantı (2026-10-05, yerelde, commit/deploy yok)

Komutan isteği: "fiyat nedir" gibi yorumlarda yapay zekâ ürünü tespit edip fiyatı ve bağlantıyı hazırlasın;
gönderimi kendisi onaylayacak ("ben onaylarım, o düzgün hazırlasın yeter").

- Sorun: yorum ürünü söylemez, gönderi açıklaması da model kodu içermez. Çözüm: GÖNDERİ bir kez site
  ürününe + rengine bağlanır (`InstagramMediaProduct`, tablo `instagram_media_products`, additive).
- `trendyol_qna/instagram_urun.py` (yeni): Shopify'dan `urun_ara`, `urun_getir`, `katalog` (176 aktif ürün,
  10 dk bellek); `bagla` / `bagi_kaldir`; `urun_baglami` (taslak istemine canlı fiyat + stoktaki numaralar +
  ürün sayfası); `oner` (AI, gönderi açıklaması + katalogdan ürün/renk seçer, ONAYSIZ kaydeder).
- Fiyat kaynağı: SİTE (Shopify varyant fiyatı), bağlantı gullushoes.com ürün sayfası. Shopify'da varyant başlığı
  "Renk / Beden"; aynı üründe renkler farklı fiyatlı olabiliyor → bağ renk de taşır ('' = tüm renkler).
- Kural: onaysız AI önerisi taslağa fiyat olarak GİRMEZ; istem "fiyat/bağlantı yazma, netleştir" der.
  Kullanıcının onayladığı bağ sonraki AI önerisiyle ezilmez.
- Akış: yeni yorum düşen gönderi bağsızsa AI öneri üretir (gönderi başına süreçte tek deneme); kartta
  "AI önerisi … [Doğru, onayla]". Onaylanınca o gönderinin bekleyen yorumlarının taslakları (en çok 15)
  yeniden üretilir; sonraki yeni yorumlara taslak kendiliğinden gelir.
- `qna_routes.py`: `/soru-cevap/api/instagram-yorum/urun-ara` (GET), `/urun-bagla` (POST; `kaldir` ile siler).
- `soru_cevap.html`: karta ürün şeridi (bağsız / AI önerisi / onaylı) + ürün arama paneli.
- Doğrulama: 36 test (yalıtılmış), ürün arama + katalog gerçek Shopify verisiyle salt-okunur denendi, kart
  üç haliyle önizlemede görüldü. AI önerisinin isabeti ve taslak kalitesi CANLIDA DENENMEDİ.
- Kapsam dışı: DM'lerde ürün tespiti (düz "fiyat?" mesajında AI hâlâ hangi ürün olduğunu sorar).

## Düzeltme (aynı gün, yayından sonra fark edildi)
- AI ürün önerisi yalnız YENİ yorum düşünce tetikleniyordu; özellik açılmadan önce düşmüş bekleyen yorumların
  gönderilerine hiç öneri üretilmiyordu (kartta hep "bağlı değil"). `sync_comments` artık her turda
  `_bagsiz_bekleyen_gonderiler()` ile bekleyeni olup bağı olmayan gönderileri de öneriye veriyor
  (tekrarı `oner_async` süreç içinde süzer). 37 test. Bu düzeltme 1790a4c yayınında YOK; ayrı commit+deploy bekliyor.

## Mesajlara (DM) elle ürün bağlama (aynı gün, yerelde)
- Komutan: "DM'dekine ürünü ben vereyim." Mesajın bağlı olduğu gönderi olmadığından AI önerisi YOK; ürünü
  kullanıcı konuşmaya elle bağlar.
- Ayrı tablo/kolon açılmadı: bağ `InstagramMediaProduct`'ta `media_id = "conv:<konuşma id>"` anahtarıyla tutulur
  (`instagram_urun.konusma_anahtari`). Gerçek gönderi kimlikleri yalnız rakam olduğundan çakışmaz.
- `/soru-cevap/api/instagram/urun-bagla` (bağla/kaldır; bekleyen konuşmanın taslağını ürün bilgisiyle yeniden üretir).
- Mesaj kartında yorum kartındaki ürün şeridinin aynısı (`yorumUrunHtml` uç ve "gönderi/konuşma" sözcüğü parametreli)
  + onaylı bağda "Kaldır" düğmesi (yorum kartında da). Yorumda bağ kaldırılınca o gönderinin hazır taslakları sıfırlanır.
- Bağ konuşmada kalır; sonraki müşteri mesajlarının taslağı da o ürünle gelir.
- 38 test. Mesaj kartındaki şerit tarayıcıda GÖRÜLMEDİ (yalnız JS sözdizimi denetlendi; aynı bileşen yorum kartında görüldü).

## Ürün bağlanınca cevap kutusu hemen dolar (aynı gün, yerelde)
- Komutan ürünü bağlayıp kendi yazdığını gönderdi; müşteriye yalnız yazdığı gitti, ürün bilgisi eklenmedi.
  Sebep: bağ yalnız AI taslağını besliyordu (taslak 1–2 dk sonra, o da kutu "dirty" ise hiç görünmüyordu).
- Çözüm: `instagram_urun.hazir_metin` — AI'sız, siteden canlı okunan "ürün (renk) fiyatı X. Stokta olan
  numaralar: … / Detaylar ve sipariş için: <bağlantı>" metni. `urun-bagla` uçları `urun_metni` döndürür;
  `urunBagla` (soru_cevap.html) bunu cevap kutusuna yazar: kutu boşsa "Merhaba," ile, doluysa yazılanın
  sonuna; aynı bağlantı zaten yazılıysa eklemez. Kullanıcı gönderilecek metni kutuda GÖRÜR (gizli ekleme yok).
- Doğrulama: 39 test; önizlemede dört durum (boş kutu, yazılı kutu, bağlantı zaten var, DM kartı) sahte
  sunucuyla denendi. Canlıda denenmedi; commit+deploy bekliyor.

## Bağlantı gönderimde garanti + eski sayfa kendini yeniler (aynı gün, yerelde)
- Komutan f7da975 yayınından sonra da "mesajda ürün linki gitmedi" dedi. Sunucu parçası sağlamdı (51 ürün/renk
  bileşiminde hazır metin bağlantılı üretildi). Açık: metin kutuya yalnız BAĞLAMA ANINDA yazılıyordu; ürün
  önceden bağlıysa (ya da sekme eski ekran koduyla açıksa) kutuya hiçbir şey düşmüyor, mesaj bağlantısız gidiyordu.
- Çözüm 1 (kök): `instagram_dm.urun_baglantisi_ekle` — onaylı bağın adresi metinde yoksa `answer_conversation`
  ve `answer_comment` GÖNDERİRKEN sona ekler ("Detaylar ve sipariş için: <url>"). Adres tablodan okunur
  (Shopify çağrısı yok). Onaysız öneri eklemez; yorum notuna eklenmez. Kartta bunu söyleyen satır var.
- Çözüm 2: onaylı şeritte "Fiyatı kutuya yaz" düğmesi (`yalniz_metin` → yeniden bağlamadan hazır metni kutuya yazar).
- Çözüm 3: `qna_routes.sayfa_surumu` (şablon dosyasının değişim zamanı) sayfaya ve liste cevabına konur; farklıysa
  ve yazılmakta olan cevap yoksa sayfa kendini yeniler. Bugün iki kez "eski sekme" yüzünden yanlış görüntü oldu.
  Bu sürümden ÖNCE açılmış sekmeler bir kez elle yenilenmeli.
- 41 test. Canlıda denenmedi; commit+deploy bekliyor.
