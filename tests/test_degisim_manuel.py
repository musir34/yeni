from flask import Flask

import degisim


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.rolled_back = False

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeDegisim:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def make_app():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='test-secret')
    app.register_blueprint(degisim.degisim_bp)
    return app


def valid_product_form(**overrides):
    data = {
        'kayit_tipi': 'manuel',
        'siparis_no': '',
        'ad': 'Ayşe',
        'soyad': 'Yılmaz',
        'adres': 'Test adresi',
        'telefon_no': '5551112233',
        'degisim_nedeni': 'Beden değişimi',
        'urun_barkod': 'ABC123',
        'urun_model_kodu': 'MODEL1',
        'urun_renk': 'Siyah',
        'urun_beden': '39',
        'urun_adet': '1',
    }
    data.update(overrides)
    return data


def test_manual_exchange_generates_internal_reference_without_order_number(monkeypatch):
    fake_session = FakeSession()
    monkeypatch.setattr(degisim, 'db', type('FakeDb', (), {'session': fake_session})())
    monkeypatch.setattr(degisim, 'Degisim', FakeDegisim)
    monkeypatch.setattr(degisim, 'generate_kargo_kodu', lambda: '5551234567')
    monkeypatch.setattr(degisim, '_safe_log', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        degisim,
        'allocate_from_shelves',
        lambda barcode, qty=1: {'allocated': qty, 'shelf_codes': ['A-1']},
    )
    app = make_app()

    with app.test_client() as client:
        response = client.post('/degisim-kaydet', data=valid_product_form())

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/degisim_talep')
    assert fake_session.committed is True
    assert len(fake_session.added) == 1
    record = fake_session.added[0]
    assert record.siparis_no.startswith('MANUEL-')
    assert record.siparis_no != 'MANUEL-'
    assert record.ad == 'Ayşe'


def test_order_mode_still_requires_order_number():
    app = make_app()

    with app.test_client() as client:
        response = client.post(
            '/degisim-kaydet',
            data=valid_product_form(kayit_tipi='siparisli', siparis_no=''),
        )

    assert response.status_code == 400
    assert 'sipariş numarası' in response.get_json()['message'].lower()


def test_exchange_rejects_unknown_entry_mode():
    app = make_app()

    with app.test_client() as client:
        response = client.post(
            '/degisim-kaydet',
            data=valid_product_form(kayit_tipi='bilinmeyen'),
        )

    assert response.status_code == 400
    assert 'kayıt tipi' in response.get_json()['message'].lower()
