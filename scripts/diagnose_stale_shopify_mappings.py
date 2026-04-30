"""21 stale Shopify mapping'inin gerçek durumunu Shopify GraphQL ile kontrol eder.

Her stale mapping için:
- InventoryItem hâlâ var mı?
- tracked durumu nedir?
- Bağlı variant/product hâlâ aktif mi (status, archived)?

Çıktı: tablo + öneri (sil / yeniden eşle / aktif et).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("DISABLE_JOBS", "1")

from app import app
from models import db, ShopifyMapping, CentralStock
from shopify_site.shopify_stock_service import shopify_stock_service

STALE_DAYS = 2
CHUNK = 50

NODES_QUERY = """
query CheckItems($ids: [ID!]!) {
  nodes(ids: $ids) {
    __typename
    ... on InventoryItem {
      id
      tracked
      sku
      variant {
        id
        title
        sku
        barcode
        product {
          id
          title
          status
        }
      }
    }
  }
}
"""


def main() -> int:
    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(days=STALE_DAYS)
        stale = ShopifyMapping.query.filter(
            (ShopifyMapping.last_sync_at.is_(None)) | (ShopifyMapping.last_sync_at < cutoff)
        ).all()
        print(f"Stale mapping (>{STALE_DAYS} gün): {len(stale)}\n")

        # CentralStock'ta var mı kontrolü
        bcs = [m.barcode for m in stale]
        cs_map = {cs.barcode: cs.qty for cs in CentralStock.query.filter(CentralStock.barcode.in_(bcs)).all()}

        # Inventory item ID'leri ile Shopify'a sor
        inv_ids = [m.shopify_inventory_item_id for m in stale if m.shopify_inventory_item_id]
        node_map: dict = {}
        for i in range(0, len(inv_ids), CHUNK):
            chunk = inv_ids[i:i + CHUNK]
            try:
                data = shopify_stock_service._graphql(NODES_QUERY, {"ids": chunk})
            except Exception as exc:
                print(f"!! GraphQL hata (chunk {i}): {exc}")
                continue
            for node in (data.get("nodes") or []):
                if node:
                    node_map[node["id"]] = node
                # null node'lar = silinmiş item

        # Rapor
        deleted, archived, untracked, ok = [], [], [], []
        unknown = []  # Shopify'da hiç dönmedi → silinmiş
        for m in stale:
            inv_id = m.shopify_inventory_item_id
            in_panel = m.barcode in cs_map
            panel_qty = cs_map.get(m.barcode, "—")
            node = node_map.get(inv_id)

            if node is None:
                unknown.append((m, in_panel, panel_qty))
                continue

            tracked = node.get("tracked")
            variant = node.get("variant") or {}
            product = (variant or {}).get("product") or {}
            status = product.get("status")
            title = (product.get("title") or "")[:50]

            row = (m, in_panel, panel_qty, tracked, status, title)
            if status == "ARCHIVED":
                archived.append(row)
            elif not tracked:
                untracked.append(row)
            else:
                ok.append(row)

        # Yazdır
        def _fmt_row(r, with_extra=False):
            m = r[0]; in_panel = r[1]; panel_qty = r[2]
            base = f"  {m.barcode:25s} | inv={m.shopify_inventory_item_id[-12:]:12s} | panel_var={'E' if in_panel else 'H'} qty={panel_qty}"
            if with_extra and len(r) > 3:
                tracked, status, title = r[3], r[4], r[5]
                base += f" | tracked={tracked} status={status} | {title}"
            return base

        print(f"=== ❌ Shopify'da SİLİNMİŞ (InventoryItem yok) — {len(unknown)} adet ===")
        for r in unknown:
            print(_fmt_row(r))
        print(f"\n=== 📦 ARCHIVED ürün — {len(archived)} adet ===")
        for r in archived:
            print(_fmt_row(r, with_extra=True))
        print(f"\n=== 🚫 tracked=false — {len(untracked)} adet ===")
        for r in untracked:
            print(_fmt_row(r, with_extra=True))
        print(f"\n=== ✅ Aktif ve trackable (neden fail ediyor anlaşılmadı) — {len(ok)} adet ===")
        for r in ok:
            print(_fmt_row(r, with_extra=True))

        # Özet öneri
        print("\n" + "=" * 60)
        print("ÖNERİ:")
        if unknown:
            print(f"  • {len(unknown)} silinmiş InventoryItem → ShopifyMapping'ten SİLİNMELİ")
        if archived:
            print(f"  • {len(archived)} archived ürün → Shopify'da yeniden aktive et VEYA mapping'i sil")
        if untracked:
            print(f"  • {len(untracked)} tracked=false → _enable_tracking_for_mappings çalışmıyor; manuel aç")
        if ok:
            print(f"  • {len(ok)} aktif ürün hâlâ fail ediyor → 1 sync sonrası logs/app.log'da [SHOPIFY] FAIL satırlarına bak")
        return 0


if __name__ == "__main__":
    sys.exit(main())
