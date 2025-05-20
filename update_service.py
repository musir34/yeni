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
            async with session.put(url, headers=headers, data=json.dumps(payload)) as response:
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
    logger.info("======= confirm_packing fonksiyonu başlatıldı =======")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request form: {request.form}")
    
    try:
        # 1) Form verilerini alalım
        order_number = request.form.get('order_number')
        if not order_number:
            logger.error("Sipariş numarası form verisinde bulunamadı!")
            flash('Sipariş numarası bulunamadı.', 'danger')
            return redirect(url_for('home.home'))

        logger.info(f"İşlenecek sipariş numarası: {order_number}")

        # Gönderilen barkodları topla
        barkodlar = []
        for key in request.form:
            if key.startswith('barkod_right_') or key.startswith('barkod_left_'):
                barkod_value = request.form[key].strip()
                barkodlar.append(barkod_value)
                logger.debug(f"Barkod eklendi: {key}={barkod_value}")

        logger.info(f"Toplam {len(barkodlar)} barkod alındı: {barkodlar}")

        # 2) OrderCreated tablosundan siparişi bul
        logger.info(f"OrderCreated tablosunda sipariş aranıyor: {order_number}")
        order_created = OrderCreated.query.filter_by(order_number=order_number).first()
        if not order_created:
            logger.error(f"Sipariş bulunamadı: {order_number}")
            flash('Created tablosunda bu sipariş bulunamadı.', 'danger')
            return redirect(url_for('home.home'))
        
        logger.info(f"Sipariş bulundu: {order_created}")
        logger.info(f"Sipariş detayları: id={order_created.id}, order_number={order_created.order_number}, status={getattr(order_created, 'status', 'status alanı yok')}")

        # 3) Sipariş detaylarını parse et
        details_json = order_created.details or '[]'
        logger.info(f"Sipariş detay JSON: {details_json}")
        try:
            details = json.loads(details_json)
            logger.info(f"Parse edilen detaylar: {json.dumps(details, ensure_ascii=False)}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse hatası: {e}")
            details = []
            logger.error(f"order.details JSON parse edilemedi: {order_created.details}")

        # 4) Beklenen barkodları hesapla (miktar*2 = sol/sağ barkod)
        expected_barcodes = []
        logger.info("Beklenen barkodlar hesaplanıyor...")
        for detail in details:
            barcode = detail.get('barcode')
            if not barcode:
                logger.warning(f"Bir detay satırında barkod bulunamadı: {detail}")
                continue

            quantity = int(detail.get('quantity', 1))
            logger.info(f"Ürün: barcode={barcode}, miktar={quantity}")
            # Her adet ürün için 2 barkod: sol + sağ
            count = quantity * 2  
            expected_barcodes.extend([barcode] * count)
            logger.debug(f"Bu ürün için {count} barkod eklendi")

        logger.info(f"Beklenen barkodlar: {expected_barcodes}")

        # 5) Karşılaştırma
        logger.info("Barkodlar karşılaştırılıyor...")
        logger.info(f"Gelen barkodlar (sıralı): {sorted(barkodlar)}")
        logger.info(f"Beklenen barkodlar (sıralı): {sorted(expected_barcodes)}")
        
        if sorted(barkodlar) != sorted(expected_barcodes):
            logger.error("Barkodlar uyuşmuyor!")
            if len(barkodlar) != len(expected_barcodes):
                logger.error(f"Barkod sayıları farklı: Gelen={len(barkodlar)}, Beklenen={len(expected_barcodes)}")
            
            # Hangi barkodların eksik/fazla olduğunu bul
            in_expected_not_in_received = set(expected_barcodes) - set(barkodlar)
            in_received_not_in_expected = set(barkodlar) - set(expected_barcodes)
            
            if in_expected_not_in_received:
                logger.error(f"Beklenen ama alınmayan barkodlar: {in_expected_not_in_received}")
            if in_received_not_in_expected:
                logger.error(f"Alınan ama beklenmeyen barkodlar: {in_received_not_in_expected}")
                
            flash('Barkodlar uyuşmuyor, lütfen tekrar deneyin!', 'danger')
            return redirect(url_for('home.home'))

        logger.info("✅ Barkodlar eşleşti. İşlem devam ediyor...")

        # 6) Trendyol API'ye status=Picking çağrısı (shipmentPackageId'ye göre)
        logger.info("Trendyol API için hazırlık başlatılıyor...")
        # ShipmentPackageId'leri JSON detaydan veya tablo alanından alalım
        shipment_package_ids = set()

        # 6a) details içinde her satırda 'shipmentPackageId' varsa toplayın
        logger.info("ShipmentPackageId'ler toplanıyor...")
        for detail in details:
            sp_id = detail.get('shipmentPackageId') or order_created.shipment_package_id or order_created.package_number
            if sp_id:
                shipment_package_ids.add(sp_id)
                logger.debug(f"ShipmentPackageId eklendi: {sp_id} (detaylardan)")

        # eğer hiç yoksa, sipariş tablosundaki (order_created.shipment_package_id) ya da (package_number) kullanılabilir
        if not shipment_package_ids:
            logger.warning("Detaylardan hiç shipmentPackageId bulunamadı, order_created'dan alınacak")
            sp_id_fallback = order_created.shipment_package_id or order_created.package_number
            if sp_id_fallback:
                shipment_package_ids.add(sp_id_fallback)
                logger.info(f"Fallback ShipmentPackageId eklendi: {sp_id_fallback}")

        if not shipment_package_ids:
            logger.error("Hiçbir şekilde shipmentPackageId bulunamadı!")
            flash("shipmentPackageId bulunamadı. API güncellemesi yapılamıyor.", 'danger')
            return redirect(url_for('home.home'))

        logger.info(f"Toplanan shipmentPackageId'ler: {shipment_package_ids}")

        # 6b) lines (Trendyol formatında) hazırlama
        logger.info("Trendyol için 'lines' hazırlanıyor...")
        lines = []
        for detail in details:
            # Önce line_id'ye bak, yoksa line_ids_api alanını kontrol et
            line_id = detail.get('line_id')
            if not line_id:
                line_id = detail.get('line_ids_api')
                logger.info(f"line_id bulunamadı, line_ids_api kullanılıyor: {line_id}")
                
            if not line_id:
                logger.error(f"Bir detay satırında line_id veya line_ids_api bulunamadı: {detail}")
                flash("'line_id' değeri yok, Trendyol update mümkün değil.", 'danger')
                return redirect(url_for('home.home'))

            q = int(detail.get('quantity', 1))
            line = {
                "lineId": int(line_id),
                "quantity": q
            }
            lines.append(line)
            logger.debug(f"Line eklendi: lineId={line_id}, quantity={q}")

        logger.info(f"Toplam {len(lines)} satır oluşturuldu: {lines}")

        # 6c) lines'ı shipmentPackageId'ye göre gruplandırıp Trendyol'a yolla
        from collections import defaultdict
        lines_by_sp = defaultdict(list)
        logger.info("Satırlar shipmentPackageId'ye göre gruplandırılıyor...")

        for detail_line in lines:
            # Detay JSON'daki 'shipmentPackageId' bulalım
            # veya fallback olarak order_created'dan
            sp_id_detail = None
            
            # Tek tek details'e bakıp line_id eşleşen satırın shipmentPackageId'sini alalım
            for d in details:
                if str(d.get('line_id')) == str(detail_line["lineId"]):
                    sp_id_detail = d.get('shipmentPackageId')
                    logger.debug(f"Satır için shipmentPackageId bulundu: lineId={detail_line['lineId']}, sp_id={sp_id_detail}")

            # fallback
            if not sp_id_detail:
                sp_id_detail = order_created.shipment_package_id or order_created.package_number
                logger.debug(f"Satır için fallback shipmentPackageId kullanılıyor: lineId={detail_line['lineId']}, sp_id={sp_id_detail}")

            if not sp_id_detail:
                logger.error(f"Bu satır için hiçbir shipmentPackageId bulunamadı: {detail_line}")
                flash(f"LineId {detail_line['lineId']} için shipmentPackageId bulunamadı!", 'danger')
                return redirect(url_for('home.home'))

            lines_by_sp[sp_id_detail].append(detail_line)
            logger.debug(f"Satır eklendi: sp_id={sp_id_detail}, line={detail_line}")

        logger.info(f"Gruplandırma sonucu: {lines_by_sp}")

        # Trendyol güncellemesi
        logger.info("⏱️ Trendyol API çağrıları başlatılıyor...")
        supplier_id = SUPPLIER_ID
        trendyol_success = True  # API çağrılarının genel başarı durumu

        for sp_id, lines_for_sp in lines_by_sp.items():
            logger.info(f"Trendyol API çağrısı: supplier_id={supplier_id}, sp_id={sp_id}, lines={lines_for_sp}")
            try:
                result = await update_order_status_to_picking(supplier_id, sp_id, lines_for_sp)
                if result:
                    logger.info(f"✅ API çağrısı başarılı: sp_id={sp_id}")
                    flash(f"Paket {sp_id} Trendyol'da 'Picking' olarak güncellendi.", 'success')
                else:
                    logger.error(f"❌ API çağrısı başarısız: sp_id={sp_id}")
                    flash(f"Trendyol API güncellemesi sırasında hata. Paket ID: {sp_id}", 'danger')
                    trendyol_success = False
            except Exception as e:
                logger.error(f"❌ API çağrısı exception: sp_id={sp_id}, error={e}")
                flash(f"Trendyol API çağrısında istisna: {e}", 'danger')
                trendyol_success = False

        # Eğer Trendyol API çağrıları başarısız olduysa, kullanıcıya uyarı ver ama işleme devam et
        if not trendyol_success:
            logger.warning("Trendyol API çağrılarında bazı hatalar oluştu, ama işleme devam ediliyor.")

        # 7) Veritabanı tarafında OrderCreated -> OrderPicking taşı
        logger.info("Veritabanında OrderCreated -> OrderPicking taşıma işlemi başlatılıyor...")
        
        # OrderCreated kaydını al, OrderPicking'e ekle, OrderCreated'tan sil
        data = order_created.__dict__.copy()
        data.pop('_sa_instance_state', None)

        try:
            # Kolonları, OrderPicking tablosunda var olanlarla filtreleyelim
            # SQLAlchemy ile sınıf sütunlarını al
            picking_cols = OrderPicking.__dict__.keys()
            logger.info(f"Raw OrderPicking attributes: {picking_cols}")
            # SQLAlchemy iç attributelerini filtrele (_ile başlayanlar)
            picking_cols = {c for c in picking_cols if not c.startswith('_')}
            
            logger.info(f"OrderPicking tablo kolonları: {picking_cols}")
            data = {k: v for k, v in data.items() if k in picking_cols}
            logger.info(f"Filtrelenmiş veri: {data}")

            # Yeni picking kaydı oluştur
            new_picking_record = OrderPicking(**data)
            # picking tablosunda ek kolonlar varsa set edebilirsiniz:
            new_picking_record.picking_start_time = datetime.utcnow()
            
            logger.info(f"Oluşturulan OrderPicking kaydı: {new_picking_record}")
            
            # Veritabanı işlemlerini gerçekleştir
            db.session.add(new_picking_record)
            db.session.delete(order_created)
            
            logger.info("Değişiklikler veritabanına commit ediliyor...")
            db.session.commit()
            logger.info(f"✅ Veritabanı taşıma tamamlandı: OrderCreated -> OrderPicking. Order num: {order_number}")
        except Exception as db_error:
            logger.error(f"❌ Veritabanı taşıma hatası: {db_error}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            db.session.rollback()
            flash(f"Veritabanı işleminde hata: {db_error}", 'danger')
            return redirect(url_for('home.home'))

        # 8) Bir sonraki created siparişi bul
        logger.info("Bir sonraki sipariş aranıyor...")
        try:
            next_created = OrderCreated.query.order_by(OrderCreated.order_date).first()
            if next_created:
                logger.info(f"Bir sonraki sipariş bulundu: {next_created.order_number}")
                flash(f'Bir sonraki Created sipariş: {next_created.order_number}.', 'info')
            else:
                logger.info("Başka Created sipariş bulunamadı.")
                flash('Yeni Created sipariş bulunamadı.', 'info')
        except Exception as e:
            logger.error(f"Sonraki sipariş aranırken hata: {e}")
            flash('Sonraki sipariş aranırken hata oluştu.', 'warning')

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
