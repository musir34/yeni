# 2026-09-28 — WhatsApp bildirim alıcı dağılımı

## Ne değişti
- `whatsapp_alici.py` (yeni): hangi bildirim türü hangi numaraya gider. Kayıt
  `PlatformConfig('whatsapp_alici_ayar').extra_config["alicilar"]` içinde, anahtar numaranın
  son 4 hanesi: `{"0953": {"ad": "Mağaza", "olaylar": [...]}}`. Migration yok.
- `/whatsapp-duyuru` sayfasına "Bildirim Alıcıları" tablosu (ad + 6 olay kutucuğu) ve
  `POST /whatsapp-duyuru/api/alicilar` eklendi (admin + 2FA + fetch kalkanı).
- Soru bildirimleri (Shopify + Trendyol) artık `alicilar("soru")` listesine gider.
- Duyuru formunda alıcılar adlarıyla görünür; "Duyuru" sütunu varsayılan işareti belirler.
- `whatsapp_notify` async işlevlerine `only_last4` parametresi eklendi.

## Kararlar (komutan, 2026-09-28)
- Yönetim yeri: kullanıcı yönetimi DEĞİL, ayrı ekran. Neden: mağaza hattı panel kullanıcısı
  değil; mail abonelikleriyle karışmasın.
- İlk dağılım (`ILK_DAGILIM`, DB kaydı yokken geçerli): üretim siparişi + iptal → Ahmet (…0104);
  soru + gecikme + geciken → Mağaza (…0953); duyuru → ikisi.

## Davranış notları
- Olay anahtarları: uretim_siparis, uretim_iptal, soru, gecikme_uyarisi, geciken_siparis, duyuru.
- Numaraların kendisi hâlâ .env'de (WHATSAPP_STAFF_NUMBERS); ekrandan numara eklenmez.
  .env'e yeni eklenen ve dağılımda olmayan numara TÜM olayları alır (ekrandan daraltılır).
- Dağılım okunamazsa (DB hatası) bildirim kaybolmasın diye ilk dağılıma / herkese düşer.
- Alıcı çözümü thread başlamadan, çağıranın app context'inde yapılır.

## Henüz bağlanmayan olaylar
uretim_siparis, uretim_iptal, gecikme_uyarisi, geciken_siparis — tabloda sütunları var ama
tetikleyici kod yok (şablon onayı, gecikme eşiği/sıklığı, yedek görsel bekleniyor).

## Ek (aynı gün) — tek sayfa + menü
- Komutan emri: WhatsApp ile ilgili her şey tek sayfadan yönetilsin.
- Üst menü Kullanıcı açılırına "Mesajlar" bölümü eklendi → "WhatsApp Mesajları" (admin'e özel).
- Sayfa başlığı "WhatsApp Mesajları" oldu; bölümler: Mesaj Gönder, Bildirim Alıcıları, altta
  /whatsapp-baglanti linki. Adres aynı kaldı: /whatsapp-duyuru (yer imi bozulmasın diye).
- İleride eklenecek WhatsApp ayarları (gecikme eşiği/sıklığı vb.) BU sayfaya kart olarak eklenmeli.

## Ek (aynı gün) — tasarım panel düzenine çekildi
- Komutan: sayfalar mevcut panel tasarımına uygun olmalı. İlk sürüm dar (760px) ortalı, yeşil
  düğmeli, Anasayfa düğmesiz bir düzendi; panelle uyumsuzdu.
- Örnek alınan desen: `kargo_mutabakat.html` / `user_logs.html` → üstte "Anasayfa" düğmesi + h3
  başlık + soluk alt başlık; `card` + `card-header fw-bold`; 12px köşe + hafif gölge;
  ana eylem `btn-primary` (marka gül rengi), ikincil kayıt `btn-sm btn-success`; tam genişlik,
  `row` / `col-lg-*` iki sütun; iç içe `.container` YOK (base.html zaten sarıyor).
- Uygulanan: `whatsapp_duyuru.html` (Mesaj Gönder sol, Bildirim Alıcıları sağ) ve
  `whatsapp_baglanti.html` (yalnız kabuk; Meta bağlantı akışı/JS değişmedi).
- Doğrulama: şablon gerçek base.html + gullu-common.css ile statik HTML'e basılıp başsız Chrome
  ile ekran görüntüsü alındı (masaüstü). Mobil görüntü başsız Chrome'un asgari pencere
  genişliği yüzünden güvenilir değil; gerçek cihazda bakılmalı.
