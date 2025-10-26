# Gerekli kütüphaneleri ve modülleri import edin
from flask import Blueprint, request, render_template, flash, redirect, url_for, send_from_directory
import pandas as pd
import os
import random
import logging
from datetime import datetime
from werkzeug.utils import secure_filename
from sqlalchemy import func

logger = logging.getLogger(__name__)

# Veritabanı modellerinizi import edin
try:
    from .models import db, ExcelUpload
    from .models import OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled
except ImportError:
    from models import db, ExcelUpload
    from models import OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled

# Blueprint'i oluşturun
commission_update_bp = Blueprint('commission_update_bp', __name__)

# Ayarlar
UPLOAD_FOLDER = './uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def parse_excel_date(date_value):
    """Excel tarihini datetime'a dönüştürür."""
    if pd.isna(date_value):
        return None
    if isinstance(date_value, pd.Timestamp):
        return date_value.to_pydatetime()
    if isinstance(date_value, datetime):
        return date_value
    if isinstance(date_value, str):
        date_value = date_value.strip()
        if ' ' in date_value:
            date_value = date_value.split(' ')[0]
        for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y.%m.%d"]:
            try:
                return datetime.strptime(date_value, fmt)
            except ValueError:
                pass
        logger.warning(f"Tanınamayan tarih formatı: {date_value}")
        return None
    if isinstance(date_value, (int, float)):
        try:
            return pd.to_datetime(date_value, unit='D', origin='1899-12-30').to_pydatetime()
        except Exception as e:
            logger.warning(f"Sayısal tarih parse hatası: {e}")
            return None
    return None


@commission_update_bp.route('/update-commission-from-excel', methods=['GET', 'POST'])
def update_commission_from_excel():
    if request.method == 'POST':
        files = request.files.getlist('excel_files')

        if not files or not files[0].filename:
            flash("Excel dosyası yüklenmedi!", "danger")
            return redirect(request.url)

        total_updated = 0
        total_not_found = 0
        total_files_processed = 0
        error_files = []

        for f in files:
            filename = secure_filename(f.filename)
            if not filename:
                continue

            ext = filename.rsplit('.', 1)[-1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                flash(f"{filename}: Geçersiz uzantı. Sadece ({', '.join(ALLOWED_EXTENSIONS)}) yükleyebilirsiniz.", "danger")
                error_files.append(filename)
                continue

            save_path = os.path.join(UPLOAD_FOLDER, filename)

            try:
                f.save(save_path)

                df = pd.read_excel(save_path, engine='openpyxl' if ext == 'xlsx' else None)
                df.columns = [str(c).strip() for c in df.columns]

                required_columns = {'Sipariş No', 'Komisyon', 'Sipariş Tarihi'}
                if not required_columns.issubset(df.columns):
                    missing_cols = required_columns - set(df.columns)
                    flash(f"{filename}: Gerekli sütunlar bulunamadı: {', '.join(missing_cols)}", "danger")
                    error_files.append(filename)
                    continue

                df.rename(columns={
                    'Sipariş No': 'order_number',
                    'Komisyon': 'commission',
                    'Sipariş Tarihi': 'order_date_excel'
                }, inplace=True, errors='ignore')

                upload_date = datetime.utcnow()
                valid_dates = []

                if 'order_date_excel' in df.columns:
                    valid_dates = [d for d in (parse_excel_date(dt) for dt in df['order_date_excel']) if d is not None]
                    if valid_dates:
                        upload_date = random.choice(valid_dates)

                new_upload = ExcelUpload(
                    filename=filename,
                    upload_time=upload_date
                )
                db.session.add(new_upload)
                db.session.commit()

                df['order_number'] = df['order_number'].astype(str).str.strip()
                order_numbers_in_excel = df['order_number'].unique().tolist()

                # Tüm sipariş tablolarından siparişleri çek
                all_orders = []
                table_classes = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled]
                for tbl_cls in table_classes:
                    all_orders.extend(tbl_cls.query.filter(tbl_cls.order_number.in_(order_numbers_in_excel)).all())

                order_map = {}
                for order in all_orders:
                    if order.order_number not in order_map:
                        order_map[order.order_number] = []
                    order_map[order.order_number].append(order)

                updated_objects = []
                file_not_found_count = 0

                for idx, row in df.iterrows():
                    order_num = str(row.get('order_number', '')).strip()
                    if not order_num:
                        logger.debug(f"{filename} - Satır {idx + 2}: Boş sipariş numarası, atlanıyor")
                        continue

                    raw_commission = row.get('commission')
                    comm_val = 0.0
                    try:
                        if pd.notna(raw_commission):
                            comm_val = abs(float(raw_commission))
                    except (ValueError, TypeError) as e:
                        print(
                            f"[DEBUG] {filename} - Sipariş {order_num} (Satır {idx + 2}): Geçersiz komisyon '{raw_commission}', 0.0 olarak ayarlandı. Hata: {e}")
                        comm_val = 0.0

                    raw_date_in_excel = row.get('order_date_excel')
                    parsed_date = parse_excel_date(raw_date_in_excel)

                    if not parsed_date:
                        if valid_dates:
                            parsed_date = random.choice(valid_dates)

                    if order_num in order_map:
                        orders_to_update = order_map[order_num]
                        # Komisyonu siparişteki ürün sayısına bölebilir veya eşit dağıtabilirsiniz.
                        # Şimdilik eşit dağıtıyorum.
                        commission_per_order = comm_val / len(orders_to_update) if orders_to_update else 0
                        for order_to_update in orders_to_update:
                            order_to_update.commission = commission_per_order
                            if parsed_date:
                                order_to_update.order_date = parsed_date
                            updated_objects.append(order_to_update)
                    else:
                        file_not_found_count += 1
                        logger.debug(f"{filename} - Sipariş {order_num} veritabanında bulunamadı")

                if updated_objects:
                    db.session.bulk_save_objects(updated_objects)
                    db.session.commit()

                print(
                    f"[LOG] -> Dosya({filename}): {len(updated_objects)} kayıt güncellendi, {file_not_found_count} bulunamadı.")
                total_updated += len(updated_objects)
                total_not_found += file_not_found_count
                total_files_processed += 1

            except pd.errors.EmptyDataError:
                flash(f"{filename}: Dosya boş veya okunamadı.", "danger")
                error_files.append(filename)
            except FileNotFoundError:
                flash(f"{filename}: Dosya bulunamadı.", "danger")
                error_files.append(filename)
            except Exception as e:
                db.session.rollback()
                print(f"[ERROR] -> Dosya ({filename}) işlenirken genel hata: {e}")
                flash(f"{filename} işlenirken bir hata oluştu: {e}", "danger")
                error_files.append(filename)
            finally:
                try:
                    os.remove(save_path)
                except OSError as e:
                    print(f"[WARNING] Dosya silinemedi: {save_path}, Hata: {e}")

        if total_files_processed > 0:
            flash(
                f"Toplam {total_files_processed} dosya başarıyla işlendi. "
                f"{total_updated} kayıt güncellendi, {total_not_found} kayıt bulunamadı.",
                "success"
            )
        if error_files:
            flash(f"Şu dosyalarda hata oluştu veya işlenemedi: {', '.join(error_files)}", "danger")

        return redirect(url_for('commission_update_bp.update_commission_from_excel'))

    show_all = (request.args.get('all', '0') == '1')
    sort_by = request.args.get('sort', 'date')

    query = ExcelUpload.query

    if sort_by == 'name':
        query = query.order_by(ExcelUpload.filename.asc())
    else:
        query = query.order_by(ExcelUpload.upload_time.desc())

    if not show_all:
        uploads = query.limit(10).all()
    else:
        uploads = query.all()

    return render_template(
        'update_commission.html',
        uploads=uploads,
        show_all=show_all,
        sort_by=sort_by
    )


@commission_update_bp.route('/download/<path:filename>')
def download_excel(filename):
    """Yüklenen Excel dosyasını indirmek için."""
    try:
        return send_from_directory(
            UPLOAD_FOLDER,
            filename,
            as_attachment=True
        )
    except FileNotFoundError:
        flash(f"{filename} adlı dosya bulunamadı!", "danger")
        return redirect(url_for('commission_update_bp.update_commission_from_excel'))