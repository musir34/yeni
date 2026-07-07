---
type: community
cohesion: 0.07
members: 48
---

# Kimlik Doğrulama & Kullanıcı Yönetimi

**Cohesion:** 0.07 - loosely connected
**Members:** 48 nodes

## Members
- [[Admin kullanıcının 2FA'sını sıfırlar, yeniden kurulum gerektirir.]] - rationale - login_logout.py
- [[Admin kullanıcının PC cihaz limitini gunceller.]] - rationale - login_logout.py
- [[Admin kullanıcının bildirim görselini kaldır.]] - rationale - login_logout.py
- [[Admin kullanıcının şifresini sıfırlar ve yeni geçici şifre oluşturur.]] - rationale - login_logout.py
- [[Admin kullanıcıya bildirim görseli ata.]] - rationale - login_logout.py
- [[Admin şifre + 2FA + cihazların hepsini sıfırlar.]] - rationale - login_logout.py
- [[Belirli bir kullanıcının tüm aktif oturumlarını ve trusted cihazlarını     sonla]] - rationale - login_logout.py
- [[Cihaz limitini kontrol eder. (izin_var, mesaj) döner.]] - rationale - login_logout.py
- [[Kayıtlı (güvenilen) cihaz. Cookie token ile eşleşir.]] - rationale - models.py
- [[Kimlik doğrulama, cihaz yönetimi ve oturum sistemi.  Giriş akışı   Tanınan ciha]] - rationale - login_logout.py
- [[Tüm cihazları siler ve session_version artırarak tüm oturumları geçersiz kılar.]] - rationale - login_logout.py
- [[Tüm kullanıcıların oturumlarını ve cihazlarını geçersiz kılar.]] - rationale - login_logout.py
- [[User-Agent'tan cihaz tipini belirler 'mobile' veya 'pc'.]] - rationale - login_logout.py
- [[User-Agent'tan okunabilir cihaz adı çıkarır.]] - rationale - login_logout.py
- [[UserDevice]] - code - models.py
- [[Yeni cihaz kaydeder ve çerez ayarlar.]] - rationale - login_logout.py
- [[_check_device_limit()]] - code - login_logout.py
- [[_detect_device_name()]] - code - login_logout.py
- [[_detect_device_type()]] - code - login_logout.py
- [[_get_trusted_device()]] - code - login_logout.py
- [[_log_action()]] - code - login_logout.py
- [[_register_device()]] - code - login_logout.py
- [[admin_force_logout_user()]] - code - login_logout.py
- [[admin_reset_2fa()]] - code - login_logout.py
- [[admin_reset_all()]] - code - login_logout.py
- [[admin_reset_password()]] - code - login_logout.py
- [[approve_users()]] - code - login_logout.py
- [[check_role()]] - code - login_logout.py
- [[cihaz_sil()]] - code - login_logout.py
- [[cihazlarim()]] - code - login_logout.py
- [[clear_notification_image()]] - code - login_logout.py
- [[delete_user()]] - code - login_logout.py
- [[device_limit_reached()]] - code - login_logout.py
- [[force_logout_all()]] - code - login_logout.py
- [[generate_qr_code()]] - code - login_logout.py
- [[home_redirect()]] - code - login_logout.py
- [[login()]] - code - login_logout.py
- [[login_logout.py]] - code - login_logout.py
- [[login_user()]] - code - login_logout.py
- [[logout()]] - code - login_logout.py
- [[set_notification_image()]] - code - login_logout.py
- [[setup_totp()]] - code - login_logout.py
- [[show_qr_code()]] - code - login_logout.py
- [[tum_cihazlardan_cikis()]] - code - login_logout.py
- [[update_max_pc()]] - code - login_logout.py
- [[update_notify()]] - code - login_logout.py
- [[verify_totp()]] - code - login_logout.py
- [[İstekteki çerezden güvenilen cihazı döner (varsa).]] - rationale - login_logout.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Kimlik_Dorulama__Kullanc_Ynetimi
SORT file.name ASC
```

## Connections to other communities
- 6 edges to [[_COMMUNITY_Community 59]]
- 4 edges to [[_COMMUNITY_Silme & Toplu Yazdırma İşlemleri]]
- 3 edges to [[_COMMUNITY_Community 82]]
- 2 edges to [[_COMMUNITY_Veri Modelleri (SQLAlchemy)]]
- 1 edge to [[_COMMUNITY_Akıllı Motor (İndirim & Fiyat)]]
- 1 edge to [[_COMMUNITY_Canlı Panel (SSE)]]
- 1 edge to [[_COMMUNITY_Ürün Çekme & Görsel İndirme]]
- 1 edge to [[_COMMUNITY_Kasa & Gelir-Gider]]
- 1 edge to [[_COMMUNITY_Community 65]]
- 1 edge to [[_COMMUNITY_Community 128]]
- 1 edge to [[_COMMUNITY_Community 64]]

## Top bridge nodes
- [[login_logout.py]] - degree 49, connects to 11 communities
- [[_log_action()]] - degree 19, connects to 2 communities
- [[_register_device()]] - degree 8, connects to 1 community
- [[UserDevice]] - degree 5, connects to 1 community
- [[_check_device_limit()]] - degree 4, connects to 1 community