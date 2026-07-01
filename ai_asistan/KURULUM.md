# AI Asistanı — Sunucu Kurulum Rehberi

Panel içi AI asistanı: soru → sunucuda headless Claude Code (Max aboneliği) →
salt-okunur PostgreSQL sorgusu → Türkçe cevap. **API faturası yok, terminal erişimi yok.**

Aşağıdaki adımları **sunucuda** (138.199.218.72) SSH ile yaparsın. Kod tarafı hazır.

---

## 1) Salt-okunur DB rolü oluştur (GÜVENLİK TEMELİ)

`create_readonly_role.sql` içindeki parolayı güçlü bir şeyle değiştir, sonra:

```bash
psql "postgresql://musir:<MUSIR_PAROLA>@138.199.218.72:5432/gulludb" \
     -f ai_asistan/create_readonly_role.sql
```

Çıktıda `ai_readonly` rolü için **yalnızca SELECT** yetkileri görünmeli.

`.env`'e ekle (aynı parolayla):
```
AI_DB_URL="postgresql://ai_readonly:<AI_PAROLA>@138.199.218.72:5432/gulludb"
```

## 2) Node.js + Claude Code kur (sunucuda yoksa)

```bash
# Node 18+ gerekli (postgres MCP npx ile çalışır)
node --version
# Claude Code
curl -fsSL https://claude.ai/install.sh | bash    # veya npm i -g @anthropic-ai/claude-code
claude --version
```

## 3) Claude Code'a Max aboneliğinle giriş yap (API DEĞİL)

```bash
claude login
```
- Tarayıcı akışında **Max/Pro aboneliği** ile giriş yap.
- **ÖNEMLİ:** Sunucu ortamında `ANTHROPIC_API_KEY` **tanımlı OLMASIN**. Varsa kaldır:
  ```bash
  grep -i anthropic_api_key .env    # varsa sil
  ```
  (Blueprint zaten alt-süreçten bu anahtarı temizliyor, ama ortamda hiç olmaması en temizi.)

## 4) MCP bağlantısı (parola .env'de, dosyaya YAZILMAZ)

`.mcp.json` parolayı `${AI_DB_URL}` env değişkeninden okur — git'e sızmaz.
Adım 1'de `.env`'e eklediğin `AI_DB_URL` yeterli. Flask `.env`'i otomatik yükler ve
blueprint bu değişkeni Claude Code alt-sürecine aktarır.

Bağlantıyı elle test etmek için (env'i yükleyerek):
```bash
cd ai_asistan
export $(grep -E "^AI_DB_URL=" ../.env | sed 's/"//g')
claude -p "gulludb'de kaç tablo var? Sadece sayıyı söyle." --allowedTools "mcp__gulludb__query"
```

## 5) Flask'a blueprint'i kaydet

`app.py` içinde ~129. satırdaki `app.register_blueprint(idefix_bp)` satırının ALTINA ekle:

```python
from ai_asistan.blueprint import ai_asistan_bp
app.register_blueprint(ai_asistan_bp)
```

## 6) Servisi yeniden başlat

```bash
sudo systemctl restart gullupanel.service
sudo systemctl status gullupanel.service --no-pager
```

## 7) Test et

Panelde `/ai-asistan` sayfasını aç, "Bugün kaç sipariş geldi?" diye sor.

---

## Güvenlik özeti (neden güvenli)
| Katman | Koruma |
|--------|--------|
| DB rolü | `ai_readonly` yalnızca SELECT — yazma fiziksel olarak imkânsız |
| MCP | postgres MCP tüm sorguları READ ONLY transaction'da çalıştırır |
| Araç kısıtı | `--allowedTools "mcp__gulludb__query"` — başka hiçbir araç yok, terminal yok |
| Erişim | `@login_required` — sadece panele girmiş kullanıcılar |
| Zaman aşımı | DB'de 30sn statement_timeout + Flask'ta 90sn süre sınırı |
| Maliyet | Abonelik (API anahtarı süreçten temizli) → sabit aylık, sürpriz fatura yok |

## Bilinmesi gerekenler (dürüst sınırlar)
- Tek Max hesabı → eşzamanlı çok kullanıcı aynı limiti paylaşır. Küçük ekip için yeterli.
- Yoğun kullanımda rate limit'e takılabilir (fatura değil, "biraz bekle").
- İş kurallarını genişletmek için `ai_asistan/IS_KURALLARI.md` dosyasını güncelle.
