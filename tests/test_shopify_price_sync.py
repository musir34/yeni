"""Fiyat eşitleme: gerçek SQL sorguları, bellek içi DB ve sahte Shopify yanıtları."""
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from flask import Flask
from flask_login import LoginManager

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Product, ShopifyMapping, db
from shopify_site import shopify_routes
from shopify_site.shopify_price_compare import PriceCompareService


@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="test", SQLALCHEMY_DATABASE_URI="sqlite://", LOGIN_DISABLED=True)
    db.init_app(app)
    login = LoginManager(app)
    login.user_loader(lambda user_id: None)
    app.register_blueprint(shopify_routes.shopify_bp)
    monkeypatch.setattr(shopify_routes.ShopifyConfig, "is_configured", lambda: True)
    monkeypatch.setattr(shopify_routes, "log_user_action", lambda *args, **kwargs: None)
    with app.app_context():
        Product.__table__.create(db.engine)
        ShopifyMapping.__table__.create(db.engine)
        yield app
        db.session.remove()


def seed(barcode, model="0110", price=100, variant=None):
    variant = variant or f"gid://shopify/ProductVariant/{barcode}"
    db.session.add(Product(barcode=barcode, product_main_id=model, sale_price=price, quantity=7))
    db.session.add(ShopifyMapping(barcode=barcode, shopify_variant_id=variant, shopify_inventory_item_id="inventory-" + barcode))
    db.session.commit()
    return variant


def mock_shopify(monkeypatch, service, nodes, responses=None):
    mutations = []
    reads = []
    responses = responses or {}

    def graphql(query, variables):
        if query == service.PRICE_SYNC_QUERY:
            reads.append(variables["ids"])
            return {"nodes": [deepcopy(nodes.get(vid)) for vid in variables["ids"]]}
        assert query == service.PRICE_SYNC_MUTATION
        mutations.append(deepcopy(variables))
        override = responses.get(variables["productId"])
        if isinstance(override, Exception):
            raise override
        if override is not None:
            return {"productVariantsBulkUpdate": deepcopy(override)}
        return {"productVariantsBulkUpdate": {"productVariants": deepcopy(variables["variants"]), "userErrors": []}}

    monkeypatch.setattr(service, "_graphql", graphql)
    return mutations, reads


def node(variant, product="product-1", price="200.00"):
    return {"id": variant, "price": price, "product": {"id": product}}


def test_selected_model_updates_each_variant_to_its_own_price(app, monkeypatch):
    v1 = seed("a", price=123.45)
    v2 = seed("b", price=234.56)
    other = seed("c", model="0115", price=900)
    unmapped = Product(barcode="unmapped", product_main_id="0110", sale_price=50)
    db.session.add(unmapped)
    db.session.commit()
    service = PriceCompareService()
    calls, reads = mock_shopify(monkeypatch, service, {
        v1: node(v1), v2: node(v2, "product-2"), other: node(other),
    })
    result = service.sync_model_prices("0110")
    assert result == {"success": True, "updated": 2, "unchanged": 0, "skipped": 0, "failed": 0, "errors": []}
    assert {c["productId"] for c in calls} == {"product-1", "product-2"}
    assert {v["id"]: v["price"] for c in calls for v in c["variants"]} == {v1: "123.45", v2: "234.56"}
    assert other not in reads[0]
    assert all(set(v) == {"id", "price"} for c in calls for v in c["variants"])
    assert db.session.get(Product, "a").quantity == 7
    assert db.session.get(Product, "a").sale_price == 123.45


@pytest.mark.parametrize("price", [None, 0, -5, float("nan"), float("inf"), 0.001])
def test_invalid_trendyol_prices_never_sent(app, monkeypatch, price):
    seed("a", price=price)
    service = PriceCompareService()
    calls, reads = mock_shopify(monkeypatch, service, {})
    result = service.sync_model_prices("0110")
    assert result["skipped"] == 1
    assert calls == reads == []


def test_equal_missing_and_duplicate_barcode_mappings(app, monkeypatch):
    equal = seed("a")
    missing = seed("b")
    first = seed("c", price=321)
    second = "gid://shopify/ProductVariant/second"
    db.session.add(ShopifyMapping(barcode="c", shopify_variant_id=second, shopify_inventory_item_id="second"))
    db.session.commit()
    service = PriceCompareService()
    calls, _ = mock_shopify(monkeypatch, service, {
        equal: node(equal, price="100.00"), first: node(first), second: node(second, "product-2"),
    })
    result = service.sync_model_prices("0110")
    assert (result["updated"], result["unchanged"], result["skipped"]) == (2, 1, 1)
    assert {v["id"] for c in calls for v in c["variants"]} == {first, second}


@pytest.mark.parametrize("bad_response", [
    {"userErrors": [{"message": "Yetki eksik"}], "productVariants": []},
    {"userErrors": [], "productVariants": []},
    {"userErrors": [], "productVariants": [{"id": "gid://shopify/ProductVariant/b", "price": "999"}]},
    RuntimeError("Shopify bağlantısı kesildi"),
])
def test_partial_failure_keeps_confirmed_success_count(app, monkeypatch, bad_response):
    first = seed("a")
    second = seed("b")
    service = PriceCompareService()
    mock_shopify(monkeypatch, service, {first: node(first), second: node(second, "product-2")},
                 {"product-2": bad_response})
    result = service.sync_model_prices("0110")
    assert result["success"] is False
    assert (result["updated"], result["failed"]) == (1, 1)
    assert result["errors"]


def test_batches_stay_within_250_and_one_shopify_product(app, monkeypatch):
    nodes = {}
    for i in range(251):
        variant = seed(str(i))
        nodes[variant] = node(variant)
    service = PriceCompareService()
    calls, reads = mock_shopify(monkeypatch, service, nodes)
    assert service.sync_model_prices("0110")["updated"] == 251
    assert [len(ids) for ids in reads] == [250, 1]
    assert [len(call["variants"]) for call in calls] == [250, 1]


def test_all_models_include_groups_hidden_by_difference_filters(app, monkeypatch):
    equal = seed("a")
    different = seed("b", model="0115")
    service = PriceCompareService()
    monkeypatch.setattr(service, "fetch_variant_prices", lambda: {
        equal: {"price": 100, "title": "", "product_title": ""},
        different: {"price": 105, "title": "", "product_title": ""},
    })
    result = service.compare(only_differences=True, min_diff_percent=10)
    assert result["groups"] == []
    assert result["model_codes"] == ["0110", "0115"]


def test_missing_model_code_group_can_be_synced(app, monkeypatch):
    variants = [seed("a", model=None), seed("b", model="")]
    service = PriceCompareService()
    mock_shopify(monkeypatch, service, {v: node(v) for v in variants})
    assert service.sync_model_prices("(model kodu yok)")["updated"] == 2


def test_unknown_model_does_not_fall_back_to_all(app, monkeypatch):
    seed("a")
    service = PriceCompareService()
    calls, reads = mock_shopify(monkeypatch, service, {})
    assert service.sync_model_prices("does-not-exist")["success"] is False
    assert calls == reads == []


@pytest.mark.parametrize("payload", [{}, [], {"model_code": None}, {"model_code": ""}, {"model_code": ["0110"]}])
def test_sync_endpoint_requires_explicit_model(app, monkeypatch, payload):
    monkeypatch.setattr(shopify_routes.price_compare_service, "sync_model_prices",
                        lambda code: pytest.fail("Geçersiz seçim Shopify'a gönderilmemeli"))
    assert app.test_client().post("/shopify/api/price-compare/sync", json=payload).status_code == 400


def test_sync_endpoint_ignores_client_price_and_requires_login(app, monkeypatch):
    variant = seed("a", price=345.67)
    calls, _ = mock_shopify(monkeypatch, shopify_routes.price_compare_service, {variant: node(variant)})
    response = app.test_client().post("/shopify/api/price-compare/sync", json={"model_code": "0110", "price": 1})
    assert response.json["updated"] == 1
    assert calls[0]["variants"][0]["price"] == "345.67"
    app.config["LOGIN_DISABLED"] = False
    assert app.test_client().post("/shopify/api/price-compare/sync", json={"model_code": "0110"}).status_code == 401
    assert len(calls) == 1


def test_sync_endpoint_uses_price_page_permission():
    from sayfa_yetki import sayfa_bul
    assert sayfa_bul("shopify.price_compare_sync", "/shopify/api/price-compare/sync").kod == "shopify_fiyat"
