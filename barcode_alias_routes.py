"""
Barkod Alias Yönetim Blueprint
═══════════════════════════════════

Bu modül barkod alias (takma ad) sistemini yönetir.
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, BarcodeAlias, Product
from barcode_alias_helper import (
    normalize_barcode, 
    add_alias, 
    remove_alias, 
    get_all_aliases,
    get_alias_info
)

barcode_alias_bp = Blueprint('barcode_alias', __name__, url_prefix='/barcode-alias')


@barcode_alias_bp.route('/')
@login_required
def index():
    """Barkod alias listesi ve yönetim sayfası"""
    aliases = BarcodeAlias.query.order_by(BarcodeAlias.main_barcode, BarcodeAlias.alias_barcode).all()
    
    # Ana barkodlara göre grupla
    grouped = {}
    for alias in aliases:
        if alias.main_barcode not in grouped:
            grouped[alias.main_barcode] = []
        grouped[alias.main_barcode].append(alias)
    
    return render_template('barcode_alias.html', grouped=grouped)


@barcode_alias_bp.route('/add', methods=['POST'])
@login_required
def add_alias_route():
    """Yeni alias ekle ve stokları birleştir"""
    alias_barcode = request.form.get('alias_barcode', '').strip().replace(' ', '')
    main_barcode = request.form.get('main_barcode', '').strip().replace(' ', '')
    note = request.form.get('note', '').strip()
    merge_stocks = request.form.get('merge_stocks', 'on') == 'on'  # Checkbox
    
    if not alias_barcode or not main_barcode:
        flash('Barkod boş olamaz', 'danger')
        return redirect(url_for('barcode_alias.index'))
    
    # Ana barkod gerçekten var mı?
    product = Product.query.filter_by(barcode=main_barcode).first()
    if not product:
        flash(f'Ana barkod sistemde bulunamadı: {main_barcode}', 'warning')
        # Yine de ekleyelim (manuel işlem için)
    
    result = add_alias(
        alias_barcode=alias_barcode,
        main_barcode=main_barcode,
        created_by=current_user.username,
        note=note,
        merge_stocks=merge_stocks
    )
    
    if result['success']:
        flash(result['message'], 'success')
        
        # Stok birleştirme detayları
        if merge_stocks and result.get('stock_merged'):
            stock_info = result['stock_merged']
            if stock_info['central_merged'] > 0:
                flash(f"✅ Merkez stok birleştirildi: {stock_info['central_merged']} adet", 'info')
            if stock_info['raf_merged'] > 0:
                flash(f"✅ Raf stokları birleştirildi: {stock_info['raf_merged']} adet", 'info')
    else:
        flash(result['message'], 'danger')
    
    return redirect(url_for('barcode_alias.index'))


@barcode_alias_bp.route('/delete/<string:alias_barcode>', methods=['POST'])
@login_required
def delete_alias_route(alias_barcode):
    """Alias sil"""
    result = remove_alias(alias_barcode)
    
    if result['success']:
        flash(result['message'], 'success')
    else:
        flash(result['message'], 'danger')
    
    return redirect(url_for('barcode_alias.index'))


@barcode_alias_bp.route('/api/check/<string:barcode>')
def api_check_barcode(barcode):
    """Bir barkod hakkında bilgi döner (API)"""
    info = get_alias_info(barcode)
    return jsonify(info)


@barcode_alias_bp.route('/api/normalize/<string:barcode>')
def api_normalize(barcode):
    """Barkodu normalize eder (API)"""
    normalized = normalize_barcode(barcode)
    return jsonify({
        'original': barcode,
        'normalized': normalized,
        'is_alias': (barcode != normalized)
    })
