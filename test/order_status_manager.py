import logging
import json
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError

# Mevcut tablolarınız (örnek)
from models import db, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled

logger = logging.getLogger(__name__)

# Statü -> Tablo Eşleme (örnek)
STATUS_TABLE_MAP = {
    'Created': OrderCreated,
    'Picking': OrderPicking,
    'Shipped': OrderShipped,
    'Delivered': OrderDelivered,
    'Cancelled': OrderCancelled
}

def find_order_across_tables(order_number):
    """
    order_number'a sahip siparişi 5 tabloda da arar.
    Bulursa (obj, tablo_sinifi), bulamazsa (None, None) döndürür.
    """
    for table_cls in STATUS_TABLE_MAP.values():
        obj = table_cls.query.filter_by(order_number=order_number).first()
        if obj:
            return obj, table_cls
    return None, None

def move_order_between_tables(order_obj, old_table_cls, new_table_cls):
    """
    Sipariş kaydını eski tablodan silip, verileri yeni tabloya taşır.
    """
    try:
        data = order_obj.__dict__.copy()
        data.pop('_sa_instance_state', None)

        # Yeni tabloda olmayan kolonları ayıkla
        new_cols = set(new_table_cls.__table__.columns.keys())
        filtered_data = {k: v for k, v in data.items() if k in new_cols}

        # Yeni tablo için kayıt oluştur
        new_obj = new_table_cls(**filtered_data)
        db.session.add(new_obj)

        # Eski kaydı sil
        db.session.delete(order_obj)
        db.session.flush()  # flush ile veritabanında işlemleri uygula (commit yok)

        logger.info(f"{old_table_cls.__tablename__} -> {new_table_cls.__tablename__} taşıma tamam. order_number={order_obj.order_number}")

        return new_obj
    except Exception as e:
        db.session.rollback()
        logger.error(f"Tablo taşıma hatası: {e}")
        raise

def update_order_status(order_number, new_status, additional_data=None):
    """
    Eski sistemde 'status' kolonunu güncelliyorduk;
    şimdi siparişi 'OrderCreated', 'OrderPicking', vb. tablolar arasında taşıyoruz.
    additional_data varsa, tablo objesindeki ilgili alanları günceller.
    """
    try:
        old_obj, old_table_cls = find_order_across_tables(order_number)

        if not old_obj:
            logger.warning(f"Sipariş bulunamadı: order_number={order_number}")
            return None

        if new_status not in STATUS_TABLE_MAP:
            logger.warning(f"Geçersiz statü: {new_status}")
            return None

        new_table_cls = STATUS_TABLE_MAP[new_status]

        # 1) Eğer zaten aynı tabloya aitse (ör. eski statü 'Created', yeni statü yine 'Created' vb.)
        if old_table_cls == new_table_cls:
            # Sadece alanları güncelleyelim
            if additional_data:
                for key, value in additional_data.items():
                    if hasattr(old_obj, key):
                        setattr(old_obj, key, value)
            logger.info(f"Aynı statü, sadece ek veri güncellendi. order_number={order_number} -> status={new_status}")
            db.session.commit()
            return old_obj

        # 2) Farklı tabloya geçiş
        #    (ör. Created -> Picking)
        new_obj = move_order_between_tables(old_obj, old_table_cls, new_table_cls)

        # additional_data varsa, yeni objenin alanlarını güncelle
        if additional_data:
            for key, value in additional_data.items():
                if hasattr(new_obj, key):
                    setattr(new_obj, key, value)

        # Tablolar arası taşıma + ek alan güncelleme tamam, commit
        db.session.commit()
        logger.info(f"Sipariş {order_number} -> yeni statü {new_status} olarak güncellendi (tablo değişti).")
        return new_obj

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Veritabanı hatası: {e}")
        raise
    except Exception as e:
        db.session.rollback()
        logger.error(f"Beklenmeyen hata: {e}")
        raise

def get_orders_by_status(status, page=1, per_page=50, search=None):
    """
    Eski sistemde 'Order.query.filter_by(status=...)' yapılıyordu;
    şimdi 'status' bir tabloyu ifade ediyor. (ör. status='Created' -> OrderCreated tablosu)
    """
    try:
        if status not in STATUS_TABLE_MAP:
            logger.warning(f"Geçersiz statü: {status}")
            # Boş bir sonuç döndürelim ya da Exception atabilirsiniz
            class FakePaginate:
                items = []
                total = 0
                pages = 0
            return FakePaginate()

        table_cls = STATUS_TABLE_MAP[status]
        query = table_cls.query

        # Arama filtresi
        if search:
            # order_number gibi kolonların var olduğunu varsayıyoruz
            query = query.filter(table_cls.order_number.ilike(f'%{search}%'))

        # Tarihe göre sıralama (aynı kolon adlarının her tabloda olduğunu varsayıyoruz)
        query = query.order_by(table_cls.order_date.desc())

        # Sayfalama
        paginated_orders = query.paginate(page=page, per_page=per_page, error_out=False)
        return paginated_orders

    except Exception as e:
        logger.error(f"Siparişleri getirirken hata: {e}")
        raise
