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

        logger.info(f"API yanıtı: Status Code={status}, Response Text={text}")

        if status == 200:
            logger.info(f"Paket {shipment_package_id} Trendyol'da 'Picking' statüsüne güncellendi.")
            return True
        else:
            logger.error(f"Beklenmeyen durum kodu veya hata: {status}, Yanıt: {text}")
            return False

    except Exception as e:
        logger.error(f"Trendyol API üzerinden paket statüsü güncellenirken hata: {e}")
        traceback.print_exc()
        return False

@update_service_bp.route('/confirm_packing', methods=['POST'])
async def confirm_packing():
    logger.info("======= confirm_packing fonksiyonu başlatıldı =======")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request form: {request.form}")

    try:
        # 1) Sipariş no
        order_number = request.form.get('order_number')
        if not order_number:
            flash('Sipariş numarası bulunamadı.', 'danger')
            return redirect(url_for('siparis_hazirla.index'))


        # 2) Okutulan barkodlar
        barkodlar = []
        for key in list(request.form.keys()):
            if key.startswith('barkod_right_') or key.startswith('barkod_left_'):
                for v in request.form.getlist(key):
                    v = (v or '').strip()
                    if v:
                        barkodlar.append(v)

        # 3) Sipariş kaydı
        order_created = OrderCreated.query.filter_by(order_number=order_number).first()
        if not order_created:
            flash('Created tablosunda bu sipariş yok.', 'danger')
            return redirect(url_for('siparis_hazirla.index'))


        # 4) Detaylar
        try:
            details = json.loads(order_created.details or '[]')
        except json.JSONDecodeError:
            details = []

        # 5) Beklenen barkodlar (adet*2 — sağ/sol)
        expected_barcodes = []
        for d in details:
            bc = d.get('barcode')
            if not bc:
                continue
            quantity = int(d.get('quantity', 1))
            expected_barcodes.extend([bc] * (quantity * 2))

        # 6) Basit doğrulama
        if any(bc not in expected_barcodes for bc in barkodlar):
            flash('Geçersiz barkod girişi, lütfen tekrar deneyin!', 'danger')
            return redirect(url_for('siparis_hazirla.index'))

        if len(barkodlar) < len(set(expected_barcodes)):
            flash('Bazı barkodlar eksik olabilir, işlem devam ediyor.', 'warning')

        # 7) RAF + CENTRAL düş (Klasik commit/rollback)
        try:
            uyarilar = []

            for d in details:
                bc = d.get("barcode")
                adet = int(d.get("quantity") or 0)
                if not bc or adet <= 0:
                    continue

                chosen_raf = request.form.get(f"pick_{bc}")
                kalan = adet

                # 7a) Seçilen raftan düş
                if chosen_raf:
                    rec = (RafUrun.query
                           .filter_by(raf_kodu=chosen_raf, urun_barkodu=bc)
                           .with_for_update()
                           .first())
                    if rec:
                        use = min(rec.adet or 0, kalan)
                        rec.adet = (rec.adet or 0) - use
                        kalan -= use

                # 7b) Kalan varsa diğer raflardan (çok stoklu önce) tamamla
                if kalan > 0:
                    digerler = (RafUrun.query
                                .filter(RafUrun.urun_barkodu == bc,
                                        RafUrun.adet > 0)
                                .order_by(RafUrun.adet.desc())
                                .with_for_update()
                                .all())
                    for r in digerler:
                        if chosen_raf and r.raf_kodu == chosen_raf:
                            continue
                        if kalan == 0:
                            break
                        use = min(r.adet or 0, kalan)
                        r.adet = (r.adet or 0) - use
                        kalan -= use

                # 7c) CentralStock düş (tam adet)
                cs = CentralStock.query.get(bc)
                if not cs:
                    cs = CentralStock(barcode=bc, qty=0)
                    db.session.add(cs)
                cs.qty = max(0, (cs.qty or 0) - adet)

                if kalan > 0:
                    uyarilar.append(f"{bc} için {kalan} adet eksik (raf yetersiz)")

            db.session.commit()

            if uyarilar:
                flash(" / ".join(uyarilar), "warning")
            logger.info("Raf ve merkezi stok düşümü tamamlandı.")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Stok düşümünde hata: {e}", exc_info=True)
            flash("Stok düşümünde hata oluştu.", 'danger')
            return redirect(url_for('siparis_hazirla.index'))


        # 8) Trendyol: Picking’e geçir
        try:
            shipment_package_ids = set()
            for d in details:
                sp = d.get('shipmentPackageId') or order_created.shipment_package_id or order_created.package_number
                if sp:
                    shipment_package_ids.add(sp)
            if not shipment_package_ids:
                flash("shipmentPackageId yok; API güncellenemiyor.", 'danger')
                return redirect(url_for('siparis_hazirla.index'))


            lines = []
            for d in details:
                lid = d.get('line_id') or d.get('line_ids_api')
                if not lid:
                    flash("'line_id' yok; Trendyol update mümkün değil.", 'danger')
                    return redirect(url_for('siparis_hazirla.index'))

                q = int(d.get('quantity', 1))
                lines.append({"lineId": int(lid), "quantity": q})

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

            trendyol_success = True
            for sp_id, ln in lines_by_sp.items():
                ok = await update_order_status_to_picking(SUPPLIER_ID, sp_id, ln)
                if ok:
                    flash(f"Paket {sp_id} Trendyol'da 'Picking' oldu.", 'success')
                else:
                    trendyol_success = False
                    flash(f"Trendyol güncellemesi hatası. Paket: {sp_id}", 'danger')
            if not trendyol_success:
                logger.warning("Trendyol çağrılarında hata(lar) var; işleme devam edildi.")
        except Exception as e:
            logger.error(f"Trendyol çağrısı istisnası: {e}", exc_info=True)
            flash(f"Trendyol API çağrısında istisna: {e}", 'danger')

        # 9) OrderCreated -> OrderPicking taşı
        try:
            data = order_created.__dict__.copy()
            data.pop('_sa_instance_state', None)
            picking_cols = {c.name for c in OrderPicking.__table__.columns}
            data = {k: v for k, v in data.items() if k in picking_cols}

            new_rec = OrderPicking(**data)
            new_rec.picking_start_time = datetime.utcnow()

            db.session.add(new_rec)
            db.session.delete(order_created)
            db.session.commit()
            logger.info(f"Taşıma tamam: Created ➜ Picking ({order_number})")
        except Exception as db_error:
            db.session.rollback()
            logger.error(f"Taşıma hatası: {db_error}", exc_info=True)
            flash(f"Veritabanı taşıma hatası: {db_error}", 'danger')
            return redirect(url_for('siparis_hazirla.index'))


        # 10) Sonraki sipariş info
        try:
            nxt = OrderCreated.query.order_by(OrderCreated.order_date).first()
            if nxt:
                flash(f'Bir sonraki Created: {nxt.order_number}', 'info')
            else:
                flash('Yeni Created sipariş yok.', 'info')
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Hata: {e}", exc_info=True)
        flash('Bir hata oluştu.', 'danger')

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