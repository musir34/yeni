"""
Idefix Satıcı Paneli Route'ları
"""

from flask import Blueprint, render_template, jsonify, request
from .idefix_service import idefix_service
from logger_config import app_logger

idefix_bp = Blueprint('idefix', __name__, 
                       url_prefix='/idefix',
                       template_folder='../templates/idefix')


@idefix_bp.route('/')
def index():
    """Idefix ana sayfa"""
    return render_template('idefix/index.html', 
                          seller_name=idefix_service.seller_name,
                          seller_id=idefix_service.seller_id)


@idefix_bp.route('/siparisler')
def siparisler():
    """Idefix siparişler sayfası"""
    return render_template('idefix/siparisler.html',
                          seller_name=idefix_service.seller_name)


@idefix_bp.route('/urunler')
def urunler():
    """Idefix ürünler sayfası"""
    return render_template('idefix/urunler.html',
                          seller_name=idefix_service.seller_name,
                          seller_id=idefix_service.seller_id)


@idefix_bp.route('/api/orders')
def api_orders():
    """Siparişleri JSON olarak döndürür"""
    orders = idefix_service.get_orders()
    return jsonify(orders or {"orders": [], "message": "Henüz sipariş yok"})


@idefix_bp.route('/api/products')
def api_products():
    """Ürünleri JSON olarak döndürür - eşleşme bilgisiyle birlikte"""
    from models import Product
    
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 50, type=int)  # Default 50
    barcode = request.args.get('barcode', None)
    all_products = request.args.get('all', 'false').lower() == 'true'
    
    # Tüm ürünleri getir
    if all_products:
        result = idefix_service.get_all_products()
        if result.get("success"):
            # Her ürün için eşleşme bilgisini ekle
            products_with_match = []
            for product in result.get("products", []):
                bc = product.get("barcode", "").strip()
                if bc:
                    db_product = Product.query.filter_by(barcode=bc).first()
                    product["is_matched"] = db_product is not None
                    if db_product:
                        product["our_title"] = db_product.title
                        product["our_stock"] = db_product.quantity
                else:
                    product["is_matched"] = False
                products_with_match.append(product)
            result["products"] = products_with_match
        return jsonify(result)
    
    # Limit kontrolü
    if limit > 100:
        limit = 100
    
    result = idefix_service.get_products(page=page, limit=limit, barcode=barcode)
    return jsonify(result)


@idefix_bp.route('/api/products/search')
def api_search_products():
    """Barkod ile ürün arar"""
    barcode = request.args.get('barcode', '')
    app_logger.info(f"[IDEFIX] API: Ürün arama - barcode: {barcode}")
    
    if not barcode:
        return jsonify({"success": False, "error": "Barkod gerekli", "products": []})
    
    result = idefix_service.get_product_by_barcode(barcode)
    app_logger.info(f"[IDEFIX] API: Arama yanıtı - success: {result.get('success')}")
    return jsonify(result)


@idefix_bp.route('/api/stock', methods=['POST'])
def api_update_stock():
    """Tek ürün stok güncelleme endpoint'i"""
    data = request.json or {}
    barcode = data.get('barcode')
    quantity = data.get('quantity')
    
    app_logger.info(f"[IDEFIX] API: Stok güncelleme - barcode: {barcode}, quantity: {quantity}")
    
    if not barcode or quantity is None:
        return jsonify({"error": "barcode ve quantity gerekli"}), 400
    
    result = idefix_service.update_stock(barcode, int(quantity))
    return jsonify(result)


@idefix_bp.route('/api/push-all-stocks', methods=['POST'])
def api_push_all_stocks():
    """
    Tüm Idefix ürünlerinin stoklarını güncelle
    Trendyol mantığıyla: CentralStock - Reserved = Available
    """
    import json
    from models import db, Product, CentralStock, OrderCreated
    
    app_logger.info("[IDEFIX] ========== TOPLU STOK GÖNDERİMİ BAŞLADI ==========")
    
    try:
        def _parse(raw):
            try:
                if not raw: return []
                d = json.loads(raw) if isinstance(raw, str) else raw
                return d if isinstance(d, list) else [d]
            except:
                return []

        def _i(x, d=0):
            try:
                return int(str(x).strip())
            except:
                return d
        
        # 1. Idefix ürünlerini bul
        idefix_products = Product.query.filter(
            Product.platforms.ilike('%idefix%')
        ).all()
        app_logger.info(f"[IDEFIX] {len(idefix_products)} Idefix ürünü bulundu")
        
        if not idefix_products:
            return jsonify({"success": False, "error": "Idefix'te satılan ürün bulunamadı"})
        
        # 2. CentralStock
        central_stocks = {cs.barcode: cs.qty for cs in CentralStock.query.all()}
        
        # 3. Created rezerv
        reserved = {}
        created_orders = OrderCreated.query.with_entities(OrderCreated.details).all()
        for (details_str,) in created_orders:
            for it in _parse(details_str):
                bc = (it.get("barcode") or "").strip()
                q  = _i(it.get("quantity"), 0)
                if bc and q > 0:
                    reserved[bc] = reserved.get(bc, 0) + q
        
        # 4. Stok hesapla
        items = []
        for product in idefix_products:
            bc = product.barcode
            if not bc:
                continue
            central_qty = central_stocks.get(bc, 0)
            reserved_qty = reserved.get(bc, 0)
            available = max(0, central_qty - reserved_qty)
            items.append({
                "barcode": bc,
                "inventoryQuantity": available
            })
        
        app_logger.info(f"[IDEFIX] {len(items)} ürün hazırlandı")
        
        # 5. Batch gönder
        BATCH_SIZE = 100
        total = len(items)
        parts = (total + BATCH_SIZE - 1) // BATCH_SIZE
        
        success_count = 0
        error_count = 0
        batch_results = []
        
        for i in range(0, total, BATCH_SIZE):
            batch_num = i // BATCH_SIZE + 1
            batch = items[i:i+BATCH_SIZE]
            
            result = idefix_service.update_stocks(batch)
            
            if result.get("success"):
                success_count += 1
                batch_results.append({"batch": batch_num, "status": "success"})
            else:
                error_count += 1
                batch_results.append({"batch": batch_num, "status": "error", "error": result.get("error")})
        
        app_logger.info(f"[IDEFIX] Gönderim tamamlandı - Başarılı: {success_count}/{parts}")
        app_logger.info("[IDEFIX] ========== TOPLU STOK GÖNDERİMİ TAMAMLANDI ==========")
        
        return jsonify({
            "success": True,
            "total_products": len(items),
            "batches_sent": parts,
            "success_count": success_count,
            "error_count": error_count,
            "batch_results": batch_results
        })
        
    except Exception as e:
        app_logger.error(f"[IDEFIX] Toplu stok gönderimi hatası: {str(e)}")
        import traceback
        app_logger.error(f"[IDEFIX] Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


@idefix_bp.route('/api/sync-prices', methods=['POST'])
def api_sync_prices():
    """
    Trendyol'daki fiyatları Idefix'e senkronize et
    Eşleşen ürünlerin sale_price ve list_price değerlerini Idefix'e gönder
    """
    import json
    from models import Product
    
    app_logger.info("[IDEFIX] ========== FİYAT SENKRONİZASYONU BAŞLADI ==========")
    
    try:
        # Idefix ürünlerini bul (platforms'da idefix olan ve fiyatı olan)
        idefix_products = Product.query.filter(
            Product.platforms.ilike('%idefix%'),
            Product.sale_price.isnot(None),
            Product.sale_price > 0
        ).all()
        
        app_logger.info(f"[IDEFIX] {len(idefix_products)} fiyatlı Idefix ürünü bulundu")
        
        if not idefix_products:
            return jsonify({
                "success": True,
                "message": "Fiyat güncellenecek ürün bulunamadı",
                "count": 0
            })
        
        # Fiyat listesi hazırla
        items = []
        for product in idefix_products:
            bc = product.barcode
            if not bc:
                continue
            
            sale_price = float(product.sale_price or 0)
            list_price = float(product.list_price or sale_price)
            
            if sale_price > 0:
                items.append({
                    "barcode": bc,
                    "salePrice": sale_price,
                    "listPrice": list_price if list_price >= sale_price else sale_price
                })
        
        app_logger.info(f"[IDEFIX] {len(items)} ürün fiyatı hazırlandı")
        
        # Örnek fiyatları logla
        if items[:3]:
            for it in items[:3]:
                app_logger.info(f"[IDEFIX] Örnek: {it['barcode']} - {it['salePrice']} TL")
        
        # Idefix'e gönder
        result = idefix_service.update_prices(items)
        
        app_logger.info(f"[IDEFIX] Fiyat senkronizasyonu tamamlandı - Başarılı: {result.get('total_success', 0)}")
        app_logger.info("[IDEFIX] ========== FİYAT SENKRONİZASYONU TAMAMLANDI ==========")
        
        return jsonify({
            "success": result.get("success", False),
            "total_products": len(items),
            "total_success": result.get("total_success", 0),
            "total_error": result.get("total_error", 0),
            "message": f"{len(items)} ürün fiyatı senkronize edildi"
        })
        
    except Exception as e:
        app_logger.error(f"[IDEFIX] Fiyat senkronizasyonu hatası: {str(e)}")
        import traceback
        app_logger.error(f"[IDEFIX] Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


# ===================== ÜRÜN EŞLEŞTİRME =====================

@idefix_bp.route('/eslestirme')
def eslestirme():
    """Idefix ürün eşleştirme sayfası"""
    app_logger.info("[IDEFIX] Eşleştirme sayfası açıldı")
    return render_template('idefix/eslestirme.html',
                          seller_name=idefix_service.seller_name,
                          seller_id=idefix_service.seller_id)


@idefix_bp.route('/api/sync-products', methods=['POST'])
def api_sync_products():
    """
    Idefix ürünlerini çek ve mevcut ürünlerle eşleştir
    Barkod eşleşen ürünlere 'idefix' platformu ekle
    """
    import json
    from datetime import datetime
    from models import db, Product
    
    app_logger.info("[IDEFIX] ========== ÜRÜN SENKRONİZASYONU BAŞLADI ==========")
    
    try:
        # Tüm Idefix ürünlerini çek
        app_logger.info("[IDEFIX] Idefix API'den ürünler çekiliyor...")
        result = idefix_service.get_all_products()
        
        if not result.get("success"):
            app_logger.error(f"[IDEFIX] API hatası: {result.get('error')}")
            return jsonify({
                "success": False,
                "error": result.get("error", "Ürünler çekilemedi")
            })
        
        idefix_products = result.get("products", [])
        app_logger.info(f"[IDEFIX] ✓ {len(idefix_products)} Idefix ürünü çekildi")
        
        # Veritabanındaki toplam ürün sayısı
        db_product_count = Product.query.count()
        app_logger.info(f"[IDEFIX] Veritabanındaki toplam ürün: {db_product_count}")
        
        # Eşleştirme sonuçları
        matched = []
        unmatched = []
        updated = 0
        processed = 0
        
        app_logger.info("[IDEFIX] Eşleştirme işlemi başlıyor...")
        
        for idefix_product in idefix_products:
            processed += 1
            barcode = idefix_product.get("barcode", "").strip()
            
            if not barcode:
                app_logger.debug(f"[IDEFIX] Boş barkod atlandı (index: {processed})")
                continue
            
            # Her 100 üründe bir progress log
            if processed % 100 == 0:
                app_logger.info(f"[IDEFIX] İşlenen: {processed}/{len(idefix_products)} - Eşleşen: {len(matched)} - Eşleşmeyen: {len(unmatched)}")
            
            # Veritabanında barkod ara
            product = Product.query.filter_by(barcode=barcode).first()
            
            if product:
                # Eşleşme bulundu
                try:
                    # Mevcut platformları al
                    current_platforms = []
                    if product.platforms:
                        try:
                            current_platforms = json.loads(product.platforms)
                        except:
                            current_platforms = ["trendyol"]
                    
                    # idefix yoksa ekle
                    if "idefix" not in current_platforms:
                        current_platforms.append("idefix")
                        product.platforms = json.dumps(current_platforms)
                        updated += 1
                        app_logger.debug(f"[IDEFIX] Platform eklendi: {barcode} -> {current_platforms}")
                    
                    # Idefix bilgilerini güncelle
                    product.idefix_product_id = str(idefix_product.get("reference", ""))
                    product.idefix_status = idefix_product.get("status", "")
                    product.idefix_last_sync = datetime.utcnow()
                    
                    matched.append({
                        "barcode": barcode,
                        "title": idefix_product.get("title", ""),
                        "idefix_status": idefix_product.get("status", ""),
                        "our_title": product.title,
                        "platforms": current_platforms
                    })
                    
                except Exception as e:
                    app_logger.error(f"[IDEFIX] Ürün güncelleme hatası ({barcode}): {e}")
            else:
                # Eşleşme bulunamadı
                unmatched.append({
                    "barcode": barcode,
                    "title": idefix_product.get("title", ""),
                    "vendorStockCode": idefix_product.get("vendorStockCode", ""),
                    "idefix_status": idefix_product.get("status", ""),
                    "price": idefix_product.get("price", 0),
                    "inventoryQuantity": idefix_product.get("inventoryQuantity", 0)
                })
        
        # Değişiklikleri kaydet
        app_logger.info("[IDEFIX] Veritabanına kaydediliyor...")
        db.session.commit()
        
        app_logger.info("[IDEFIX] ========== SENKRONİZASYON TAMAMLANDI ==========")
        app_logger.info(f"[IDEFIX] 📊 SONUÇLAR:")
        app_logger.info(f"[IDEFIX]    - Toplam Idefix Ürün: {len(idefix_products)}")
        app_logger.info(f"[IDEFIX]    - Eşleşen: {len(matched)}")
        app_logger.info(f"[IDEFIX]    - Eşleşmeyen: {len(unmatched)}")
        app_logger.info(f"[IDEFIX]    - Platform Güncellenen: {updated}")
        
        return jsonify({
            "success": True,
            "total_idefix": len(idefix_products),
            "matched_count": len(matched),
            "unmatched_count": len(unmatched),
            "updated_count": updated,
            "matched": matched,
            "unmatched": unmatched
        })
        
    except Exception as e:
        db.session.rollback()
        app_logger.error(f"[IDEFIX] ❌ SENKRONİZASYON HATASI: {str(e)}")
        import traceback
        app_logger.error(f"[IDEFIX] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@idefix_bp.route('/api/match-product', methods=['POST'])
def api_match_product():
    """
    Manuel ürün eşleştirme
    Idefix barkodunu mevcut bir ürün barkoduna eşleştirir (alias olarak)
    """
    import json
    from datetime import datetime
    from models import db, Product, BarcodeAlias
    
    data = request.json or {}
    idefix_barcode = data.get("idefix_barcode", "").strip()
    our_barcode = data.get("our_barcode", "").strip()
    
    app_logger.info(f"[IDEFIX] Manuel eşleştirme - Idefix: {idefix_barcode} -> Bizim: {our_barcode}")
    
    if not idefix_barcode or not our_barcode:
        return jsonify({"success": False, "error": "Her iki barkod da gerekli"}), 400
    
    try:
        # Bizim ürünümüzü bul
        product = Product.query.filter_by(barcode=our_barcode).first()
        
        if not product:
            return jsonify({"success": False, "error": f"Ürün bulunamadı: {our_barcode}"}), 404
        
        # Barkod alias ekle (farklı barkodlar için)
        if idefix_barcode != our_barcode:
            existing_alias = BarcodeAlias.query.filter_by(alias_barcode=idefix_barcode).first()
            
            if not existing_alias:
                alias = BarcodeAlias(
                    alias_barcode=idefix_barcode,
                    main_barcode=our_barcode,
                    note=f"Idefix eşleştirme"
                )
                db.session.add(alias)
                app_logger.info(f"[IDEFIX] Barkod alias eklendi: {idefix_barcode} -> {our_barcode}")
        
        # Platformları güncelle
        current_platforms = []
        if product.platforms:
            try:
                current_platforms = json.loads(product.platforms)
            except:
                current_platforms = ["trendyol"]
        
        if "idefix" not in current_platforms:
            current_platforms.append("idefix")
            product.platforms = json.dumps(current_platforms)
        
        product.idefix_last_sync = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Ürün eşleştirildi: {idefix_barcode} -> {our_barcode}",
            "platforms": current_platforms
        })
        
    except Exception as e:
        db.session.rollback()
        app_logger.error(f"[IDEFIX] Manuel eşleştirme hatası: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@idefix_bp.route('/api/platforms/<barcode>')
def api_get_platforms(barcode):
    """Bir ürünün platformlarını getirir"""
    import json
    from models import Product
    
    product = Product.query.filter_by(barcode=barcode).first()
    
    if not product:
        return jsonify({"success": False, "error": "Ürün bulunamadı"}), 404
    
    platforms = []
    if product.platforms:
        try:
            platforms = json.loads(product.platforms)
        except:
            platforms = ["trendyol"]
    
    return jsonify({
        "success": True,
        "barcode": barcode,
        "platforms": platforms,
        "idefix_status": product.idefix_status,
        "idefix_last_sync": product.idefix_last_sync.isoformat() if product.idefix_last_sync else None
    })


@idefix_bp.route('/api/our-products')
def api_our_products():
    """Bizim ürünlerimizi arama için listeler"""
    from models import Product
    
    search = request.args.get('search', '').strip()
    limit = request.args.get('limit', 20, type=int)
    
    if len(search) < 2:
        return jsonify({"success": True, "products": []})
    
    # Barkod veya ürün adına göre ara
    products = Product.query.filter(
        db.or_(
            Product.barcode.ilike(f"%{search}%"),
            Product.title.ilike(f"%{search}%"),
            Product.product_main_id.ilike(f"%{search}%")
        )
    ).limit(limit).all()
    
    result = []
    for p in products:
        result.append({
            "barcode": p.barcode,
            "title": p.title,
            "product_main_id": p.product_main_id,
            "color": p.color,
            "size": p.size
        })
    
    return jsonify({"success": True, "products": result})
