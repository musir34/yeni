# -*- coding: utf-8 -*-
"""/alissa — Muhammet ALİSSA haftalık hesap sayfası (yalnız admin)."""
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import (Blueprint, current_app, flash, jsonify, redirect, render_template,
                   request, session, url_for)

from finans import _hata_flash          # yetersiz bakiye → "Emin misiniz?" kutusu (_finans_flash.html)
import finans_service as fs
from finans_service import FinansHata
from login_logout import login_required, roles_required
from models import db
from user_logs import log_user_action
from . import ayar, cari, hesap, senkron

logger = logging.getLogger(__name__)

alissa_bp = Blueprint('alissa', __name__, url_prefix='/alissa', template_folder='templates')

SAYFA = 'Muhammet Alissa Hesabı'
BINLIK = re.compile(r'^\d{1,3}(\.\d{3})+$')
TUTAR_SINIRI = Decimal('10000000000')   # kolon Numeric(12,2)


def _tutar_oku(metin):
    """'1.234,56' veya '1234.56' → Decimal. Geçersizse None."""
    metin = (metin or '').strip().replace('₺', '').replace(' ', '')
    if ',' in metin or BINLIK.match(metin):
        # Türkçe yazım: nokta binlik ayırıcı ('1.500' = bin beş yüz), virgül ondalık
        metin = metin.replace('.', '').replace(',', '.')
    try:
        deger = Decimal(metin)
    except InvalidOperation:
        return None
    if not deger.is_finite() or abs(deger) >= TUTAR_SINIRI:
        return None
    return deger.quantize(Decimal('0.01'))


def _uid():
    return int(session['user_id'])


def _cari():
    """Finans carisini haftalık netlerle eşitleyip döner; Finans tarafı kurulu değilse None (sayfa yine açılır)."""
    try:
        return cari.esitle(_uid())
    except Exception as e:  # noqa: BLE001 — sayfa Finans hatasıyla kapanmasın
        logger.exception('Alissa: Finans cari eşitleme hatası')
        flash(f'Finans cari bağlantısı kurulamadı; ödemeler görüntülenemiyor. Hata: {e}', 'danger')
        return None


@alissa_bp.route('/', methods=['GET'])
@login_required
@roles_required('admin')
def index():
    # Veri eskiyse sayfa açılışında arka planda tazele (sayfa beklemez).
    if senkron.eskidi():
        senkron.arka_planda_baslat(current_app._get_current_object())

    bugun = senkron.simdi_ist().date()
    c = _cari()
    ozet = hesap.haftalik(bugun, odenen=cari.odenen(c) if c else hesap.SIFIR)
    secili, detay = None, []
    if request.args.get('hafta'):
        try:
            secili = hesap.hafta_basi(date.fromisoformat(request.args['hafta']))
            detay = hesap.hafta_detay(secili)
        except ValueError:
            flash('Geçersiz hafta.', 'warning')
    return render_template(
        'alissa/index.html', ozet=ozet, secili=secili, detay=detay, bugun=bugun,
        modeller=hesap.model_ozet(), odemeler=cari.odemeler(c) if c else [], cari=c,
        hesaplar=fs.odeme_hesaplari(), durum=senkron.durum(),
        tutarlar=ayar.tutarlar(), etiketler=ayar.ETIKET)


@alissa_bp.route('/senkron', methods=['POST'])
@login_required
@roles_required('admin')
def senkron_baslat():
    if senkron.arka_planda_baslat(current_app._get_current_object()):
        flash('Trendyol verileri çekiliyor; bitince sayfa kendini yeniler.', 'info')
    else:
        flash('Senkron zaten çalışıyor.', 'warning')
    return redirect(url_for('alissa.index'))


@alissa_bp.route('/durum', methods=['GET'])
@login_required
@roles_required('admin')
def senkron_durum():
    d = senkron.durum()
    return jsonify(calisiyor=d['calisiyor'], hata=d['hata'])


@alissa_bp.route('/odeme', methods=['POST'])
@login_required
@roles_required('admin')
def odeme_ekle():
    """Finans ile aynı yol: seçilen kasa hesabından düşer, Alissa carisinin borcu azalır (tek transaction)."""
    tutar = _tutar_oku(request.form.get('tutar'))
    try:
        tarih = date.fromisoformat(request.form.get('tarih') or '')
    except ValueError:
        tarih = None
    if tutar is None or tutar <= 0 or tarih is None:
        flash('Ödeme kaydedilmedi: tarih ve sıfırdan büyük bir tutar girin.', 'danger')
        return redirect(url_for('alissa.index'))
    aciklama = (request.form.get('aciklama') or '').strip()[:255]
    try:
        c = cari.cari_getir(_uid())
        h = cari.odeme_yap(c, request.form.get('hesap', ''), tutar, fs.parse_tarih(tarih.isoformat()),
                           aciklama, _uid())
        log_user_action('CREATE', {'işlem_açıklaması': f'Alissa ödemesi — {tutar} TL ({tarih}) '
                                                        f'{h.islem.hesap.ad} {aciklama}', 'sayfa': SAYFA})
        flash(f'{tutar} TL ödeme kaydedildi; {h.islem.hesap.ad} hesabından düştü.', 'success')
    except FinansHata as e:
        _hata_flash(e)
    return redirect(url_for('alissa.index'))


@alissa_bp.route('/odeme/<int:odeme_id>/iptal', methods=['POST'])
@login_required
@roles_required('admin')
def odeme_iptal(odeme_id):
    """Cari + kasa hareketi birlikte geri alınır (finans_cari_service.hareket_iptal)."""
    try:
        c = cari.cari_getir(_uid())
        h = cari.odeme_iptal(c, odeme_id, _uid())
        log_user_action('DELETE', {'işlem_açıklaması': f'Alissa ödemesi iptal — {h.tutar} TL ({h.tarih:%Y-%m-%d})',
                                   'sayfa': SAYFA})
        flash('Ödeme iptal edildi; kasa ve cari bakiyesi geri alındı.', 'success')
    except FinansHata as e:
        _hata_flash(e)
    return redirect(url_for('alissa.index'))


@alissa_bp.route('/ayar', methods=['POST'])
@login_required
@roles_required('admin')
def ayar_kaydet():
    yeni = {}
    for anahtar in ayar.VARSAYILAN:
        deger = _tutar_oku(request.form.get(anahtar))
        if deger is None or deger < 0:
            flash(f'Ayarlar kaydedilmedi: "{ayar.ETIKET[anahtar]}" geçersiz.', 'danger')
            return redirect(url_for('alissa.index'))
        yeni[anahtar] = deger
    for anahtar, deger in yeni.items():
        ayar.yaz(anahtar, deger)
    db.session.commit()
    log_user_action('UPDATE', {'işlem_açıklaması': f'Alissa hesap ayarları — {yeni}', 'sayfa': SAYFA})
    flash('Ayarlar kaydedildi. Yeni tutarlar bundan sonra işlenen siparişlere uygulanır.', 'success')
    return redirect(url_for('alissa.index'))
