# AI Asistanı — Çoklu Sohbet + Sağlam Altyapı (2026-07-10)

## Amaç
1. Sohbet botuna "yeni sohbet" ve "geçmiş sohbetler" özelliği (widget + /ai-asistan sayfası).
2. "Sunucu hatası"nın kökten çözümü: senkron 90 sn'lik Claude çağrısı gunicorn
   worker'ını blokluyor (varsayılan 30 sn worker timeout → 502). Asenkron modele geçilir.
3. Premium cevap kalitesi: geçmişi prompta metin olarak yapıştırmak yerine
   `claude --resume <session_id>` ile gerçek oturum bağlamı + `--model opus`.

## Mimari

### DB (additive migration, mevcut tabloya dokunma yok)
- `ai_sohbet`: id (PK), kullanici (str, index), baslik (str), claude_session_id (str, null),
  created_at, updated_at (index).
- `ai_mesaj`: id (PK), sohbet_id (FK ai_sohbet.id, index), rol ('kullanici'|'asistan'),
  metin (text), durum ('hazir'|'bekliyor'|'hata'), created_at.
- Migration: `migrations/versions/add_ai_sohbet.py`, down_revision=None, try/except'li
  (projedeki add_stock_listing_policy deseni).

### Asenkron akış
- `POST /ai-asistan/sor` {soru, sohbet_id?}: sohbet yoksa oluştur (başlık = sorunun ilk 60 kr),
  kullanıcı mesajını `hazir`, asistan mesajını `bekliyor` olarak DB'ye yaz,
  arka plan thread'inde `claude -p` başlat, ANINDA `{mesaj_id, sohbet_id}` döndür.
- Thread: `claude -p --model opus --output-format json` (+ sohbetin session_id'si varsa
  `--resume`; cevaptaki session_id sohbete kaydedilir). Timeout 240 sn.
  Geçici hatada 1 otomatik retry. Sonuç asistan mesajına yazılır (durum hazir/hata).
- `GET /ai-asistan/durum/<mesaj_id>`: {durum, metin} — frontend 2 sn'de bir yoklar.
- Aynı anda kullanıcı başına tek bekleyen soru (ikinci soru gelirse 429-benzeri uyarı).

### Sohbet yönetimi endpoint'leri
- `GET /sohbetler` → [{id, baslik, updated_at}] en yeni üstte (son 50).
- `POST /yeni` → yeni boş sohbet mantıken gereksiz: yeni sohbet ilk soruyla oluşur;
  frontend "yeni sohbet" = aktif sohbet_id'yi sıfırlamak.
- `GET /sohbet/<id>` → mesajlar (sahiplik kontrolü: sohbet.kullanici == aktif kullanıcı).
- `POST /sohbet/<id>/sil` → sohbeti + mesajlarını sil (sahiplik kontrolü).
- Eski `gecmis/<kullanici>.json` varsa ilk sohbet listelemede "Eski sohbet" adıyla
  DB'ye bir kez içeri alınır ve dosya `.imported` uzantısına taşınır.
- Eski `/gecmis` ve `/temizle` endpoint'leri kaldırılır (tek tüketicileri bu iki şablon,
  ikisi de aynı anda güncelleniyor).

### Güvenlik (mevcut korumalar korunur)
- Blueprint-level 2FA kalkanı, login_required, allowedTools beyaz listesi,
  ANTHROPIC env temizliği, salt-okunur MCP aynen kalır.
- Sohbet erişiminde sahiplik kontrolü (başkasının sohbet_id'siyle okuma/yazma 404).

## UI
- Widget başlığı: ➕ (yeni sohbet), 🕘 (geçmiş listesi overlay: başlık+tarih+sil),
  çöp butonu = aktif sohbeti sil. Aktif sohbet_id localStorage'da; polling sayfa
  yenilemeye dayanıklı (bekleyen mesaj varsa açılışta yoklamaya devam).
- /ai-asistan sayfası: aynı butonlar başlık şeridinde, aynı endpoint'ler.

## Deploy
1. `git pull`
2. `cd /path && alembic -c migrations/alembic.ini upgrade heads` (veya mevcut migration
   çalıştırma yöntemi)
3. `systemctl restart gullupanel.service`
