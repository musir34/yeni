from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime
import traceback
import json
import base64
import aiohttp
import asyncio
from logger_config import api_logger as logger
from sqlalchemy import asc
from collections import Counter, defaultdict

# Yeni tablolar (Created, Picking vs.) ve DB objesi
from models import db, OrderCreated, OrderPicking, Product, RafUrun, CentralStock
# Trendyol API kimlikleri ve BASE_URL
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID

update_service_bp = Blueprint('update_service', __name__)

BASE_URL = "https://apigw.trendyol.com/integration/order/sellers/"


# ==== yardımcı: barcode normalize ====
def _norm_bc(x: str) -> str:
    if not x:
        return ""
    return x.strip().replace(" ", "")

# ==== ayar: sağ/sol okutma modu ====
SCAN_MODE = "pair"  # "single" ya da "pair"
REQ_PER_UNIT = 2 if SCAN_MODE == "pair" else 1


##############################################
# Trendyol API üzerinden statü güncelleme
##############################################
async def update_order_status_to_picking(supplier_id, shipment_package_id, lines):
    """
    Trendyol API'ye PUT isteği atarak belirtilen package_id'yi 'Picking' statüsüne çevirir.
    lines: [{ "lineId": <int>, "quantity": <int> }, ...]
    """
    try:
        url = f"{BASE_URL}{supplier_id}/shipment-packages/{shipment_package_id}"

        credentials = f"{API_KEY}:{API_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/json",
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        payload = {
            "lines": lines,
            "params": {},
            "status": "Picking"
        }
        logger.debug(f"PUT {url}")
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Payload: {json.dumps(payload, ensure_ascii=False)}")

        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=headers, json=payload) as response:

                status = response.status
                text = await response.text()

        # Yanıtı detaylı logla
        if text:
            logger.info(f"API yanıtı: Status={status}, Response={text}")
            # Trendyol bazen hata mesajını body'de döndürebilir
            try:
                response_json = json.loads(text)
                if "error" in response_json or "message" in response_json:
                    logger.error(f"✗ Trendyol API Hata Mesajı: {response_json}")
                    return False
            except:
                pass  # JSON değilse devam et
        else:
            logger.info(f"API yanıtı: Status={status}, Response=<boş>")

        # Başarılı durum kodları: 200, 201, 204
        if status in [200, 201, 204]:
            logger.info(f"✓ Paket {shipment_package_id} Trendyol'da 'Picking' statüsüne güncellendi.")
            return True
        else:
            logger.error(f"✗ Trendyol API Hatası: Status={status}, Paket={shipment_package_id}, Yanıt={text}")
            return False

    except Exception as e:
        logger.error(f"Trendyol API üzerinden paket statüsü güncellenirken hata: {e}")
        traceback.print_exc()
        return False

@update_service_bp.route('/confirm_packing', methods=['POST'])
async def confirm_packing():
    logger.info("======= [confirm_packing] START =======")
    logger.info(f"[REQ] method={request.method} form_keys={list(request.form.keys())}")

    try:
        # 1) Sipariş no
        order_number = request.form.get('order_number')
        if not order_number:
            logger.warning("[CHK] order_number yok")
            flash('Sipariş numarası bulunamadı.', 'danger')
            return redirect(url_for('siparis_hazirla.index'))
        logger.info(f"[ORDER] num={order_number}")

        # 2) Okutulan barkodlar (normalize)
        barkodlar = []
        for key in request.form.keys():
            if key.startswith('barkod_right_') or key.startswith('barkod_left_'):
                vals = [ _norm_bc(v) for v in request.form.getlist(key) if v and _norm_bc(v) ]
                if vals:
                    logger.debug(f"[SCAN] {key} -> {vals}")
                    barkodlar.extend(vals)
        logger.info(f"[SCAN] toplam_okutma={len(barkodlar)}")

        # 3) Sipariş kaydı - OrderCreated veya WooOrder tablosundan bul
        from archive import find_order_across_tables
        from woocommerce_site.models import WooOrder
        
        order_created, table_cls = find_order_across_tables(order_number)
        
        if not order_created:
            logger.error("[DB] Sipariş hiçbir tabloda bulunamadı")
            flash('Sipariş bulunamadı.', 'danger')
            return redirect(url_for('siparis_hazirla.index'))
        
        is_woo_order = table_cls == WooOrder
        logger.info(f"[ORDER] Bulundu: {order_number}, Tablo: {table_cls.__name__ if hasattr(table_cls, '__name__') else 'WooOrder'}")

        # 4) Detaylar
        try:
            if is_woo_order:
                # 🔥 WooCommerce siparişi - line_items'dan details oluştur
                # Barkod doğrulaması için woo_product_id kullanılır (barkod = woo_product_id)
                details = []
                for item in order_created.line_items or []:
                    product_id = item.get('product_id')
                    variation_id = item.get('variation_id')
                    woo_id = variation_id if variation_id else product_id
                    
                    # 🔥 WooCommerce'de barkod = woo_product_id
                    # Görüntüde barkod gösterilir ama arka planda woo_id ile eşleşir
                    barcode = str(woo_id)
                    
                    details.append({
                        'barcode': barcode,  # woo_product_id
                        'quantity': item.get('quantity', 1),
                        'woo_product_id': product_id,
                        'woo_variation_id': variation_id,
                        'product_name': item.get('name', '')
                    })
                logger.info(f"[DETAILS][WOO] {len(details)} ürün, line_items'dan oluşturuldu (woo_id bazlı)")
            else:
                # Trendyol siparişi - standart details parse
                details = json.loads(order_created.details or '[]')
                logger.info(f"[DETAILS][TY] satir={len(details)}")
        except json.JSONDecodeError:
            logger.exception("[DETAILS] JSON hatalı, boş dizi kullanılacak")
            details = []

        # 5) Barkod doğrulama (başarısızsa stok düşmeyeceğiz)
        from collections import Counter
        from models import Product
        
        eksikler = []
        toplam_gerekli_okutma = 0

        if is_woo_order:
            # 🔥 WooCommerce siparişi için özel doğrulama
            # Taranan barkodlar -> woo_product_id'ye çevrilir ve siparişle karşılaştırılır
            
            # Taranan barkodların woo_product_id'lerini bul
            scanned_woo_ids = []
            for bc in barkodlar:
                product = Product.query.filter_by(barcode=bc).first()
                if product and product.woo_product_id:
                    scanned_woo_ids.append(str(product.woo_product_id))
                    logger.debug(f"[VERIFY][WOO] Barkod {bc} -> woo_id={product.woo_product_id}")
                else:
                    # Barkod Product tablosunda yok veya woo_product_id yok
                    # Belki doğrudan woo_id tarandı?
                    scanned_woo_ids.append(bc)
                    logger.debug(f"[VERIFY][WOO] Barkod {bc} eşleştirilmedi, olduğu gibi kullanılıyor")
            
            scan_cnt = Counter(scanned_woo_ids)
            
            for d in details:
                woo_id = str(d.get('barcode'))  # WooCommerce'de barcode = woo_id
                q = int(d.get('quantity') or 0)
                if not woo_id or q <= 0:
                    continue
                gerekli = q * REQ_PER_UNIT
                varolan = scan_cnt.get(woo_id, 0)
                toplam_gerekli_okutma += gerekli
                logger.debug(f"[VERIFY][WOO] woo_id={woo_id} q={q} gerekli={gerekli} varolan={varolan}")
                if varolan < gerekli:
                    # Kullanıcıya göstermek için Product tablosundan barkod al
                    product = Product.query.filter_by(woo_product_id=int(woo_id)).first()
                    display_name = product.barcode if product else woo_id
                    eksikler.append(f"{display_name}: {varolan}/{gerekli}")
        else:
            # Trendyol siparişi - standart doğrulama
            scan_cnt = Counter(barkodlar)
            
            for d in details:
                bc = _norm_bc(d.get('barcode'))
                q = int(d.get('quantity') or 0)
                if not bc or q <= 0:
                    logger.debug(f"[DETAILS] atla bc={bc} q={q}")
                    continue
                gerekli = q * REQ_PER_UNIT
                varolan = scan_cnt.get(bc, 0)
                toplam_gerekli_okutma += gerekli
                logger.debug(f"[VERIFY] bc={bc} q={q} gerekli_okutma={gerekli} varolan={varolan}")
                if varolan < gerekli:
                    eksikler.append(f"{bc}: {varolan}/{gerekli}")

        logger.info(f"[VERIFY] REQ_PER_UNIT={REQ_PER_UNIT} toplam_gerekli_okutma={toplam_gerekli_okutma} okutulan={len(barkodlar)}")

        if eksikler:
            msg = "Eksik okutma -> " + " | ".join(eksikler)
            logger.warning(f"[VERIFY][FAIL] {msg}")
            flash(f"Barkod doğrulama başarısız. {msg}", "danger")
            return redirect(url_for('siparis_hazirla.index'))

        logger.info("[VERIFY][OK] Barkod doğrulama geçti. Stok düşümüne geçiliyor.")

        # 6) RAF + CENTRAL düş (sadece quantity kadar)
        try:
            uyarilar = []
            toplam_dusen = 0
            toplam_beklenen = 0  # Düşmesi gereken toplam adet

            for d in details:
                # 🔥 WooCommerce için woo_id'den gerçek barkod al
                if is_woo_order:
                    woo_id = d.get("barcode")  # WooCommerce'de barcode = woo_id
                    product = Product.query.filter_by(woo_product_id=int(woo_id)).first()
                    if product:
                        bc = product.barcode  # Gerçek barkod
                        logger.info(f"[STOCK][WOO] woo_id={woo_id} -> barcode={bc}")
                    else:
                        logger.warning(f"[STOCK][WOO] woo_id={woo_id} için Product bulunamadı, stok düşülmüyor")
                        continue
                else:
                    bc = _norm_bc(d.get("barcode"))
                
                adet = int(d.get("quantity") or 0)
                if not bc or adet <= 0:
                    logger.debug(f"[STOCK] atla bc={bc} adet={adet}")
                    continue
                
                toplam_beklenen += adet  # Beklenen toplamı artır
                chosen_raf = request.form.get(f"pick_{d.get('barcode')}")  # Form'dan gelen key (woo_id veya barkod)
                kalan = adet
                logger.info(f"[STOCK] basla bc={bc} adet={adet} chosen_raf={chosen_raf}")

                # 6a) Seçilen raftan düş
                if chosen_raf:
                    rec = (RafUrun.query
                           .filter_by(raf_kodu=chosen_raf, urun_barkodu=bc)
                           .with_for_update()
                           .first())
                    if rec:
                        use = min(rec.adet or 0, kalan)
                        eski = rec.adet or 0
                        rec.adet = max(0, eski - use)
                        kalan -= use
                        toplam_dusen += use
                        logger.debug(f"[STOCK][RAF1] {chosen_raf}/{bc} {eski}->{rec.adet} (use={use})")
                    else:
                        logger.debug(f"[STOCK][RAF1] kayıt yok: {chosen_raf}/{bc}")

                # 6b) Diğer raflardan (çok stoklu)
                if kalan > 0:
                    digerler = (RafUrun.query
                                .filter(RafUrun.urun_barkodu == bc, RafUrun.adet > 0)
                                .order_by(RafUrun.adet.desc())
                                .with_for_update()
                                .all())
                    for r in digerler:
                        if chosen_raf and r.raf_kodu == chosen_raf:
                            continue
                        if kalan == 0:
                            break
                        eski = r.adet or 0
                        use = min(eski, kalan)
                        r.adet = max(0, eski - use)
                        kalan -= use
                        toplam_dusen += use
                        logger.debug(f"[STOCK][RAF2] {r.raf_kodu}/{bc} {eski}->{r.adet} (use={use})")

                # 6c) CentralStock: quantity kadar düş
                cs = CentralStock.query.get(bc)
                if not cs:
                    cs = CentralStock(barcode=bc, qty=0)
                    db.session.add(cs)
                    logger.debug(f"[CENTRAL] yeni kayıt olustu bc={bc}")

                eski_cs = cs.qty or 0
                cs.qty = max(0, eski_cs - adet)
                logger.debug(f"[CENTRAL] bc={bc} {eski_cs}->{cs.qty} (dusen={adet})")

                if kalan > 0:
                    warn = f"{bc} için {kalan} adet eksik (raf yetersiz)"
                    uyarilar.append(warn)
                    logger.warning(f"[STOCK][WARN] {warn}")

            db.session.commit()
            logger.info(f"[STOCK][OK] commit; toplam_dusen={toplam_dusen}/{toplam_beklenen}")
            
            # ⚠️ Kritik: Stok yetersizse Trendyol'a güncelleme GÖNDERME
            if toplam_beklenen > 0 and toplam_dusen == 0:
                logger.error(f"[STOCK][CRITICAL] Hiç stok düşmedi! Trendyol'a güncelleme gönderilmiyor.")
                flash("❌ Stok yetersiz! Hiçbir ürün raflardan çekilemedi. Sipariş Picking'e geçirilemedi.", 'danger')
                return redirect(url_for('siparis_hazirla.index'))
            elif toplam_dusen < toplam_beklenen:
                logger.warning(f"[STOCK][PARTIAL] Kısmi stok düşümü: {toplam_dusen}/{toplam_beklenen}")
                flash(f"⚠️ Kısmi hazırlandı: {toplam_dusen}/{toplam_beklenen} adet. Devam ediliyor...", 'warning')
            
            if uyarilar:
                flash(" / ".join(uyarilar), "warning")
        except Exception as e:
            db.session.rollback()
            logger.exception("[STOCK][ERR] rollback")
            flash("Stok düşümünde hata oluştu.", 'danger')
            return redirect(url_for('siparis_hazirla.index'))

        # 7) Trendyol: Picking’e geçir (aynı, ama log zengin)
        try:
            shipment_package_ids = set()
            for d in details:
                sp = d.get('shipmentPackageId') or order_created.shipment_package_id or order_created.package_number
                if sp:
                    shipment_package_ids.add(sp)
            logger.info(f"[TYL] paket_sayisi={len(shipment_package_ids)} ids={list(shipment_package_ids)}")

            if not shipment_package_ids:
                logger.error("[TYL] shipmentPackageId yok; API atlanıyor")
                flash("shipmentPackageId yok; API güncellenemiyor.", 'danger')
                return redirect(url_for('siparis_hazirla.index'))

            lines = []
            for d in details:
                lid = d.get('line_id') or d.get('line_ids_api')
                if not lid:
                    logger.error("[TYL] line_id yok; iptal")
                    flash("'line_id' yok; Trendyol update mümkün değil.", 'danger')
                    return redirect(url_for('siparis_hazirla.index'))
                q = int(d.get('quantity', 1))
                lines.append({"lineId": int(lid), "quantity": q})

            # paket -> lines eşleme
            lines_by_sp = defaultdict(list)
            for ln in lines:
                sp_for_line = None
                for d in details:
                    lid = d.get('line_id') or d.get('line_ids_api')
                    if str(lid) == str(ln["lineId"]):
                        sp_for_line = d.get('shipmentPackageId')
                        break
                if not sp_for_line:
                    sp_for_line = order_created.shipment_package_id or order_created.package_number
                lines_by_sp[sp_for_line].append(ln)

            logger.debug(f"[TYL] lines_by_sp: { {k: len(v) for k,v in lines_by_sp.items()} }")

            trendyol_success = True
            trendyol_failed_packages = []
            for sp_id, ln in lines_by_sp.items():
                logger.info(f"[TYL][PUT] sp_id={sp_id} lines={ln}")
                ok = await update_order_status_to_picking(SUPPLIER_ID, sp_id, ln)
                if ok:
                    flash(f"✓ Paket {sp_id} Trendyol'da 'Picking' oldu.", 'success')
                    logger.info(f"[TYL][OK] sp_id={sp_id}")
                else:
                    trendyol_success = False
                    trendyol_failed_packages.append(sp_id)
                    flash(f"✗ Trendyol güncellemesi hatası. Paket: {sp_id}", 'danger')
                    logger.error(f"[TYL][FAIL] sp_id={sp_id}")
            
            if not trendyol_success:
                logger.error(f"[TYL][CRITICAL] Bazı paketler güncellenemedi: {trendyol_failed_packages}")
                flash(f"⚠️ Trendyol güncellemesi BAŞARISIZ! Paketler: {', '.join(map(str, trendyol_failed_packages))}", 'danger')
                # Trendyol güncellemesi başarısızsa, stok düşümünü geri al ve çık
                try:
                    db.session.rollback()
                    logger.warning("[TYL][ROLLBACK] Stok düşümü geri alındı")
                except:
                    pass
                return redirect(url_for('siparis_hazirla.index'))
        except Exception as e:
            logger.exception("[TYL][EXC]")
            flash(f"Trendyol API çağrısında istisna: {e}", 'danger')

        # 7.5) WooCommerce: on-hold → processing (Hazırlanıyor) statüsüne geçir
        try:
            # WooCommerce siparişi mi kontrol et
            is_woocommerce = (
                hasattr(order_created, 'source') and order_created.source == 'WOOCOMMERCE'
            ) or (
                order_created.order_number and '-' not in str(order_created.order_number)
            ) or is_woo_order
            
            if is_woocommerce:
                logger.info(f"[WOO] WooCommerce siparişi tespit edildi: {order_number}")
                
                # WooCommerce API'ye durum güncellemesi gönder
                from woocommerce_site.woo_service import WooCommerceService
                from woocommerce_site.models import WooOrder
                
                try:
                    woo_service = WooCommerceService()
                    
                    # WooOrder tablosundan sipariş ID'sini al
                    woo_order_db = WooOrder.query.filter_by(order_number=str(order_number)).first()
                    
                    if woo_order_db:
                        woo_order_id = woo_order_db.order_id
                        
                        # Statüyü 'processing' (Hazırlanıyor) yap
                        updated = woo_service.update_order_status(woo_order_id, 'processing')
                        
                        if updated:
                            logger.info(f"[WOO][OK] Sipariş {order_number} WooCommerce'te 'processing' statüsüne geçti")
                            flash(f"WooCommerce siparişi 'Hazırlanıyor' statüsüne geçirildi", 'success')
                            
                            # woo_orders tablosundaki kaydı da güncelle
                            woo_order_db.status = 'processing'
                            db.session.commit()
                        else:
                            logger.error(f"[WOO][FAIL] Sipariş {order_number} güncellenemedi")
                            flash("WooCommerce güncellenemedi, ancak işlem devam ediyor", 'warning')
                    else:
                        logger.warning(f"[WOO] Sipariş {order_number} woo_orders tablosunda bulunamadı")
                        flash("WooCommerce siparişi veritabanında bulunamadı", 'warning')
                        
                except Exception as woo_inner:
                    logger.exception(f"[WOO][INNER] WooCommerce işleme hatası")
                    flash("WooCommerce güncellenemedi, işlem devam ediyor", 'warning')
                    
        except Exception as woo_error:
            logger.exception(f"[WOO][EXC] WooCommerce güncelleme hatası")
            # Hata olsa da devam et, sipariş işleme devam etsin

        # 8) OrderCreated -> OrderPicking taşı (veya woo_orders tablosunu güncelle)
        try:
            # 🔥 Eğer sipariş woo_orders tablosundan geldiyse
            if is_woo_order:
                logger.info(f"[WOO_TABLE] Sipariş woo_orders tablosundan geldi, durum 'processing' yapıldı")
                
                # 🔥 Statüyü kesinlikle güncelle (ard arda düşmeyi önlemek için)
                # API güncelleme başarısız olsa bile veritabanında processing yap
                try:
                    woo_order_check = WooOrder.query.filter_by(order_number=str(order_number)).first()
                    if woo_order_check and woo_order_check.status != 'processing':
                        woo_order_check.status = 'processing'
                        db.session.commit()
                        logger.info(f"[WOO_TABLE] Statü 'processing' olarak güncellendi: {order_number}")
                except Exception as status_err:
                    logger.error(f"[WOO_TABLE] Statü güncelleme hatası: {status_err}")
                    db.session.rollback()
                
                # WooCommerce siparişleri OrderPicking tablosuna taşınmaz
                logger.info(f"[WOO_TABLE][OK] WooCommerce siparişi hazırlandı, woo_orders tablosunda kalıyor (status='processing')")
            else:
                # Normal akış: OrderCreated -> OrderPicking
                data = order_created.__dict__.copy()
                data.pop('_sa_instance_state', None)
                picking_cols = {c.name for c in OrderPicking.__table__.columns}
                data = {k: v for k, v in data.items() if k in picking_cols}

                new_rec = OrderPicking(**data)
                new_rec.picking_start_time = datetime.utcnow()

                db.session.add(new_rec)
                db.session.delete(order_created)
                db.session.commit()
                logger.info(f"[MOVE] Created ➜ Picking OK (order={order_number})")
        except Exception as db_error:
            db.session.rollback()
            logger.exception("[MOVE][ERR] rollback")
            flash(f"Veritabanı taşıma hatası: {db_error}", 'danger')
            return redirect(url_for('siparis_hazirla.index'))

        # 9) Sonraki sipariş info
        try:
            nxt = OrderCreated.query.order_by(OrderCreated.order_date).first()
            if nxt:
                flash(f'Bir sonraki Created: {nxt.order_number}', 'info')
                logger.info(f"[NEXT] {nxt.order_number}")
            else:
                flash('Yeni Created sipariş yok.', 'info')
                logger.info("[NEXT] yok")
        except Exception:
            logger.exception("[NEXT] hata (önemsiz)")

    except Exception as e:
        logger.exception("[GLOBAL][ERR]")
        flash('Bir hata oluştu.', 'danger')

    logger.info("======= [confirm_packing] END =======")
    return redirect(url_for('siparis_hazirla.index'))




##############################################
# Örnek diğer fonksiyonlar
##############################################

async def fetch_orders_from_api():
    """
    Trendyol API'den siparişleri asenkron olarak çeker.
    """
    auth_str = f"{API_KEY}:{API_SECRET}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')

    url = f"{BASE_URL}{SUPPLIER_ID}/orders"
    headers = {
        "Authorization": f"Basic {b64_auth_str}",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            logger.error(f"API'den siparişler çekilirken hata: {response.status} - {await response.text()}")
            return []

async def update_package_to_picking(supplier_id, package_id, line_id, quantity):
    """
    Tek bir lineId ve quantity için (daha eski örnek). Yukarıda 'update_order_status_to_picking' ile benzer işler yapıyor.
    Bu fonksiyon belki artık kullanılmayabilir, ama isterseniz koruyun.
    """
    url = f"{BASE_URL}{supplier_id}/shipment-packages/{package_id}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {base64.b64encode(f'{API_KEY}:{API_SECRET}'.encode()).decode()}"
    }

    payload = {
        "lines": [{
            "lineId": line_id,
            "quantity": quantity
        }],
        "params": {},
        "status": "Picking"
    }

    logger.debug(f"Sending API request to URL: {url}")
    logger.debug(f"Headers: {headers}")
    logger.debug(f"Payload: {payload}")

    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=headers, json=payload) as response:
            if response.status == 200:
                logger.info(f"Paket başarıyla Picking statüsüne güncellendi. Yanıt: {await response.json()}")
            else:
                logger.error(f"Paket güncellenemedi! Hata kodu: {response.status}, Yanıt: {await response.text()}")