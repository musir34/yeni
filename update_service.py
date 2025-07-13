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
from models import db, OrderCreated, OrderPicking, Product, RafUrun
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
        form_keys = list(request.form.keys())
        logger.info(f"Tüm form anahtarları: {form_keys}")
        
        # Flask form.getlist() kullanarak aynı isimli tüm değerleri al
        for key in form_keys:
            if key.startswith('barkod_right_') or key.startswith('barkod_left_'):
                barkod_values = request.form.getlist(key)
                for barkod_value in barkod_values:
                    barkod_value = barkod_value.strip()
                    if barkod_value:  # Boş barkodları dahil etme
                        barkodlar.append(barkod_value)
                        logger.debug(f"Barkod eklendi: {key}={barkod_value}")
                    else:
                        logger.warning(f"Boş barkod atlandı: {key}")

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

        # 5) Karşılaştırma - Sadece barkod türlerini kontrol et
        logger.info("Barkodlar karşılaştırılıyor...")
        logger.info(f"Gelen barkodlar (sıralı): {sorted(barkodlar)}")
        logger.info(f"Beklenen barkodlar (sıralı): {sorted(expected_barcodes)}")

        # Basit kontrol: Gelen her barkod beklenen listede var mı?
        barkod_error = False
        for barkod in barkodlar:
            if barkod not in expected_barcodes:
                logger.error(f"Beklenmeyen barkod: {barkod}")
                barkod_error = True
                break

        if barkod_error:
            flash('Geçersiz barkod girişi, lütfen tekrar deneyin!', 'danger')
            return redirect(url_for('home.home'))

        # Sayı kontrolü gevşetildi - sadece minimum kontrol
        if len(barkodlar) < len(set(expected_barcodes)):
            logger.warning(f"Barkod sayısı az olabilir: Gelen={len(barkodlar)}, Beklenen türler={len(set(expected_barcodes))}")
            # Uyarı ver ama devam et
            flash('Bazı barkodlar eksik olabilir, ama işlem devam ediyor.', 'warning')

        logger.info("✅ Barkodlar eşleşti. İşlem devam ediyor...")

        # === YENİ RAF STOK DÜŞME KODU BAŞLANGICI ===
        try:
            logger.info("🚚 Siparişteki her ürün için raflardan düşülüyor...")
            all_stock_sufficient = True
            insufficient_stock_items = []

            for detail in details:
                barkod = detail.get("barcode")
                adet = int(detail.get("quantity", 1))

                if not barkod or adet <= 0:
                    continue

                raf_kayitlari = RafUrun.query.filter(
                    RafUrun.urun_barkodu == barkod,
                    RafUrun.adet > 0
                ).order_by(asc(RafUrun.raf_kodu)).all()

                logger.info(f"➡️ {adet} adet {barkod} raftan düşülecek. Müsait raflar: {[r.raf_kodu for r in raf_kayitlari]}")

                kalan_adet = adet
                for raf in raf_kayitlari:
                    if kalan_adet == 0:
                        break

                    dusulecek = min(raf.adet, kalan_adet)
                    raf.adet -= dusulecek
                    kalan_adet -= dusulecek
                    logger.info(f"✅ {barkod} → {raf.raf_kodu} rafından {dusulecek} adet düşüldü (rafta kalan: {raf.adet})")

                if kalan_adet > 0:
                    all_stock_sufficient = False
                    logger.warning(f"❌ YETERSİZ RAF STOĞU: {barkod} için {kalan_adet} adet daha bulunamadı!")
                    insufficient_stock_items.append(f"{barkod} ({kalan_adet} adet eksik)")

            # Tüm ürünler kontrol edildikten sonra genel durumu değerlendir
            if not all_stock_sufficient:
                db.session.rollback() # Yapılan tüm değişiklikleri geri al
                error_msg = f"Raf Stoğu Yetersiz! İşlem iptal edildi. Eksik ürünler: {', '.join(insufficient_stock_items)}"
                flash(error_msg, 'danger')
                logger.error(error_msg)
                return redirect(url_for('home.home'))

            # Her şey yolundaysa değişiklikleri commit et
            db.session.commit()
            logger.info("Tüm ürünler için raf stokları başarıyla güncellendi.")

        except Exception as raf_error:
            db.session.rollback()
            logger.error(f"Raf stoklarını düşürürken kritik hata: {raf_error}", exc_info=True)
            flash('Raf stokları güncellenirken kritik bir hata oluştu. İşlem durduruldu.', 'danger')
            return redirect(url_for('home.home'))
        # === YENİ RAF STOK DÜŞME KODU BİTİŞİ ===


        # 6) Trendyol API'ye status=Picking çağrısı (shipmentPackageId'ye göre)
        logger.info("Trendyol API için hazırlık başlatılıyor...")
        shipment_package_ids = set()

        logger.info("ShipmentPackageId'ler toplanıyor...")
        for detail in details:
            sp_id = detail.get('shipmentPackageId') or order_created.shipment_package_id or order_created.package_number
            if sp_id:
                shipment_package_ids.add(sp_id)
                logger.debug(f"ShipmentPackageId eklendi: {sp_id} (detaylardan)")

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

        logger.info("Trendyol için 'lines' hazırlanıyor...")
        lines = []
        for detail in details:
            line_id = detail.get('line_id') or detail.get('line_ids_api')
            if not line_id:
                logger.error(f"Bir detay satırında line_id veya line_ids_api bulunamadı: {detail}")
                flash("'line_id' değeri yok, Trendyol update mümkün değil.", 'danger')
                return redirect(url_for('home.home'))

            q = int(detail.get('quantity', 1))
            line = { "lineId": int(line_id), "quantity": q }
            lines.append(line)
            logger.debug(f"Line eklendi: lineId={line_id}, quantity={q}")

        logger.info(f"Toplam {len(lines)} satır oluşturuldu: {lines}")

        lines_by_sp = defaultdict(list)
        logger.info("Satırlar shipmentPackageId'ye göre gruplandırılıyor...")

        for detail_line in lines:
            sp_id_detail = None
            for d in details:
                current_line_id = d.get('line_id') or d.get('line_ids_api')
                if str(current_line_id) == str(detail_line["lineId"]):
                    sp_id_detail = d.get('shipmentPackageId')

            if not sp_id_detail:
                sp_id_detail = order_created.shipment_package_id or order_created.package_number

            if not sp_id_detail:
                logger.error(f"Bu satır için hiçbir shipmentPackageId bulunamadı: {detail_line}")
                flash(f"LineId {detail_line['lineId']} için shipmentPackageId bulunamadı!", 'danger')
                return redirect(url_for('home.home'))

            lines_by_sp[sp_id_detail].append(detail_line)
            logger.debug(f"Satır eklendi: sp_id={sp_id_detail}, line={detail_line}")

        logger.info(f"Gruplandırma sonucu: {dict(lines_by_sp)}")

        logger.info("⏱️ Trendyol API çağrıları başlatılıyor...")
        supplier_id = SUPPLIER_ID
        trendyol_success = True

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

        if not trendyol_success:
            logger.warning("Trendyol API çağrılarında bazı hatalar oluştu, ama işleme devam ediliyor.")

        # 7) Veritabanı tarafında OrderCreated -> OrderPicking taşı
        logger.info("Veritabanında OrderCreated -> OrderPicking taşıma işlemi başlatılıyor...")

        data = order_created.__dict__.copy()
        data.pop('_sa_instance_state', None)

        try:
            picking_cols = {c.name for c in OrderPicking.__table__.columns}
            logger.info(f"OrderPicking tablo kolonları: {picking_cols}")

            data = {k: v for k, v in data.items() if k in picking_cols}
            logger.info(f"Filtrelenmiş veri: {data}")

            new_picking_record = OrderPicking(**data)
            new_picking_record.picking_start_time = datetime.utcnow()

            logger.info(f"Oluşturulan OrderPicking kaydı: {new_picking_record}")

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