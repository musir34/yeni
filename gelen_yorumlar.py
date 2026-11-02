# gelen_yorumlar.py — 💬 Gelen Yorumlar (Güllü Yorum gönderim takibi) sayfası
# Ana sayfa "Paneller → Shopify (Site)" altındaki düğme: kaç müşteriye yorum e-postası gitti,
# kaçı bağlantıyı açtı, kaçı yorum yazdı. Veri Güllü Yorum'un SQLite dosyasından SALT OKUNUR
# gelir (gelen_yorumlar_service); panel hiçbir şeye yazmaz, e-posta göndermez, Shopify'a gitmez.
from flask import Blueprint, render_template, request, redirect, url_for, flash

from login_logout import login_required, roles_required
from user_logs import log_user_action
from gelen_yorumlar_service import GelenYorumHata, Ozet, YILDIZLAR, YildizDagilimi, iade_isaretle, oku, oku_yorumlar
from logger_config import app_logger as logger

gelen_yorumlar_bp = Blueprint('gelen_yorumlar_bp', __name__)

SAYFA_BOYU = 100  # Gönderim listesi ve yorumlar sayfa başına kayıt (Komutan emri 2026-11-02)


def _sayfa_no(deger) -> int:
    try:
        return max(1, int(deger))
    except (TypeError, ValueError):
        return 1


def _sayfala(liste: list, sayfa: int) -> tuple[list, int, int]:
    """(dilim, geçerli sayfa, toplam sayfa); taşan sayfa no son sayfaya çekilir."""
    toplam_sayfa = max(1, -(-len(liste) // SAYFA_BOYU))
    sayfa = min(sayfa, toplam_sayfa)
    bas = (sayfa - 1) * SAYFA_BOYU
    return liste[bas:bas + SAYFA_BOYU], sayfa, toplam_sayfa


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
    satir_toplam, yorum_toplam = len(satirlar), len(yorumlar)
    satirlar, sayfa, sayfa_toplam = _sayfala(satirlar, _sayfa_no(request.args.get('sayfa')))
    yorumlar, ysayfa, ysayfa_toplam = _sayfala(yorumlar, _sayfa_no(request.args.get('ysayfa')))
    return render_template('gelen_yorumlar.html', ozet=ozet, satirlar=satirlar, yorumlar=yorumlar,
                           yildiz=yildiz, yildizlar=YILDIZLAR, sekme=sekme,
                           sadece_yorum=sadece_yorum, hata=hata,
                           satir_toplam=satir_toplam, yorum_toplam=yorum_toplam,
                           sayfa=sayfa, sayfa_toplam=sayfa_toplam,
                           ysayfa=ysayfa, ysayfa_toplam=ysayfa_toplam)


@gelen_yorumlar_bp.route('/gelen-yorumlar/iade-edildi', methods=['POST'])
@login_required
@roles_required('admin')
def iade_edildi():
    """Teşvik iadesi yapıldı düğmesi — Güllü Yorum `mark-refunded` ile aynı tek güncelleme (Komutan kararı)."""
    order_name = (request.form.get('order_name') or '').strip()
    sekme = request.form.get('sekme') or 'gonderimler'
    # İşaretlemeden sonra aynı sayfaya (ve filtreye) dönülsün
    geri = redirect(url_for('gelen_yorumlar_bp.gelen_yorumlar_page', sekme=sekme,
                            filtre=request.form.get('filtre') or None,
                            sayfa=_sayfa_no(request.form.get('sayfa')),
                            ysayfa=_sayfa_no(request.form.get('ysayfa'))))
    if not order_name:
        flash('Sipariş numarası eksik', 'danger')
        return geri
    try:
        isaretlendi = iade_isaretle(order_name)
    except GelenYorumHata as e:
        logger.warning(f"[GELEN-YORUMLAR] iade işareti yazılamadı ({order_name}): {e}")
        flash('Güllü Yorum verisine ulaşılamadı, iade işaretlenemedi', 'danger')
        return geri
    if isaretlendi:
        log_user_action('UPDATE', {'sayfa': 'Gelen Yorumlar', 'siparis': order_name, 'değişiklik': 'Teşvik iadesi yapıldı işaretlendi'})
        flash(f'{order_name} iade edildi olarak işaretlendi', 'success')
    else:
        flash(f'{order_name} için işaretlenecek bekleyen iade yok (teşviksiz ya da zaten işaretli)', 'warning')
    return geri
