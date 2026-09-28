"""whatsapp_alici dağılım testleri — DB'ye dokunmaz, kayıt okuma taklit edilir."""
import pytest

import whatsapp_alici


@pytest.fixture
def numaralar(monkeypatch):
    monkeypatch.setenv("WHATSAPP_STAFF_NUMBERS", "905520000953,905360000104,905001117777")


def _kayit(monkeypatch, deger):
    def oku():
        if isinstance(deger, Exception):
            raise deger
        return deger
    monkeypatch.setattr(whatsapp_alici, "_kayitli", oku)


def test_kayit_yoksa_ilk_dagilim_gecerli(numaralar, monkeypatch):
    _kayit(monkeypatch, None)

    assert whatsapp_alici.alicilar("uretim_siparis") == ["0104", "7777"]
    assert whatsapp_alici.alicilar("uretim_iptal") == ["0104", "7777"]
    assert whatsapp_alici.alicilar("soru") == ["0953", "7777"]
    assert whatsapp_alici.alicilar("geciken_siparis") == ["0953", "7777"]
    assert whatsapp_alici.alicilar("duyuru") == ["0953", "0104", "7777"]


def test_kayitli_dagilim_ilk_dagilimi_ezer(numaralar, monkeypatch):
    _kayit(monkeypatch, {
        "0953": {"ad": "Mağaza", "olaylar": ["uretim_siparis"]},
        "0104": {"ad": "Ahmet", "olaylar": []},
        "7777": {"ad": "Depo", "olaylar": ["soru", "bilinmeyen_olay"]},
    })

    assert whatsapp_alici.alicilar("uretim_siparis") == ["0953"]
    assert whatsapp_alici.alicilar("soru") == ["7777"]
    assert whatsapp_alici.alicilar("duyuru") == []
    assert whatsapp_alici.dagilim()[2] == {"son4": "7777", "ad": "Depo", "olaylar": ["soru"]}


def test_env_den_cikan_numara_listede_gorunmez(monkeypatch):
    monkeypatch.setenv("WHATSAPP_STAFF_NUMBERS", "905360000104")
    _kayit(monkeypatch, {"0953": {"ad": "Mağaza", "olaylar": ["soru"]},
                         "0104": {"ad": "Ahmet", "olaylar": ["soru"]}})

    assert whatsapp_alici.alicilar("soru") == ["0104"]


def test_db_hatasinda_ilk_dagilima_doner(numaralar, monkeypatch):
    _kayit(monkeypatch, RuntimeError("db yok"))

    assert whatsapp_alici.alicilar("soru") == ["0953", "7777"]


def test_kaydet_bilinmeyen_numarayi_reddeder(numaralar):
    with pytest.raises(ValueError):
        whatsapp_alici.kaydet([{"son4": "9999", "ad": "X", "olaylar": ["soru"]}])
