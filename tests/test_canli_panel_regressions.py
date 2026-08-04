from datetime import datetime
from pathlib import Path

from canli_panel import (
    IST,
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
