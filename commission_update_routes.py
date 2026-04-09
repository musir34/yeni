# commission_update_routes.py — Sipariş Verisi Excel'den Güncelleme
from flask import Blueprint, request, render_template, jsonify, send_from_directory
import pandas as pd
import os
import logging
from datetime import datetime
from werkzeug.utils import secure_filename

from user_logs import log_user_action

logger = logging.getLogger(__name__)

try:
    from .models import db, ExcelUpload
    from .models import OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled
except ImportError:
    from models import db, ExcelUpload
    from models import OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled

commission_update_bp = Blueprint('commission_update_bp', __name__)

UPLOAD_FOLDER = './uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

TABLE_CLASSES = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled]


def _parse_date(val):
    """Excel tarihini datetime'a çevirir."""
    if pd.isna(val):
        return None
    if isinstance(val, (pd.Timestamp, datetime)):
        return val if isinstance(val, datetime) else val.to_pydatetime()
    if isinstance(val, str):
        val = val.strip()
        for fmt in ["%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                pass
    return None


@commission_update_bp.route('/update-commission-from-excel', methods=['GET'])
def update_commission_page():
    show_all = request.args.get('all', '0') == '1'
    sort_by = request.args.get('sort', 'date')
    query = ExcelUpload.query
    if sort_by == 'name':
        query = query.order_by(ExcelUpload.filename.asc())
    else:
        query = query.order_by(ExcelUpload.upload_time.desc())
    uploads = query.all() if show_all else query.limit(10).all()
    return render_template('update_commission.html', uploads=uploads, show_all=show_all, sort_by=sort_by)


@commission_update_bp.route('/api/upload-commission-excel', methods=['POST'])
def api_upload_commission_excel():
    """Excel dosyalarını işler: amount, discount, commission günceller. JSON döner."""
    files = request.files.getlist('excel_files')
    if not files or not files[0].filename:
        return jsonify(success=False, message="Dosya yüklenmedi"), 400

    results = []

    for f in files:
        filename = secure_filename(f.filename)
        if not filename:
            continue
        ext = filename.rsplit('.', 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            results.append({"file": filename, "error": "Geçersiz dosya uzantısı"})
            continue

        save_path = os.path.join(UPLOAD_FOLDER, filename)
        try:
            f.save(save_path)
            df = pd.read_excel(save_path, engine='openpyxl' if ext == 'xlsx' else None)
            df.columns = [str(c).strip() for c in df.columns]

            required = {'Sipariş No', 'Komisyon', 'Sipariş Tutarı'}
            if not required.issubset(df.columns):
                missing = required - set(df.columns)
                results.append({"file": filename, "error": f"Eksik sütunlar: {', '.join(missing)}"})
                continue

            # Tarih parse
            first_date = None
            if 'Sipariş Tarihi' in df.columns:
                dates = [_parse_date(d) for d in df['Sipariş Tarihi'] if _parse_date(d)]
                first_date = dates[0] if dates else None

            # Upload kaydı
            upload_rec = ExcelUpload(filename=filename, upload_time=first_date or datetime.utcnow())
            db.session.add(upload_rec)
            db.session.flush()

            # Sipariş numaralarını topla
            df['_order_num'] = df['Sipariş No'].astype(str).str.strip()
            order_numbers = df['_order_num'].unique().tolist()

            # DB'den tüm eşleşen siparişleri çek
            order_map = {}
            for cls in TABLE_CLASSES:
                for o in cls.query.filter(cls.order_number.in_(order_numbers)).all():
                    order_map.setdefault(o.order_number, []).append(o)

            updated = 0
            not_found = 0
            skipped = 0

            for _, row in df.iterrows():
                on = str(row.get('Sipariş No', '')).strip()
                if not on:
                    continue

                # Excel değerlerini oku
                siparis_tutari = abs(float(row.get('Sipariş Tutarı', 0) or 0))
                komisyon = abs(float(row.get('Komisyon', 0) or 0))
                indirim = abs(float(row.get('İndirim', 0) or 0))

                # amount = müşterinin ödediği net fiyat = sipariş tutarı - indirim
                net_amount = siparis_tutari - indirim

                if on in order_map:
                    for order in order_map[on]:
                        order.amount = round(net_amount, 2)
                        order.discount = round(indirim, 2)
                        order.commission = round(komisyon, 2)
                    updated += 1
                else:
                    not_found += 1

            db.session.commit()

            results.append({
                "file": filename,
                "total_rows": len(df),
                "updated": updated,
                "not_found": not_found,
                "skipped": skipped,
            })

            try:
                log_user_action("UPDATE", {
                    "işlem_açıklaması": f"Sipariş verileri Excel'den güncellendi — {filename}: {updated} güncellendi, {not_found} bulunamadı",
                    "sayfa": "Sipariş Veri Güncelleme",
                })
            except Exception:
                pass

        except Exception as e:
            db.session.rollback()
            logger.error(f"Excel işleme hatası ({filename}): {e}", exc_info=True)
            results.append({"file": filename, "error": str(e)})
        finally:
            try:
                os.remove(save_path)
            except OSError:
                pass

    total_updated = sum(r.get("updated", 0) for r in results)
    total_not_found = sum(r.get("not_found", 0) for r in results)
    return jsonify(
        success=True,
        message=f"{len(results)} dosya işlendi — {total_updated} sipariş güncellendi, {total_not_found} bulunamadı",
        results=results,
    )


@commission_update_bp.route('/download/<path:filename>')
def download_excel(filename):
    try:
        return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify(success=False, message="Dosya bulunamadı"), 404
