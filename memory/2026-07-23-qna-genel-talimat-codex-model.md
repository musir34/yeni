# Q&A genel talimat alanı + Codex model seçimi (2026-07-23)

## Ne değişti
1. **Q&A genel talimatı:** /soru-cevap üstüne açılır-kapanır "AI Genel Talimatı" kartı
   eklendi (yalnızca yönetici görür). Yazılan talimat DB'de saklanır ve TÜM yeni
   taslaklar + Düzelttir revizyonlarının sistem promptuna eklenir; boşsa etkisiz.
   - Saklama: `trendyol_qna/qna_ayar.py` — PlatformConfig ayar torbası
     (`platform='qna_ayar'`, `extra_config.genel_talimat`), migration YOK.
   - Prompt'a ekleme: `trendyol_qna/qna_ai.py::_kurallar()` (kurallar → talimat → bilgi bankası sırası).
   - Endpoint: `/soru-cevap/api/genel-talimat` GET/POST (POST yalnızca yönetici; CSRF fetch başlığı before_request'te).

2. **Codex model seçimi (alan bazlı):** Motor "codex" seçiliyken iki ekranda da
   (soru-cevap + ai-asistan) ikinci bir dropdown çıkar: Varsayılan / gpt-5.2 /
   gpt-5.1-codex-max / gpt-5.1-codex-mini / Diğer… (serbest giriş).
   - Saklama: `ai_asistan/motor_ayar.py` — aynı `ai_motor` torbasında
     `asistan_codex_model` / `qna_codex_model` anahtarları; model adı deseni
     `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` (alt sürece argüman gidiyor).
   - Öncelik: DB ayarı > .env CODEX_MODEL > codex config.toml varsayılanı.
     DİKKAT: panelden "Varsayılan" seçilirse '' KAYDEDİLİR ve env CODEX_MODEL artık
     o alan için okunmaz (bilinçli: varsayılan = codex'in kendi ayarı).
   - `_codex_calistir` artık `model=` parametresi alır (None → env'e düşer, geriye uyumlu).
   - `/ai-asistan/motor` endpoint'i genişledi: GET `codex_modeller` + `codex_hazir`
     döner; POST `motor` ve/veya `codex_model` kabul eder (ikisi de yoksa 400).

3. **AI asistan genel talimatı (aynı gün eklendi):** /ai-asistan başlığındaki
   araçlara ⚙(sliders) butonu → açılır "AI Genel Talimatı" paneli (yalnızca yönetici).
   - Saklama: `ai_asistan/asistan_ayar.py` (`platform='asistan_ayar'`, migration YOK).
   - Injection: `blueprint.py::_system_prompt()` sonuna `_genel_talimat_ekle()` ile —
     hem Claude hem Codex yolu buradan geçtiği için tek nokta.
   - DİKKAT: sistem promptu yalnızca TAZE oturumda gönderilir (resume'da değil,
     blueprint.py `_dene` içi) → talimat süren sohbeti etkilemez, yeni sohbette
     devreye girer; UI kayıt mesajı bunu söylüyor.
   - Endpoint: `/ai-asistan/genel-talimat` GET/POST (yönetici + fetch başlığı CSRF).

## Neden
Kullanıcı taslakların genel üslubunu/mesajını tek yerden yönlendirmek ve Codex
motorunda hangi modelin çalıştığını panelden seçmek istedi.

## Deploy
Sunucuda: `git pull && systemctl restart gullupanel.service`. Migration gerekmez.
