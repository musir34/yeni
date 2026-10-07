"""
Anasayfa "Stok Eritme" görevi.

Komutan kararı (2026-10-07): üretim modu dışındaki modeller iki grupta eritilecek.
Alissa (TED-003) modelleri kapsam dışı, listelere yazılmaz. Model listeleri sabittir;
stok rakamları her açılışta central_stock'tan canlı okunur.
"""
import logging

from sqlalchemy import func

from models import db, CentralStock, Product

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


def _grup_stoklari(modeller: list[str]) -> dict:
    """Verilen modellerin merkezi stoğunu model bazında toplar.

    Dönüş: {'modeller': [{'kod', 'stok'}...] (liste sırası korunur), 'toplam': int}
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
    liste = [{'kod': m, 'stok': stok.get(m, 0)} for m in modeller]
    return {'modeller': liste, 'toplam': sum(x['stok'] for x in liste)}


def eritme_ozeti() -> dict:
    """Anasayfa kartı için iki grubun model listesi ve canlı stok toplamları."""
    return {
        'cok_satan': _grup_stoklari(COK_SATAN_MODELLER),
        'agir_giden': _grup_stoklari(AGIR_GIDEN_MODELLER),
    }
