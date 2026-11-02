"""
Anasayfa "Stok Eritme" görevi.

Komutan kararı (2026-10-07): üretim modu dışındaki modeller iki grupta eritilecek.
Alissa (TED-003) modelleri kapsam dışı, listelere yazılmaz. Model listeleri sabittir;
stok rakamları her açılışta central_stock'tan canlı okunur.
"""
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import func

from models import (db, CentralStock, Product, OrderCreated, OrderHazirlaniyor,
                    OrderPicking, OrderShipped, OrderDelivered)
from time_utils import IST, ist_to_utc

logger = logging.getLogger(__name__)

# Çok satan, fiyatla eritilecek modeller (Yusuf Mavi + Atölye)
COK_SATAN_MODELLER = [
    '9', '099', '0109', '0172', '0106', '0419', '017', '018', '020',
]

# Ağır giden modeller (üretim modu dışı, Alissa hariç)
AGIR_GIDEN_MODELLER = [
    '001', '0023', '007', '0103', '0104', '0105', '0107', '0108', '0111', '0112',
    '0114', '0118', '0126', '0198', '021', '0234', '024', '025', '026', '0268',
    '03155', '03495', '035', '037', '039', '044', '0478', '050', '056', '057',
    '060', '067', '068', '072', '073', '0734', '075', '076', '078', '079',
    '0792', '080', '081', '082', '086', '087', '088', '090', '092', '1310',
    '1313', '1320', '1329', '1330', '1338', '1340', '1350', '140', '142', '143',
    '145', '147', '149', '150', '1505', '151', '152', '153', '154', '155',
    '159', '169', '1709', '1710', '2001', '2002', '2003', '2183', '247', '395',
    '410', '420', '4407', '701', '720', '760', '770', '777', '886', '8888',
    '990', '9999', 'BG-500',
    'TYC00384750805', 'TYC0928363849M00000098009', 'TYC0932877755M00000108006',
    'TYCA56BA5EB8276A08', 'TYCEETHCFN174462279640712', 'TYCF3FAE199595D106',
]


# Bugünkü sipariş sayımı: anasayfa günlük sipariş kutucuğuyla aynı 5 tablo.
# İptaller (orders_cancelled) bilinçle dışarıda (Komutan kararı 2026-11-02).
_BUGUN_TABLOLARI = (OrderCreated, OrderHazirlaniyor, OrderPicking, OrderShipped, OrderDelivered)


def _bugun_utc_araligi(simdi: datetime | None = None) -> tuple[datetime, datetime]:
    """İstanbul bugünü 00:00–23:59 → naive UTC [başlangıç, bitiş) (order_date naive UTC saklanır)."""
    simdi = (simdi or datetime.now(IST)).astimezone(IST)
    gun_basi = datetime(simdi.year, simdi.month, simdi.day)
    return ist_to_utc(gun_basi), ist_to_utc(gun_basi + timedelta(days=1))


def _siparis_barkodlari(details) -> set[str]:
    try:
        det = json.loads(details) if isinstance(details, str) else details
    except (json.JSONDecodeError, TypeError):
        return set()
    if not isinstance(det, list):
        return set()
    return {str(d.get("barcode") or "").strip() for d in det if isinstance(d, dict)} - {""}


def _bugunku_siparisler(modeller: list[str]) -> dict[str, set[str]]:
    """Model kodu → bugün (İstanbul) gelen Trendyol sipariş numaraları kümesi.
    Sipariş, kalem barkodundan ya da product_main_id kolonundan modele bağlanır;
    küme olduğu için aynı sipariş bir modele ve grup toplamına bir kez girer.
    Hata → boş sözlük (kart düşmez)."""
    try:
        hedef = set(modeller)
        barkod_model = {str(bc).strip(): str(m).strip() for bc, m in
                        (db.session.query(Product.barcode, Product.product_main_id)
                         .filter(Product.product_main_id.in_(modeller)).all()) if bc}
        bas, bit = _bugun_utc_araligi()
        model_siparis: dict[str, set[str]] = {}
        for M in _BUGUN_TABLOLARI:
            for no, details, main_id in (db.session.query(M.order_number, M.details, M.product_main_id)
                                         .filter(M.order_date >= bas, M.order_date < bit).all()):
                bagli = {barkod_model[bc] for bc in _siparis_barkodlari(details) if bc in barkod_model}
                bagli |= {x.strip() for x in str(main_id or "").split(",")} & hedef
                for m in bagli:
                    model_siparis.setdefault(m, set()).add(str(no))
        return model_siparis
    except Exception:
        logger.warning("[ERITME] bugünkü siparişler okunamadı", exc_info=True)
        db.session.rollback()
        return {}


def _grup_stoklari(modeller: list[str]) -> dict:
    """Verilen modellerin merkezi stoğunu model bazında toplar.

    Dönüş: {'modeller': [{'kod', 'stok', 'bugun'}...] (liste sırası korunur), 'toplam': int,
            'bugun_toplam': int (gruba bugün gelen benzersiz sipariş)}
    Hata → sıfırlar (anasayfa bu yüzden düşmez).
    """
    try:
        rows = (db.session.query(Product.product_main_id, func.coalesce(func.sum(CentralStock.qty), 0))
                .join(CentralStock, CentralStock.barcode == Product.barcode)
                .filter(Product.product_main_id.in_(modeller))
                .group_by(Product.product_main_id)
                .all())
        stok = {str(m).strip(): int(q or 0) for m, q in rows}
    except Exception:
        logger.warning("[ERITME] grup stoğu okunamadı", exc_info=True)
        db.session.rollback()
        stok = {}
    bugun = _bugunku_siparisler(modeller)
    liste = [{'kod': m, 'stok': stok.get(m, 0), 'bugun': len(bugun.get(m, ()))} for m in modeller]
    bugun_toplam = len(set().union(*bugun.values()))
    return {'modeller': liste, 'toplam': sum(x['stok'] for x in liste), 'bugun_toplam': bugun_toplam}


def eritme_ozeti() -> dict:
    """Anasayfa kartı için iki grubun model listesi ve canlı stok toplamları."""
    return {
        'cok_satan': _grup_stoklari(COK_SATAN_MODELLER),
        'agir_giden': _grup_stoklari(AGIR_GIDEN_MODELLER),
    }
