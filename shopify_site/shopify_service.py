"""
Shopify Admin GraphQL servis katmanı.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

from .shopify_config import ShopifyConfig

logger = logging.getLogger(__name__)


class ShopifyService:
    """Shopify Admin API için temel servis."""

    def __init__(self):
        self.config = ShopifyConfig
        self.timeout = self.config.TIMEOUT

    def is_configured(self) -> bool:
        return self.config.is_configured()

    def _post_graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "error": "Shopify API ayarları eksik"}

        payload = {
            "query": query,
            "variables": variables or {},
        }

        try:
            response = requests.post(
                self.config.graphql_url(),
                headers=self.config.get_headers(),
                json=payload,
                timeout=self.timeout,
            )

            # 401 → token geçersiz, yenile ve tekrar dene
            if response.status_code == 401:
                self.config.reset_token()
                response = requests.post(
                    self.config.graphql_url(),
                    headers=self.config.get_headers(),
                    json=payload,
                    timeout=self.timeout,
                )

            response.raise_for_status()
            body = response.json()

            errors = body.get("errors")
            data = body.get("data")

            # Shopify GraphQL partial response: errors + data birlikte gelebilir
            # (orn. read_customers scope yoksa customer=null doner ama siparis verisi gelir)
            if errors and data:
                # ACCESS_DENIED hatalarini uyari olarak logla, veriyi dondur
                access_denied = all(
                    e.get("extensions", {}).get("code") == "ACCESS_DENIED"
                    for e in errors
                )
                if access_denied:
                    scopes = {e.get("extensions", {}).get("requiredAccess", "?") for e in errors}
                    logger.warning(
                        "[SHOPIFY] Kismi erisim hatasi (veri dondu). Eksik scope: %s",
                        ", ".join(scopes),
                    )
                else:
                    logger.warning("[SHOPIFY] GraphQL partial errors: %s", errors)

                return {
                    "success": True,
                    "data": data,
                    "extensions": body.get("extensions", {}),
                    "warnings": [e.get("message", "") for e in errors[:3]],
                }

            if errors:
                logger.error("[SHOPIFY] GraphQL errors: %s", errors)
                return {"success": False, "error": errors}

            return {
                "success": True,
                "data": data or {},
                "extensions": body.get("extensions", {}),
            }
        except requests.exceptions.RequestException as exc:
            logger.error("[SHOPIFY] Request error: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}
        except ValueError as exc:
            logger.error("[SHOPIFY] JSON parse error: %s", exc, exc_info=True)
            return {"success": False, "error": "Shopify yanıtı JSON olarak okunamadı"}

    @staticmethod
    def _build_gid(resource_type: str, resource_id: str | int) -> str:
        raw_id = str(resource_id)
        if raw_id.startswith("gid://"):
            return raw_id
        return f"gid://shopify/{resource_type}/{raw_id}"

    def test_connection(self) -> Dict[str, Any]:
        query = """
        query ShopInfo {
          shop {
            id
            name
            email
            myshopifyDomain
            currencyCode
            primaryDomain {
              host
              url
            }
          }
        }
        """
        result = self._post_graphql(query)
        if not result.get("success"):
            return result

        return {
            "success": True,
            "shop": result["data"].get("shop"),
        }

    def run_graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._post_graphql(query, variables)

    def get_orders(
        self,
        limit: int = 20,
        query_filter: Optional[str] = None,
        after: Optional[str] = None,
        oldest_first: bool = False,
    ) -> Dict[str, Any]:
        reverse_val = "false" if oldest_first else "true"
        query = """
        query GetOrders($first: Int!, $query: String, $after: String) {
          orders(first: $first, query: $query, after: $after, reverse: """ + reverse_val + """, sortKey: PROCESSED_AT) {
            pageInfo {
              hasNextPage
              hasPreviousPage
              endCursor
              startCursor
            }
            edges {
              cursor
              node {
                id
                legacyResourceId
                name
                displayFinancialStatus
                displayFulfillmentStatus
                createdAt
                cancelledAt
                tags
                note
                currentTotalPriceSet {
                  shopMoney {
                    amount
                    currencyCode
                  }
                }
                totalRefundedSet {
                  shopMoney {
                    amount
                    currencyCode
                  }
                }
                customer {
                  firstName
                  lastName
                  email
                  phone
                }
                shippingAddress {
                  name
                  city
                  province
                  country
                }
                paymentGatewayNames
                fulfillments {
                  id
                  status
                  trackingInfo {
                    number
                    url
                    company
                  }
                  createdAt
                }
                lineItems(first: 20) {
                  edges {
                    node {
                      title
                      sku
                      quantity
                      currentQuantity
                      variant {
                        id
                        barcode
                        image {
                          url
                        }
                      }
                      originalTotalSet {
                        shopMoney {
                          amount
                          currencyCode
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        variables: Dict[str, Any] = {
            "first": max(1, min(limit, 100)),
            "query": query_filter,
        }
        if after:
            variables["after"] = after

        result = self._post_graphql(query, variables)
        if not result.get("success"):
            return result

        orders_data = result["data"].get("orders", {})
        page_info = orders_data.get("pageInfo", {})
        edges = orders_data.get("edges", [])
        orders = []
        for edge in edges:
            node = edge.get("node", {})
            node["cursor"] = edge.get("cursor")
            node["line_items"] = [
                item.get("node", {})
                for item in node.get("lineItems", {}).get("edges", [])
            ]
            node.pop("lineItems", None)
            # Her line item'a resolved panel barkodunu ekle
            try:
                from models import ShopifyMapping, Product
                from barcode_alias_helper import normalize_barcode as _nbc
                for li in node["line_items"]:
                    v = li.get("variant") or {}
                    vbc = v.get("barcode") or ""
                    vsku = li.get("sku") or ""
                    res = None
                    if vbc:
                        p = Product.query.filter_by(barcode=_nbc(vbc)).first()
                        if p: res = p.barcode
                    if not res and vsku:
                        m = ShopifyMapping.query.filter_by(shopify_sku=vsku).first()
                        if m: res = m.barcode
                    if not res and vbc:
                        m = ShopifyMapping.query.filter_by(shopify_barcode=vbc).first()
                        if m: res = m.barcode
                    li["resolved_barcode"] = res or vbc or ""
            except Exception:
                pass
            orders.append(node)

        return {
            "success": True,
            "orders": orders,
            "count": len(orders),
            "pageInfo": page_info,
        }

    def get_orders_count(self, query_filter: Optional[str] = None) -> Dict[str, Any]:
        """Siparis sayisini dondurur."""
        query = """
        query OrdersCount($query: String) {
          ordersCount(query: $query) {
            count
          }
        }
        """
        result = self._post_graphql(query, {"query": query_filter})
        if not result.get("success"):
            return result

        count = result["data"].get("ordersCount", {}).get("count", 0)
        return {"success": True, "count": count}

    def create_fulfillment(
        self,
        order_id: str | int,
        tracking_number: Optional[str] = None,
        tracking_company: Optional[str] = None,
        tracking_url: Optional[str] = None,
        notify_customer: bool = True,
    ) -> Dict[str, Any]:
        """Siparis icin fulfillment olusturur."""
        # Once order'dan fulfillment order id'leri al
        fo_query = """
        query GetFulfillmentOrders($id: ID!) {
          order(id: $id) {
            fulfillmentOrders(first: 10) {
              edges {
                node {
                  id
                  status
                  lineItems(first: 50) {
                    edges {
                      node {
                        id
                        remainingQuantity
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        gid = self._build_gid("Order", order_id)
        fo_result = self._post_graphql(fo_query, {"id": gid})
        if not fo_result.get("success"):
            return fo_result

        fo_edges = (
            fo_result["data"]
            .get("order", {})
            .get("fulfillmentOrders", {})
            .get("edges", [])
        )

        # Fulfill edilebilir fulfillment order'lari bul
        # Her fulfillmentOrderId icin line item'lari grupla
        fo_groups = {}
        for fo_edge in fo_edges:
            fo_node = fo_edge.get("node", {})
            fo_status = fo_node.get("status")
            logger.debug("[SHOPIFY] FulfillmentOrder id=%s status=%s", fo_node.get("id"), fo_status)
            if fo_status in ("OPEN", "IN_PROGRESS", "SCHEDULED"):
                fo_id = fo_node["id"]
                for li_edge in fo_node.get("lineItems", {}).get("edges", []):
                    li_node = li_edge.get("node", {})
                    if li_node.get("remainingQuantity", 0) > 0:
                        if fo_id not in fo_groups:
                            fo_groups[fo_id] = []
                        fo_groups[fo_id].append({
                            "id": li_node["id"],
                            "quantity": li_node["remainingQuantity"],
                        })

        fulfillment_line_items = [
            {"fulfillmentOrderId": fo_id, "fulfillmentOrderLineItems": items}
            for fo_id, items in fo_groups.items()
        ]

        if not fulfillment_line_items:
            return {
                "success": False,
                "error": "Karsilanacak urun bulunamadi (tumu zaten karsilanmis olabilir).",
            }

        # Fulfillment olustur
        mutation = """
        mutation FulfillOrder($fulfillment: FulfillmentV2Input!) {
          fulfillmentCreateV2(fulfillment: $fulfillment) {
            fulfillment {
              id
              status
              trackingInfo {
                number
                url
                company
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        tracking_info = {}
        if tracking_number:
            tracking_info["number"] = tracking_number
        if tracking_company:
            tracking_info["company"] = tracking_company
        if tracking_url:
            tracking_info["url"] = tracking_url

        variables: Dict[str, Any] = {
            "fulfillment": {
                "lineItemsByFulfillmentOrder": fulfillment_line_items,
                "notifyCustomer": notify_customer,
            }
        }
        if tracking_info:
            variables["fulfillment"]["trackingInfo"] = tracking_info

        logger.info("[SHOPIFY] Fulfillment olusturuluyor: fo_count=%d, tracking=%s", len(fulfillment_line_items), tracking_info)
        result = self._post_graphql(mutation, variables)
        if not result.get("success"):
            logger.error("[SHOPIFY] Fulfillment GraphQL hatasi: %s", result.get("error"))
            return result

        payload = result["data"].get("fulfillmentCreateV2", {})
        errors = payload.get("userErrors") or []
        if errors:
            logger.error("[SHOPIFY] Fulfillment userErrors: %s", errors)
        else:
            logger.info("[SHOPIFY] Fulfillment basarili: %s", payload.get("fulfillment", {}).get("id"))
        return {
            "success": not errors,
            "fulfillment": payload.get("fulfillment"),
            "errors": errors,
        }

    def add_order_note(self, order_id: str | int, note: str) -> Dict[str, Any]:
        """Siparise not ekler."""
        mutation = """
        mutation UpdateOrderNote($input: OrderInput!) {
          orderUpdate(input: $input) {
            order {
              id
              note
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        gid = self._build_gid("Order", order_id)
        variables = {"input": {"id": gid, "note": note}}
        result = self._post_graphql(mutation, variables)
        if not result.get("success"):
            return result

        payload = result["data"].get("orderUpdate", {})
        errors = payload.get("userErrors") or []
        return {
            "success": not errors,
            "order": payload.get("order"),
            "errors": errors,
        }

    def add_order_tags(self, order_id: str | int, tags: List[str]) -> Dict[str, Any]:
        """Siparise etiket ekler."""
        mutation = """
        mutation AddOrderTags($id: ID!, $tags: [String!]!) {
          tagsAdd(id: $id, tags: $tags) {
            node {
              ... on Order {
                id
                tags
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        gid = self._build_gid("Order", order_id)
        result = self._post_graphql(mutation, {"id": gid, "tags": tags})
        if not result.get("success"):
            return result

        payload = result["data"].get("tagsAdd", {})
        errors = payload.get("userErrors") or []
        return {
            "success": not errors,
            "node": payload.get("node"),
            "errors": errors,
        }

    # Özel sipariş statüleri (tag olarak yönetilir)
    ORDER_STATUSES = ["Beklemede", "Hazirlaniyor", "Kargoda", "Teslim Edildi"]

    def remove_order_tags(self, order_id: str | int, tags: List[str]) -> Dict[str, Any]:
        """Siparisten etiket kaldirir."""
        mutation = """
        mutation RemoveOrderTags($id: ID!, $tags: [String!]!) {
          tagsRemove(id: $id, tags: $tags) {
            node {
              ... on Order {
                id
                tags
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        gid = self._build_gid("Order", order_id)
        result = self._post_graphql(mutation, {"id": gid, "tags": tags})
        if not result.get("success"):
            return result

        payload = result["data"].get("tagsRemove", {})
        errors = payload.get("userErrors") or []
        return {
            "success": not errors,
            "node": payload.get("node"),
            "errors": errors,
        }

    def update_order_status(self, order_id: str | int, new_status: str) -> Dict[str, Any]:
        """Siparis statusunu gunceller (eski status tagini kaldirir, yenisini ekler)."""
        if new_status not in self.ORDER_STATUSES:
            return {"success": False, "error": f"Gecersiz status: {new_status}"}

        # Önce mevcut statü taglerini kaldır
        old_statuses = [s for s in self.ORDER_STATUSES if s != new_status]
        remove_result = self.remove_order_tags(order_id, old_statuses)
        if not remove_result.get("success"):
            logger.warning("[SHOPIFY] Eski status tagleri kaldirilirken hata: %s", remove_result)

        # Yeni statü tagini ekle
        tag_result = self.add_order_tags(order_id, [new_status])

        # Teslim Edildi ise siparisi Shopify'da da arsivle (close)
        if new_status == "Teslim Edildi" and tag_result.get("success"):
            close_result = self.close_order(order_id)
            if not close_result.get("success"):
                logger.warning("[SHOPIFY] Siparis arsivlenemedi: %s", close_result)

        return tag_result

    def close_order(self, order_id: str | int) -> Dict[str, Any]:
        """Siparisi Shopify'da arsivler (kapatir)."""
        mutation = """
        mutation CloseOrder($input: OrderCloseInput!) {
          orderClose(input: $input) {
            order {
              id
              closed
              closedAt
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        gid = self._build_gid("Order", order_id)
        result = self._post_graphql(mutation, {"input": {"id": gid}})
        if not result.get("success"):
            return result

        payload = result["data"].get("orderClose", {})
        errors = payload.get("userErrors") or []
        return {
            "success": not errors,
            "order": payload.get("order"),
            "errors": errors,
        }

    def mark_as_paid(self, order_id: str | int) -> Dict[str, Any]:
        """Siparisi odendi olarak isaretle."""
        mutation = """
        mutation MarkAsPaid($input: OrderMarkAsPaidInput!) {
          orderMarkAsPaid(input: $input) {
            order {
              id
              displayFinancialStatus
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        gid = self._build_gid("Order", order_id)
        result = self._post_graphql(mutation, {"input": {"id": gid}})
        if not result.get("success"):
            return result

        payload = result["data"].get("orderMarkAsPaid", {})
        errors = payload.get("userErrors") or []
        return {
            "success": not errors,
            "order": payload.get("order"),
            "errors": errors,
        }

    def get_order(self, order_id: str | int) -> Dict[str, Any]:
        query = """
        query GetOrder($id: ID!) {
          order(id: $id) {
            id
            legacyResourceId
            name
            createdAt
            cancelledAt
            cancelReason
            note
            tags
            displayFinancialStatus
            displayFulfillmentStatus
            paymentGatewayNames
            customer {
              firstName
              lastName
              email
              phone
            }
            billingAddress {
              name
              address1
              address2
              city
              province
              zip
              country
              phone
            }
            shippingAddress {
              name
              address1
              address2
              city
              province
              zip
              country
              phone
            }
            currentTotalPriceSet {
              shopMoney {
                amount
                currencyCode
              }
            }
            totalRefundedSet {
              shopMoney {
                amount
                currencyCode
              }
            }
            refunds(first: 20) {
              id
              note
              createdAt
              totalRefundedSet {
                shopMoney {
                  amount
                  currencyCode
                }
              }
              refundLineItems(first: 50) {
                edges {
                  node {
                    quantity
                    lineItem {
                      title
                      sku
                      quantity
                    }
                    subtotalSet {
                      shopMoney {
                        amount
                        currencyCode
                      }
                    }
                  }
                }
              }
            }
            lineItems(first: 50) {
              edges {
                node {
                  id
                  title
                  sku
                  quantity
                  currentQuantity
                  originalTotalSet {
                    shopMoney {
                      amount
                      currencyCode
                    }
                  }
                  variant {
                    id
                    legacyResourceId
                    sku
                    barcode
                    image {
                      url
                    }
                    inventoryItem {
                      id
                      sku
                    }
                  }
                }
              }
            }
          }
        }
        """
        gid = self._build_gid("Order", order_id)
        result = self._post_graphql(query, {"id": gid})
        if not result.get("success"):
            return result

        order = result["data"].get("order")
        if order:
            order["line_items"] = [item.get("node", {}) for item in order.get("lineItems", {}).get("edges", [])]
            order.pop("lineItems", None)

            # Her line item'a resolved panel barkodunu ekle
            from models import ShopifyMapping, Product
            for li in order["line_items"]:
                variant = li.get("variant") or {}
                v_barcode = variant.get("barcode") or ""
                v_sku = li.get("sku") or ""
                resolved = None
                # 1) variant.barcode ile Product'ta ara
                if v_barcode:
                    from barcode_alias_helper import normalize_barcode
                    p = Product.query.filter_by(barcode=normalize_barcode(v_barcode)).first()
                    if p:
                        resolved = p.barcode
                # 2) ShopifyMapping ile SKU -> panel barkod
                if not resolved and v_sku:
                    m = ShopifyMapping.query.filter_by(shopify_sku=v_sku).first()
                    if m:
                        resolved = m.barcode
                # 3) ShopifyMapping ile variant barcode -> panel barkod
                if not resolved and v_barcode:
                    m = ShopifyMapping.query.filter_by(shopify_barcode=v_barcode).first()
                    if m:
                        resolved = m.barcode
                li["resolved_barcode"] = resolved or v_barcode or ""

            # Refund detaylarini parse et
            refunds_raw = order.get("refunds") or []
            parsed_refunds = []
            for ref in refunds_raw:
                ref_items = []
                for edge in (ref.get("refundLineItems") or {}).get("edges", []):
                    node = edge.get("node", {})
                    li = node.get("lineItem") or {}
                    ref_items.append({
                        "title": li.get("title", ""),
                        "sku": li.get("sku", ""),
                        "original_quantity": li.get("quantity", 0),
                        "refunded_quantity": node.get("quantity", 0),
                        "refund_amount": float((node.get("subtotalSet") or {}).get("shopMoney", {}).get("amount", 0)),
                    })
                parsed_refunds.append({
                    "id": ref.get("id", ""),
                    "note": ref.get("note", ""),
                    "created_at": ref.get("createdAt", ""),
                    "total": float((ref.get("totalRefundedSet") or {}).get("shopMoney", {}).get("amount", 0)),
                    "items": ref_items,
                })
            order["parsed_refunds"] = parsed_refunds

        return {
            "success": bool(order),
            "order": order,
            "error": None if order else "Sipariş bulunamadı",
        }

    def cancel_order(self, order_id: str | int, reason: str = "CUSTOMER", refund: bool = False, restock: bool = False, note: Optional[str] = None) -> Dict[str, Any]:
        mutation = """
        mutation CancelOrder($orderId: ID!, $reason: OrderCancelReason!, $refund: Boolean!, $restock: Boolean!, $note: String) {
          orderCancel(orderId: $orderId, reason: $reason, refund: $refund, restock: $restock, staffNote: $note) {
            job {
              id
              done
            }
            orderCancelUserErrors {
              field
              message
            }
          }
        }
        """
        variables = {
            "orderId": self._build_gid("Order", order_id),
            "reason": reason,
            "refund": refund,
            "restock": restock,
            "note": note,
        }
        result = self._post_graphql(mutation, variables)
        if not result.get("success"):
            return result

        payload = result["data"].get("orderCancel", {})
        errors = payload.get("orderCancelUserErrors") or []
        return {
            "success": not errors,
            "job": payload.get("job"),
            "errors": errors,
        }

    def get_products(self, limit: int = 20, query_filter: Optional[str] = None) -> Dict[str, Any]:
        query = """
        query GetProducts($first: Int!, $query: String) {
          products(first: $first, query: $query, reverse: true, sortKey: UPDATED_AT) {
            edges {
              node {
                id
                legacyResourceId
                title
                handle
                status
                totalInventory
                vendor
                productType
                updatedAt
                variants(first: 20) {
                  edges {
                    node {
                      id
                      legacyResourceId
                      title
                      sku
                      inventoryQuantity
                      inventoryItem {
                        id
                        sku
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        result = self._post_graphql(query, {"first": max(1, min(limit, 100)), "query": query_filter})
        if not result.get("success"):
            return result

        edges = result["data"].get("products", {}).get("edges", [])
        products = []
        for edge in edges:
            node = edge.get("node", {})
            node["variants"] = [variant.get("node", {}) for variant in node.get("variants", {}).get("edges", [])]
            products.append(node)

        return {
            "success": True,
            "products": products,
            "count": len(products),
        }

    def get_product(self, product_id: str | int) -> Dict[str, Any]:
        query = """
        query GetProduct($id: ID!) {
          product(id: $id) {
            id
            legacyResourceId
            title
            handle
            status
            totalInventory
            vendor
            productType
            tags
            updatedAt
            variants(first: 50) {
              edges {
                node {
                  id
                  legacyResourceId
                  title
                  sku
                  barcode
                  inventoryQuantity
                  inventoryItem {
                    id
                    sku
                  }
                }
              }
            }
          }
        }
        """
        gid = self._build_gid("Product", product_id)
        result = self._post_graphql(query, {"id": gid})
        if not result.get("success"):
            return result

        product = result["data"].get("product")
        if product:
            product["variants"] = [variant.get("node", {}) for variant in product.get("variants", {}).get("edges", [])]

        return {
            "success": bool(product),
            "product": product,
            "error": None if product else "Ürün bulunamadı",
        }

    def get_locations(self, limit: int = 20) -> Dict[str, Any]:
        query = """
        query GetLocations($first: Int!) {
          locations(first: $first) {
            edges {
              node {
                id
                legacyResourceId
                name
                isActive
                fulfillsOnlineOrders
                address {
                  address1
                  city
                  country
                }
              }
            }
          }
        }
        """
        result = self._post_graphql(query, {"first": max(1, min(limit, 100))})
        if not result.get("success"):
            return result

        locations = [edge.get("node", {}) for edge in result["data"].get("locations", {}).get("edges", [])]
        return {
            "success": True,
            "locations": locations,
            "count": len(locations),
        }

    def adjust_inventory(self, inventory_item_id: str | int, location_id: str | int, delta: int, reason: str = "correction") -> Dict[str, Any]:
        mutation = """
        mutation AdjustInventory($input: InventoryAdjustQuantitiesInput!) {
          inventoryAdjustQuantities(input: $input) {
            inventoryAdjustmentGroup {
              createdAt
              reason
              changes {
                name
                delta
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        variables = {
            "input": {
                "reason": reason,
                "name": "available",
                "changes": [
                    {
                        "delta": int(delta),
                        "inventoryItemId": self._build_gid("InventoryItem", inventory_item_id),
                        "locationId": self._build_gid("Location", location_id),
                    }
                ],
            }
        }
        result = self._post_graphql(mutation, variables)
        if not result.get("success"):
            return result

        payload = result["data"].get("inventoryAdjustQuantities", {})
        errors = payload.get("userErrors") or []
        return {
            "success": not errors,
            "adjustment": payload.get("inventoryAdjustmentGroup"),
            "errors": errors,
        }


shopify_service = ShopifyService()