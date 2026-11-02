# 2026-11-02 — Gelen Yorumlar: 100'erli sayfalama

- Komutan emri (agentation geri bildirimi): /gelen-yorumlar gönderim listesi ve yorumlar 100'erli sayfa sayfa.
- gelen_yorumlar.py: SAYFA_BOYU=100, `_sayfala` / `_sayfa_no`; parametreler `sayfa` (gönderimler), `ysayfa` (yorumlar).
  Servis/SQL değişmedi (liste zaten tümü çekiliyor, dilimleme rotada). Taşan/bozuk sayfa no → 1 ya da son sayfa.
- Sekme rozetleri artık toplam sayıyı gösterir (satir_toplam / yorum_toplam), sayfadaki adedi değil.
- İade Edildi formu sayfa/ysayfa/filtre taşır → işaretlemeden sonra aynı sayfaya dönülür.
- Şablon: `sayfalama` makrosu (Önceki/Sonraki, ilk-son + ±2, … boşluk). DB değişikliği yok. Deploy bekliyor.
- Ek (aynı gün): mobil uyum. Tablo kendi CSS'inde `.gy-table td {white-space:nowrap}` + mobile.css → telefonda taşma.
  ≤767px: satır kırar; Müşteri/E-posta/Gönderim/İlk bakış/Yorum tarihi `d-none d-md-table-cell`, bilgileri Sipariş
  hücresi altında `d-md-none gy-mobil-bilgi`; sayı kutuları/yorum kartı dolgusu küçüldü, Hepsi/Yalnız yorum düğmeleri
  tam genişlik; <576px `.gy-sayfa .row` gutter .75rem. Masaüstü değişmedi (1300px'te doğrulandı). Commit bekliyor.
