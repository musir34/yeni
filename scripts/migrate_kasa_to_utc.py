"""TEK SEFERLİK veri düzeltmesi: kasa tarih kolonlarını İstanbul-yerel → UTC'ye kaydır.

NEDEN
-----
Kasa modülü eskiden `datetime.now()` (İstanbul, UTC+3) ile saklıyordu. Kod artık
UTC saklıyor (naive=UTC konvansiyonu) ve gösterimde `| ist` ile İstanbul'a çeviriyor.
Mevcut ESKİ satırlar hâlâ İstanbul-yerel; onları **−3 saat** kaydırıp UTC yapmak gerekir.
Türkiye 2016'dan beri kalıcı UTC+3 (DST yok) → sabit −3 saat doğru.

GÜVENLİK
--------
- Varsayılan **DRY-RUN**: hiçbir şey yazmaz, sayıları ve örnekleri gösterir.
- `--apply`: tek transaction'da −3s uygular, `applied_migrations` işaretçisi yazar.
- **Çift-uygulama koruması**: işaretçi varsa tekrar UYGULAMAZ (−6s olmaz).
- `--revert`: +3s geri alır ve işaretçiyi siler (acil çıkış).

Kullanım (sunucuda):
    python -m scripts.migrate_kasa_to_utc              # dry-run (önizleme)
    python -m scripts.migrate_kasa_to_utc --apply      # uygula
    python -m scripts.migrate_kasa_to_utc --revert     # geri al
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

MARKER = "kasa_utc_shift_2026_07"
# (tablo, kolon)
TARGETS = [
    ("odeme", "odeme_tarihi"),
    ("kasa", "tarih"),
    ("ana_kasa", "guncelleme_tarihi"),
    ("ana_kasa_islemler", "tarih"),
]
SHIFT = "interval '3 hours'"


def main() -> int:
    ap = argparse.ArgumentParser(description="Kasa tarihlerini İstanbul→UTC kaydır (tek seferlik)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true", help="−3 saat uygula")
    g.add_argument("--revert", action="store_true", help="+3 saat geri al (işaretçiyi de sil)")
    args = ap.parse_args()

    from app import app
    from sqlalchemy import text
    from models import db

    with app.app_context():
        # İşaretçi tablosu
        db.session.execute(text(
            "CREATE TABLE IF NOT EXISTS applied_migrations "
            "(key TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT now())"
        ))
        db.session.commit()
        already = db.session.execute(
            text("SELECT 1 FROM applied_migrations WHERE key=:k"), {"k": MARKER}
        ).first() is not None

        # ---- ÖNİZLEME ----
        print(f"=== Kasa UTC kaydırma — işaretçi '{MARKER}' {'VAR (uygulanmış)' if already else 'YOK'} ===")
        for tbl, col in TARGETS:
            row = db.session.execute(text(
                f"SELECT count(*) n, min({col}) mn, max({col}) mx FROM {tbl} WHERE {col} IS NOT NULL"
            )).first()
            print(f"  {tbl}.{col}: {row.n} satır | min={row.mn} | max={row.mx}")
        # Örnek: bir tablodan 3 satır, before → after(-3s) önizleme
        sample = db.session.execute(text(
            "SELECT id, tarih AS before, tarih - interval '3 hours' AS after_utc "
            "FROM kasa WHERE tarih IS NOT NULL ORDER BY id DESC LIMIT 3"
        )).all()
        print("  örnek kasa (before → after -3s):")
        for s in sample:
            print(f"    #{s.id}: {s.before}  →  {s.after_utc}")

        # ---- REVERT ----
        if args.revert:
            if not already:
                print("\n[REVERT] İşaretçi yok — muhtemelen uygulanmadı. Yine de +3s geri alınsın mı?")
                print("         Güvenlik için iptal edildi. Emin isen işaretçiyi elle ekleyip çalıştır.")
                return 1
            for tbl, col in TARGETS:
                db.session.execute(text(f"UPDATE {tbl} SET {col} = {col} + {SHIFT} WHERE {col} IS NOT NULL"))
            db.session.execute(text("DELETE FROM applied_migrations WHERE key=:k"), {"k": MARKER})
            db.session.commit()
            print("\n[REVERT] +3 saat geri alındı, işaretçi silindi.")
            return 0

        # ---- APPLY ----
        if args.apply:
            if already:
                print("\n[APPLY] Zaten uygulanmış (işaretçi var) → HİÇBİR ŞEY yapılmadı. Çift kaydırma önlendi.")
                return 0
            for tbl, col in TARGETS:
                res = db.session.execute(text(
                    f"UPDATE {tbl} SET {col} = {col} - {SHIFT} WHERE {col} IS NOT NULL"
                ))
                print(f"  {tbl}.{col}: {res.rowcount} satır −3s")
            db.session.execute(text("INSERT INTO applied_migrations(key) VALUES (:k)"), {"k": MARKER})
            db.session.commit()
            print("\n[APPLY] Tamamlandı. Artık kasa tarihleri UTC; panelde `| ist` ile İstanbul gösterilir.")
            return 0

        print("\n[DRY-RUN] Hiçbir değişiklik yazılmadı. Uygulamak için: --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
