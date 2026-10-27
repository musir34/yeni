# 2026-10-27 — Kargo Gönderileri: tarihe göre sıralama + mobil kart düzeni

**İstek:** /kargo-gonderi en yeni sipariş üstte sıralansın; telefonda çok karışık görünüyor.

## Değişiklik
- `mng_kargo/routes.py` liste: `order_by(id.desc())` → `order_by(olusturuldu_at.desc(), id.desc())`
  (kayıt kimliği yerine oluşturulma tarihi; geri doldurulan/yeniden açılan kayıtlar da doğru sıraya girer).
- `templates/kargo_gonderi.html`: masaüstü aynı; `max-width: 767.98px` altında tablo satırı karta dönüşür.
  - Hücreler `data-label` taşır, `td::before` ile etiket solda, değer sağda.
  - Boş hücreler (`-` olan il/ilçe, takip no, kapıda ödeme, son sorgu, hata) mobilde `kg-m-gizle` ile gizlenir.
  - İşlem hücresi (`kg-islem`) alt bant: düğmeler parmak boyunda; yalnız adres düzeltme formu (`kg-adres`)
    tam genişlik (il/ilçe/adres alt alta, yeniden dene düğmesi tam satır).
  - `mobile.css` ≤767px `.table { white-space:nowrap }` kuralı kart içinde `white-space:normal !important` ile açıldı.
- Doğrulama: örnek kayıtlarla render edilip 390 px iframe'de ekran görüntüsüyle kontrol edildi (masaüstü değişmedi).
- Deploy: `git pull && systemctl restart gullupanel.service` (şema yok).
