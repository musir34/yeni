# -*- coding: utf-8 -*-
"""
Shopify Stok Senkronizasyon Servisi
====================================
Shopify Admin GraphQL API (2026-01) ile barkod eşleştirme ve stok güncelleme.

Akış:
1. Shopify'dan tüm variant'ları çek (barcode alanı ile)
2. Panel'deki barkodlarla eşleştir -> ShopifyMapping tablosuna kaydet
3. CentralStock'tan mevcut stokları al -> Shopify'a gönder
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .shopify_config import ShopifyConfig

logger = logging.getLogger(__name__)


class ShopifyStockService:
    """Shopify stok eşleştirme ve senkronizasyon servisi."""

    VARIANTS_PAGE_SIZE = 250

    def __init__(self):
        self.config = ShopifyConfig
        self._location_id: Optional[str] = None
        self._last_unmatched: List[Dict[str, Any]] = []  # Son eşleştirmede eşleşmeyenler

    def is_configured(self) -> bool:
        return self.config.is_configured()

    # ─────────────────────────────────────────────────────────────
    # GraphQL helper
    # ─────────────────────────────────────────────────────────────
    def _graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import requests

        payload = {"query": query, "variables": variables or {}}
        resp = requests.post(
            self.config.graphql_url(),
            headers=self.config.get_headers(),
            json=payload,
            timeout=self.config.TIMEOUT,
        )

        # 401 → token geçersiz, yenile ve tekrar dene
        if resp.status_code == 401:
            self.config.reset_token()
            resp = requests.post(
                self.config.graphql_url(),
                headers=self.config.get_headers(),
                json=payload,
                timeout=self.config.TIMEOUT,
            )

        resp.raise_for_status()
        body = resp.json()

        if body.get("errors"):
            raise RuntimeError(f"GraphQL errors: {body['errors']}")

        return body.get("data", {})

    # ─────────────────────────────────────────────────────────────
    # Location
    # ─────────────────────────────────────────────────────────────
    def get_location_id(self) -> str:
        """İlk aktif fulfillment lokasyonunun GID'sini döndür."""
        if self._location_id:
            return self._location_id

        configured = self.config.LOCATION_ID
        if configured:
            if configured.startswith("gid://"):
                self._location_id = configured
            else:
                self._location_id = f"gid://shopify/Location/{configured}"
            return self._location_id

        data = self._graphql("""
            query { locations(first: 10) { edges { node { id name isActive fulfillsOnlineOrders } } } }
        """)
        edges = data.get("locations", {}).get("edges", [])
        for edge in edges:
            node = edge["node"]
            if node.get("isActive") and node.get("fulfillsOnlineOrders"):
                self._location_id = node["id"]
                logger.info("[SHOPIFY] Lokasyon: %s (%s)", node["name"], node["id"])
                return self._location_id

        if edges:
            self._location_id = edges[0]["node"]["id"]
            return self._location_id

        raise RuntimeError("Shopify'da aktif lokasyon bulunamadı")

    # ─────────────────────────────────────────────────────────────
    # Tüm Variant'ları çek
    # ─────────────────────────────────────────────────────────────
    def fetch_all_variants(self) -> List[Dict[str, Any]]:
        """
        Shopify'dan tüm product variant'ları çeker.
        Her variant: id, sku, barcode, title, product title, inventoryItem id.
        """
        query = """
        query GetVariants($first: Int!, $after: String) {
          productVariants(first: $first, after: $after) {
            edges {
              node {
                id
                title
                sku
                barcode
                inventoryQuantity
                product { title }
                inventoryItem { id }
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
        """
        all_variants: List[Dict[str, Any]] = []
        after = None

        while True:
            data = self._graphql(query, {"first": self.VARIANTS_PAGE_SIZE, "after": after})
            block = data.get("productVariants", {})
            edges = block.get("edges", [])

            for edge in edges:
                node = edge["node"]
                all_variants.append({
                    "variant_id": node["id"],
                    "title": node.get("title", ""),
                    "sku": (node.get("sku") or "").strip(),
                    "barcode": (node.get("barcode") or "").strip(),
                    "inventory_quantity": node.get("inventoryQuantity", 0),
                    "product_title": (node.get("product") or {}).get("title", ""),
                    "inventory_item_id": (node.get("inventoryItem") or {}).get("id", ""),
                })

            page_info = block.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")

        logger.info("[SHOPIFY] %d variant çekildi", len(all_variants))
        return all_variants

    # ─────────────────────────────────────────────────────────────
    # Barkod Eşleştirme
    # ─────────────────────────────────────────────────────────────
    def match_barcodes(self) -> Dict[str, Any]:
        """
        Shopify variant barkodlarını panel barkodlarıyla eşleştir ve DB'ye kaydet.
        Eşleştirme mantığı:
        1. Shopify variant.barcode == Product.barcode (birebir)
        2. Shopify variant.sku == Product.barcode (SKU olarak eşleşme)
        3. BarcodeAlias üzerinden eşleşme
        """
        from models import db, Product, BarcodeAlias, ShopifyMapping

        # 1. Shopify'dan tüm variant'ları çek
        shopify_variants = self.fetch_all_variants()

        # 2. Panel barkodlarını al
        panel_barcodes = {p.barcode.strip().lower(): p.barcode for p in Product.query.with_entities(Product.barcode).all()}

        # 3. Alias barkodlarını al
        alias_map: Dict[str, str] = {}
        for alias in BarcodeAlias.query.all():
            alias_map[alias.alias_barcode.strip().lower()] = alias.main_barcode

        # 4. Her Shopify varyantını ayrı ayrı eşleştir (varyant barkoduna göre)
        matched = 0
        unmatched_shopify = []
        new_mappings: List[ShopifyMapping] = []
        seen_variant_ids = set()  # Aynı Shopify varyantı tekrar eklemesin

        for variant in shopify_variants:
            shopify_barcode = variant["barcode"]
            shopify_sku = variant["sku"]
            inventory_item_id = variant["inventory_item_id"]
            variant_id = variant["variant_id"]

            if not inventory_item_id:
                continue

            # Aynı Shopify varyantı zaten işlendiyse atla
            if variant_id in seen_variant_ids:
                continue
            seen_variant_ids.add(variant_id)

            # Panel barkodu bul
            panel_barcode = None

            # Yöntem 1: Barkod eşleşmesi
            if shopify_barcode:
                key = shopify_barcode.lower()
                if key in panel_barcodes:
                    panel_barcode = panel_barcodes[key]
                elif key in alias_map:
                    panel_barcode = alias_map[key]

            # Yöntem 2: SKU eşleşmesi
            if not panel_barcode and shopify_sku:
                key = shopify_sku.lower()
                if key in panel_barcodes:
                    panel_barcode = panel_barcodes[key]
                elif key in alias_map:
                    panel_barcode = alias_map[key]

            if panel_barcode:
                new_mappings.append(ShopifyMapping(
                    barcode=panel_barcode,
                    shopify_variant_id=variant_id,
                    shopify_inventory_item_id=inventory_item_id,
                    shopify_product_title=variant["product_title"],
                    shopify_variant_title=variant["title"],
                    shopify_sku=shopify_sku,
                    shopify_barcode=shopify_barcode,
                ))
                matched += 1
            else:
                unmatched_shopify.append({
                    "variant_id": variant_id,
                    "product_title": variant["product_title"],
                    "variant_title": variant["title"],
                    "sku": shopify_sku,
                    "barcode": shopify_barcode,
                })

        # 5. Eski unique constraint varsa kaldır (barcode artık unique değil)
        from sqlalchemy import text
        try:
            db.session.execute(text("DROP INDEX IF EXISTS ix_shopify_mappings_barcode"))
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_shopify_mappings_barcode_nouni "
                "ON shopify_mappings (barcode)"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()

        # 6. Eski eşleştirmeleri temizle ve yenilerini kaydet
        ShopifyMapping.query.delete()
        db.session.flush()

        for mapping in new_mappings:
            db.session.add(mapping)

        db.session.commit()

        logger.info("[SHOPIFY] Eşleştirme tamamlandı: %d eşleşti, %d eşleşmedi",
                     matched, len(unmatched_shopify))

        # Tüm eşleşmeyenleri cache'le (CSV export için)
        self._last_unmatched = unmatched_shopify

        # Eşleşmeme nedenlerini analiz et
        no_barcode_no_sku = 0
        no_barcode_has_sku = 0
        has_barcode_no_match = 0
        for item in unmatched_shopify:
            has_bc = bool(item.get("barcode"))
            has_sk = bool(item.get("sku"))
            if not has_bc and not has_sk:
                no_barcode_no_sku += 1
            elif not has_bc and has_sk:
                no_barcode_has_sku += 1
            else:
                has_barcode_no_match += 1

        logger.info("[SHOPIFY] Eşleşmeme nedenleri: barcode+sku boş=%d, sadece sku var(panelde yok)=%d, barcode var ama panelde yok=%d",
                     no_barcode_no_sku, no_barcode_has_sku, has_barcode_no_match)

        return {
            "success": True,
            "matched": matched,
            "unmatched": len(unmatched_shopify),
            "total_shopify": len(shopify_variants),
            "total_panel": len(panel_barcodes),
            "unmatched_reasons": {
                "no_barcode_no_sku": no_barcode_no_sku,
                "has_sku_not_in_panel": no_barcode_has_sku,
                "has_barcode_not_in_panel": has_barcode_no_match,
            },
            "unmatched_items": unmatched_shopify[:100],
        }

    def get_unmatched_items(self) -> List[Dict[str, Any]]:
        """Son eşleştirmede eşleşmeyen tüm ürünleri döndür."""
        return self._last_unmatched

    # ─────────────────────────────────────────────────────────────
    # Stok Gönderimi
    # ─────────────────────────────────────────────────────────────
    def push_stock(self, barcodes: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        CentralStock'taki stokları Shopify'a gönder.
        barcodes: Belirli barkodlar (None ise tüm eşleşenler)
        """
        from models import db, CentralStock, ShopifyMapping

        location_id = self.get_location_id()

        # Eşleştirmeleri al
        query = ShopifyMapping.query
        if barcodes:
            query = query.filter(ShopifyMapping.barcode.in_(barcodes))
        mappings = query.all()

        if not mappings:
            return {"success": False, "error": "Eşleştirme bulunamadı. Önce barkod eşleştirmesi yapın."}

        # CentralStock'tan stokları al
        mapping_barcodes = [m.barcode for m in mappings]
        stocks = {cs.barcode: cs.qty for cs in CentralStock.query.filter(CentralStock.barcode.in_(mapping_barcodes)).all()}

        # Batch olarak gönder (aynı mutation ile max 100 öğe)
        results = {"success_count": 0, "error_count": 0, "skipped_count": 0, "details": [], "errors": []}
        batch: List[Dict] = []

        for mapping in mappings:
            qty = stocks.get(mapping.barcode, 0)
            batch.append({
                "mapping": mapping,
                "qty": max(0, qty),
            })

        # Shopify inventorySetQuantities max 100 item per call
        BATCH_SIZE = 100
        for i in range(0, len(batch), BATCH_SIZE):
            chunk = batch[i:i + BATCH_SIZE]
            self._send_stock_batch(chunk, location_id, results)

        # Sonuçları kaydet
        db.session.commit()

        total = results["success_count"] + results["error_count"] + results["skipped_count"]
        logger.info("[SHOPIFY] Stok gönderimi: %d başarılı, %d hata, %d atlandı / %d toplam",
                     results["success_count"], results["error_count"], results["skipped_count"], total)

        return {
            "success": True,
            "total": total,
            "success_count": results["success_count"],
            "error_count": results["error_count"],
            "skipped_count": results["skipped_count"],
            "errors": results["errors"][:20],
        }

    def _send_stock_batch(self, batch: List[Dict], location_id: str, results: Dict):
        """Tek bir batch stok güncellemesi gönder."""
        mutation = """
        mutation InventorySetQuantities($input: InventorySetQuantitiesInput!) {
          inventorySetQuantities(input: $input) {
            inventoryAdjustmentGroup {
              createdAt
              reason
              changes { name delta }
            }
            userErrors { field message }
          }
        }
        """

        for item in batch:
            mapping = item["mapping"]
            qty = item["qty"]

            variables = {
                "input": {
                    "name": "available",
                    "reason": "correction",
                    "ignoreCompareQuantity": True,
                    "quantities": [{
                        "inventoryItemId": mapping.shopify_inventory_item_id,
                        "locationId": location_id,
                        "quantity": qty,
                    }],
                }
            }

            try:
                data = self._graphql(mutation, variables)
                payload = data.get("inventorySetQuantities", {})
                errors = payload.get("userErrors") or []

                if errors:
                    err_msg = "; ".join(e.get("message", "") for e in errors)
                    results["error_count"] += 1
                    results["errors"].append({"barcode": mapping.barcode, "error": err_msg})
                    logger.warning("[SHOPIFY] Stok hatası %s: %s", mapping.barcode, err_msg)
                else:
                    results["success_count"] += 1
                    mapping.last_stock_sent = qty
                    mapping.last_sync_at = datetime.utcnow()
                    results["details"].append({"barcode": mapping.barcode, "qty": qty})
            except Exception as exc:
                results["error_count"] += 1
                results["errors"].append({"barcode": mapping.barcode, "error": str(exc)})
                logger.error("[SHOPIFY] Stok gönderim hatası %s: %s", mapping.barcode, exc)

    # ─────────────────────────────────────────────────────────────
    # Eşleştirme Listesi
    # ─────────────────────────────────────────────────────────────
    def get_mappings(self, page: int = 1, per_page: int = 50, search: str = "") -> Dict[str, Any]:
        """Kayıtlı eşleştirmeleri listele."""
        from models import ShopifyMapping, CentralStock

        query = ShopifyMapping.query
        if search:
            like = f"%{search}%"
            query = query.filter(
                (ShopifyMapping.barcode.ilike(like)) |
                (ShopifyMapping.shopify_product_title.ilike(like)) |
                (ShopifyMapping.shopify_sku.ilike(like))
            )

        total = query.count()
        mappings = query.order_by(ShopifyMapping.shopify_product_title).offset((page - 1) * per_page).limit(per_page).all()

        # Stokları al
        barcodes = [m.barcode for m in mappings]
        stocks = {cs.barcode: cs.qty for cs in CentralStock.query.filter(CentralStock.barcode.in_(barcodes)).all()} if barcodes else {}

        items = []
        for m in mappings:
            d = m.to_dict()
            d["current_stock"] = stocks.get(m.barcode, 0)
            items.append(d)

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Dashboard istatistikleri."""
        from models import ShopifyMapping, CentralStock, Product

        total_mappings = ShopifyMapping.query.count()
        total_products = Product.query.count()
        total_stock = CentralStock.query.count()

        last_sync = ShopifyMapping.query.filter(
            ShopifyMapping.last_sync_at.isnot(None)
        ).order_by(ShopifyMapping.last_sync_at.desc()).first()

        return {
            "total_mappings": total_mappings,
            "total_products": total_products,
            "total_stock_items": total_stock,
            "last_sync_at": last_sync.last_sync_at.isoformat() if last_sync and last_sync.last_sync_at else None,
        }


shopify_stock_service = ShopifyStockService()
