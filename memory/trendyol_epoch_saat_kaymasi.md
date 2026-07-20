# Trendyol epoch saat kayması (+3) — kök neden ve düzeltme

**Tarih:** 2026-07-20 · **Tetikleyen:** sipariş 11431155266 panelde 16:15, Trendyol'da 13:15

## Kök neden (kanıtlandı)

Trendyol'un `orderDate` epoch ms değeri **gerçek UTC epoch değil** — İstanbul duvar
saatini kodluyor.

```
raw orderDate ms : 1784553305943
utcfromtimestamp : 2026-07-20 13:15:05   ← Trendyol panelindeki saat
gerçek UTC (o an): 2026-07-20 12:41:16   ← yani 34 dk "gelecekte"
created_at (DB)  : 2026-07-20 10:18:16   ← siparişi çektiğimiz an
```

Sipariş kendisini çektiğimiz andan 3 saat sonra oluşamaz → gerçek an 10:15 UTC.

`order_service.py` `ts_to_dt` bunu `utcfromtimestamp` ile okuyup naive yazıyordu →
DB'de **İstanbul saati** duruyordu. `order_list.html:342`'deki `| ist` filtresi bunu
UTC sanıp bir +3 daha ekleyince **16:15** çıkıyordu. Eskiden gösterimde çevrim
olmadığı için hata görünmüyordu; `| ist` eklenince ortaya çıktı. İlgili:
[[project-timezone-display]]

## Yan etkiler

- Aynı `ts_to_dt` `agreed_delivery_date`, `estimated_delivery_start/end`,
  `origin_shipment_date` alanlarını da yazıyor — hepsi +3 kaymıştı.
- `overdue_orders.py` kaymış `agreed_delivery_date`'i gerçek `utcnow()` ile
  karşılaştırdığı için gecikmeleri **3 saat geç** yakalıyordu. İlgili:
  [[project-overdue-orders]]
- `new_orders_service._to_ist` ve `siparis_hazirla.to_ist` naive'i IST varsayıyordu;
  kaymış veri sayesinde *kazara* doğru çalışıyorlardı. Aynı yardımcılar `archive_date`
  ve `degisim_tarihi` (ikisi de `utcnow` ile yazılıyor, yani gerçek UTC) için ise
  zaten 3 saat eksik gösteriyordu.

## Yapılan

- `order_service.py` — `ts_to_dt` artık `ist_to_utc(utcfromtimestamp(...))` ile naive
  UTC yazıyor.
- `new_orders_service.py`, `siparis_hazirla.py` — yerel `to_ist` kopyaları silindi,
  `time_utils.to_ist` (naive=UTC) kullanılıyor. Üç kolon da artık tek konvansiyonda.
- `tests/test_trendyol_order_date.py` — gerçek datapoint ile regresyon testi
  (fix olmadan RED verdiği doğrulandı).
- `scripts/migrate_trendyol_dates_to_utc.py` — tek seferlik −3 saat backfill;
  dry-run varsayılan, `applied_migrations` işaretçisiyle çift-uygulama koruması,
  `--revert` çıkışı. Kapsam: 37.453 satır / 9 tablo.

## İade ve iptal tarafı (2. tur inceleme)

- **`iade_islemleri.py`** (`return_orders.return_date`, 9.540 satır, CANLI) — +3 kaymış
  ama **SEBEBİ FARKLI**. `claimDate` epoch'u GERÇEK UTC'dir; kaymayı eski koddaki
  `datetime.fromtimestamp` yarattı (bkz. aşağıda `app.py:61` TZ tuzağı).
  Ölçüm: API↔DB eşleşen kayıtlarda fark tam **+3.00 saat**
  (`return_date == utcfromtimestamp(claimDate) + 3`).
  Doğru fix: `utcfromtimestamp` — `ist_to_utc` UYGULANMAZ (ilk denemede yanlış
  yapıp `ist_to_utc` eklemiştim, 3 saat eksik yazacaktı; geri alındı).
  Migration −3s olarak KALIYOR (miktar aynı, gerekçe farklı).
- **`claims_service.py`** (`returns` tablosu) — aynı desen ama tablo **boş (0 satır)**,
  ölü yol. Tutarlılık için düzeltildi (`utcfromtimestamp`).

### ⚠️ `app.py:61` TZ TUZAĞI — bu oturumun en önemli bulgusu

```python
os.environ['TZ'] = 'Europe/Istanbul'; time.tzset()
```
Sunucu OS'i UTC olsa bile **uygulama içinde** `datetime.now()` İstanbul saati döner
(sunucuda ölçüldü: `now()`=16:25, `utcnow()`=13:25). `utcnow`/`utcfromtimestamp`
etkilenmez. Yani `datetime.now()` ile naive-UTC kolona yazan/karşılaştıran her yer
**+3 saat ileri**. `time_utils.py` docstring'i "sunucu UTC" diyor — bu satırla
çelişiyor, ileride karar verilmeli (satır kalacak mı?).
- **İPTALLER — kayma YOK.** `orders_cancelled.cancellation_date` her zaman `utcnow`
  ile yazılıyor (`archive.py:434`), Trendyol epoch'u içermiyor. İptal siparişlerinin
  `order_date`'i ise zaten ana migration kapsamında.
- **`return_orders.process_date`** — `datetime.now()` ile yazılıyor (sunucu UTC) →
  dokunulmadı. (Şu an 0 dolu satır.)

## Kullanıcı hareketleri + sipariş izi sürme (3. tur)

Bunlarda Trendyol epoch'u yok; `UserLog.timestamp` ve `OrderAuditLog.ts` zaten
`utcnow` ile yazılıyor (**depolama doğruydu**). Hata gösterimde ve **ters yönde**:
ham `strftime`/`str()` ile UTC basıldığı için 3 saat GERİDE görünüyorlardı.

- `order_audit_routes.py` — yeni `_ts()` yardımcısı; `_serialize_order_row`
  (order_date/created_at/updated_at/picking_start_time), olay zamanı (:261),
  StockMovement (:307), UserLog (:330) ve isoformat çıktıları (:407, `since`)
  artık `fmt_ist`/`to_ist` kullanıyor. Filtre karşılaştırmaları UTC KALDI.
- `user_logs.py` — Excel çıktısındaki `Tarih` kolonu `fmt_ist` ile; ayrıca
  details'e yazılan `'Zaman'` alanı da İstanbul saatine çevrildi ki aynı
  Excel'deki `Tarih` ile çelişmesin. (Eski kayıtların details'i düzelmez.)
- Web ekranı `templates/user_logs.html:119-120` zaten `| ist` kullanıyordu → dokunulmadı.
- Not: iz sürme ekranındaki `order_date` migration ÖNCESİ kazara doğru görünüyordu;
  migration sonrası diğerleriyle birlikte doğru olacak.

Kanıt (RED/GREEN): `_serialize_order_row` eski kod `10:15` → yeni kod `13:15`.

## 4. tur — TZ tuzağından doğan düzeltmeler

**Takvim-günü filtreleri** (kullanıcının seçtiği gün İstanbul'dur, kolon naive UTC →
`ist_to_utc` ile sarıldı): `profit.py` (ayrı `db_query_start_date`/`end_date`;
`start_date_obj` takvim aritmetiği için IST bırakıldı), `agent_api.py` (sipariş +
değişim filtreleri, "bugünkü siparişler"), `degisim.py`, `user_logs.py`
(gösterimi düzeltmiştim ama **filtre** ham kalmıştı).

**`datetime.now()` → `utcnow()`** (UTC kolonuyla karşılaştırma/yazım):
`akilli_motor.py` (satış penceresi cutoff + "bugün önerdim mi" dedupe),
`archive.py` (archive_date, order_date fallback, geçen-süre hesabı),
`agent_api.py` (degisim_tarihi, siparis_tarihi), `claims_service.py`,
`get_products.py` (cost_date), `product_service.py` (last_update_date).

**`rapor_gir.py` gün kesme:** `func.date(zaman_damgasi)` UTC gününü kesiyordu →
00:00–03:00 raporları önceki güne düşüyordu. `_ist()` yardımcısıyla çift çevrim:
`timezone('Europe/Istanbul', timezone('UTC', col))`. DİKKAT: tek çevrim YANLIŞ
(naive'i IST sanar) — sunucuda ölçülerek doğrulandı.

**`stock_alert_service.py`** stok uyarı mailindeki teslim tarihi `fmt_ist` ile;
**`stock_sync/health_monitor.py`** mail "Kontrol zamanı" `fmt_ist` ile.

## AÇIK KALAN (yapılmadı)

- **Karışık kolonlar:** `archive_date`, `degisim_tarihi`, `cost_date`,
  `last_update_date` — geçmişte hem `utcnow` (UTC) hem `datetime.now()` (IST)
  ile yazılmış. Ayırt edici işaret yok, bu yüzden migration YAZILMADI; körlemesine
  kaydırmak doğru satırları bozar. Kod bundan sonra hep UTC yazıyor.
- **Naive ISO çıktılar:** `agent_api.py`, `stock_sync/routes.py`, `models.py to_dict`
  ve birkaç yerde `.isoformat()` tz göstergesi olmadan dönüyor; tüketici UTC mi IST mi
  bilemiyor. Kozmetik/entegrasyon riski.
- `app.py:61` TZ satırının kaderi (kalsın mı, kalkmalı mı).

## Dikkat — deploy sırası

Migration servis DURDURULMUŞ hâlde çalıştırılmalı. Yeni kod çalışırken migration
koşulursa, yeni kodun yazdığı (zaten doğru UTC) satırlar da −3 kaydırılır.

```
systemctl stop gullupanel.service
git pull
venv/bin/python -m scripts.migrate_trendyol_dates_to_utc          # dry-run
venv/bin/python -m scripts.migrate_trendyol_dates_to_utc --apply
systemctl start gullupanel.service
```

`source IS NULL` satırlar Trendyol sayılır (source kolonu öncesi eski kayıtlar:
sayısal sipariş no + Trendyol kargo, tarih aralığı çakışmıyor). Shopify/manuel hariç.
`orders` tablosunda `source` kolonu yok → script atlar (tablo zaten boş).
