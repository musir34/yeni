from types import SimpleNamespace

from flask import Flask

import degisim
import iade_yonetimi


class FakeQuery:
    def __init__(self, exchange):
        self.exchange = exchange
        self.requested_number = None

    def filter_by(self, **kwargs):
        self.requested_number = kwargs.get('degisim_no')
        return self

    def first(self):
        return self.exchange


def make_app():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='test-secret')
    app.register_blueprint(degisim.degisim_bp)
    return app


def sample_exchange():
    return SimpleNamespace(
        degisim_no='9a46ce15-421d-4d02-8060-cf13f0cb5426',
        siparis_no='TY-12345',
        ad='Ayşe',
        soyad='Yılmaz',
        degisim_nedeni='38 yerine 39 numara gönderilecek',
    )


def test_exchange_return_code_uses_database_values_and_stable_request_id(monkeypatch):
    exchange = sample_exchange()
    query = FakeQuery(exchange)
    captured = {}

    monkeypatch.setattr(degisim, 'Degisim', SimpleNamespace(query=query))
    monkeypatch.setattr(degisim, '_safe_log', lambda *args, **kwargs: None)

    def fake_create(payload):
        captured.update(payload)
        return {'ok': True, 'iadeKodu': 'TY-12345-1', 'labelUrl': 'https://mn.tc/test'}

    monkeypatch.setattr(iade_yonetimi, 'create_iade', fake_create)
    app = make_app()

    with app.test_client() as client:
        with client.session_transaction() as flask_session:
            flask_session['role'] = 'manager'
            flask_session['username'] = 'yonetici'
        response = client.post(
            f'/degisim/{exchange.degisim_no}/iade-kodu-olustur',
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )

    assert response.status_code == 200
    assert response.get_json()['iadeKodu'] == 'TY-12345-1'
    assert query.requested_number == exchange.degisim_no
    assert captured == {
        'orderNumber': 'TY-12345',
        'email': '',
        'customerName': 'Ayşe Yılmaz',
        'reason': '38 yerine 39 numara gönderilecek',
        'source': 'degisim',
        'requestId': exchange.degisim_no,
        'createdBy': 'yonetici',
    }


def test_exchange_return_code_rejects_worker_before_database_lookup(monkeypatch):
    monkeypatch.setattr(degisim, 'Degisim', SimpleNamespace(
        query=SimpleNamespace(filter_by=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError('Veritabanına bakılmamalı')
        ))
    ))
    app = make_app()

    with app.test_client() as client:
        with client.session_transaction() as flask_session:
            flask_session['role'] = 'worker'
        response = client.post(
            '/degisim/test/iade-kodu-olustur',
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )

    assert response.status_code == 403


def test_exchange_return_code_reports_missing_record(monkeypatch):
    monkeypatch.setattr(degisim, 'Degisim', SimpleNamespace(query=FakeQuery(None)))
    app = make_app()

    with app.test_client() as client:
        with client.session_transaction() as flask_session:
            flask_session['role'] = 'admin'
        response = client.post(
            '/degisim/missing/iade-kodu-olustur',
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )

    assert response.status_code == 404
    assert 'bulunamadı' in response.get_json()['mesaj'].lower()
