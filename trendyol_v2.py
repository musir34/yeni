# -*- coding: utf-8 -*-
"""
Trendyol Ürün V2 API yardımcıları
==================================
Trendyol, ürün servislerini 15 Eylül 2026'da V2'ye taşıyor (V1 kapanacak).
V2'de GET ürün listesi (/products/approved) v1'in düz (barkod başına tek kayıt)
yapısı yerine içerik(content) + variants iç içe yapısı döndürüyor.

Bu modül, v2 yanıtını mevcut kodun beklediği v1 düz sözlük biçimine çevirir;
böylece ayrıştırma/DB kodları değişmeden çalışmaya devam eder.

V2 sayfalama notu: size en fazla 100, page*size en fazla 10.000 olabilir.
10.000+ içerik için nextPageToken gerekir (bu satıcıda içerik sayısı çok altında).
"""

PRODUCTS_APPROVED_URL = "https://apigw.trendyol.com/integration/product/sellers/{seller_id}/products/approved"

# V2 sayfa boyutu üst sınırı (v1'de 200/1000 kullanılabiliyordu)
V2_MAX_PAGE_SIZE = 100


def _attr_value(attributes, name):
    """Attribute listesinden isme göre değer çeker (yoksa None)."""
    for attr in attributes or []:
        if attr.get('attributeName') == name:
            return attr.get('attributeValue')
    return None


def flatten_v2_content(content):
    """
    V2 /products/approved yanıtındaki tek bir content öğesini,
    v1'in düz ürün sözdizimine (varyant başına bir sözlük) çevirir.

    v2'de bulunmayan v1 alanları (gtin, hasActiveCampaign, currencyType vb.)
    None döner; mevcut .get(...) tabanlı ayrıştırıcılar bunu tolere eder.
    """
    flat_products = []
    brand = content.get('brand') or {}
    category = content.get('category') or {}
    content_attributes = content.get('attributes') or []

    for variant in content.get('variants') or []:
        variant_attributes = variant.get('attributes') or []
        # Renk content'te, Beden varyantta gelir; ikisini birleştirip
        # v1'deki gibi tek attributes listesi olarak sunuyoruz.
        merged_attributes = content_attributes + variant_attributes
        price = variant.get('price') or {}
        stock = variant.get('stock') or {}

        flat_products.append({
            'barcode': variant.get('barcode', ''),
            'title': content.get('title', ''),
            'productMainId': content.get('productMainId', ''),
            'description': content.get('description', ''),
            'brand': brand.get('name', ''),
            'brandId': brand.get('id'),
            'categoryName': category.get('name', ''),
            'pimCategoryId': category.get('id'),
            'images': content.get('images', []),
            'attributes': merged_attributes,
            'quantity': stock.get('quantity', 0) or 0,
            'listPrice': price.get('listPrice', 0),
            'salePrice': price.get('salePrice', 0),
            'vatRate': variant.get('vatRate', 0),
            'stockCode': variant.get('stockCode', ''),
            'archived': variant.get('archived', False),
            'locked': variant.get('locked', False),
            'onSale': variant.get('onSale', False),
            'blacklisted': variant.get('blacklisted', False),
            # /products/approved yalnızca onaylı içerik döndürür
            'approved': True,
            'rejected': False,
            'productUrl': variant.get('productUrl', ''),
            'supplierId': variant.get('supplierId'),
            'id': variant.get('variantId'),
            'productContentId': content.get('contentId'),
            'gender': _attr_value(content_attributes, 'Cinsiyet'),
            'lastUpdateDate': variant.get('sellerModifiedDate') or content.get('lastModifiedDate'),
            'createDateTime': variant.get('sellerCreatedDate') or content.get('creationDate'),
        })

    return flat_products


def flatten_v2_page(page_data):
    """V2 yanıtındaki content listesini düz ürün listesine çevirir."""
    flat_products = []
    for content in page_data.get('content') or []:
        flat_products.extend(flatten_v2_content(content))
    return flat_products
