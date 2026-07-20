"""TEK SEFERLİK veri düzeltmesi: Trendyol sipariş tarihlerini İstanbul-yerel → UTC'ye kaydır.

NEDEN
-----
Trendyol'un `orderDate` epoch değeri gerçek UTC epoch DEĞİL; İstanbul duvar
saatini kodluyor. `order_service.ts_to_dt` bunu `utcfromtimestamp` ile
okuyordu, yani DB'ye **İstanbul saati** naive olarak yazılıyordu.

Kanıt (sipariş 11431155266, 2026-07-20):
    raw orderDate ms : 1784553305943
    utcfromtimestamp : 2026-07-20 13:15:05   ← Trendyol panelindeki saat
    created_at (DB)  : 2026-07-20 10:18:16   ← siparişi çektiğimiz an (gerçek UTC)
Sipariş, kendisini çektiğimiz andan 3 saat sonra oluşamaz → gerçek an 10:15 UTC.

Kod artık `ist_to_utc(...)` ile naive UTC yazıyor. Mevcut ESKİ satırlar hâlâ
İstanbul-yerel; onları **−3 saat** kaydırmak gerekir.
Türkiye 2016'dan beri kalıcı UTC+3 (DST yok) → sabit −3 saat doğru.

KAPSAM
------
Yalnızca Trendyol kaynaklı satırlar. `source IS NULL` olanlar da dahildir:
bunlar `source` kolonu doldurulmadan önceki eski Trendyol kayıtları (hepsi
10-11 haneli sayısal sipariş no + Trendyol kargo firması, tarih aralığı
TRENDYOL satırlarıyla çakışmıyor). Shopify/manuel satırlar HARİÇ.

İade tarafı da +3 kaymış ama SEBEBİ FARKLI. `claimDate` epoch'u GERÇEK UTC'dir
(orders API'sinden farklı); kaymayı eski koddaki `datetime.fromtimestamp` yaratmış:
`app.py:61` TZ'yi Europe/Istanbul'a set ettiği için bu çağrı İstanbul duvar saati
üretiyordu. Ölçümle doğrulandı — API↔DB eşleşen kayıtlarda fark tam +3.00 saat:
`return_date == utcfromtimestamp(claimDate) + 3`.
Sonuç: kaydırma miktarı yine −3 saat (`return_orders.return_date`,
`returns.create_date/last_modified_date`).
`return_orders.process_date` `datetime.now()` ile yazılıyor (sunucu UTC) → DOKUNULMAZ.
`orders_cancelled.cancellation_date` da `utcnow` ile yazılıyor → DOKUNULMAZ.

ÖNEMLİ — SIRALAMA
-----------------
Bu script servis DURDURULMUŞ hâlde, yeni kod deploy edilmeden ÖNCE veya deploy
ile aynı bakım penceresinde çalıştırılmalı. Aksi hâlde yeni kodun yazdığı
(zaten doğru UTC olan) satırlar da −3 saat kaydırılır.

    systemctl stop gullupanel.service
    git pull
    venv/bin/python -m scripts.migrate_trendyol_dates_to_utc          # dry-run
    venv/bin/python -m scripts.migrate_trendyol_dates_to_utc --apply
    systemctl start gullupanel.service

GÜVENLİK
--------
- Varsayılan **DRY-RUN**: hiçbir şey yazmaz, sayıları ve örnekleri gösterir.
- `--apply`: tek transaction'da −3s uygular, `applied_migrations` işaretçisi yazar.
- **Çift-uygulama koruması**: işaretçi varsa tekrar UYGULAMAZ (−6s olmaz).
- `--revert`: +3s geri alır ve işaretçiyi siler (acil çıkış).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

MARKER = "trendyol_epoch_utc_shift_2026_07"

# Trendyol epoch'undan (ts_to_dt) yazılan tüm tarih kolonları
COLUMNS = [
    "order_date",
    "agreed_delivery_date",
    "estimated_delivery_start",
    "estimated_delivery_end",
    "origin_shipment_date",
]

TABLES = [
    "orders",
    "orders_created",
    "orders_hazirlaniyor",
    "orders_picking",
    "orders_ready_to_ship",
    "orders_shipped",
    "orders_delivered",
    "orders_cancelled",
    "orders_archived",
    "archive",
]

# Shopify/manuel satırlara DOKUNMA. NULL = source kolonu öncesi eski Trendyol.
WHERE_TRENDYOL = "(source IS NULL OR lower(source) = 'trendyol')"

# `source` kolonu olmayan, %100 Trendyol kaynaklı tablolar.
# return_orders.return_date'in TEK yazarı iade_islemleri.py (Trendyol claimDate);
# process_date `datetime.now()` ile yazılıyor (sunucu UTC) → DOKUNULMAZ.
KAYNAKSIZ_HEDEFLER = [
    ("return_orders", ["return_date"]),
    ("returns", ["create_date", "last_modified_date"]),
]

SHIFT = "interval '3 hours'"


def _tablo_kolonlari(db, text, tablo):
    rows = db.session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t"
    ), {"t": tablo}).all()
    return {r.column_name for r in rows}


def _hedefleri_bul(db, text):
    """(tablo, kolonlar, where) listesi — yalnızca gerçekten var olanlar."""
    hedefler = []
    for tablo in TABLES:
        varolan = _tablo_kolonlari(db, text, tablo)
        # `source` yoksa Trendyol/Shopify ayrımı yapılamaz → dokunma (ör. legacy `orders`)
        if not varolan or "source" not in varolan:
            continue
        cols = [c for c in COLUMNS if c in varolan]
        if cols:
            hedefler.append((tablo, cols, WHERE_TRENDYOL))
    for tablo, istenen in KAYNAKSIZ_HEDEFLER:
        varolan = _tablo_kolonlari(db, text, tablo)
        cols = [c for c in istenen if c in varolan]
        if cols:
            hedefler.append((tablo, cols, "TRUE"))
    return hedefler


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Trendyol sipariş tarihlerini İstanbul→UTC kaydır (tek seferlik)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true", help="−3 saat uygula")
    g.add_argument("--revert", action="store_true", help="+3 saat geri al (işaretçiyi de sil)")
    args = ap.parse_args()

    from app import app
    from sqlalchemy import text
    from models import db

    with app.app_context():
        db.session.execute(text(
            "CREATE TABLE IF NOT EXISTS applied_migrations "
            "(key TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT now())"
        ))
        db.session.commit()
        already = db.session.execute(
            text("SELECT 1 FROM applied_migrations WHERE key=:k"), {"k": MARKER}
        ).first() is not None

        hedefler = _hedefleri_bul(db, text)

        # ---- ÖNİZLEME ----
        print(f"=== Trendyol tarih kaydırma — işaretçi '{MARKER}' "
              f"{'VAR (uygulanmış)' if already else 'YOK'} ===")
        toplam = 0
        for tbl, cols, where in hedefler:
            ana = cols[0]  # tabloyu temsil eden tarih kolonu
            row = db.session.execute(text(
                f"SELECT count(*) n, min({ana}) mn, max({ana}) mx "
                f"FROM {tbl} WHERE {ana} IS NOT NULL AND {where}"
            )).first()
            haric = db.session.execute(text(
                f"SELECT count(*) n FROM {tbl} WHERE NOT ({where})"
            )).first()
            toplam += row.n
            print(f"  {tbl}: {row.n} satır ({ana}) | min={row.mn} | max={row.mx} "
                  f"| hariç tutulan={haric.n}")
            print(f"      kolonlar: {', '.join(cols)}")
        print(f"  → toplam {toplam} satır etkilenecek")

        sample = db.session.execute(text(
            f"SELECT order_number, order_date AS before, "
            f"order_date - {SHIFT} AS after_utc "
            f"FROM orders_delivered WHERE order_date IS NOT NULL AND {WHERE_TRENDYOL} "
            f"ORDER BY order_date DESC LIMIT 3"
        )).all()
        print("  örnek (before → after -3s):")
        for s in sample:
            print(f"    {s.order_number}: {s.before}  →  {s.after_utc}")

        # ---- REVERT ----
        if args.revert:
            if not already:
                print("\n[REVERT] İşaretçi yok — muhtemelen uygulanmadı.")
                print("         Güvenlik için iptal edildi. Emin isen işaretçiyi elle ekleyip çalıştır.")
                return 1
            for tbl, cols, where in hedefler:
                for col in cols:
                    db.session.execute(text(
                        f"UPDATE {tbl} SET {col} = {col} + {SHIFT} "
                        f"WHERE {col} IS NOT NULL AND {where}"
                    ))
            db.session.execute(text("DELETE FROM applied_migrations WHERE key=:k"), {"k": MARKER})
            db.session.commit()
            print("\n[REVERT] +3 saat geri alındı, işaretçi silindi.")
            return 0

        # ---- APPLY ----
        if args.apply:
            if already:
                print("\n[APPLY] Zaten uygulanmış (işaretçi var) → HİÇBİR ŞEY yapılmadı. "
                      "Çift kaydırma önlendi.")
                return 0
            for tbl, cols, where in hedefler:
                for col in cols:
                    res = db.session.execute(text(
                        f"UPDATE {tbl} SET {col} = {col} - {SHIFT} "
                        f"WHERE {col} IS NOT NULL AND {where}"
                    ))
                    print(f"  {tbl}.{col}: {res.rowcount} satır −3s")
            db.session.execute(text("INSERT INTO applied_migrations(key) VALUES (:k)"), {"k": MARKER})
            db.session.commit()
            print("\n[APPLY] Tamamlandı. Trendyol tarihleri artık UTC; "
                  "panelde `| ist` ile İstanbul gösterilir.")
            return 0

        print("\n[DRY-RUN] Hiçbir değişiklik yazılmadı. Uygulamak için: --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
