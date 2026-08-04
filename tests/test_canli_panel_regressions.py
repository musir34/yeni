from datetime import datetime
from pathlib import Path

import canli_panel as panel
from canli_panel import (
    IST,
    _aggregate_shopify_sales,
    _model_matches,
    _normalize_source_filter,
    _order_net_amount,
    _return_adjusted_amount,
    _utc_naive_bounds,
)


def test_source_filter_is_case_insensitive_and_shopify_stays_shopify():
    assert _normalize_source_filter("Shopify") == "shopify"
    assert _normalize_source_filter("TRENDYOL") == "trendyol"
    assert _normalize_source_filter("invalid") == "all"


def test_model_filter_supports_partial_case_insensitive_match():
    assert _model_matches("099-001", "099")
    assert _model_matches("ABC-10", "abc")
    assert not _model_matches("100-001", "099")


def test_istanbul_range_is_converted_to_naive_utc_for_database_queries():
    start = datetime(2026, 8, 5, 0, 0, tzinfo=IST)
    end = datetime(2026, 8, 6, 0, 0, tzinfo=IST)
    start_utc, end_utc = _utc_naive_bounds(start, end)

    assert start_utc == datetime(2026, 8, 4, 21, 0)
    assert end_utc == datetime(2026, 8, 5, 21, 0)
    assert start_utc.tzinfo is None
    assert end_utc.tzinfo is None


def test_stored_net_amount_does_not_subtract_discount_twice():
    assert _order_net_amount(100, 20) == 100


def test_return_adjusts_quantity_and_revenue_with_the_same_ratio():
    assert _return_adjusted_amount(10, 2, 1_000) == 800
    assert _return_adjusted_amount(1, 2, 100) == 0
    assert _return_adjusted_amount(0, 1, 100) == 0


def test_procurement_modal_does_not_copy_current_inputs_into_last_card():
    template = (Path(__file__).parents[1] / "templates" / "canli_panel.html").read_text()

    assert "_tedarikStep = _tedarikKartlar.length - 1" not in template
    assert "_submitTedarik(false)" in template
    assert "function _resetModalControls()" in template


def test_refresh_restarts_sse_with_current_filters():
    template = (Path(__file__).parents[1] / "templates" / "canli_panel.html").read_text()
    refresh_handler = template.split("btnYenile.onclick", 1)[1].split("liveToggle.onchange", 1)[0]

    assert "startSSE(m)" in refresh_handler
    assert "yukle(m)" in refresh_handler


def test_supplier_api_requires_login(client):
    response = client.get("/api/tedarikcilar")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_cancelled_orders_are_removed_from_range_order_numbers(monkeypatch):
    class FakeQuery:
        def filter(self, *_args):
            return self

        def all(self):
            return [("SATIS-1",), ("IPTAL-1",)]

    monkeypatch.setattr(panel.db.session, "query", lambda *_args: FakeQuery())
    monkeypatch.setattr(panel, "_apply_source_filter", lambda query, *_args: query)
    monkeypatch.setattr(
        panel,
        "_cancelled_order_numbers_between",
        lambda *_args, **_kwargs: {"IPTAL-1"},
    )

    start = datetime(2026, 7, 7, tzinfo=IST)
    end = datetime(2026, 8, 6, tzinfo=IST)

    assert panel._order_numbers_created_between(start, end, "trendyol") == {"SATIS-1"}


def test_shopify_api_orders_are_aggregated_without_refunded_or_unpaid_orders():
    def line(barcode, quantity=1, current_quantity=1, total="500"):
        return {
            "quantity": quantity,
            "currentQuantity": current_quantity,
            "resolved_barcode": barcode,
            "originalTotalSet": {"shopMoney": {"amount": total}},
        }

    orders = [
        {
            "legacyResourceId": "1",
            "displayFinancialStatus": "PAID",
            "currentTotalPriceSet": {"shopMoney": {"amount": "150"}},
            "line_items": [line("BC-1", quantity=2, current_quantity=1, total="300")],
        },
        {
            "legacyResourceId": "2",
            "displayFinancialStatus": "PENDING",
            "paymentGatewayNames": ["Cash on Delivery"],
            "currentTotalPriceSet": {"shopMoney": {"amount": "500"}},
            "line_items": [line("BC-2")],
        },
        {
            "legacyResourceId": "3",
            "displayFinancialStatus": "PENDING",
            "paymentGatewayNames": ["Bank Transfer"],
            "currentTotalPriceSet": {"shopMoney": {"amount": "500"}},
            "line_items": [line("BC-3")],
        },
        {
            "legacyResourceId": "4",
            "displayFinancialStatus": "REFUNDED",
            "currentTotalPriceSet": {"shopMoney": {"amount": "0"}},
            "line_items": [line("BC-4", current_quantity=0)],
        },
        {
            "legacyResourceId": "5",
            "displayFinancialStatus": "PAID",
            "currentTotalPriceSet": {"shopMoney": {"amount": "500"}},
            "line_items": [line("BC-5")],
        },
    ]

    quantities, amounts, order_ids = _aggregate_shopify_sales(
        orders,
        excluded_order_ids={"SH-5"},
    )

    assert quantities == {"BC-1": 1, "BC-2": 1}
    assert amounts == {"BC-1": 150.0, "BC-2": 500.0}
    assert order_ids == {"SH-1", "SH-2"}
