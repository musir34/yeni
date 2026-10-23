# 2026-10-23 — Üretim modu: renk bazlı kapsam + anasayfa kartında renkler

## Ne değişti
- `uretim_modu.py`: ayar torbasına `renkler` haritası; `set_model_renkler`, `get_uretim_renkler`, `model_renkleri`; `get_uretim_barcodes` renk kısıtını uygular; `toggle_model` çıkarırken renk kaydını siler.
- `uretim_routes.py`: `GET /uretim/api/model-renkler`, `POST /uretim/api/model-renk-kaydet`.
- `templates/uretim.html`: ayar bölümünde renk seçici (Ekle + çipte 🎨), çipte renk kapsamı yazısı.
- `templates/product_list.html`: ⋮ Üretim Modu düğmesi renk seçen pencere açar; çıkarma pencereden.
- `uretim_gorevi.py` + `templates/home.html`: kartta model altında ürün adı yerine üretime dahil renkler.

## Neden
Komutan emri: model üretim moduna alınırken tüm renkler ya da seçilen birkaç renk; anasayfa kartında renkler görünsün.

## Notlar
- Şema/migration yok; renk alanı olmayan mevcut kayıtlar "tüm renkler" sayılır.
- Seçilmeyen rengin barkodu sabit 10 almaz, gerçek stokla gider; o renge gelen sipariş üretime düşmez.
- Önceden açılmış üretim kayıtları renk daraltılınca silinmez, listede kalır.
- Test: tests/test_uretim_renk_kapsami.py (8 test, geçti).
