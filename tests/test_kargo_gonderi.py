"""MNG giden gönderi servisi — izole sqlite + sahte MNG istemcisi (ağ yok).

Kapsam: kayıt oluşturunca MNG siparişi açılır (idempotent), barkod ikinci aşamada alınır
(MNG iki aşama kuralı), API hatasında kayıt 'bekliyor' kalır ve takip işi yeniden dener,
durum geçişleri kaynak statüsünü ileri yönde düşürür (değişim 'Kargoya Verildi'/'Teslim Edildi',
manuel 'Kargoda'/'Teslim Edildi', Shopify fulfillment bir kez + etiket), kapıda ödeme teslimde
tahsil sayılır ve 20 TL altı reddedilir, silmede iptal (barkodluysa cancelshipment),
anahtar kapalıyken hiçbir şey olmaz / tabloya gidilmez.

Çalıştırma (çıplak pytest YASAK — conftest canlı uygulamayı yükler):
  DISABLE_JOBS=1 python -m pytest --noconftest tests/test_kargo_gonderi.py -q
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_kargo_gonderi_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"
os.environ["MNG_OTOMATIK_GONDERI"] = "1"
os.environ["MNG_ORTAM"] = "sandbox"

from flask import Flask  # noqa: E402

from models import Degisim, KargoGonderi, YeniSiparis, db  # noqa: E402
from mng_kargo import servis  # noqa: E402
from mng_kargo.client import MngClient, MngHata  # noqa: E402
from mng_kargo.durum import GonderiDurumu, kod_cevir  # noqa: E402
from mng_kargo.govde import Alici  # noqa: E402

app = Flask(__name__)
app.config.update(SECRET_KEY="t", SQLALCHEMY_DATABASE_URI=os.environ["DATABASE_URL"],
                  SQLALCHEMY_TRACK_MODIFICATIONS=False, TESTING=True)
db.init_app(app)

SUBE_YOK = MngHata("MNG POST /barcodecmdapi/createbarcode HTTP 500 [20001] <WERR> X NO'LU SİPARİŞ KAYDI İÇİN VARIŞ ŞUBESİ BULUNAMADI ! DAHA SONRA TEKRAR DENEYİN ! </WERR>", kod="20001", http=500)
COD_SINIR = MngHata("MNG POST /barcodecmdapi/createbarcode HTTP 500 [20001] <WERR>Tahsilatlı Kapıda Gönderi Tutar en az 20 TL ve üstü olmalıdır.</WERR>", kod="20001", http=500)


class SahteAyar:
    ortam = "sandbox"
    customer_number = "800169398"


class SahteClient:
    """Çağrıları kaydeder; davranış senaryoya göre ayarlanır."""

    def __init__(self):
        self.ayar = SahteAyar()
        self.siparisler = []             # createOrder istekleri
        self.barkodlar = []              # createbarcode istekleri
        self.iptaller = []               # cancelorder referansları
        self.iptal_gonderiler = []       # cancelshipment (ref, shipmentId)
        self.hata = None                 # MngHata → siparis_olustur fırlatır
        self.barkod_hatasi = None        # MngHata → barkod_olustur fırlatır
        self.durumlar = {}               # referans → GonderiDurumu

    def siparis_olustur(self, istek):
        if self.hata:
            raise self.hata
        self.siparisler.append(istek)
        return {"orderInvoiceId": "1816638341", "shipperBranchCode": "03412900", "referenceId": istek.referans}

    def barkod_olustur(self, istek, tekrar=True):
        if self.barkod_hatasi:
            raise self.barkod_hatasi
        self.barkodlar.append(istek)
        return {"shipmentId": "195991365254", "invoiceId": "RZ880714",
                "barcodes": [{"barcode": "D@53BH21RZ13CKAAA6J", "value": "^XA^PW831^LL0959^XZ"}]}

    def barkod_sonucu(self, istek, cevap, siparis=None):
        return MngClient.barkod_sonucu(self, istek, cevap, siparis)

    def durum(self, referans):
        return self.durumlar.get(referans)

    def iptal(self, referans):
        self.iptaller.append(referans)
        return {}

    def iptal_gonderi(self, referans, shipment_id):
        self.iptal_gonderiler.append((referans, shipment_id))
        return {}


def _durum(kod, **ek):
    d = kod_cevir(kod)
    return GonderiDurumu(kod=kod, durum=d, mng_metni=ek.get("metin", ""), shipment_id="195991365254",
                         teslim_edildi=(d == "teslim"), teslim_alan=ek.get("alan", ""), teslim_zamani=None,
                         takip_url="")


@pytest.fixture()
def ctx():
    # Yalnız gerekli tablolar: tüm metadata'da (tasks.commit_due) çift indeks sqlite'ı kırıyor
    tablolar = [KargoGonderi.__table__, Degisim.__table__, YeniSiparis.__table__]
    with app.app_context():
        db.metadata.drop_all(bind=db.engine, tables=tablolar)
        db.metadata.create_all(bind=db.engine, tables=tablolar)
        sahte = SahteClient()
        servis._client = sahte
        yield sahte
        db.session.remove()


def _alici():
    return Alici(ad_soyad="Ayşe Yılmaz", adres="Moda Cad. 3", telefon="5321234567", il="İSTANBUL", ilce="KADIKÖY")


def _ac_ve_barkodla(kaynak, ref, ad, referans, **ek):
    """Sipariş aç + işleme al (barkod_iste) → hazırlandı."""
    k = servis.gonderi_ac(kaynak, ref, ad, referans, _alici(), **ek)
    servis.barkod_iste(kaynak, ref)
    return KargoGonderi.query.get(k.id)


def _yenile(k):
    k.son_sorgu_at = None
    db.session.commit()


# ---------------------------------------------------------------- açma (iki aşama)
def test_gonderi_ac_siparisi_acar_barkod_ikinci_asamada(ctx):
    k1 = servis.gonderi_ac("degisim", "uuid-1", "5551234567", servis.degisim_referansi("5551234567"), _alici())
    k2 = servis.gonderi_ac("degisim", "uuid-1", "5551234567", servis.degisim_referansi("5551234567"), _alici())
    assert k1.id == k2.id and k1.referans == "DG5551234567"
    assert k1.durum == "siparis_acildi" and k1.shipment_id is None
    assert len(ctx.siparisler) == 1 and ctx.siparisler[0].alici.il == "İSTANBUL"

    servis.takip_isi()                                    # işleme alınmadı → barkod (ve SMS) istenmez
    assert ctx.barkodlar == [] and not k1.barkod_istendi
    assert servis.barkod_iste("degisim", "uuid-1")        # "İşleme Al" → barkod
    k = KargoGonderi.query.get(k1.id)
    assert k.barkod_istendi
    assert k.durum == "hazirlandi" and k.shipment_id == "195991365254" and k.barkod.startswith("D@")
    assert k.zpl.startswith("^XA") and k.takip_url.endswith("takipNo=195991365254")


def test_sube_cozulmediyse_barkod_sonraki_turda(ctx):
    ctx.barkod_hatasi = SUBE_YOK
    k = _ac_ve_barkodla("manuel", "SP1", "SP1", "MN1")
    assert k.durum == "siparis_acildi" and k.barkod_istendi and "şubesini henüz çözmedi" in k.hata
    ctx.barkod_hatasi = None
    assert servis.takip_isi()["barkod"] == 1              # bayrak duruyor → takip işi alır
    assert KargoGonderi.query.get(k.id).durum == "hazirlandi"


def test_barkod_iste_siparis_henuz_acilmadiysa_bayrak_kalir(ctx):
    ctx.hata = MngHata("MNG token hatası", http=500)
    k = servis.gonderi_ac("manuel", "SP1b", "SP1b", "MN1B", _alici())
    assert k.durum == "bekliyor"
    assert servis.barkod_iste("manuel", "SP1b") is False
    assert KargoGonderi.query.get(k.id).barkod_istendi
    ctx.hata = None
    ozet = servis.takip_isi()                            # önce açar, aynı turda barkodu alır
    assert ozet["acildi"] == 1 and ozet["barkod"] == 1
    assert KargoGonderi.query.get(k.id).durum == "hazirlandi"


def test_barkod_kalici_hatasi_hataya_duser(ctx):
    ctx.barkod_hatasi = COD_SINIR
    k = _ac_ve_barkodla("manuel", "SP2", "SP2", "MN2", kapida_odeme_tutari=25)
    assert k.durum == "hata" and "20 TL" in k.hata


def test_kapida_odeme_20_tl_alti_api_ye_gitmez(ctx):
    k = servis.gonderi_ac("manuel", "SP3", "SP3", "MN3", _alici(), kapida_odeme_tutari=15)
    assert k.durum == "hata" and "alt sınır" in k.hata and ctx.siparisler == []


def test_api_hatasi_kaydi_bekliyor_birakir_ve_takip_yeniden_dener(ctx):
    ctx.hata = MngHata("MNG token hatası", http=500)
    k = servis.gonderi_ac("manuel", "SP4", "SP4", servis.manuel_referansi(7), _alici(), kapida_odeme_tutari=1249.9)
    assert k.durum == "bekliyor" and k.deneme == 1 and float(k.kapida_odeme_tutari) == 1249.9
    ctx.hata = None
    assert servis.takip_isi()["acildi"] == 1
    k = KargoGonderi.query.get(k.id)
    assert k.durum == "siparis_acildi" and k.hata is None
    assert ctx.siparisler[0].kapida_odeme_tutari == 1249.9


def test_deneme_siniri_dolunca_hata(ctx):
    ctx.hata = MngHata("kimlik", kod="401", http=401)
    k = servis.gonderi_ac("manuel", "SP5", "SP5", "MN5", _alici())
    for _ in range(servis.MAX_DENEME):
        servis.takip_isi()
    assert KargoGonderi.query.get(k.id).durum == "hata"


def test_bekliyor_pencere_dolunca_hata(ctx):
    ctx.hata = MngHata("x")
    k = servis.gonderi_ac("manuel", "SP6", "SP6", "MN6", _alici())
    k.olusturuldu_at = datetime.utcnow() - timedelta(days=4); db.session.commit()
    servis.takip_isi()
    k = KargoGonderi.query.get(k.id)
    assert k.durum == "hata" and "süresi doldu" in k.hata


def test_anahtar_kapaliyken_hicbir_sey_olmaz(ctx, monkeypatch):
    monkeypatch.setenv("MNG_OTOMATIK_GONDERI", "0")
    assert servis.gonderi_ac("manuel", "SP7", "SP7", "MN7", _alici()) is None
    assert KargoGonderi.query.count() == 0 and ctx.siparisler == []


def test_anahtar_kapaliyken_tabloya_dokunulmaz(ctx, monkeypatch):
    """Kod tablo betiğinden önce deploy edilse de (tablo yok) silme/liste akışları bozulmaz."""
    db.metadata.drop_all(bind=db.engine, tables=[KargoGonderi.__table__])
    monkeypatch.setenv("MNG_OTOMATIK_GONDERI", "0")
    assert servis.gonderi_haritasi("degisim", ["d1"]) == {}
    assert servis.gonderi_iptal("degisim", "d1") is False
    assert servis.gonderi_bul("manuel", "SP1") is None


def test_anahtar_acikken_tablo_yoksa_savepoint_ile_yutulur(ctx):
    db.metadata.drop_all(bind=db.engine, tables=[KargoGonderi.__table__])
    assert servis.gonderi_haritasi("degisim", ["d1"]) == {}
    assert servis.gonderi_ac("manuel", "SPX", "SPX", "MNX", _alici()) is None
    db.session.add(YeniSiparis(siparis_no="SPY", musteri_adi="A"))   # oturum hâlâ kullanılabilir
    db.session.commit()
    assert YeniSiparis.query.filter_by(siparis_no="SPY").one()


# ---------------------------------------------------------------- takip → kaynak
def test_degisim_statusu_kargoda_sonra_teslim(ctx):
    db.session.add(Degisim(degisim_no="d1", siparis_no="S1", degisim_durumu="İşleme Alındı",
                           kargo_kodu="5550000001", urunler_json="[]"))
    db.session.commit()
    k = _ac_ve_barkodla("degisim", "d1", "5550000001", "DG5550000001")

    ctx.durumlar[k.referans] = _durum(1)
    _yenile(k); servis.takip_isi()
    assert Degisim.query.filter_by(degisim_no="d1").one().degisim_durumu == "İşleme Alındı"   # hazırlandı ≠ yolda

    ctx.durumlar[k.referans] = _durum(2, metin="Transfer_Asamasinda")
    _yenile(k); servis.takip_isi()
    assert Degisim.query.filter_by(degisim_no="d1").one().degisim_durumu == "Kargoya Verildi"
    k = KargoGonderi.query.get(k.id)
    assert k.durum == "kargoda" and k.kargoda_at is not None and k.kaynak_durum == "Kargoya Verildi"

    ctx.durumlar[k.referans] = _durum(5, alan="AYSE YILMAZ")
    _yenile(k); servis.takip_isi()
    assert Degisim.query.filter_by(degisim_no="d1").one().degisim_durumu == "Teslim Edildi"
    k = KargoGonderi.query.get(k.id)
    assert k.durum == "teslim" and k.teslim_alan == "AYSE YILMAZ" and k.teslim_zamani is not None
    assert servis.acik_gonderiler() == []        # kapanmış, bir daha sorulmaz


def test_manuel_kapida_odeme_teslimde_tahsil(ctx):
    db.session.add(YeniSiparis(siparis_no="SP9", musteri_adi="A", durum="Hazırlanıyor", kapida_odeme=True))
    db.session.commit()
    k = _ac_ve_barkodla("manuel", "SP9", "SP9", "MN9", kapida_odeme_tutari=500)
    assert ctx.barkodlar[-1].kapida_odeme_tutari == 500
    ctx.durumlar[k.referans] = _durum(4)
    _yenile(k); servis.takip_isi()
    assert YeniSiparis.query.filter_by(siparis_no="SP9").one().durum == "Kargoda"
    assert not KargoGonderi.query.get(k.id).tahsil_edildi

    ctx.durumlar[k.referans] = _durum(5)
    _yenile(k); servis.takip_isi()
    assert YeniSiparis.query.filter_by(siparis_no="SP9").one().durum == "Teslim Edildi"
    assert KargoGonderi.query.get(k.id).tahsil_edildi


def test_kaynak_statusu_geri_alinmaz(ctx):
    db.session.add(YeniSiparis(siparis_no="SP10", musteri_adi="A", durum="Teslim Edildi"))
    db.session.commit()
    k = _ac_ve_barkodla("manuel", "SP10", "SP10", "MN10")
    ctx.durumlar[k.referans] = _durum(2)
    _yenile(k); servis.takip_isi()
    assert YeniSiparis.query.filter_by(siparis_no="SP10").one().durum == "Teslim Edildi"


def test_bilinmeyen_kaynak_statusu_ezilmez(ctx):
    db.session.add(YeniSiparis(siparis_no="SP21", musteri_adi="A", durum="İade"))
    db.session.commit()
    k = _ac_ve_barkodla("manuel", "SP21", "SP21", "MN21")
    ctx.durumlar[k.referans] = _durum(2)
    _yenile(k); servis.takip_isi()
    assert YeniSiparis.query.filter_by(siparis_no="SP21").one().durum == "İade"
    assert KargoGonderi.query.get(k.id).kaynak_durum == "Kargoda"     # bir daha denenmez


def test_gonderi_kaydi_geri_gitmez_ve_hata_temizlenir(ctx):
    k = _ac_ve_barkodla("manuel", "SP22", "SP22", "MN22")
    k.hata = "sorgu: eski hata"; db.session.commit()
    ctx.durumlar[k.referans] = _durum(3)
    _yenile(k); servis.takip_isi()
    k = KargoGonderi.query.get(k.id)
    assert k.durum == "kargoda" and k.hata is None
    ctx.durumlar[k.referans] = _durum(1)
    _yenile(k); servis.takip_isi()
    assert KargoGonderi.query.get(k.id).durum == "kargoda"


def test_sorgu_araligi_icinde_tekrar_sorulmaz(ctx):
    k = _ac_ve_barkodla("manuel", "SP11", "SP11", "MN11")
    ctx.durumlar[k.referans] = _durum(2)
    _yenile(k)
    assert servis.takip_isi()["sorgulandi"] == 1
    assert servis.takip_isi()["sorgulandi"] == 0


# ---------------------------------------------------------------- iptal
def test_silmede_barkodlu_gonderi_cancelshipment_ve_cancelorder(ctx):
    k = _ac_ve_barkodla("degisim", "d2", "5550000002", "DG5550000002")
    assert servis.gonderi_iptal("degisim", "d2")
    assert ctx.iptal_gonderiler == [("DG5550000002", "195991365254")] and ctx.iptaller == ["DG5550000002"]
    assert KargoGonderi.query.get(k.id).durum == "iptal" and servis.gonderi_bul("degisim", "d2") is None


def test_silmede_barkodsuz_siparis_yalniz_cancelorder(ctx):
    servis.gonderi_ac("manuel", "SP12", "SP12", "MN12", _alici())
    assert servis.gonderi_iptal("manuel", "SP12")
    assert ctx.iptal_gonderiler == [] and ctx.iptaller == ["MN12"]


def test_bekleyen_kayit_iptalinde_api_cagrilmaz(ctx):
    ctx.hata = MngHata("x")
    servis.gonderi_ac("manuel", "SP13", "SP13", "MN13", _alici())
    assert servis.gonderi_iptal("manuel", "SP13")
    assert ctx.iptaller == [] and ctx.iptal_gonderiler == []


def test_teslim_edilmis_iptal_edilmez(ctx):
    k = _ac_ve_barkodla("manuel", "SP14", "SP14", "MN14")
    k.durum = "teslim"; db.session.commit()
    assert not servis.gonderi_iptal("manuel", "SP14")


def test_iptal_edilen_kaynaga_ikinci_gonderi_acilmaz(ctx):
    servis.gonderi_ac("manuel", "SP20", "SP20", "MN20", _alici())
    assert servis.gonderi_iptal("manuel", "SP20")
    assert servis.gonderi_ac("manuel", "SP20", "SP20", "MN20", _alici()) is None
    assert KargoGonderi.query.filter_by(kaynak_ref="SP20").count() == 1


# ---------------------------------------------------------------- Shopify
def _shopify_yama(monkeypatch, sahte):
    """shopify_site paketi login_logout/qrcode zincirini çeker (yerelde yok) → modülü sahteyle değiştir."""
    paket = types.ModuleType("shopify_site")
    modul = types.ModuleType("shopify_site.shopify_service")
    modul.shopify_service = sahte
    paket.shopify_service = modul
    monkeypatch.setitem(sys.modules, "shopify_site", paket)
    monkeypatch.setitem(sys.modules, "shopify_site.shopify_service", modul)


class SahteShopify:
    def __init__(self, basarili=True):
        self.basarili = basarili
        self.fulfillments = []
        self.etiketler = []

    def create_fulfillment(self, **kw):
        self.fulfillments.append(kw)
        return {"success": self.basarili, "error": None if self.basarili else "api"}

    def update_order_status(self, order_id, new_status):
        self.etiketler.append(new_status)
        return {"success": self.basarili}


def test_shopify_fulfillment_bir_kez_ve_hatada_yeniden_denenir(ctx, monkeypatch):
    sahte = SahteShopify(basarili=False)
    _shopify_yama(monkeypatch, sahte)
    k = _ac_ve_barkodla("shopify", "77001", "#1428", "SH1428")
    ctx.durumlar[k.referans] = _durum(2)
    _yenile(k); servis.takip_isi()                       # Shopify hata → kaynak_durum boş kalır
    assert KargoGonderi.query.get(k.id).kaynak_durum is None

    sahte.basarili = True
    _yenile(k); servis.takip_isi()                       # aynı durum, yeniden dener → başarı
    k = KargoGonderi.query.get(k.id)
    assert k.kaynak_durum == "Kargoda"
    assert len(sahte.fulfillments) == 2 and sahte.fulfillments[-1]["tracking_number"] == "195991365254"
    assert sahte.fulfillments[-1]["tracking_url"].endswith("takipNo=195991365254")
    assert sahte.etiketler[-1] == "Kargoda"

    ctx.durumlar[k.referans] = _durum(4)                 # dağıtımda: yine 'Kargoda' hedefi → hiçbir çağrı yok
    _yenile(k); servis.takip_isi()
    assert len(sahte.fulfillments) == 2 and sahte.etiketler.count("Kargoda") == 1

    ctx.durumlar[k.referans] = _durum(5)                 # teslim: yalnız etiket, fulfillment tekrar yok
    _yenile(k); servis.takip_isi()
    assert len(sahte.fulfillments) == 2 and sahte.etiketler[-1] == "Teslim Edildi"
    assert KargoGonderi.query.get(k.id).kaynak_durum == "Teslim Edildi"


def test_shopify_ilk_gorulen_teslimse_fulfillment_yine_acilir(ctx, monkeypatch):
    sahte = SahteShopify()
    _shopify_yama(monkeypatch, sahte)
    k = _ac_ve_barkodla("shopify", "77002", "#1429", "SH1429")
    ctx.durumlar[k.referans] = _durum(5)
    _yenile(k); servis.takip_isi()
    assert len(sahte.fulfillments) == 1 and sahte.etiketler == ["Teslim Edildi"]


# ---------------------------------------------------------------- referans
def test_referanslar():
    assert servis.degisim_referansi("5551234567") == "DG5551234567"
    assert servis.manuel_referansi(42) == "MN42"
    assert servis.shopify_referansi("#1428") == "SH1428"
    with pytest.raises(ValueError):
        servis.shopify_referansi("abc")


# ---------------------------------------------------------------- Shopify kapıda ödeme tespiti
def test_shopify_kapida_odeme_yalniz_odenmemis_cod():
    from mng_kargo.shopify_tarama import kapida_odeme_mi, kapida_odeme_tutari
    cod = {"paymentGatewayNames": ["Cash on Delivery (COD)"], "displayFinancialStatus": "PENDING",
           "currentTotalPriceSet": {"shopMoney": {"amount": "1249.90"}}}
    assert kapida_odeme_mi(cod) and kapida_odeme_tutari(cod) == 1249.9
    assert not kapida_odeme_mi({"paymentGatewayNames": ["Cash on Delivery (COD)", "manual"], "displayFinancialStatus": "PAID"})
    assert not kapida_odeme_mi({"paymentGatewayNames": ["iyzico sandbox"], "displayFinancialStatus": "PAID"})
    assert not kapida_odeme_mi({"paymentGatewayNames": ["manual"], "displayFinancialStatus": "PENDING"})
    assert not kapida_odeme_mi({"paymentGatewayNames": ["Money Order"], "displayFinancialStatus": "PENDING"})


# ---------------------------------------------------------------- desi = 2 × çift
def test_desi_cift_sayisina_gore(ctx):
    k = _ac_ve_barkodla("manuel", "SP30", "SP30", "MN30", adet=3)
    assert k.parca_adet == 3
    parca = ctx.siparisler[-1].parcalar[0]
    assert (parca.desi, parca.kg) == (6, 3)
    assert ctx.barkodlar[-1].parcalar[0].desi == 6
    k1 = servis.gonderi_ac("manuel", "SP31", "SP31", "MN31", _alici())
    assert k1.parca_adet == 1 and ctx.siparisler[-1].parcalar[0].desi == 2


def test_shopify_urun_adedi():
    from mng_kargo.shopify_tarama import urun_adedi
    assert urun_adedi({"line_items": [{"quantity": 2, "currentQuantity": 2}, {"quantity": 1, "currentQuantity": 0}]}) == 2
    assert urun_adedi({"lineItems": {"edges": [{"node": {"quantity": 3}}]}}) == 3
    assert urun_adedi({"line_items": []}) == 1


# ---------------------------------------------------------------- Shopify iptal taraması
class SahteShopifyIptal:
    def __init__(self, iptal_idler):
        self.iptal_idler = iptal_idler

    def get_orders(self, limit=20, query_filter=None, **kw):
        assert "status:cancelled" in query_filter
        return {"success": True, "orders": [{"legacyResourceId": i} for i in self.iptal_idler]}


def test_shopify_yonetiminden_iptal_mng_gonderisini_iptal_eder(ctx, monkeypatch):
    from mng_kargo.shopify_tarama import iptalleri_tara
    _shopify_yama(monkeypatch, SahteShopifyIptal(["77010", "77012"]))
    k1 = _ac_ve_barkodla("shopify", "77010", "#1510", "SH1510")        # barkodlu, kurye almadı → iptal
    k2 = servis.gonderi_ac("shopify", "77011", "#1511", "SH1511", _alici())   # iptal değil → kalır
    k3 = _ac_ve_barkodla("shopify", "77012", "#1512", "SH1512")
    k3.durum = "kargoda"; db.session.commit()                            # kurye aldı → iptal edilmez (taramaya girmez)
    assert iptalleri_tara() == 1
    assert KargoGonderi.query.get(k1.id).durum == "iptal" and ctx.iptal_gonderiler == [("SH1510", "195991365254")]
    assert KargoGonderi.query.get(k2.id).durum == "siparis_acildi"
    assert KargoGonderi.query.get(k3.id).durum == "kargoda"


def test_shopify_gonderi_bul_iki_ad_bicimi_ve_etiket_hazirligi(ctx):
    """/order-label: site siparişi 'SH-<id>' ya da '#1446' adıyla gelir; MNG gönderisi varsa MNG etiketi."""
    k = servis.gonderi_ac("shopify", "77020", "#1520", "SH1520", _alici())      # sipariş açık, barkod yok
    assert servis.shopify_gonderi_bul("SH-77020").id == k.id
    assert servis.shopify_gonderi_bul("#1520").id == k.id
    assert servis.shopify_gonderi_bul("1520") is None                           # Trendyol/manuel numarası sayılır
    assert servis.shopify_gonderi_bul("") is None
    assert servis.etiketi_var(k)                                                # sipariş açık → etiket sayfası barkodu alır
    k.durum = "bekliyor"; db.session.commit()
    assert not servis.etiketi_var(k)                                            # MNG'de açılmadı → klasik etiket
    k2 = _ac_ve_barkodla("shopify", "77021", "#1521", "SH1521")
    assert servis.etiketi_var(servis.shopify_gonderi_bul("#1521")) and k2.zpl
    assert servis.kayit_iptal(k2)
    assert servis.shopify_gonderi_bul("#1521") is None                          # iptal edilen gönderi etiket vermez
