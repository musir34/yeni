from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime
import traceback
import json
import base64
import aiohttp
import asyncio
from logger_config import api_logger as logger

# Yeni tablolar (Created, Picking vs.) ve DB objesi
from models import db, OrderCreated, OrderPicking, Product
# Trendyol API kimlikleri ve BASE_URL
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL

update_service_bp = Blueprint('update_service', __name__)

##############################################
# Trendyol API üzerinden statü güncelleme
##############################################
async def update_order_status_to_picking(supplier_id, shipment_package_id, lines):
    """
    Trendyol API'ye PUT isteği atarak belirtilen package_id'yi 'Picking' statüsüne çevirir.
    lines: [{ "lineId": <int>, "quantity": <int> }, ...]
    """
    try:
        url = f"{BASE_URL}suppliers/{supplier_id}/shipment-packages/{shipment_package_id}"

        credentials = f"{API_KEY}:{API_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/json"
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
            async with session.put(url, headers=headers, data=json.dumps(payload), timeout=30) as response:
                status = response.status
                text = await response.text()

        logger.info(f"API yanıtı: Status Code={status}, Response Text={text}")

        if status == 200:
            # Yanıt boş olabilir, yine de başarılı sayarız
            logger.info(f"Paket {shipment_package_id} Trendyol'da 'Picking' statüsüne güncellendi.")
            return True
        else:
            logger.error(f"Beklenmeyen durum kodu veya hata: {status}, Yanıt: {text}")
            return False

    except Exception as e:
        logger.error(f"Trendyol API üzerinden paket statüsü güncellenirken hata: {e}")
        traceback.print_exc()
        return False


##############################################
# confirm_packing: Barkodlar onayı, tablo taşıma
##############################################
@update_service_bp.route('/confirm_packing', methods=['POST'])
async def confirm_packing():
    """
    Formdan gelen order_number ve barkodları karşılaştırır.
    Eğer doğruysa, Trendyol API'de statüyü 'Picking' yapar,
    veritabanında OrderCreated -> OrderPicking taşıması yapar.
    """
    try:
        # 1) Form verilerini alalım
        order_number = request.form.get('order_number')
        if not order_number:
            flash('Sipariş numarası bulunamadı.', 'danger')
            return redirect(url_for('home.home'))

        logger.debug(f"Received order_number: {order_number}")

        # Gönderilen barkodları topla
        barkodlar = []
        for key in request.form:
            if key.startswith('barkod_right_') or key.startswith('barkod_left_'):
                barkod_value = request.form[key].strip()
                barkodlar.append(barkod_value)

        logger.debug(f"Received barcodes: {barkodlar}")

        # 2) OrderCreated tablosundan siparişi bul
        order_created = OrderCreated.query.filter_by(order_number=order_number).first()
        if not order_created:
            flash('Created tablosunda bu sipariş bulunamadı.', 'danger')
            logger.warning("Order not found in OrderCreated.")
            return redirect(url_for('home.home'))

        # 3) Sipariş detaylarını parse et
        details_json = order_created.details or '[]'
        try:
            details = json.loads(details_json)
            logger.debug(f"Parsed details: {details}")
        except json.JSONDecodeError:
            details = []
            logger.error(f"order.details JSON parse edilemedi: {order_created.details}")

        # 4) Beklenen barkodları hesapla (miktar*2 = sol/sağ barkod)
        expected_barcodes = []
        for detail in details:
            barcode = detail.get('barcode')
            if not barcode:
                continue

            quantity = int(detail.get('quantity', 1))
            # Her adet ürün için 2 barkod: sol + sağ
            count = quantity * 2  
            expected_barcodes.extend([barcode] * count)

        logger.debug(f"Expected barcodes: {expected_barcodes}")

        # 5) Karşılaştırma
        if sorted(barkodlar) != sorted(expected_barcodes):
            flash('Barkodlar uyuşmuyor, lütfen tekrar deneyin!', 'danger')
            logger.warning("Barcodes do not match.")
            return redirect(url_for('home.home'))

        logger.debug("Barcodes match. Devam ediliyor...")

        # 6) Trendyol API'ye status=Picking çağrısı (shipmentPackageId'ye göre)
        # ShipmentPackageId'leri JSON detaydan veya tablo alanından alalım
        shipment_package_ids = set()

        # 6a) details içinde her satırda 'shipmentPackageId' varsa toplayın
        for detail in details:
            sp_id = detail.get('shipmentPackageId') or order_created.shipment_package_id or order_created.package_number
            if sp_id:
                shipment_package_ids.add(sp_id)

        # eğer hiç yoksa, sipariş tablosundaki (order_created.shipment_package_id) ya da (package_number) kullanılabilir
        if not shipment_package_ids:
            sp_id_fallback = order_created.shipment_package_id or order_created.package_number
            if sp_id_fallback:
                shipment_package_ids.add(sp_id_fallback)

        if not shipment_package_ids:
            flash("shipmentPackageId bulunamadı. API güncellemesi yapılamıyor.", 'danger')
            logger.error("shipmentPackageId is missing. Cannot update Trendyol API.")
            return redirect(url_for('home.home'))

        # 6b) lines (Trendyol formatında) hazırlama
        lines = []
        for detail in details:
            line_id = detail.get('line_id')
            if not line_id:
                # Trendyol update için lineId gerekli
                flash("'line_id' değeri yok, Trendyol update mümkün değil.", 'danger')
                return redirect(url_for('home.home'))

            q = int(detail.get('quantity', 1))
            line = {
                "lineId": int(line_id),
                "quantity": q
            }
            lines.append(line)

        # 6c) lines'ı shipmentPackageId'ye göre gruplandırıp Trendyol'a yolla
        from collections import defaultdict
        lines_by_sp = defaultdict(list)

        for detail_line in lines:
            # Detay JSON'daki 'shipmentPackageId' bulalım
            # veya fallback olarak order_created'dan
            sp_id_detail = None
            # Aradığımız detail objeyi bulmak için line_id eşleşmesi yapabiliriz
            # ama bu kod basit olsun diye 'detail_line["lineId"]''a göre bulabilir
            # ya da her satırda sp_id var mi? Yukarıda toplanmış olabilir.

            # Tek tek details'e bakıp line_id eşleşen satırın shipmentPackageId'sini alalım
            for d in details:
                if str(d.get('line_id')) == str(detail_line["lineId"]):
                    sp_id_detail = d.get('shipmentPackageId')

            # fallback
            if not sp_id_detail:
                sp_id_detail = order_created.shipment_package_id or order_created.package_number

            lines_by_sp[sp_id_detail].append(detail_line)

        # Trendyol güncellemesi
        supplier_id = SUPPLIER_ID
        for sp_id, lines_for_sp in lines_by_sp.items():
            logger.info(f"Calling Trendyol for sp_id={sp_id}, lines={lines_for_sp}")
            result = await update_order_status_to_picking(supplier_id, sp_id, lines_for_sp)
            if result:
                flash(f"Paket {sp_id} Trendyol'da 'Picking' olarak güncellendi.", 'success')
            else:
                flash(f"Trendyol API güncellemesi sırasında hata. Paket ID: {sp_id}", 'danger')

        # 7) Veritabanı tarafında OrderCreated -> OrderPicking taşı
        # (order_created kaydını al, OrderPicking'e ekle, OrderCreated'tan sil)
        data = order_created.__dict__.copy()
        data.pop('_sa_instance_state', None)

        # Kolonları, OrderPicking tablosunda var olanlarla filtreleyelim
        picking_cols = {c.name for c in OrderPicking.__table__.columns}
        data = {k: v for k, v in data.items() if k in picking_cols}

        # Yeni picking kaydı oluştur
        new_picking_record = OrderPicking(**data)
        # picking tablosunda ek kolonlar varsa set edebilirsiniz:
        new_picking_record.picking_start_time = datetime.utcnow()

        db.session.add(new_picking_record)
        db.session.delete(order_created)
        db.session.commit()
        logger.info(f"Taşıma tamam: OrderCreated -> OrderPicking. Order num: {order_number}")

        # 8) Bir sonraki created siparişi bul
        next_created = OrderCreated.query.order_by(OrderCreated.order_date).first()
        if next_created:
            flash(f'Bir sonraki Created sipariş: {next_created.order_number}.', 'info')
        else:
            flash('Yeni Created sipariş bulunamadı.', 'info')

    except Exception as e:
        logger.error(f"Hata: {e}")
        traceback.print_exc()
        flash('Bir hata oluştu.', 'danger')

    return redirect(url_for('home.home'))


##############################################
# Örnek diğer fonksiyonlar
##############################################

async def fetch_orders_from_api():
    """
    Trendyol API'den siparişleri asenkron olarak çeker.
    """
    auth_str = f"{API_KEY}:{API_SECRET}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')

    url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/orders"
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
    url = f"{BASE_URL}suppliers/{supplier_id}/shipment-packages/{package_id}"
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
