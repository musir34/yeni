# AI asistanı: görsel ekleri + sürükle-bırak + yapıştırma (2026-10-14)

**Sorun:** Asistana yalnız Excel/CSV/PDF eklenebiliyordu (metne çevrilip soruya iliştirilir);
görsel bilerek yoktu. Komutan görsel + sürükle-bırak istedi.

**Ne değişti**
- `ai_asistan/blueprint.py`
  - `GORSEL_UZANTILAR` (.png .jpg .jpeg .webp .gif) + dosya imzası kontrolü (`GORSEL_IMZALAR`).
  - Görseller soru başına geçici klasöre yazılır (`gorsel_klasoru_olustur` → `mkdtemp
    gullu_ai_gorsel_*`), güvenli adla (`gorsel1.png`…). Dosya adı/uzantısı `_dosya_adi_uzanti`.
  - `_claude_calistir(..., gorseller)`: `--allowedTools` listesine YALNIZ o klasör için
    `Read(//klasor/**)` kuralı + `--add-dir klasor`. Sunucuda doğrulandı (2026-10-14): 96x96
    PNG "OKUDUM red", aynı çağrıda `.env` → "ENV-OKUYAMADIM". Codex: `-i` (images=) ile.
  - `_ai_calistir` / `_codex_sql_dongusu` görsel listesini geçirir.
  - `sor()` ikiye bölündü: doğrulama + `_soruyu_kuyrukla(...)`. Klasör sahipliği:
    thread başlayınca `devir["thread"]=True` → thread `finally`'de siler
    (`gorsel_klasoru_sil`); 400/hata ile dönen yollarda `sor()` siler.
  - Soruya "Kullanıcının eklediği görseller" bölümü (ad → yol listesi); sohbet geçmişinde 🖼️ ad.
- `templates/ai_asistan.html`: accept listesi görsel dahil; ortak `dosyaEkle()`;
  sürükle-bırak (`.ai-chat` üstünde `.surukle` vurgusu, pencere düzeyinde varsayılan açma
  engeli); `paste` ile panodaki ekran görüntüsü `yapistirilan-<ts>.png` adıyla eklenir;
  görsel çipinde küçük önizleme.

**Sınırlar:** en fazla 3 dosya, dosya başına 10 MB (nginx `client_max_body_size` 10M olan
sunucu bloğu varsa toplam istek de 10M'ı geçmemeli). GIF ilk kare olarak görülür.

**Doğrulama:** py_compile, Jinja parse, `node --check`; sunucuda canlı claude izin testi.
Panelden uçtan uca deneme deploy sonrası (ekran görüntüsü yapıştırıp "bu nedir?" sor).

**Durum:** yerelde, commit/deploy bekliyor (`git pull && systemctl restart gullupanel.service`).

**2026-10-14 ek: küçük sohbet kutusu (widget).** `templates/includes/ai_widget.html` (her sayfada sağ altta yüzen asistan) aynı yetenekleri aldı: ataş düğmesi + gizli dosya girişi, ek çipleri (`.aiw-ekler`), panel üzerine sürükle-bırak (`#aiw-panel.surukle`), yapıştırma (yalnız panel açıkken ve odak panelde/boştayken; sayfadaki formlara karışmaz), dosya varsa FormData ile `/ai-asistan/sor`. Sunucu tarafı ortak, ek kod yok.
