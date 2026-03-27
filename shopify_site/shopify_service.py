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
    ) -> Dict[str, Any]:
        query = """
        query GetOrders($first: Int!, $query: String, $after: String) {
          orders(first: $first, query: $query, after: $after, reverse: true, sortKey: PROCESSED_AT) {
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
                  city
                  province
                  country
                }
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
        fulfillment_line_items = []
        for fo_edge in fo_edges:
            fo_node = fo_edge.get("node", {})
            if fo_node.get("status") in ("OPEN", "IN_PROGRESS"):
                for li_edge in fo_node.get("lineItems", {}).get("edges", []):
                    li_node = li_edge.get("node", {})
                    if li_node.get("remainingQuantity", 0) > 0:
                        fulfillment_line_items.append({
                            "fulfillmentOrderId": fo_node["id"],
                            "fulfillmentOrderLineItems": [{
                                "id": li_node["id"],
                                "quantity": li_node["remainingQuantity"],
                            }],
                        })

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

        result = self._post_graphql(mutation, variables)
        if not result.get("success"):
            return result

        payload = result["data"].get("fulfillmentCreateV2", {})
        errors = payload.get("userErrors") or []
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
            displayFinancialStatus
            displayFulfillmentStatus
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