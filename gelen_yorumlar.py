# gelen_yorumlar.py — 💬 Gelen Yorumlar (Güllü Yorum gönderim takibi) sayfası
# Ana sayfa "Paneller → Shopify (Site)" altındaki düğme: kaç müşteriye yorum e-postası gitti,
# kaçı bağlantıyı açtı, kaçı yorum yazdı. Veri Güllü Yorum'un SQLite dosyasından SALT OKUNUR
# gelir (gelen_yorumlar_service); panel hiçbir şeye yazmaz, e-posta göndermez, Shopify'a gitmez.
from flask import Blueprint, render_template, request

from login_logout import login_required, roles_required
from gelen_yorumlar_service import GelenYorumHata, Ozet, YILDIZLAR, YildizDagilimi, oku, oku_yorumlar
from logger_config import app_logger as logger

gelen_yorumlar_bp = Blueprint('gelen_yorumlar_bp', __name__)


@gelen_yorumlar_bp.route('/gelen-yorumlar', methods=['GET'])
@login_required
@roles_required('admin')
def gelen_yorumlar_page():
    sadece_yorum = request.args.get('filtre') == 'yorum'
    sekme = 'yorumlar' if request.args.get('sekme') == 'yorumlar' else 'gonderimler'
    try:
        ozet, satirlar = oku(sadece_yorum=sadece_yorum)
        yorumlar, yildiz = oku_yorumlar()
        hata = None
    except GelenYorumHata as e:
        logger.warning(f"[GELEN-YORUMLAR] Güllü Yorum verisine ulaşılamadı: {e}")
        ozet, satirlar, yorumlar, yildiz = Ozet(), [], [], YildizDagilimi({})
        hata = "Güllü Yorum verisine ulaşılamadı"
    return render_template('gelen_yorumlar.html', ozet=ozet, satirlar=satirlar, yorumlar=yorumlar,
                           yildiz=yildiz, yildizlar=YILDIZLAR, sekme=sekme,
                           sadece_yorum=sadece_yorum, hata=hata)
