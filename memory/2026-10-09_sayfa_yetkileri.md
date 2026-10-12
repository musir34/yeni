# 2026-10-09 — Sayfa yetkileri: rol varsayılanı ± kişiye özel istisna, yalnız sahip düzenler

**Komutan emri:** "Finans'ı yönetici olmayan bir kullanıcıya açmak istiyorum ama sağlam altyapı: kullanıcı
yönetiminde hangi kullanıcı hangi sayfaya erişebilecek adlarıyla belli olsun; yönetici tüm sayfalar, personel
normaller; istersem yöneticiden sayfa kaldırabilir, personele sayfa ekleyebilirim, kişiye özel; bunu sadece ben
sahip olarak yapabilirim." Sahip: `musir`.

**Önceki durum:** Yetki tamamen rol bazlı (`admin/manager/worker`, `session['role']`), üç ayrı koruma biçimi
(`roles_required`, blueprint `before_request` kalkanları, satır içi `session.get('role')`), menü sabit HTML ve
rotalarla uyumsuz, sahip kavramı ve merkezi sayfa listesi yok.

**Ne kuruldu:**
- `sayfa_yetki.py`: SAYFA KATALOĞU (kod, ad, grup, blueprints/endpoints/yollar, rol varsayılanı). Eşleme sırası
  yollar → endpoints → blueprints; böylece tek blueprint'teki alt sayfalar ayrı yetkilenir (finans/cari, /kart,
  /gelir/excel, /calisan; shopify fiyat). Rol varsayılanları = BUGÜNKÜ erişim → devreye girince kimse değişmez.
  `erisebilir()`: sahip → her şey; istisna varsa o; yoksa rol. `istisna_farki()`: yalnız varsayılandan fark saklanır.
  `ensure_schema()`: açılışta users.is_owner + tablo garantisi (script çalışmadan restart olursa panel çökmez).
- `models.py`: `User.is_owner` (Boolean, server_default false) + `KullaniciSayfaYetki(user_id, sayfa_kodu, izin)`
  unique(user_id, sayfa_kodu). `scripts/add_sayfa_yetki.py --sahip musir` (additive; sahip ataması yalnız burada).
- `app.py`: `check_sayfa_yetkisi` before_request (check_authentication ile aynı muafiyetler; katalog dışı endpoint
  dokunulmaz; fetch/JSON isteğinde 403 JSON, sayfa isteğinde uyarı + anasayfa; hata → serbest bırakır).
  Jinja global `sayfa_erisebilir('kod')`; `sayfa_yetki_routes` blueprint kaydı.
- `login_logout.roles_required`: rol tutmuyorsa `istisna_ile_acik_mi()` → sahip ya da o sayfaya izin=True istisnası
  olan geçer. İstisnasız kullanıcıda rol kontrolü aynen sürer → sayfası herkese açık ama alt eylemi admin/manager
  olan rotalar (ürün listesi varyant silme vb.) korunur. Blueprint kalkanlarındaki admin kontrolü (whatsapp_duyuru/
  baglanti) istisnayı TANIMAZ (bilinçli sınır).
- `sayfa_yetki_routes.py`: GET/POST `/admin/sayfa-yetki/<username>` — yalnız `is_owner`, POST fetch başlığı şart,
  sahibe kısıt 400, bilinmeyen kod 400, user_logs'a eklenen/kaldırılan sayfa adlarıyla yazar.
- `_ust_menu.html`: TÜM katalog kalemleri `sayfa_erisebilir` ile sarıldı (görünen = açılabilen); eski rol koşulları kalktı.
- `approve_users.html`: "Sayfa Yetkileri" sütunu (N/M · k özel; sahipte taç rozeti) + tek modal (gruplu onay
  kutuları, rol/özel rozetleri, "Rol varsayılanına dön", Kaydet). Sahip değilse görüntüleme modu.
- Testler: `tests/test_sayfa_yetki.py` (5 saf). Uçtan uca sqlite denemesi (scratchpad): personel finans kapalı →
  istisnayla açık, kart kapalı kaldı; adminden raf kaldırıldı → rota 302 + menüde yok; admin POST 403; sahip 400'ler.

**Deploy:** `git pull`, sonra `DISABLE_JOBS=1 venv/bin/python scripts/add_sayfa_yetki.py --sahip musir`, sonra
`systemctl restart gullupanel.service`. Script atlanırsa şema açılışta kendini onarır ama SAHİP ATANMAZ (kimse yetki
düzenleyemez) → script şart.

**Bilinçli sınırlar:** istisna yalnız katalog sayfaları için; `manager` rolü arayüzden atanamıyor, katalogda bugünkü
erişimiyle duruyor; satır içi rol kontrolleri (gizli_ozellikler, rapor_gir, degisim/iade eylemleri) değişmedi;
Kalan `menu.html` (gizli özellikler sayfası) eski rol koşuluyla duruyor.

## 2026-10-12 ek — "yetki var, düğme yok" olayı ve kalıcı kural
**Olay:** Komutan Ahmet'e (worker) finans yetkisi verdi, anasayfada Finans düğmesi çıkmadı. Canlı DB: Ahmet'in tek
istisnası `finans_cari=True`. Menüdeki "Finans" kalemi yalnız `finans` (Kasa Paneli) yetkisine bağlıydı; Cari için menüde
kalem yoktu → yetki doğru yazılmış ama ulaşılacak düğme yoktu.
**Kalıcı çözüm:**
- `Sayfa` kataloğuna `menu_endpoint`/`menu_ad` eklendi; `_ust_menu.html` Finans bölümü `menu_sayfalari('Finans')` ile
  KATALOGDAN üretilir → hangi finans alt sayfası verilirse menüde o kalem çıkar (Analiz & Fiyat açılır menüsü, Finans başlığı).
- `_finans_nav.html` sekmeleri `sayfa_erisebilir` ile yetkiye bağlı (Panel/Gelir/Defter/Tanımlar/Rapor → finans, Kredi Kartı
  → finans_kart, Cari → finans_cari).
- Eylem sayfası kavramı: `finans_calisan` (hakediş ödemesi; panel, düzenli ödemeler ve cari detayda modal) `menude=False`,
  `ebeveynler=("finans","finans_cari")` → yetkisi tamamen ebeveynlerinden türer, yetki ekranında kutu değil, istisna almaz.
- `menu_disi=True`: bilinçli menü dışı URL sayfaları (raporlama, amazon, gizli_ozellikler).
- TEST ZORLAR: `test_her_gorunen_sayfanin_menude_bir_girisi_var` — yetki ekranındaki her sayfa menüde ya elle
  `sayfa_erisebilir('kod')` ile ya da katalogdan `menu_sayfalari('grup')` ile yer almalı; aksi hâlde test kırılır.
  Yeni sayfa eklerken: katalog + menü girişi (ya da menu_disi gerekçesiyle).
