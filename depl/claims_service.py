
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import base64
import aiohttp
import asyncio
import json
from datetime import datetime, timedelta
from models import db, Order, Return
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL
import logging

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('claims_service.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

claims_service_bp = Blueprint('claims_service', __name__)

@claims_service_bp.route('/fetch-trendyol-claims', methods=['POST'])
async def fetch_trendyol_claims_route():
    try:
        await fetch_trendyol_claims_async()
        flash('İade talepleri başarıyla güncellendi!', 'success')
    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_claims_route - {e}")
        flash('İade talepleri güncellenirken bir hata oluştu.', 'danger')

    return redirect(url_for('claims_service.claims_list'))


@claims_service_bp.route('/claims-list', methods=['GET'])
def claims_list():
    """
    Tüm iade taleplerini listeler
    """
    claims = Return.query.order_by(Return.create_date.desc()).all()
    return render_template('claims_list.html', claims=claims)


async def fetch_trendyol_claims_async():
    """
    Trendyol API'den tüm iade taleplerini asenkron olarak çeker
    """
    try:
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/claims"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        # Son 30 günlük iade taleplerini alalım
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # Tarih formatı: yyyy-MM-dd
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        # İlk isteği yaparak toplam iade ve sayfa sayısını alalım
        params = {
            "status": "CREATED,REQUESTED_TO_SOLVE,REJECTED,SOLVED,RECEIVED,CANCELLED,COMPLETED",
            "startDate": start_date_str,
            "endDate": end_date_str,
            "page": 0,
            "size": 100  # Maksimum sayfa boyutu
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                response_data = await response.json()
                if response.status != 200:
                    logger.error(f"API Error: {response.status} - {response_data}")
                    return

                total_elements = response_data.get('totalElements', 0)
                total_pages = response_data.get('totalPages', 1)
                logger.info(f"Toplam iade sayısı: {total_elements}, Toplam sayfa sayısı: {total_pages}")

                # Tüm sayfalar için istek hazırlayalım
                tasks = []
                semaphore = asyncio.Semaphore(5)  # Aynı anda maksimum 5 istek
                for page_number in range(total_pages):
                    params_page = params.copy()
                    params_page['page'] = page_number
                    task = fetch_claims_page(session, url, headers, params_page, semaphore)
                    tasks.append(task)

                # Asenkron olarak tüm istekleri yapalım
                pages_data = await asyncio.gather(*tasks)

                # Gelen iadeleri birleştirelim
                all_claims_data = []
                for claims in pages_data:
                    if claims:
                        all_claims_data.extend(claims)

                logger.info(f"Toplam çekilen iade sayısı: {len(all_claims_data)}")

                # İadeleri işleyelim
                process_all_claims(all_claims_data)

    except Exception as e:
        logger.error(f"Hata: fetch_trendyol_claims_async - {e}")


async def fetch_claims_page(session, url, headers, params, semaphore):
    """
    Belirli bir sayfadaki iade taleplerini çeker
    """
    async with semaphore:
        try:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    logger.error(f"API isteği başarısız oldu: {response.status} - {await response.text()}")
                    return []
                data = await response.json()
                claims_data = data.get('content', [])
                return claims_data
        except Exception as e:
            logger.error(f"Hata: fetch_claims_page - {e}")
            return []


def process_all_claims(all_claims_data):
    """
    Trendyol'dan çekilen iade taleplerini veritabanına kaydeder
    """
    try:
        # Mevcut iadeleri al
        existing_claims = Return.query.all()
        existing_claims_dict = {claim.claim_id: claim for claim in existing_claims}
        
        # Yeni iadeleri toplu kaydetmek için liste
        new_claims = []
        updated_count = 0
        
        for claim_data in all_claims_data:
            claim_id = str(claim_data.get('id', ''))
            if not claim_id:
                continue
                
            # İade verilerini hazırla
            claim_line = claim_data.get('claimLine', {})
            shipment_address = claim_data.get('shipmentAddress', {})
            
            # Unix timestamp ms -> datetime
            create_date = datetime.fromtimestamp(claim_data.get('createDate', 0) / 1000) if claim_data.get('createDate') else None
            last_modified_date = datetime.fromtimestamp(claim_data.get('lastModifiedDate', 0) / 1000) if claim_data.get('lastModifiedDate') else None
            
            claim_data_dict = {
                'claim_id': claim_id,
                'order_number': str(claim_data.get('orderNumber', '')),
                'order_line_id': str(claim_line.get('id', '')) if claim_line else '',
                'status': claim_data.get('status', ''),
                'reason': claim_data.get('reason', ''),
                'barcode': claim_line.get('barcode', '') if claim_line else '',
                'product_name': claim_line.get('productName', '') if claim_line else '',
                'product_color': claim_line.get('productColor', '') if claim_line else '',
                'product_size': claim_line.get('productSize', '') if claim_line else '',
                'quantity': claim_line.get('quantity', 0) if claim_line else 0,
                'customer_name': f"{shipment_address.get('firstName', '')} {shipment_address.get('lastName', '')}".strip(),
                'address': shipment_address.get('address', '') if shipment_address else '',
                'create_date': create_date,
                'last_modified_date': last_modified_date,
                'notes': claim_data.get('notes', ''),
                'details': json.dumps(claim_data, ensure_ascii=False)
            }
            
            if claim_id in existing_claims_dict:
                # Mevcut iadeyi güncelle
                existing_claim = existing_claims_dict[claim_id]
                for key, value in claim_data_dict.items():
                    setattr(existing_claim, key, value)
                db.session.add(existing_claim)
                updated_count += 1
            else:
                # Yeni iade oluştur
                new_claim = Return(**claim_data_dict)
                new_claims.append(new_claim)
        
        # Yeni iadeleri toplu olarak ekle
        if new_claims:
            db.session.bulk_save_objects(new_claims)
            logger.info(f"Toplam {len(new_claims)} yeni iade talebi eklendi")
            
        if updated_count > 0:
            logger.info(f"Toplam {updated_count} iade talebi güncellendi")
        
        db.session.commit()
        logger.info("İade veritabanı güncellendi")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Hata: process_all_claims - {e}")


@claims_service_bp.route('/approve-claim/<claim_id>', methods=['POST'])
async def approve_claim(claim_id):
    """
    İade talebini onaylar
    """
    try:
        claim = Return.query.filter_by(claim_id=claim_id).first()
        if not claim:
            flash('İade talebi bulunamadı', 'error')
            return redirect(url_for('claims_service.claims_list'))
            
        # Trendyol API'ye onay gönder
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/claims/{claim_id}/approve"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        reason = request.form.get('reason', 'İade talebi onaylandı')
        payload = {"reason": reason}
        
        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    response_text = await response.text()
                    logger.error(f"API isteği başarısız oldu: {response.status} - {response_text}")
                    flash(f'İade talebi onaylanırken hata oluştu: {response_text}', 'error')
                    return redirect(url_for('claims_service.claims_list'))
                    
                # Veritabanını güncelle
                claim.status = 'APPROVED'
                claim.notes = f"{claim.notes}\nOnaylandı: {reason}"
                claim.last_modified_date = datetime.now()
                db.session.commit()
                
                flash('İade talebi başarıyla onaylandı', 'success')
                return redirect(url_for('claims_service.claims_list'))
                
    except Exception as e:
        db.session.rollback()
        logger.error(f"Hata: approve_claim - {e}")
        flash(f'İade talebi onaylanırken bir hata oluştu: {str(e)}', 'error')
        return redirect(url_for('claims_service.claims_list'))


@claims_service_bp.route('/reject-claim/<claim_id>', methods=['POST'])
async def reject_claim(claim_id):
    """
    İade talebini reddeder
    """
    try:
        claim = Return.query.filter_by(claim_id=claim_id).first()
        if not claim:
            flash('İade talebi bulunamadı', 'error')
            return redirect(url_for('claims_service.claims_list'))
            
        # Trendyol API'ye red gönder
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/claims/{claim_id}/reject"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        reason = request.form.get('reason', 'İade talebi reddedildi')
        payload = {"reason": reason}
        
        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    response_text = await response.text()
                    logger.error(f"API isteği başarısız oldu: {response.status} - {response_text}")
                    flash(f'İade talebi reddedilirken hata oluştu: {response_text}', 'error')
                    return redirect(url_for('claims_service.claims_list'))
                    
                # Veritabanını güncelle
                claim.status = 'REJECTED'
                claim.notes = f"{claim.notes}\nReddedildi: {reason}"
                claim.last_modified_date = datetime.now()
                db.session.commit()
                
                flash('İade talebi başarıyla reddedildi', 'success')
                return redirect(url_for('claims_service.claims_list'))
                
    except Exception as e:
        db.session.rollback()
        logger.error(f"Hata: reject_claim - {e}")
        flash(f'İade talebi reddedilirken bir hata oluştu: {str(e)}', 'error')
        return redirect(url_for('claims_service.claims_list'))
