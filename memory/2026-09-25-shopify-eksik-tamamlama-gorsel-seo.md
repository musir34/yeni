# 2026-09-25 — Ürün Yükleme: Shopify eksik tamamlama + görsel SEO + prompt ayrımı

Komutan emri: "Trendyol'da model seçilir, motor barkodları Shopify'da kontrol eder,
olmayanları renk ve görsel olarak ayırır. SEO çok önemli: her görsele ayrı ALT,
görseller Google'da listelensin; Shopify için Google uyumlu, Trendyol için Trendyol'a
uygun içerik." Fiyat: sitedeki kardeş varyanttan (formdan değil).

## Ne değişti

**1. Eksik tamamlama modu (Shopify)** — `urun_yukleme/shopify_urun.py`
- `sitedeki_barkodlar(barkodlar)`: Trendyol haritasındaki barkodları Shopify'da
  toplu tarar (40'lık `barcode:X OR ...` parçaları, bire bir doğrulama). Döner:
  pid/handle/title + {barkod: pid}. Birden çok ürüne dağılmışsa çoğunluk + uyarı logu.
- `eksik_tamamla(taslak, form, renk_gorselleri)`: sitedeki ürüne YALNIZ olmayan
  (renk, beden) varyantlarını ekler. productSet tam-set yazımı yerine additive uçlar:
  `productOptionUpdate(optionValuesToAdd)` → `productUpdate(media)` (yeni renk
  görselleri, AI ALT ile) → `productVariantsBulkCreate` (fiyat kardeş varyanttan,
  SKU/barkod Trendyol standardı, stok formdan) → `productVariantAppendMedia`
  (yeni renk: yeni bloğun ilk görseli; mevcut renge yeni beden: rengin mevcut kapağı).
  Fark CANLI barkod listesinden hesaplanır. İdempotent tekrar: mevcut seçenek değeri
  yeniden eklenmez, aynı ALT'lı görsel yeniden yüklenmez (yarım kalan deneme dersi).
  Fark yoksa `varyant: 0` + mesaj (UI sarı bant).
- `gorsel_alt(taslak, renk, i, varsayilan)`: AI ALT varsa o, yoksa şablon; `urun_ac`
  da artık bunu kullanıyor.

**2. Taslak akışı** — `urun_yukleme/routes.py` `_taslak_worker`
- Mevcut model (harita) + shopify hedefi → `sitedeki_barkodlar`; pid varsa
  `site_eksik` modu: "tüm renkler/bedenler formda olmalı" güvenceleri ATLANIR (ekleme
  var, silme yok). Tarama düşerse taslak ÜRETİLMEZ (tam-set moduna sessiz düşüş
  mevcut ürünü yeniden yazardı).
- `taslak.shopify = {"mod":"eksik", mevcut_pid/handle/baslik/url, eksik_renkler,
  eksik_varyantlar, sitede_var}`; `taslak.site` revizyon (Düzelttir) için saklanır.
- AI: Trendyol (`metin_uret`) ve site (`site_metin_uret`) AYRI promptlar, paralel
  (ThreadPool 2). Eksik modda site metni üretilmez (sitedeki metne dokunulmaz).
- ALT: `alt_uret` renk başına paralel (ThreadPool 3); tam modda tüm renkler, eksik
  modda yalnız sitede olmayan renkler; revizyonda önceki ALT'lar korunur.
  `taslak.renkler[renk].alt = [...]` (görsel sırası).
- `_bilgi_kur` artık `gorseller: {renk: [tüm yollar]}` veriyor (ilk görsel listesi
  `gorsel_yollari` aynı kaldı).

**3. Yükleme** — `_yukle_worker`
- CDN dosya adı SEO'lu: `model-urunadi-slug-renk-sira.jpg`; `cdn_yukle(altlar=)` ile
  dosya kütüğü ALT'ı da yazılır.
- Eksik + yalnız site hedefinde sitede zaten olan renklerin görseli CDN'e gitmez.
- `sh.mod == "eksik"` → `eksik_tamamla`, değilse `urun_ac`.
- `/api/yukle`: eksik modda H1/SEO denetimi yok (mevcut_pid şart); önizlemeden
  gelen `alt` düzeltmeleri kabul edilir.

**4. AI metin** — `urun_yukleme/ai_metin.py`
- Trendyol promptundan `shopify_blok`/`genel` çıkarıldı (yalnız Trendyol kuralları).
- `KURALLAR_SITE` + `_site_prompt` + `site_metin_uret`: Google SEO kuralları (doğal
  Türkçe, yığma yasak, H1 50-70, SEO başlık 50-60 " - Güllü Shoes", meta 140-160 +
  CTA, renk başına BENZERSİZ 40-70 kelimelik paragraf `renk_bolumleri`).
- `shopify_aciklama_kur(..., renk_bolumleri)`: "Renk Seçenekleri" altına renk başına
  `<h4>` bölümü (sitede SEO başlık/meta üründe TEK olduğundan renk bazlı Google
  görünürlüğü buradan + ALT + renk-* etiket koleksiyonlarından gelir).
- `KURALLAR_ALT` + `alt_uret(renk, yollar, urun_adi)`: claude yolu görselleri Read
  ile açıp her birine 60-125 karakter benzersiz ALT yazar; codex/hata → `alt_sablon`
  (açı şablonu: önden/yandan/arkadan/topuk...). Yükleme asla bloklanmaz.
- `_claude_calistir/_run_ai` `kurallar` parametresi aldı (sistem promptu seçilir).

**5. Şablon** — `templates/urun_yukleme.html`
- Önizleme: eksik modda H1/SEO editörü yerine "Eksik Tamamlama" kartı (sitedeki ürün
  linki, eksik renkler, eklenecek varyantlar, sitede olanlar).
- Renk kartında görsel başına düzenlenebilir ALT satırları (küçük resimli,
  `altThumbYukle`); yüklemede `renkDuzeltme[renk].alt` gönderilir.
- Sonuç: "sitedeki ürüne N varyant eklendi (yeni renk/beden)", fark yoksa sarı bant.
- Aktar yardım metnine eksik tamamlama satırı.

## Test
`tests/test_urun_yukleme_shopify_eksik.py` (7 test, Shopify sahte): barkod tarama,
yalnız eksikleri ekleme (seçenek/medya/varyant/kapak/fiyat kanıtı), fark yoksa
göndermeme, yarım kalan deneme tekrarı, ALT yedek, renk bölümleri.

## Notlar / riskler
- Yeni medya sırası varsayımı productSet'teki `_kapaklari_ata` ile aynı (girdi sırası).
- Codex motoru görsel açamaz → ALT şablona düşer; görsel-bazlı ALT için claude motoru.
- ALT üretimi renk başına ayrı claude çağrısı (≤8 görsel): taslak süresi uzar
  (UI zaman aşımı 6 dk).
- Deploy: `git pull && systemctl restart gullupanel.service` (migration yok).

## Canlı test ekleri (aynı gün, 011 dersleri)
- **app_context**: ThreadPool iş parçacıkları Flask bağlamını devralmaz → `_baglamli(app, fn)` sarmalı (043bfb4).
- **Beden birleşimi**: Getir bedenleri tüm renklerin birleşimi doldurur; buçuğu olmayan renklerde "yeni varyant" çıkıp önek-dolu (730734) hatası veriyordu. Yalnız-site hedefinde Trendyol'daki rengin Trendyol'da olmayan bedenine barkod TAHSİS EDİLMEZ, ikili atlanır (boş barkod = her yerde atla), uyarı bandı (5d1a601). "İkisi" hedefinde eski davranış (buçuk ekleme tahsis alır). NOT: 730734 öneki dolu — Stiletto'ya yeni model/buçuk için yeni önek gerekecek.
- **Görseller Trendyol'dan indirilmez** (varsayılan): kalite düşük, kullanıcı her renge kendi görselini yükler; Getir yanında "Görselleri de Trendyol'dan indir" kutusu (`gorseller_indir`).
- **Kapaksız mevcut renkler**: `site_kapaksiz_renkler(pid)` → sitede hiçbir varyantına görsel bağlı olmayan renkler; taslakta `shopify.kapaksiz_renkler` + `kapak_atanacak` (görseli yüklenenler). `eksik_tamamla` bu renklerin görsellerini galeriye ekleyip TÜM varyantlarına kapak atar (varyant/metin dokunulmaz); ALT üretimi bu renkleri de kapsar. 011'de tüm renkler kapaksızdı → vitrin hepsinde siyahı gösteriyordu.
- **Beden sırası**: sitede beden sırası = seçenek değeri sırası; tam yüklemede `bedenleri_sirala` (35, 35,5, 36 ...), eksik tamamlamada yeni beden eklenince `productOptionsReorder` ile tüm liste sayısal sıraya (f36b72f). Sıra zaten doğruysa çağrı yok.
- **011 sıfırdan**: sitede tek 011 ürünü (gid 8992676937906, 213 varyant, hepsi stok 5 = ShopifyMapping hiç kurulmamış). Silme (arşiv DEĞİL: barkod taraması arşivliyi de bulur) → Getir → 18 renge görsel → AI → Onayla → Shopify sayfasında "Barkod Eşleştir" (tabloyu baştan yazar) + stok gönder → eski handle'a 301: `011-sivri-burun-stiletto-kavisli-yan-dekolteli-ince-topuklu-kadin-ayakkabi-vegan-deri-ve-hafizali-ped`.
- **009 dersi kapatıldı (kullanıcı emri "009 dersi olmasın")**: eksik modda KAPAKLI mevcut renge yüklenen görsel = "ek görsel": galeriye eklenir, kapak değişmez, `_galeri_bloguna_tasi` (productReorderMedia, hamleler sırayla → simülasyonla hesaplanır) yeni görselleri o rengin kapağının hemen arkasına taşır. Taslakta `shopify.ek_gorsel_renkler`. `_yukle_worker` görsel şartı yeniden tanımlandı: ŞART = Trendyol'a yeni varyant gidecek renkler + sitede yeni açılacak renkler (tam yüklemede tümü); eksik modda diğerleri isteğe bağlı (Getir görsel indirmediği için mevcut renklere görsel zorlanmaz — İkisi hedefinde yeni renk eklerken 18 renge görsel istenmez).
