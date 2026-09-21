# Sipariş Notu Mail Bildirimi (2026-09-21)

**Ne değişti**
- `mail_service.py`: yeni olay `siparis_notu` — NOTIFY_EVENTS / EVENT_COLORS / EVENT_TITLES'e eklendi;
  `build_order_note_email(order_number, note, updated_by, is_update)` HTML şablonu eklendi
  (not metni `html.escape` ile kaçırılıyor, satır sonları `<br/>`).
- `siparis_notu.py` → `/siparis-notu/api/kaydet`: commit sonrası `notify("siparis_notu", ...)`.
  Bildirim hatası kaydı etkilemez (try/except + logger.warning). Not **silindiğinde** mail gitmez.
- `templates/approve_users.html`: kullanıcı yönetimi → Bildirimler açılırına
  "Siparişe not eklendiğinde" kutusu eklendi (value=`siparis_notu`).

**Neden**: Sipariş notu yazıldığında belirlenen kişilere mail gitsin istendi.
Alıcı seçimi mevcut `users.notify_events` altyapısıyla; WhatsApp'a dokunulmadı (kullanıcı tercihi).

**Not**: DB/şema değişikliği yok. Mail için `GMAIL_USER` + `GMAIL_APP_PASSWORD` gerekli.
