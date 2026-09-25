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
