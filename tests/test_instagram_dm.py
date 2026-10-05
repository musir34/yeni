"""Instagram DM entegrasyonu — izole sqlite testi (gerçek uygulama/Instagram yok).

Çalıştırma (çıplak pytest YASAK — conftest canlı uygulamayı yükler):
  DISABLE_JOBS=1 .venv/bin/python -m pytest --noconftest tests/test_instagram_dm.py
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_tmp_db = tempfile.NamedTemporaryFile(suffix="_instagram_dm_test.db", delete=False)
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
os.environ["DISABLE_JOBS"] = "1"

from flask import Flask  # noqa: E402

from models import db, InstagramConversation, InstagramMessage, PlatformConfig  # noqa: E402
from trendyol_qna import instagram_dm  # noqa: E402

SECRET = "test-app-secret"
VERIFY = "test-verify-token"
BIZ = "17841400000000000"
MUSTERI = "5834920000000000"

app = Flask(__name__)
app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI=os.environ["DATABASE_URL"],
                  SQLALCHEMY_TRACK_MODIFICATIONS=False)
db.init_app(app)
app.register_blueprint(instagram_dm.instagram_bp)

with app.app_context():
    for _m in (InstagramConversation, InstagramMessage, PlatformConfig):
        _m.__table__.create(bind=db.engine, checkfirst=True)


@pytest.fixture(autouse=True)
def _temiz(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", SECRET)
    monkeypatch.setenv("INSTAGRAM_VERIFY_TOKEN", VERIFY)
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "tohum-token")
    monkeypatch.delenv("INSTAGRAM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("INSTAGRAM_API_VERSION", raising=False)
    # Arka plan işleri (profil/bildirim/AI) gerçek uygulamayı yükler — testte kapalı
    cagrilar = []
    monkeypatch.setattr(instagram_dm, "sonrasi_async", lambda ids: cagrilar.append(list(ids)))
    with app.app_context():
        for m in (InstagramMessage, InstagramConversation, PlatformConfig):
            db.session.query(m).delete()
        db.session.commit()
        yield cagrilar
        db.session.rollback()


def _imzali(payload: dict, secret: str = SECRET):
    govde = json.dumps(payload).encode("utf-8")
    imza = "sha256=" + hmac.new(secret.encode(), govde, hashlib.sha256).hexdigest()
    return govde, {"X-Hub-Signature-256": imza, "Content-Type": "application/json"}


def _olay(mid: str, text: str = "Mavi olan stokta var mı?", dk_once: int = 5, **mesaj_ek):
    zaman = datetime.now(timezone.utc) - timedelta(minutes=dk_once)
    mesaj = {"mid": mid, "text": text, **mesaj_ek}
    gonderen, alici = (BIZ, MUSTERI) if mesaj.get("is_echo") else (MUSTERI, BIZ)
    return {"object": "instagram", "entry": [{"id": BIZ, "time": int(zaman.timestamp()), "messaging": [{
        "sender": {"id": gonderen}, "recipient": {"id": alici},
        "timestamp": int(zaman.timestamp() * 1000), "message": mesaj}]}]}


def _gonder(payload, secret: str = SECRET):
    govde, basliklar = _imzali(payload, secret)
    return app.test_client().post("/api/instagram/webhook", data=govde, headers=basliklar)


# ── Doğrulama el sıkışması ───────────────────────────────────────────────────

def test_dogrulama_dogru_anahtarla_challenge_doner():
    r = app.test_client().get("/api/instagram/webhook", query_string={
        "hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1158201444"})
    assert r.status_code == 200
    assert r.get_data(as_text=True) == "1158201444"


def test_dogrulama_yanlis_anahtari_reddeder(monkeypatch):
    istemci = app.test_client()
    r = istemci.get("/api/instagram/webhook", query_string={
        "hub.mode": "subscribe", "hub.verify_token": "yanlis", "hub.challenge": "1"})
    assert r.status_code == 403
    # Anahtar hiç tanımlı değilse boş anahtarla da geçilemez
    monkeypatch.delenv("INSTAGRAM_VERIFY_TOKEN")
    r = istemci.get("/api/instagram/webhook", query_string={
        "hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"})
    assert r.status_code == 403


# ── İmza ─────────────────────────────────────────────────────────────────────

def test_imzasiz_ve_yanlis_imzali_bildirim_kaydedilmez(monkeypatch):
    istemci = app.test_client()
    govde = json.dumps(_olay("mid-1")).encode()
    assert istemci.post("/api/instagram/webhook", data=govde,
                        headers={"Content-Type": "application/json"}).status_code == 403
    assert _gonder(_olay("mid-1"), secret="baska-sir").status_code == 403
    # Uygulama sırrı tanımlı değilse hiçbir bildirim kabul edilmez
    monkeypatch.delenv("INSTAGRAM_APP_SECRET")
    assert _gonder(_olay("mid-1"), secret="").status_code == 403
    assert InstagramMessage.query.count() == 0


# ── Mesaj kaydı ──────────────────────────────────────────────────────────────

def test_gelen_mesaj_konusma_acar_ve_bekleyene_duser(_temiz):
    assert _gonder(_olay("mid-1")).status_code == 200
    conv = InstagramConversation.query.one()
    mesaj = InstagramMessage.query.one()
    assert conv.igsid == MUSTERI and conv.status == "new"
    assert mesaj.direction == "in" and mesaj.text == "Mavi olan stokta var mı?"
    assert instagram_dm.pencere_acik(conv)
    assert instagram_dm.new_count() == 1
    assert _temiz == [[conv.id]]


def test_ayni_mesaj_tekrar_gelirse_tek_kayit_kalir():
    _gonder(_olay("mid-1"))
    assert _gonder(_olay("mid-1")).status_code == 200
    assert InstagramMessage.query.count() == 1
    assert InstagramConversation.query.count() == 1


def test_echo_konusmayi_cevaplandi_yapar():
    _gonder(_olay("mid-1", dk_once=10))
    _gonder(_olay("mid-2", text="Evet, 38 numara mevcut.", dk_once=2, is_echo=True))
    conv = InstagramConversation.query.one()
    assert conv.status == "answered"
    assert conv.answered_by == "Instagram uygulaması"
    giden = InstagramMessage.query.filter_by(mid="mid-2").one()
    assert giden.direction == "out"
    assert instagram_dm.new_count() == 0


def test_cevaptan_sonra_yeni_mesaj_tekrar_bekleyene_dondurur():
    _gonder(_olay("mid-1", dk_once=30))
    _gonder(_olay("mid-2", text="Mevcut.", dk_once=20, is_echo=True))
    _gonder(_olay("mid-3", text="Kargo ne zaman çıkar?", dk_once=1))
    conv = InstagramConversation.query.one()
    assert conv.status == "new"
    assert InstagramMessage.query.count() == 3


def test_gec_gelen_eski_mesaj_durumu_bozmaz():
    _gonder(_olay("mid-2", text="Mevcut.", dk_once=5, is_echo=True))
    _gonder(_olay("mid-1", dk_once=30))   # sırası bozuk teslim: eski müşteri mesajı
    conv = InstagramConversation.query.one()
    assert conv.status == "answered"
    assert InstagramMessage.query.count() == 2


def test_okundu_tepki_ve_silinen_mesaj_kaydedilmez():
    olay = _olay("mid-1")
    olay["entry"][0]["messaging"][0].pop("message")
    olay["entry"][0]["messaging"][0]["read"] = {"mid": "mid-0"}
    assert _gonder(olay).status_code == 200
    assert _gonder(_olay("mid-2", is_deleted=True)).status_code == 200
    assert InstagramMessage.query.count() == 0


def test_ekli_mesajda_yalniz_https_baglanti_saklanir():
    _gonder(_olay("mid-1", text="", attachments=[
        {"type": "image", "payload": {"url": "https://lookaside.fbsbx.com/x.jpg"}}]))
    _gonder(_olay("mid-2", text="", dk_once=1, attachments=[
        {"type": "image", "payload": {"url": "javascript:alert(1)"}}]))
    ilk = InstagramMessage.query.filter_by(mid="mid-1").one()
    ikinci = InstagramMessage.query.filter_by(mid="mid-2").one()
    assert ilk.attachment_type == "image" and ilk.attachment_url.startswith("https://")
    assert ikinci.attachment_url == ""


def test_changes_bicimindeki_bildirim_de_islenir():
    olay = _olay("mid-1")
    deger = olay["entry"][0].pop("messaging")[0]
    olay["entry"][0]["changes"] = [{"field": "messages", "value": deger}]
    assert _gonder(olay).status_code == 200
    assert InstagramMessage.query.count() == 1


# ── Cevaplama ────────────────────────────────────────────────────────────────

def test_cevap_instagrama_gider_ve_kaydedilir(monkeypatch):
    _gonder(_olay("mid-1"))
    conv = InstagramConversation.query.one()
    cagri = {}

    def sahte_api(method, path, **kw):
        cagri.update(method=method, path=path, govde=kw.get("json_body"))
        return {"recipient_id": MUSTERI, "message_id": "mid-cevap"}

    monkeypatch.setattr(instagram_dm, "_api", sahte_api)
    sonuc = instagram_dm.answer_conversation(conv.id, "  Evet, mevcut.  ", username="ayse")
    assert sonuc == {"ok": True, "hata": None}
    assert cagri == {"method": "POST", "path": "me/messages",
                     "govde": {"recipient": {"id": MUSTERI}, "message": {"text": "Evet, mevcut."}}}
    db.session.refresh(conv)
    assert conv.status == "answered" and conv.answered_by == "ayse"
    assert InstagramMessage.query.filter_by(mid="mid-cevap").one().sent_by == "ayse"
    # Aynı cevabın echo bildirimi ikinci kayıt açmaz
    _gonder(_olay("mid-cevap", text="Evet, mevcut.", dk_once=0, is_echo=True))
    assert InstagramMessage.query.count() == 2


def test_24_saat_gecince_instagram_cagrilmadan_reddedilir(monkeypatch):
    _gonder(_olay("mid-1", dk_once=25 * 60))
    conv = InstagramConversation.query.one()
    monkeypatch.setattr(instagram_dm, "_api",
                        lambda *a, **k: pytest.fail("pencere kapalıyken Instagram çağrılmamalı"))
    sonuc = instagram_dm.answer_conversation(conv.id, "Merhaba", username="ayse")
    assert sonuc["ok"] is False and "24 saat" in sonuc["hata"]
    assert conv.status == "new"


def test_bos_ve_cok_uzun_cevap_reddedilir(monkeypatch):
    _gonder(_olay("mid-1"))
    conv = InstagramConversation.query.one()
    monkeypatch.setattr(instagram_dm, "_api", lambda *a, **k: pytest.fail("çağrılmamalı"))
    assert instagram_dm.answer_conversation(conv.id, "   ")["ok"] is False
    assert instagram_dm.answer_conversation(conv.id, "a" * (instagram_dm.TEXT_MAX + 1))["ok"] is False
    assert instagram_dm.answer_conversation(999999, "Merhaba")["ok"] is False


def test_instagram_reddederse_konusma_bekleyende_kalir(monkeypatch):
    _gonder(_olay("mid-1"))
    conv = InstagramConversation.query.one()

    def reddet(*a, **k):
        raise instagram_dm.InstagramHatasi("pencere dışı", code=10,
                                           subcode=instagram_dm.PENCERE_DISI_ALT_KOD)

    monkeypatch.setattr(instagram_dm, "_api", reddet)
    sonuc = instagram_dm.answer_conversation(conv.id, "Merhaba")
    assert sonuc["ok"] is False and "24 saat" in sonuc["hata"]
    assert conv.status == "new"
    assert InstagramMessage.query.count() == 1


# ── Erişim anahtarı ──────────────────────────────────────────────────────────

class _Yanit:
    def __init__(self, status_code, veri):
        self.status_code, self._veri = status_code, veri

    def json(self):
        return self._veri


def test_anahtar_yenilenince_db_deki_kullanilir_env_degisince_env(monkeypatch):
    assert instagram_dm.access_token() == "tohum-token"
    monkeypatch.setattr(instagram_dm.requests, "get", lambda *a, **k: _Yanit(
        200, {"access_token": "yeni-token", "expires_in": 60 * 86400}))
    assert instagram_dm.refresh_token_if_needed() is True
    assert instagram_dm.access_token() == "yeni-token"
    # Süresine 60 gün var: tekrar yenilemeye gitmez
    monkeypatch.setattr(instagram_dm.requests, "get",
                        lambda *a, **k: pytest.fail("erken yenileme yapılmamalı"))
    assert instagram_dm.refresh_token_if_needed() is False
    # .env'e yeni anahtar yazılırsa DB'deki eski anahtar bırakılır
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "elle-yazilan-yeni")
    assert instagram_dm.access_token() == "elle-yazilan-yeni"


def test_anahtar_yenileme_hatasi_mevcut_anahtari_bozmaz(monkeypatch):
    monkeypatch.setattr(instagram_dm.requests, "get", lambda *a, **k: _Yanit(
        400, {"error": {"message": "token too young"}}))
    assert instagram_dm.refresh_token_if_needed() is False
    assert instagram_dm.access_token() == "tohum-token"


# ── Yoklama ──────────────────────────────────────────────────────────────────

def test_yoklama_mesajlari_yonuyle_kaydeder_ve_tekrar_yazmaz(monkeypatch, _temiz):
    simdi = datetime.now(timezone.utc)

    def zs(dk):
        return (simdi - timedelta(minutes=dk)).strftime("%Y-%m-%dT%H:%M:%S+0000")

    def sahte_api(method, path, **kw):
        if path == "me":
            return {"id": "app-scoped-1", "user_id": BIZ, "username": "gullushoes"}
        if path == "me/conversations":
            return {"data": [
                {"id": "konusma-1", "updated_time": zs(1)},
                {"id": "konusma-eski", "updated_time": zs(5 * 24 * 60)},
            ]}
        if path == "konusma-1":
            return {"messages": {"data": [   # API yeniden eskiye verir
                {"id": "m3", "created_time": zs(1), "message": "Peki 39 var mı?",
                 "from": {"id": MUSTERI, "username": "ayse.y"}, "to": {"data": [{"id": BIZ}]}},
                {"id": "m2", "created_time": zs(8), "message": "38 kalmadı.",
                 "from": {"id": BIZ, "username": "gullushoes"},
                 "to": {"data": [{"id": MUSTERI, "username": "ayse.y"}]}},
                {"id": "m1", "created_time": zs(15), "message": "38 var mı?",
                 "from": {"id": MUSTERI, "username": "ayse.y"}, "to": {"data": [{"id": BIZ}]}},
            ]}}
        pytest.fail(f"beklenmeyen çağrı: {path}")

    monkeypatch.setattr(instagram_dm, "_api", sahte_api)
    monkeypatch.setattr(instagram_dm, "_ben", None)
    instagram_dm._gorulen.clear()

    assert instagram_dm.sync_conversations() == 3
    conv = InstagramConversation.query.one()
    assert conv.igsid == MUSTERI and conv.username == "ayse.y" and conv.status == "new"
    yonler = [m.direction for m in InstagramMessage.query.order_by(InstagramMessage.created_at)]
    assert yonler == ["in", "out", "in"]
    assert _temiz == [[conv.id]]
    # Değişmeyen konuşma ikinci turda ne ayrıntı ister ne kayıt açar
    assert instagram_dm.sync_conversations() == 0
    assert InstagramMessage.query.count() == 3




# ── Panel kartı ──────────────────────────────────────────────────────────────

def test_kart_sozlugu_konusmayi_eskiden_yeniye_verir():
    from trendyol_qna.qna_routes import _instagram_mesajlari, _instagram_to_dict

    _gonder(_olay("mid-1", text="38 var mı?", dk_once=30))
    _gonder(_olay("mid-2", text="Kalmadı.", dk_once=20, is_echo=True))
    _gonder(_olay("mid-3", text="39 olur mu?", dk_once=1))
    conv = InstagramConversation.query.one()
    kart = _instagram_to_dict(conv, _instagram_mesajlari([conv.id])[conv.id])
    assert kart["source"] == "instagram" and kart["status"] == "WAITING_FOR_ANSWER"
    assert [m["text"] for m in kart["mesajlar"]] == ["38 var mı?", "Kalmadı.", "39 olur mu?"]
    assert [m["yon"] for m in kart["mesajlar"]] == ["in", "out", "in"]
    assert kart["text"] == "39 olur mu?" and kart["answer_text"] == "Kalmadı."
    assert kart["pencere_acik"] is True and kart["pencere_bitis"]
    assert kart["metin_azami"] == instagram_dm.TEXT_MAX


def test_gercek_uygulama_yuklenmedi():
    assert "app" not in sys.modules


# ── Gönderi yorumları ────────────────────────────────────────────────────────

from models import InstagramComment  # noqa: E402

with app.app_context():
    InstagramComment.__table__.create(bind=db.engine, checkfirst=True)


@pytest.fixture
def yorum_api(monkeypatch):
    """Sahte Instagram: bir gönderi + yorumları. Dönen sözlük çağrıları ve veriyi taşır."""
    simdi = datetime.now(timezone.utc)

    def zs(saat):
        return (simdi - timedelta(hours=saat)).strftime("%Y-%m-%dT%H:%M:%S+0000")

    durum = {"cagrilar": [], "sayi": 4, "yorumlar": [
        {"id": "c1", "text": "38 numara var mı?", "username": "ayse.y", "timestamp": zs(2),
         "from": {"id": "111", "username": "ayse.y"}},
        {"id": "c2", "text": "Fiyat?", "username": "zeynep", "timestamp": zs(5),
         "from": {"id": "222", "username": "zeynep"},
         "replies": {"data": [{"id": "r1", "username": "gullushoes", "from": {"id": BIZ}}]}},
        {"id": "c3", "text": "Yeni sezon 🌹", "username": "gullushoes", "timestamp": zs(6),
         "from": {"id": BIZ, "username": "gullushoes"}},
        {"id": "c4", "text": "Çok eski yorum", "username": "eski", "timestamp": zs(10 * 24),
         "from": {"id": "333", "username": "eski"}},
    ]}

    def sahte_api(method, path, **kw):
        durum["cagrilar"].append((method, path, kw.get("json_body") or kw.get("params")))
        if path == "me":
            return {"id": "app-scoped-1", "user_id": BIZ, "username": "gullushoes"}
        if path == "me/media":
            return {"data": [
                {"id": "g1", "caption": "Topuklu sandalet 0121", "permalink": "https://www.instagram.com/p/abc/",
                 "media_type": "IMAGE", "media_url": "https://cdn.example.com/g1.jpg",
                 "comments_count": durum["sayi"]},
                {"id": "g2", "caption": "Yorumsuz", "media_type": "IMAGE", "comments_count": 0},
            ]}
        if path == "g1/comments":
            return {"data": durum["yorumlar"]}
        if method == "POST" and path == "me/messages":
            if durum.get("dm_hata"):
                raise instagram_dm.InstagramHatasi("özel yanıt reddedildi")
            return {"recipient_id": MUSTERI, "message_id": "mid-ozel"}
        if method == "POST" and path.endswith("/replies"):
            if durum.get("not_hata"):
                raise instagram_dm.InstagramHatasi("yorum kapalı")
            return {"id": "r-yeni"}
        pytest.fail(f"beklenmeyen çağrı: {method} {path}")

    monkeypatch.setattr(instagram_dm, "_api", sahte_api)
    monkeypatch.setattr(instagram_dm, "_ben", None)
    instagram_dm._yorum_sayilari.clear()
    db.session.query(InstagramComment).delete()
    db.session.commit()
    return durum


def test_yorum_cekme_yenileri_kaydeder_bizimkileri_ve_eskileri_atlar(yorum_api):
    assert instagram_dm.sync_comments() == 1
    satirlar = {y.comment_id: y for y in InstagramComment.query.all()}
    assert set(satirlar) == {"c1", "c2"}            # kendi yorumumuz ve 3 günden eski yok
    assert satirlar["c1"].status == "new" and satirlar["c1"].username == "ayse.y"
    assert satirlar["c1"].media_caption == "Topuklu sandalet 0121"
    assert satirlar["c1"].media_permalink.startswith("https://www.instagram.com/")
    assert satirlar["c2"].status == "answered"      # altında bizim yanıtımız var
    assert instagram_dm.new_comment_count() == 1
    # Yorum sayısı değişmediyse gönderinin yorumları yeniden istenmez
    onceki = len([c for c in yorum_api["cagrilar"] if c[1] == "g1/comments"])
    assert instagram_dm.sync_comments() == 0
    assert len([c for c in yorum_api["cagrilar"] if c[1] == "g1/comments"]) == onceki


def test_instagramdan_yanitlanan_yorum_kendiliginden_kapanir(yorum_api):
    instagram_dm.sync_comments()
    yorum_api["yorumlar"][0]["replies"] = {"data": [{"id": "r9", "username": "gullushoes"}]}
    yorum_api["sayi"] = 5
    instagram_dm.sync_comments()
    yorum = InstagramComment.query.filter_by(comment_id="c1").one()
    assert yorum.status == "answered" and yorum.answered_by == "Instagram uygulaması"


def test_yorum_cevabi_once_ozelden_sonra_not_olarak_gider(yorum_api):
    instagram_dm.sync_comments()
    yorum = InstagramComment.query.filter_by(comment_id="c1").one()
    yorum_api["cagrilar"].clear()
    sonuc = instagram_dm.answer_comment(yorum.id, "38 numara mevcut.", public_note="Özelden yanıtladık 🌹",
                                        username="ayse")
    assert sonuc == {"ok": True, "hata": None, "uyari": None}
    assert yorum_api["cagrilar"] == [
        ("POST", "me/messages", {"recipient": {"comment_id": "c1"}, "message": {"text": "38 numara mevcut."}}),
        ("POST", "c1/replies", {"message": "Özelden yanıtladık 🌹"}),
    ]
    db.session.refresh(yorum)
    assert yorum.status == "answered" and yorum.answer == "38 numara mevcut."
    assert yorum.public_note == "Özelden yanıtladık 🌹" and yorum.answered_by == "ayse"
    # Giden özel mesaj konuşma geçmişine de yazılır
    mesaj = InstagramMessage.query.filter_by(mid="mid-ozel").one()
    assert mesaj.direction == "out" and mesaj.sent_by == "ayse"
    # İkinci kez cevaplanamaz
    assert instagram_dm.answer_comment(yorum.id, "tekrar")["ok"] is False


def test_ozel_mesaj_gitmezse_yoruma_not_da_yazilmaz(yorum_api):
    instagram_dm.sync_comments()
    yorum = InstagramComment.query.filter_by(comment_id="c1").one()
    yorum_api["dm_hata"] = True
    yorum_api["cagrilar"].clear()
    sonuc = instagram_dm.answer_comment(yorum.id, "Merhaba", public_note="Not")
    assert sonuc["ok"] is False
    assert [c[1] for c in yorum_api["cagrilar"]] == ["me/messages"]
    assert yorum.status == "new"


def test_not_yazilamazsa_cevap_yine_sayilir_ve_uyari_doner(yorum_api):
    instagram_dm.sync_comments()
    yorum = InstagramComment.query.filter_by(comment_id="c1").one()
    yorum_api["not_hata"] = True
    sonuc = instagram_dm.answer_comment(yorum.id, "Merhaba", public_note="Not")
    assert sonuc["ok"] is True and "not yazılamadı" in sonuc["uyari"]
    assert yorum.status == "answered" and yorum.public_note == ""


def test_yedi_gunu_gecen_yoruma_instagram_cagrilmadan_ret(yorum_api):
    db.session.add(InstagramComment(comment_id="eski", media_id="g1", text="?", status="new",
                                    created_at=datetime.now(timezone.utc) - timedelta(days=8)))
    db.session.commit()
    yorum = InstagramComment.query.filter_by(comment_id="eski").one()
    yorum_api["cagrilar"].clear()
    sonuc = instagram_dm.answer_comment(yorum.id, "Merhaba", public_note="Not")
    assert sonuc["ok"] is False and "7 gün" in sonuc["hata"]
    assert yorum_api["cagrilar"] == []


def test_yoksay_instagrama_dokunmadan_listeden_dusurur(yorum_api):
    instagram_dm.sync_comments()
    yorum = InstagramComment.query.filter_by(comment_id="c1").one()
    yorum_api["cagrilar"].clear()
    assert instagram_dm.ignore_comment(yorum.id, username="ayse") == {"ok": True, "hata": None}
    assert yorum.status == "ignored" and yorum_api["cagrilar"] == []
    assert instagram_dm.new_comment_count() == 0


def test_yorum_kart_sozlugu():
    from trendyol_qna.qna_routes import _instagram_yorum_to_dict

    db.session.query(InstagramComment).delete()
    db.session.add(InstagramComment(comment_id="k1", media_id="g1", media_caption="Topuklu sandalet",
                                    username="ayse.y", text="Var mı?", status="new",
                                    created_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    db.session.commit()
    kart = _instagram_yorum_to_dict(InstagramComment.query.one())
    assert kart["source"] == "instagram_yorum" and kart["status"] == "WAITING_FOR_ANSWER"
    assert kart["user_name"] == "@ayse.y" and kart["product_name"] == "Topuklu sandalet"
    assert kart["ozel_yanit_bitis"] and kart["not_varsayilan"] == instagram_dm.YORUM_NOTU_VARSAYILAN


def test_gercek_uygulama_hala_yuklenmedi():
    assert "app" not in sys.modules
