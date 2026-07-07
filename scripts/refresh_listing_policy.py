"""İptal-eğilimli ürünler için otomatik listeleme tamponu politikasını günceller.

Son N günde >= M iptali olan barkodlara ekstra listeleme tamponu uygular; artık
eğilimli olmayan otomatik kayıtları temizler. Elle (auto=False) kayıtlara dokunmaz.

Kullanım (sunucuda):
    python -m scripts.refresh_listing_policy                 # 30 gün, >=2 iptal, +2 tampon
    python -m scripts.refresh_listing_policy --days 30 --min-cancels 2 --extra 2
    python -m scripts.refresh_listing_policy --dry-run       # sadece göster, yazma

Öneri: 6 saatte bir cron/job olarak çalıştır.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Listeleme tamponu politikasını güncelle")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--min-cancels", type=int, default=2)
    ap.add_argument("--extra", type=int, default=2, help="uygulanacak ekstra tampon")
    ap.add_argument("--dry-run", action="store_true", help="yazma, sadece eğilimli listeyi göster")
    args = ap.parse_args()

    from app import app
    from models import db, StockListingPolicy
    from stock_sync import listing_policy as lp

    with app.app_context():
        # Tablo yoksa oluştur (additive, checkfirst)
        try:
            StockListingPolicy.__table__.create(bind=db.engine, checkfirst=True)
        except Exception as exc:
            print(f"[UYARI] tablo oluşturma atlandı: {exc}")

        prone = lp.compute_cancel_prone(days=args.days, min_cancels=args.min_cancels)
        print(f"Son {args.days} günde >= {args.min_cancels} iptalli {len(prone)} ürün bulundu:")
        for bc, cnt in sorted(prone.items(), key=lambda x: -x[1]):
            print(f"  {bc:20s}  {cnt} iptal")

        if args.dry_run:
            print("\n[DRY-RUN] Değişiklik yazılmadı.")
            return 0

        res = lp.refresh_policies(
            days=args.days, min_cancels=args.min_cancels, extra_buffer=args.extra,
        )
        print(
            f"\nGüncellendi → eğilimli: {res['prone']}, "
            f"eklenen/değişen: {res['changed']}, temizlenen: {res['expired']}"
        )
        total = StockListingPolicy.query.count()
        auto = StockListingPolicy.query.filter_by(auto=True).count()
        print(f"Aktif politika: {total} (otomatik: {auto}, elle: {total - auto})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
