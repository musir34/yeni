"""whatsapp_gecikme testleri — DB'ye ve ağa dokunmaz (aday/kayıt/gönderim taklit)."""
from datetime import datetime

import pytest

import whatsapp_alici
import whatsapp_gecikme
import whatsapp_notify

SIMDI = datetime(2026, 9, 28, 9, 0, 0)


@pytest.fixture
def ortam(monkeypatch):
    monkeypatch.setenv("WHATSAPP_STAFF_TOKEN", "gizli")
    monkeypatch.setenv("WHATSAPP_STAFF_PHONE_NUMBER_ID", "111")
    monkeypatch.setenv("WHATSAPP_STAFF_NUMBERS", "905520000953")
    d = {"uyari": [], "geciken": [], "kayit": {"uyari": {}, "geciken": {}},
         "yazilan": [], "giden": [], "ok": True, "alicilar": ["0953"]}
    monkeypatch.setattr(whatsapp_gecikme, "_adaylar", lambda now: (d["uyari"], d["geciken"]))
    monkeypatch.setattr(whatsapp_gecikme, "_kayit_oku", lambda: d["kayit"])
    monkeypatch.setattr(whatsapp_gecikme, "_kayit_yaz", lambda veri, now: d["yazilan"].append(veri))
    monkeypatch.setattr(whatsapp_alici, "alicilar", lambda olay: d["alicilar"])

    def sahte(sablon, params, **kw):
        d["giden"].append((sablon, params, kw))
        return [{"to_last4": a, "ok": d["ok"]} for a in kw["only_last4"]]

    monkeypatch.setattr(whatsapp_notify, "notify_staff_template", sahte)
    return d


def test_yeni_siparisler_bildirilir_ve_kaydedilir(ortam):
    ortam["uyari"], ortam["geciken"] = ["1", "2"], ["9"]

    ozet = whatsapp_gecikme.gecikme_bildir(SIMDI)

    assert ozet == {"uyari": 2, "geciken": 1}
    assert [(s, p) for s, p, _ in ortam["giden"]] == [
        ("gecikme_uyarisi", ["2", "4 saatten az", "1, 2"]),
        ("geciken_siparis", ["1", "9"]),
    ]
    assert set(ortam["yazilan"][-1]["uyari"]) == {"1", "2"}
    assert set(ortam["yazilan"][-1]["geciken"]) == {"9"}


def test_daha_once_bildirilen_tekrar_gitmez(ortam):
    ortam["uyari"], ortam["geciken"] = ["1", "2"], ["9"]
    ortam["kayit"] = {"uyari": {"1": "x"}, "geciken": {"9": "x"}}

    ozet = whatsapp_gecikme.gecikme_bildir(SIMDI)

    assert ozet == {"uyari": 1, "geciken": 0}
    assert [(s, p) for s, p, _ in ortam["giden"]] == [("gecikme_uyarisi", ["1", "4 saatten az", "2"])]
    assert set(ortam["yazilan"][-1]["uyari"]) == {"1", "2"}


def test_uyarisi_giden_siparis_gecikince_ayrica_bildirilir(ortam):
    ortam["geciken"] = ["1"]
    ortam["kayit"] = {"uyari": {"1": "x"}, "geciken": {}}

    assert whatsapp_gecikme.gecikme_bildir(SIMDI) == {"uyari": 0, "geciken": 1}


def test_yeni_yoksa_mesaj_ve_kayit_yok(ortam):
    assert whatsapp_gecikme.gecikme_bildir(SIMDI) == {"uyari": 0, "geciken": 0}
    assert ortam["giden"] == [] and ortam["yazilan"] == []


def test_gonderim_basarisizsa_kaydedilmez_sonra_yeniden_denenir(ortam):
    ortam["geciken"], ortam["ok"] = ["9"], False

    assert whatsapp_gecikme.gecikme_bildir(SIMDI) == {"uyari": 0, "geciken": 0}
    assert ortam["yazilan"] == []


def test_alici_yoksa_gonderilmez_ve_kaydedilmez(ortam):
    ortam["geciken"], ortam["alicilar"] = ["9"], []

    assert whatsapp_gecikme.gecikme_bildir(SIMDI) == {"uyari": 0, "geciken": 0}
    assert ortam["giden"] == [] and ortam["yazilan"] == []


def test_uzun_liste_kisaltilir_sayi_tam_kalir(ortam):
    ortam["geciken"] = [str(10000000000 + i) for i in range(20)]

    whatsapp_gecikme.gecikme_bildir(SIMDI)

    _, params, _ = ortam["giden"][0]
    assert params[0] == "20" and params[1].endswith("(+8 sipariş daha)")
    assert len(params[1]) <= whatsapp_notify.MAX_PARAM_LENGTH
    assert len(ortam["yazilan"][-1]["geciken"]) == 20


def test_ayar_yoksa_sessiz(ortam, monkeypatch):
    monkeypatch.delenv("WHATSAPP_STAFF_TOKEN")
    ortam["geciken"] = ["9"]

    assert whatsapp_gecikme.gecikme_bildir(SIMDI) == {"uyari": 0, "geciken": 0}
    assert ortam["giden"] == []
