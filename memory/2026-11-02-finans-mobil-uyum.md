# 2026-11-02 — Finans sayfaları mobil uyum

Komutan emri: finans'ı çoğunlukla telefondan kullanıyor; tüm sayfa/alt sayfalar mobile uygun olsun.

Kök neden (canlıda 390px ölçüldü): `static/css/mobile.css:166` telefonda TÜM `.table`lara `white-space: nowrap`
veriyor → finans tabloları 400–1700px'e uzuyor, panelde sayfa yana taşıyordu (scrollW 498 > 382). Ayrıca
mobile.css `.container{padding:6px}` + `.row` negatif payı 4px taşma yapıyordu. mobile.css'e DOKUNULMADI (tüm panel).

Yapılan (yalnız finans şablonları; masaüstü görünümü değişmedi, 1200px'te doğrulandı):
- `_finans_nav.html` <style> içine `@media (max-width: 767.98px)` bloğu: fn-table satır kırar, tutar/aksiyon nowrap,
  sekmeler tek satır yatay kaydırma (Defter dropdown'ı `data-bs-popper-config` strategy fixed), `.fn-filtre` başlık
  formu, `.fn-rapor` sabit ilk sütun, `.fn-kalem-tablo` (Mal Girişi/Satış) ve `.fn-kart-tablo` (kart ekstre önizleme)
  telefonda grid kartlara döner, kart içi `.d-flex.justify-content-between` yan yana kalır; <576px'te finans
  `.row` gutter .75rem (`.container:has(.fn-tabs)`).
- Tablolarda ikincil sütunlar `d-none d-md-table-cell`, bilgileri ana hücre altında `d-md-none fn-mobil-bilgi`
  satırında; defter/cari defterde telefona özel tek "Tutar" sütunu. colspan'lı başlık/toplam satırları için
  masaüstü (colspan) + telefon (tek hücre) ikilisi.
- Panel: <576px'te "Bu ay" tutarları ve hesap kartları küçültüldü (Kalan kesiliyordu).
- Formlar: defter düzelt, mal girişi tarih/açıklama, düzenli ödeme ekle/düzenle alanları telefonda col-12.
- Doğrulama: yerel önizleme sunucusu (gerçek şablon + static, sahte veri, DB yok) ile 390px'te tüm sayfalar
  scrollW == genişlik; görsel kontrol. Canlıda değil. Deploy bekliyor.
