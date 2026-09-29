# 2026-09-28 — WhatsApp: üretim + iptal + gecikme bildirimleri bağlandı

Meta'da 5 olay şablonunun hepsi AKTİF (28 Eyl). Bu notla birlikte tüm otomatik bildirimler bağlı.

## Üretim siparişi / iptal (uretim_modu.py)
- `_wa_personel_bildirimi(olay, order_number, model_kodlari, eslesen)` eklendi; mevcut mail ve
  whatsapp_service (şirket hattı) bloklarına DOKUNULMADI, onların ardından ayrı try ile çağrılır.
- Dedupe yeni eklenmedi: üretim siparişi kaydı bir kez açıldığı, iptal `iptal_mail_at` ile
  damgalandığı için bildirim de bir kez gider.
- `uretim_siparisi` şablonu görsel ZORUNLU: ilk kalemin Product.images ilk URL'si (yalnız https).
  Görsel yoksa yedek logo yerine genel `gullu_bildirim` şablonuyla gider → logo dosyasına gerek kalmadı.
- Çok kalemli siparişte tek mesaj: ilk kalem + "(+N kalem daha)", adet toplam.
- Müşteri adı bildirime konmaz.

## Gecikme (whatsapp_gecikme.py + app.py job `whatsapp_gecikme`)
- Komutan kararı: saat başı, yalnız yeni girenler; uyarı eşiği 4 saat.
- Cron 08:00–20:00 (İstanbul) saat başı. Gecikme tanımı panelle aynı (overdue_orders: Yeni /
  Hazırlanıyor / İşleme Alındı + coalesce(agreed_delivery_date, estimated_delivery_end) vs utcnow).
- Dedupe: PlatformConfig('whatsapp_gecikme_kayit').extra_config {"uyari": {no: iso}, "geciken": {...}};
  30 günden eski kayıt budanır. Migration yok.
- Gönderim başarısızsa ya da alıcı yoksa kayıt YAZILMAZ → sonraki saat yeniden denenir.
- Şablon değişkeni 200 karakter: listede ilk 12 sipariş + "(+N sipariş daha)"; sayı tamdır.
- İLK ÇALIŞMADA o an gecikmiş tüm siparişler tek mesajda bildirilir (kayıt boş olduğu için).

## Doğrulanmayanlar
- Canlı DB'de çalıştırılmadı (lokalde tünel kapalı); sorgu derlemesi + birim testleri geçti (46).
- Görselli şablonla gerçek gönderim denenmedi. Meta görseli indiremezse hata yalnız webhook'a
  düşer, panel "kabul edildi" görür → ilk gerçek üretim siparişinde telefondan teyit gerekli.

## 2026-09-29 — Üretim siparişi görselli şablonla gitmiyordu
- Belirti: komutan üretim bildiriminin `uretim_siparisi` (görselli) şablonuyla gelmediğini bildirdi.
- Şablon adı/dili kodda doğruydu (`uretim_siparisi`, `tr`). Asıl neden görsel adresi: `_wa_urun_gorseli`
  yalnız `https://` ile başlayan Product.images değerini kabul ediyordu; göreli (`/static/images/..`),
  `http://` ya da boş değerde sessizce genel `gullu_bildirim` şablonuna düşüyordu.
  (Canlı veriyle doğrulanamadı: tünel kapalıydı; teşhis kod okumasına dayanıyor.)
- Düzeltme (uretim_modu.py): `_wa_gorsel_adresi` — http→https, göreli yol → `PANEL_BASE_URL`
  (varsayılan https://gullupanel.com) ile tamamlanır, yalnız JPG/PNG kabul (Meta webp/gif almaz);
  Product.images uygun değilse `static/images/<barkod>.jpg|jpeg|png` dosyasına bakılır.
- Genel şablona düşüşte artık log yazılır: "[URETIM] <no>: görsel yok, ... genel şablonla gidiyor".
- Doğrulandı: gullupanel.com/static girişsiz erişilebilir (check_authentication muaf).
