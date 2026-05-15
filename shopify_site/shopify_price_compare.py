# -*- coding: utf-8 -*-
"""
Shopify ↔ Trendyol Fiyat Karşılaştırma Servisi
==============================================
Shopify variant fiyatlarını (variant.price) panel ürün tablosundaki Trendyol
satış fiyatıyla (Product.sale_price) karşılaştırır.

Eşleştirme `ShopifyMapping` üzerinden yapılır — barkod eşleşmesi orada zaten
yapılmış durumda. Burada sadece o eşleşmelerin fiyat tarafına bakıyoruz.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .shopify_config import ShopifyConfig

logger = logging.getLogger(__name__)


class PriceCompareService:
    """Shopify ↔ Trendyol satış fiyatı karşılaştırma servisi."""

    VARIANTS_PAGE_SIZE = 250

    def __init__(self):
        self.config = ShopifyConfig

    def is_configured(self) -> bool:
        return self.config.is_configured()

    # ─────────────────────────────────────────────────────────────
    # GraphQL helper (shopify_stock_service ile aynı pattern)
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
    # Shopify variant fiyatlarını çek
    # ─────────────────────────────────────────────────────────────
    def fetch_variant_prices(self) -> Dict[str, Dict[str, Any]]:
        """variant_id (GID) → {price, compareAtPrice, currency, title, product_title} sözlüğü."""
        query = """
        query GetVariantPrices($first: Int!, $after: String) {
          productVariants(first: $first, after: $after) {
            edges {
              node {
                id
                title
                price
                compareAtPrice
                product { title }
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
        """
        result: Dict[str, Dict[str, Any]] = {}
        after: Optional[str] = None
        page = 0

        while True:
            data = self._graphql(query, {"first": self.VARIANTS_PAGE_SIZE, "after": after})
            block = data.get("productVariants", {})
            edges = block.get("edges", [])
            for edge in edges:
                node = edge["node"]
                result[node["id"]] = {
                    "price": _to_float(node.get("price")),
                    "compare_at_price": _to_float(node.get("compareAtPrice")),
                    "title": node.get("title", ""),
                    "product_title": (node.get("product") or {}).get("title", ""),
                }
            page += 1
            page_info = block.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")

        logger.info("[PRICE-CMP] %d Shopify variant fiyatı çekildi (%d sayfa)", len(result), page)
        return result

    # ─────────────────────────────────────────────────────────────
    # Karşılaştırma
    # ─────────────────────────────────────────────────────────────
    def compare(
        self,
        only_differences: bool = True,
        min_diff_percent: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Eşleşmiş varyantları model koduna (Product.product_main_id) göre grupla
        ve her grup için Shopify ↔ Trendyol satış fiyatı karşılaştırması yap.

        Args:
            only_differences: True ise içinde tek bir farklı variant bile olmayan
                              model grupları atılır.
            min_diff_percent: Bir grubun en az bir varyantında bu eşiğin üzerinde
                              fark olmalı; aksi halde grup atılır. 0 ise filtre yok.

        Dönüş:
            {
              "success": True,
              "summary": {...},
              "groups": [
                {
                  "model_code": "ABC123",
                  "product_title": "...",
                  "variant_count": 3,
                  "shopify_price_range": [..., ...],
                  "trendyol_price_range": [..., ...],
                  "max_abs_diff_percent": 12.5,
                  "status_summary": {"equal": 1, "shopify_higher": 2, ...},
                  "worst_status": "shopify_higher",
                  "variants": [ {barcode, color, size, shopify_price, trendyol_price, diff, diff_percent, status, variant_title}, ... ]
                },
                ...
              ]
            }
        """
        from models import Product, ShopifyMapping

        mappings: List[ShopifyMapping] = ShopifyMapping.query.all()
        if not mappings:
            return {
                "success": True,
                "summary": _empty_summary(),
                "groups": [],
            }

        # Panel ürünlerini barkoda göre çek (model_kodu, title, color, size, fiyat için)
        barcodes = [m.barcode for m in mappings]
        products = {
            p.barcode: p
            for p in Product.query.filter(Product.barcode.in_(barcodes)).all()
        }

        # Shopify fiyatlarını canlı çek
        shopify_prices = self.fetch_variant_prices()

        summary = _empty_summary()
        groups: Dict[str, Dict[str, Any]] = {}

        for m in mappings:
            sp = shopify_prices.get(m.shopify_variant_id)
            shopify_price = sp["price"] if sp else None

            product = products.get(m.barcode)
            trendyol_price = float(product.sale_price) if product and product.sale_price else None

            if shopify_price is None and trendyol_price is None:
                continue

            diff = None
            diff_percent = None
            status = "unknown"
            if shopify_price is not None and trendyol_price is not None:
                diff = round(shopify_price - trendyol_price, 2)
                base = trendyol_price if trendyol_price > 0 else shopify_price
                diff_percent = round((diff / base) * 100, 2) if base else 0.0
                if abs(diff) < 0.01:
                    status = "equal"
                elif diff > 0:
                    status = "shopify_higher"
                else:
                    status = "trendyol_higher"
            elif shopify_price is not None and trendyol_price is None:
                status = "only_shopify"
            elif trendyol_price is not None and shopify_price is None:
                status = "only_trendyol"

            summary["by_status"][status] = summary["by_status"].get(status, 0) + 1
            summary["total"] += 1

            model_code = (product.product_main_id if product and product.product_main_id else None) or "(model kodu yok)"

            grp = groups.get(model_code)
            if grp is None:
                grp = {
                    "model_code": model_code,
                    "product_title": (product.title if product else None)
                                      or (sp["product_title"] if sp else None)
                                      or m.shopify_product_title
                                      or "",
                    "variants": [],
                    "status_summary": {},
                }
                groups[model_code] = grp

            grp["variants"].append({
                "barcode": m.barcode,
                "color": (product.color if product else "") or "",
                "size": (product.size if product else "") or "",
                "variant_title": (sp["title"] if sp else None) or m.shopify_variant_title or "",
                "shopify_variant_id": m.shopify_variant_id,
                "shopify_price": shopify_price,
                "trendyol_price": trendyol_price,
                "diff": diff,
                "diff_percent": diff_percent,
                "status": status,
            })
            grp["status_summary"][status] = grp["status_summary"].get(status, 0) + 1

        # Grup özetlerini hesapla
        STATUS_PRIORITY = ["trendyol_higher", "shopify_higher", "only_shopify", "only_trendyol", "unknown", "equal"]
        result_groups: List[Dict[str, Any]] = []

        for g in groups.values():
            sh_prices = [v["shopify_price"] for v in g["variants"] if v["shopify_price"] is not None]
            ty_prices = [v["trendyol_price"] for v in g["variants"] if v["trendyol_price"] is not None]
            diffs = [v["diff_percent"] for v in g["variants"] if v["diff_percent"] is not None]
            max_abs = max((abs(d) for d in diffs), default=0.0)
            has_diff = any(v["status"] != "equal" for v in g["variants"])

            if only_differences and not has_diff:
                continue
            if min_diff_percent > 0 and max_abs < min_diff_percent:
                continue

            g["variant_count"] = len(g["variants"])
            g["shopify_price_range"] = [min(sh_prices), max(sh_prices)] if sh_prices else [None, None]
            g["trendyol_price_range"] = [min(ty_prices), max(ty_prices)] if ty_prices else [None, None]
            g["max_abs_diff_percent"] = round(max_abs, 2)
            g["worst_status"] = next((s for s in STATUS_PRIORITY if g["status_summary"].get(s)), "equal")

            # Grup içinde varyantları farkı yüksekten düşüğe sırala
            g["variants"].sort(
                key=lambda v: abs(v["diff_percent"]) if v["diff_percent"] is not None else -1,
                reverse=True,
            )
            result_groups.append(g)

        # Grupları en yüksek mutlak fark % değerine göre sırala
        result_groups.sort(key=lambda g: g["max_abs_diff_percent"], reverse=True)

        return {
            "success": True,
            "summary": summary,
            "groups": result_groups,
        }


def _to_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _empty_summary() -> Dict[str, Any]:
    return {
        "total": 0,
        "by_status": {
            "equal": 0,
            "shopify_higher": 0,
            "trendyol_higher": 0,
            "only_shopify": 0,
            "only_trendyol": 0,
        },
    }


price_compare_service = PriceCompareService()
