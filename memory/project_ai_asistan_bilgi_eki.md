# AI asistanı: veri haritası + kendini güncelleyen bilgi eki (2026-10-14)

**Sorun:** Panel asistanı "neyin nerede olduğunu" bilmiyordu. Tek aracı salt-okunur SQL;
bilgi tabanı 4 vault notu (7,6 KB); ürün/stok/üretim/kasa için talimat "şemadan kendin
keşfet" idi. Geliştirme hafızası (memory/, 68 not) ve kod ona kapalıydı.

**Ne değişti**
- `ai_asistan/vault/40_veri_haritasi.md` (yeni, elle derlendi): her iş kavramı için tablo,
  kolon, JSON alanı, tuzak ve hazır sorgu (ürün/model, stok+raf+ledger, sipariş tabloları ve
  `details` JSON `unit_price`, üretim modu `platform_configs.extra_config->'models'`,
  `uretim_siparis`, iade/değişim, finans, soru-cevap, zaman kuralları).
- `ai_asistan/bilgi_dizini.py` (yeni): her soruda taze üretilen iki bölüm —
  (1) **Proje Notları Dizini**: repo `memory/*.md` dosya adı + başlık (frontmatter
  description ya da ilk `#`) + ≤420 karakter özet, en yeni önce, toplam ≤45 KB (ölçüm: 68 not
  → 36,7 KB); (2) **Canlı Şema Özeti**: `sql_kopru.sema_ozeti()` (103 tablo, 1506 kolon,
  ~50 KB), AI_DB_URL yoksa sessizce boş.
- `blueprint._system_prompt(sema=False)`: vault + bilgi eki + genel talimat. Claude yolu
  `sema=True` (şema eklenir); Codex yolu şemayı zaten kendi talimatıyla ekliyor, değişmedi.
- `00_asistan_kimligi.md`: "önce şemayı keşfet" → önce harita, sonra şema özeti ve not dizini.

**"Yeni eklenen şeyleri kendinden bilmesi" nasıl sağlanıyor:** proje kuralı gereği her
değişiklik `memory/`'ye not düşer → dizin bir sonraki soruda otomatik içerir; yeni tablo/kolon
şema özetinde otomatik görünür. Elle güncellenecek tek yer harita notu (yeni iş kavramı).

**Maliyet:** ilk soru promptu ~95 KB (≈25k token); `--resume` ile devam eden sohbette
tekrar gönderilmez. Dosya okuma yetkisi verilmedi (`.env` sızıntı riski; Codex zaten okuyamaz).

**Doğrulama:** dizin üretimi DB'siz test edildi (68 not, frontmatter sızmıyor, en yeni önce);
py_compile geçti. Canlı deneme deploy sonrası: asistana "üretim modundaki modeller son 30 günde
ortalama kaça satıldı" sorulup haritadaki kalıbı kullanıp kullanmadığına bakılacak.

**Durum:** f420c27 push edildi (2026-10-14); sunucuda pull+restart bekliyor (`git pull && systemctl restart gullupanel.service`;
`memory/` git'te takipli, sunucuya pull ile gelir).
