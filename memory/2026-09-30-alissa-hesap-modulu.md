# 2026-09-30 — Muhammet Alissa haftalık hesap modülü (`alissa/`)

## Ne eklendi
- Yeni klasör `alissa/` (panelden bağımsız): `models.py` (alissa_* tabloları), `trendyol.py`
  (yalnız GET istemci), `senkron.py` (Trendyol → defter), `hesap.py` (haftalık özet),
  `routes.py` (`/alissa`, yalnız admin), `templates/alissa/index.html`, `kur.py`, `tests/`.
- Klasör dışında yalnız 2 dokunuş: `routes/__init__.py` (blueprint kaydı) ve
  `templates/_ust_menu.html` (admin'e "Muhammet Alissa" düğmesi).

## Neden
Komutan, tedarikçi Muhammet Alissa'ya (TED-003) haftalık ödeme yapacak; her hafta teslim
edilen satışları, iadeleri ve kesintileri görmek istiyor. Veri panelin sipariş tablolarından
değil Trendyol'un güncel servislerinden gelir (finans settlements, kargo faturası kalemleri,
sipariş v2) — panel tabloları bu ayrıntıyı tutmuyor.

## Hesap kuralları (Komutan kararı)
- Satış, Trendyol satış kaydını kestiği (teslim) haftaya; iade, iadenin kesildiği haftaya yazılır.
- Hafta neti = satış − iade − indirim/kupon − komisyon − platform hizmet bedeli (13,19/paket)
  − gönderi ve iade kargosu − sipariş başı 100 TL. Ürün maliyeti dahil değil.
- Karma siparişte paket/sipariş başı kalemler adet oranında paylaştırılır.
- Kargo faturası 4-6 hafta gecikir: önce tahmin (117,59), fatura gelince yalnız FARK faturanın
  geldiği haftaya yazılır; geçmiş haftaların rakamı değişmez.
- Ödemeler sayfadan kaydedilir; bakiye = toplam hakediş − ödenen.

## Şema (additive, migration yok)
Yeni tablolar: `alissa_hareket`, `alissa_kargo_kalem`, `alissa_siparis`, `alissa_odeme`,
`alissa_ayar`. Mevcut tablolara dokunulmaz. Panelden okunan tek şey `products.tedarikci_kodu`.

## Deploy
```
git pull
DISABLE_JOBS=1 /home/musir/gullupanel/venv/bin/python -m alissa.kur --senkron
systemctl restart gullupanel.service
```
`kur` çalıştırılmadan sayfa açılırsa tablo yok hatası verir. İlk senkron birkaç dakika sürer.

## Doğrulama
- `.venv/bin/python -m unittest alissa.tests.test_alissa` (izole SQLite, 12 test geçti).
- Gerçek Trendyol verisi modülden bellek içi DB'de geçirildi: toplam net 197.821,23 TL
  (elle çıkarılan rapordaki 197.363,64'ten 457 TL fazla — modül Mayıs/Haziran'daki iki karma
  siparişi doğru paylaştırıyor, rapor %100 Alissa saymıştı).
- Canlı DB'de henüz tablo açılmadı, canlıda denenmedi.

## Kod incelemesi sonrası düzeltmeler (aynı gün)
- Senkron kilidi tek UPDATE ile atomik alınır (`alissa_ayar.senkron_kilit`), aşama arası nabız; iki worker aynı anda başlatamaz.
- Hata sonrası sayfa her açılışta yeniden denemez (`son_deneme`, 6 saat bekler).
- Karma sipariş ayrı paketlerle giderse diğer paketin kolisi Alissa'ya yazılmaz (koli sınırı = Alissa paket sayısı).
- Tutar girişinde `1.500` artık bin beş yüz okunur (önce 1,50 okunuyordu).
- Bilinen sınır: karma sipariş iki pakette, paketler farklı senkronlarda teslim olursa 100 TL masrafın
  tamamı Alissa'ya yazılabilir (nadir; en çok 100 TL/sipariş).

## 2026-10-02 — sonradan etiketlenen model
Komutan 014 modelini tedarikçiye sonradan ekledi. Kural: etiketlenen yeni model geçmişiyle birlikte
dahil olmalı. Senkron artık bilinen model listesini (`alissa_ayar.bilinen_modeller`) tutar; listede
olmayan model görürse o çalışmada pencereyi 20 gün yerine başlangıçtan (10 Mayıs) açar. Defter tekil
olduğu için eski kayıtlar ikinci kez yazılmaz. Eski satışlar kendi teslim haftalarına girer; ödenmiş
haftaların neti artar, fark bakiyeye yansır. Test: test_sonradan_etiketlenen_model_gecmisiyle_dahil_olur.
