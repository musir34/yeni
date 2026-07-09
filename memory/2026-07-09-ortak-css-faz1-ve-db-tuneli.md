# 2026-07-09 — Şablon Ortaklaştırma Faz 1 + DB Tüneli

## Şablon ortaklaştırma Faz 1 (tamamlandı, commit bekliyor)

75 şablonun çoğu kendi CSS kopyasını taşıyordu (~9.700 satır inline CSS; `:root` marka bloğu onlarca dosyada kopyaydı, 4 farklı "başarı yeşili" tonu sapmıştı). Bugün ortaklaştırma başlatıldı ve Faz 1 bitti.

**Yapılan:**
- `base.html`'in 213 satırlık inline `<style>` bloğu birebir `static/css/gullu-common.css`'e taşındı (cascade konumu korundu: bootstrap sonrası, dark-mode.css/mobile.css öncesi). Kanonik `:root`: primary `#B76E79`, primary-dark `#A05F6A`, success `#3ac47d`, danger `#d92550`, font Inter.
- 13 sayfa `{% extends "base.html" %}` yapısına taşındı (title/extra_css/content/scripts blokları): `bulk_order_prepare`, `yeni_degisim_talebi`, `home`, `order_list`, `iade_listesi`, `order_audit`, `approve_users`, `stock_source`, `image_manager`, `degisim_talep`, `update_commission`, `archive`, `siparis_hazirla`. Önceden extends kullanan 9 sayfayla birlikte toplam 22 sayfa ortak tabanda.
- Taşınan sayfalarda ham `#B76E79` hex'leri `var(--color-primary)`'ye bağlandı.
- İki desen kullanıldı: (a) sayfanın sarmalayıcısı base'inkiyle aynıysa kaldırılıp base'inki kullanıldı (archive, approve_users, order_audit, stock_source); (b) sayfanın kendine özgü kabuğu varsa korunup base sarmalayıcısı `.container.mt-5{max-width:none;margin:0;padding:0}` ile nötrlendi (home, order_list, iade_listesi, image_manager, degisim_talep, update_commission, siparis_hazirla).
- Kanonikten farklı `:root` değerleri sayfaların `extra_css`'inde bilinçle korundu (ör. order_list/degisim_talep Bootstrap klasik success/danger tonları; update_commission'ın tamamen ayrı `--primary/--bg/--card` token sistemi).

**Kalite süreci:** Her dalgayı bir Opus 4.8 alt-ajanı taşıdı, bağımsız bir Opus 4.8 denetçi file:line kanıtıyla doğruladı. 2 orta bulgu yakalanıp düzeltildi:
1. `update_commission`: sayfaya ilk kez Bootstrap geldiği için silinen `*` reset'in kapatamadığı margin kaymaları (BS reboot h1/p margin'leri) → hedefli override'lar + Inter 800 font linki + `border-collapse` düzeltmesi.
2. `siparis_hazirla`: gullu-common'ın `input{font-size:16px!important}` kuralı 42px'lik ayar kutusunu ve raf/barkod inputlarını (Zebra TC21 toplama ekranı) büyütüyordu → `siparis_hazirla.html:509-523`'e yorumlu, hedefli `!important` override'lar.

**Önemli ders:** Daha önce Bootstrap/ortak-CSS yüklemeyen bir sayfa base'e taşınınca iki regresyon kaynağı doğar: BS reboot'un element default'ları (margin/renk) ve gullu-common'ın `!important` input kuralı. Her taşımada kontrol edilmeli.

**Durum:** Commit YOK — kullanıcı lokal görsel test yapacak (anasayfa, sipariş listesi, arşiv, sipariş hazırlama ⚙ Ayarlar + raf okutma). Onay sonrası: commit + sunucuda `git pull && systemctl restart gullupanel.service`.

**Faz 2 (kalan):** `kasa*` ailesi 9 sayfa (Bootstrap 4 → 5 dönüşümü gerektirir: data-toggle→data-bs-toggle, form-row, custom-control), özel tasarımlı 8 sayfa (`product_list` en değerlisi, `raf_olustur`, `canli_panel`, `profit`, `tedarikci_yonetimi`, `uretim_oneri*`, `rapor_gir`, `stock_addition`), `layout.html` emekliliği, alt klasör şablonları (amazon/, hepsiburada/, idefix/, shopify/, stock_sync/) envanteri. Bilerek hariç: yazdırma/etiket sayfaları (milimetrik yazıcı CSS'i) ve login/2FA ekranları.

## DB tüneli (kuruldu)

Sunucu PostgreSQL'i (138.199.218.72) dışarıya kapalı — sadece 127.0.0.1:5432 dinliyor. Lokal geliştirme için SSH tüneli kuruldu:
`ssh -f -N -L 5433:localhost:5432 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes musir@138.199.218.72`

- Lokal `.env` artık `localhost:5433`'e bakıyor (`DATABASE_URL`, `PGHOST`, `PGPORT`); eski hali `.env.bak-tunnel` yedeğinde.
- Tünel kalıcı değil: Mac yeniden başlayınca ya da bağlantı düşünce komut tekrar çalıştırılmalı.
- Dikkat: lokal `app.py` bu tünelle CANLI veritabanına ve CANLI pazaryeri adaptörlerine bağlanır — sayfa gezmek güvenli, stok/sipariş işlemi riskli (çifte senkron ihtimali).
- Güvenlik notu: `app.py` açılışta DB URL'sini şifre dahil stdout'a basıyor — kaldırılması önerildi, henüz yapılmadı.
