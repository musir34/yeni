# -*- coding: utf-8 -*-
"""
Shopify Platform Adapter
Shopify Admin GraphQL API (2026-01) stock sync adapter.
client_id + client_secret ile OAuth token alır.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from shopify_site.shopify_config import ShopifyConfig

from .base import BasePlatformAdapter, StockItem, SyncResult
from logger_config import app_logger as logger


class ShopifyAdapter(BasePlatformAdapter):
    """Shopify stock sync adapter."""

    PLATFORM_NAME = "shopify"
    BATCH_SIZE = 100
    RATE_LIMIT_DELAY = 0.3

    def _init_config(self):
        self.store_domain = ShopifyConfig.normalized_store_domain()
        self.api_version = ShopifyConfig.API_VERSION

        self._variant_map: Dict[str, Dict[str, Any]] = {}
        self._active_location_id: Optional[str] = None

        if ShopifyConfig.LOCATION_ID:
            lid = ShopifyConfig.LOCATION_ID
            self._active_location_id = lid if lid.startswith("gid://") else f"gid://shopify/Location/{lid}"

        if ShopifyConfig.is_configured():
            self.is_configured = True
            logger.info(f"[SHOPIFY] Adapter configured - Store: {self.store_domain}")
        else:
            self.is_configured = False
            logger.warning("[SHOPIFY] Adapter not configured - missing credentials")

    def _get_headers(self) -> Dict[str, str]:
        return ShopifyConfig.get_headers()

    async def _graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        session = await self.get_session()
        payload = {"query": query, "variables": variables or {}}

        async with session.post(ShopifyConfig.graphql_url(), json=payload, headers=self._get_headers()) as response:
            response_at = datetime.utcnow()
            text = await response.text()

            if response.status == 401:
                ShopifyConfig.reset_token()
                async with session.post(ShopifyConfig.graphql_url(), json=payload, headers=self._get_headers()) as retry:
                    response_at = datetime.utcnow()
                    text = await retry.text()
                    if retry.status != 200:
                        raise RuntimeError(f"Shopify GraphQL HTTP {retry.status}: {text[:300]}")
                    data = await retry.json()
                    if data.get("errors"):
                        raise RuntimeError(f"Shopify GraphQL error: {data['errors']}")
                    return {"data": data["data"], "response_at": response_at}

            if response.status != 200:
                raise RuntimeError(f"Shopify GraphQL HTTP {response.status}: {text[:300]}")

            data = await response.json()
            if data.get("errors"):
                raise RuntimeError(f"Shopify GraphQL error: {data['errors']}")
            if data.get("data") is None:
                raise RuntimeError("Shopify GraphQL returned empty data")

            return {"data": data["data"], "response_at": response_at}

    async def _ensure_location_id(self) -> Optional[str]:
        if self._active_location_id:
            return self._active_location_id

        query = """
        query { locations(first: 10) { edges { node { id name isActive fulfillsOnlineOrders } } } }
        """
        result = await self._graphql(query)
        locations = [e["node"] for e in result["data"].get("locations", {}).get("edges", [])]

        selected = next(
            (loc for loc in locations if loc.get("isActive") and loc.get("fulfillsOnlineOrders")),
            locations[0] if locations else None,
        )
        if not selected:
            logger.error("[SHOPIFY] Active location not found")
            return None

        self._active_location_id = selected["id"]
        logger.info(f"[SHOPIFY] Location: {selected.get('name')} ({self._active_location_id})")
        return self._active_location_id

    @staticmethod
    def _normalize_sku(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    async def _ensure_variant_map(self):
        if self._variant_map:
            return

        query = """
        query GetVariants($first: Int!, $after: String) {
          productVariants(first: $first, after: $after) {
            edges {
              node {
                id
                sku
                barcode
                title
                product { title }
                inventoryItem { id }
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
        """
        after = None
        total = 0

        while True:
            result = await self._graphql(query, {"first": 250, "after": after})
            block = result["data"].get("productVariants", {})
            edges = block.get("edges", [])

            for edge in edges:
                node = edge.get("node", {})
                inv_item = node.get("inventoryItem") or {}
                sku = self._normalize_sku(node.get("sku"))
                barcode = self._normalize_sku(node.get("barcode"))
                inv_item_id = inv_item.get("id")

                if inv_item_id and (barcode or sku):
                    info = {
                        "inventory_item_id": inv_item_id,
                        "variant_gid": node.get("id"),
                        "title": (node.get("product") or {}).get("title") or node.get("title"),
                        "barcode": barcode,
                        "sku": sku,
                    }
                    for key in [barcode, sku]:
                        if key:
                            self._variant_map[key] = info
                            self._variant_map[key.lower()] = info
                            # Leading-zero varyasyonları
                            stripped = key.lstrip("0")
                            if stripped and stripped != key:
                                self._variant_map[stripped] = info
                                self._variant_map[stripped.lower()] = info
                            if not key.startswith("0"):
                                self._variant_map["0" + key] = info
                                self._variant_map[("0" + key).lower()] = info
                    total += 1

            page_info = block.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")
            await asyncio.sleep(0.1)

        logger.info(f"[SHOPIFY] Loaded {total} variant mappings")

    async def send_stock_batch(self, items: List[StockItem]) -> List[SyncResult]:
        if not items:
            return []

        await self._ensure_variant_map()
        location_id = await self._ensure_location_id()

        if not location_id:
            return [
                SyncResult(barcode=item.barcode, success=False, quantity_sent=max(0, item.quantity),
                           error_message="Shopify location not found")
                for item in items
            ]

        results: List[SyncResult] = []
        matched_items = []

        for item in items:
            barcode = self._normalize_sku(item.barcode)
            sku = self._normalize_sku(item.sku)
            match = None

            def _find(val):
                if not val:
                    return None
                candidates = [val, val.lower(), val.lstrip("0"), val.lstrip("0").lower()]
                if not val.startswith("0"):
                    candidates.extend(["0" + val, ("0" + val).lower()])
                for c in candidates:
                    if c and c in self._variant_map:
                        return self._variant_map[c]
                return None

            match = _find(barcode)
            if not match:
                match = _find(sku)

            if not match:
                results.append(SyncResult(barcode=item.barcode, success=False,
                                          quantity_sent=max(0, item.quantity),
                                          error_message="Shopify variant not found"))
                continue
            matched_items.append((item, match["inventory_item_id"]))

        # Toplu gönderim: max 100 item tek API çağrısı
        BULK_SIZE = 100
        if matched_items:
            for i in range(0, len(matched_items), BULK_SIZE):
                chunk = matched_items[i:i + BULK_SIZE]
                chunk_results = await self._set_inventory_bulk(chunk, location_id)
                results.extend(chunk_results)
                if i + BULK_SIZE < len(matched_items):
                    await asyncio.sleep(self.RATE_LIMIT_DELAY)

        ok = sum(1 for r in results if r.success)
        fail = len(results) - ok
        logger.info(f"[SHOPIFY] Batch: {len(items)} total, {ok} success, {fail} error")
        if fail > 0:
            errors = [r for r in results if not r.success]
            for e in errors[:5]:
                logger.warning(f"[SHOPIFY] Error: barcode={e.barcode} msg={e.error_message}")
        return results

    async def _set_inventory_bulk(self, items_with_ids: List, location_id: str) -> List[SyncResult]:
        """Tek API çağrısında birden fazla item'ın stokunu güncelle."""
        sent_at = datetime.utcnow()
        mutation = """
        mutation InventorySetQuantities($input: InventorySetQuantitiesInput!) {
          inventorySetQuantities(input: $input) {
            inventoryAdjustmentGroup { createdAt reason changes { name delta } }
            userErrors { field message }
          }
        }
        """
        quantities = []
        for item, inv_item_id in items_with_ids:
            quantities.append({
                "inventoryItemId": inv_item_id,
                "locationId": location_id,
                "quantity": max(0, item.quantity),
            })

        variables = {
            "input": {
                "name": "available",
                "reason": "correction",
                "ignoreCompareQuantity": True,
                "quantities": quantities,
            }
        }
        try:
            result = await self._graphql(mutation, variables)
            response_at = result.get("response_at")
            payload = result["data"].get("inventorySetQuantities", {})
            errors = payload.get("userErrors") or []
            if errors:
                err_msg = "; ".join(e.get("message", "") for e in errors)
                return [
                    SyncResult(barcode=item.barcode, success=False, quantity_sent=max(0, item.quantity),
                               error_message=err_msg, response_data=payload, sent_at=sent_at, response_at=response_at)
                    for item, _ in items_with_ids
                ]
            return [
                SyncResult(barcode=item.barcode, success=True, quantity_sent=max(0, item.quantity),
                           response_data=payload, sent_at=sent_at, response_at=response_at)
                for item, _ in items_with_ids
            ]
        except Exception as exc:
            return [
                SyncResult(barcode=item.barcode, success=False, quantity_sent=max(0, item.quantity),
                           error_message=str(exc), sent_at=sent_at)
                for item, _ in items_with_ids
            ]

    async def get_platform_products(self) -> List[Dict[str, Any]]:
        await self._ensure_variant_map()
        products = []
        seen = set()
        for key, info in self._variant_map.items():
            iid = info["inventory_item_id"]
            if iid not in seen:
                seen.add(iid)
                products.append({
                    "barcode": info.get("barcode"),
                    "sku": info.get("sku"),
                    "inventory_item_id": iid,
                    "title": info.get("title"),
                })
        return products


shopify_adapter = ShopifyAdapter()
