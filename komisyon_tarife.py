"""Komisyon Hariç Tutma Listesi API'si.

Akıllı Motor ve diğer sayfalar tarafından paylaşılan
hariç tutma listelerini yönetir (kaydet/yükle/sil).
"""

from flask import Blueprint, request, jsonify
import os
import json
import logging
from datetime import datetime
from login_logout import login_required, roles_required

logger = logging.getLogger(__name__)

komisyon_tarife_bp = Blueprint('komisyon_tarife', __name__)

EXCLUDE_LISTS_FILE = './uploads/komisyon_haric_listeler.json'
os.makedirs('./uploads', exist_ok=True)


def _load_exclude_lists() -> dict:
    if os.path.exists(EXCLUDE_LISTS_FILE):
        with open(EXCLUDE_LISTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_exclude_lists(data: dict) -> None:
    with open(EXCLUDE_LISTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@komisyon_tarife_bp.route('/komisyon-tarife/listeler', methods=['GET'])
@login_required
@roles_required('admin')
def komisyon_tarife_listeler():
    return jsonify({'success': True, 'lists': _load_exclude_lists()})


@komisyon_tarife_bp.route('/komisyon-tarife/listeler', methods=['POST'])
@login_required
@roles_required('admin')
def komisyon_tarife_liste_kaydet():
    data = request.get_json()
    if not data or 'name' not in data or 'models' not in data:
        return jsonify({'success': False, 'message': 'name ve models gerekli'}), 400

    name = data['name'].strip()
    models = [m.strip() for m in data['models'] if m.strip()]

    if not name:
        return jsonify({'success': False, 'message': 'Liste adı boş olamaz'}), 400

    lists = _load_exclude_lists()
    lists[name] = {
        'models': models,
        'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    _save_exclude_lists(lists)
    return jsonify({'success': True, 'message': f'"{name}" kaydedildi'})


@komisyon_tarife_bp.route('/komisyon-tarife/listeler/<name>', methods=['DELETE'])
@login_required
@roles_required('admin')
def komisyon_tarife_liste_sil(name: str):
    lists = _load_exclude_lists()
    if name in lists:
        del lists[name]
        _save_exclude_lists(lists)
        return jsonify({'success': True, 'message': f'"{name}" silindi'})
    return jsonify({'success': False, 'message': 'Liste bulunamadı'}), 404
