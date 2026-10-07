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
    # Yeni yorum sonrası işler (AI önerisi/taslak) gerçek uygulamayı yükler — testte yalnız kaydedilir
    monkeypatch.setattr(instagram_dm, "_yeni_yorum_sonrasi", lambda ids: durum.setdefault("sonrasi", []).append(ids))
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


# ── Gönderi ↔ ürün bağı ──────────────────────────────────────────────────────

from models import InstagramMediaProduct  # noqa: E402
from trendyol_qna import instagram_urun  # noqa: E402

with app.app_context():
    InstagramMediaProduct.__table__.create(bind=db.engine, checkfirst=True)

URUN_DUGUMU = {
    "legacyResourceId": "8814245511346", "title": "Timsah Desenli Tokalı Loafer", "handle": "03155-loafer",
    "status": "ACTIVE", "onlineStoreUrl": "https://www.gullushoes.com/products/03155-loafer",
    "featuredImage": {"url": "https://cdn.shopify.com/x.jpg"},
    "variants": {"nodes": [
        {"legacyResourceId": "501", "title": "Bej Leopar / 36", "price": "1449.99", "compareAtPrice": "1899.99", "inventoryQuantity": 4, "availableForSale": True},
        {"legacyResourceId": "502", "title": "Bej Leopar / 37", "price": "1449.99", "compareAtPrice": "1899.99", "inventoryQuantity": 0, "availableForSale": False},
        {"legacyResourceId": "601", "title": "Siyah / 35", "price": "1349.61", "compareAtPrice": None, "inventoryQuantity": 0, "availableForSale": False},
        {"legacyResourceId": "602", "title": "Siyah / 36", "price": "1349.61", "compareAtPrice": None, "inventoryQuantity": 2, "availableForSale": True},
    ]},
}


@pytest.fixture
def urun_ortami(monkeypatch):
    """Sahte Shopify + boş bağ tablosu."""
    def sahte_shopify(query, variables):
        if "product(id:" in query:
            return {"product": URUN_DUGUMU if variables["id"].endswith("/8814245511346") else None}
        return {"products": {"nodes": [URUN_DUGUMU], "pageInfo": {"hasNextPage": False}}}

    monkeypatch.setattr(instagram_urun, "_shopify", sahte_shopify)
    monkeypatch.setattr(instagram_urun, "_katalog", (0.0, []))
    for m in (InstagramMediaProduct, InstagramComment):
        db.session.query(m).delete()
    db.session.add(InstagramComment(comment_id="u1", media_id="g1", username="ayse.y", text="Fiyat nedir?",
                                    media_caption="Tokalı loafer dokunuşu, bej leopar", status="new",
                                    created_at=datetime.now(timezone.utc)))
    db.session.commit()


def test_urun_arama_renk_fiyat_ve_stogu_sadelestirir(urun_ortami):
    urun = instagram_urun.urun_ara("loafer")[0]
    assert urun["id"] == "8814245511346" and urun["url"].endswith("/products/03155-loafer")
    renkler = {r["renk"]: r for r in urun["renkler"]}
    assert renkler["Bej Leopar"]["fiyat"] == 1449.99 and renkler["Bej Leopar"]["eski_fiyat"] == 1899.99
    assert [b["stokta"] for b in renkler["Bej Leopar"]["bedenler"]] == [True, False]
    assert renkler["Siyah"]["eski_fiyat"] is None
    assert instagram_urun.urun_ara("x") == []          # tek harfle Shopify'a gidilmez


def test_onaysiz_oneri_taslaga_fiyat_olarak_girmez(urun_ortami):
    assert instagram_urun.bagla("g1", "8814245511346", "Bej Leopar", confirmed=False)["ok"] is True
    assert instagram_urun.urun_baglami("g1") is None
    yorum = InstagramComment.query.filter_by(comment_id="u1").one()
    from trendyol_qna.qna_ai import _instagram_comment_draft_prompt
    prompt = _instagram_comment_draft_prompt(yorum, urun_bilgisi=None)
    assert "ONAYLANMAMIŞ" in prompt and "1.449,99" not in prompt


def test_onayli_bag_canli_fiyat_stok_ve_baglantiyi_verir(urun_ortami):
    assert instagram_urun.bagla("g1", "8814245511346", "Bej Leopar", username="ayse")["ok"] is True
    bilgi = instagram_urun.urun_baglami("g1")
    assert "Timsah Desenli Tokalı Loafer" in bilgi
    assert "https://www.gullushoes.com/products/03155-loafer?variant=501" in bilgi
    assert "YALNIZ bu renk hakkında yaz" in bilgi
    assert "Bej Leopar: 1.449,99 TL (indirimli; eski fiyat 1.899,99 TL)" in bilgi
    assert "stokta olan numaralar: 36" in bilgi and "tükenenler: 37" in bilgi
    assert "Siyah" not in bilgi                         # yalnız bağlanan renk
    yorum = InstagramComment.query.filter_by(comment_id="u1").one()
    from trendyol_qna.qna_ai import _instagram_comment_draft_prompt
    prompt = _instagram_comment_draft_prompt(yorum, urun_bilgisi=bilgi)
    assert "1.449,99 TL" in prompt and "AYNEN" in prompt and "ONAYLANMAMIŞ" not in prompt


def test_baglama_dogrulamalari(urun_ortami):
    assert instagram_urun.bagla("g1", "999", "")["ok"] is False                    # sitede yok
    assert instagram_urun.bagla("g1", "8814245511346", "Mor")["ok"] is False       # üründe olmayan renk
    assert instagram_urun.bagla("g1", "8814245511346", "", username="ayse")["ok"] is True
    assert instagram_urun.bagli_urun("g1").color == ""                             # çok renkli → tüm renkler
    assert "Siyah: 1.349,61 TL" in instagram_urun.urun_baglami("g1")
    # Kullanıcının onayladığı bağ, sonradan gelen AI önerisiyle ezilmez
    instagram_urun.bagla("g1", "8814245511346", "Siyah", confirmed=False)
    bag = instagram_urun.bagli_urun("g1")
    assert bag.confirmed is True and bag.color == ""
    instagram_urun.bagi_kaldir("g1")
    assert instagram_urun.bagli_urun("g1") is None


def test_ai_onerisi_onaysiz_kaydedilir_ve_emin_degilse_kaydedilmez(urun_ortami, monkeypatch):
    from trendyol_qna import qna_ai
    monkeypatch.setattr(qna_ai, "_run_ai", lambda prompt: "URUN: YOK")
    assert instagram_urun.oner("g1") is False and instagram_urun.bagli_urun("g1") is None
    monkeypatch.setattr(qna_ai, "_run_ai", lambda prompt: "URUN: 8814245511346 | RENK: Bej Leopar")
    assert instagram_urun.oner("g1") is True
    bag = instagram_urun.bagli_urun("g1")
    assert bag.confirmed is False and bag.color == "Bej Leopar" and bag.updated_by == "AI önerisi"
    # Listede olmayan ürün numarası uydurulursa kaydedilmez
    instagram_urun.bagi_kaldir("g1")
    monkeypatch.setattr(qna_ai, "_run_ai", lambda prompt: "URUN: 1234567890123 | RENK: ")
    assert instagram_urun.oner("g1") is False


def test_bag_onaylaninca_hazir_taslaklar_yenilenmek_uzere_sifirlanir(urun_ortami, monkeypatch):
    from trendyol_qna import qna_ai
    uretilen = []
    monkeypatch.setattr(qna_ai, "generate_instagram_comment_drafts_async", lambda ids, **k: uretilen.append(list(ids)))
    yorum = InstagramComment.query.filter_by(comment_id="u1").one()
    yorum.ai_draft, yorum.ai_draft_status = "Hangi modeli soruyorsunuz?", "ready"
    db.session.commit()
    instagram_urun.taslaklari_uret_async("g1")          # bağ yok → hiçbir şey
    assert uretilen == []
    instagram_urun.bagla("g1", "8814245511346", "Bej Leopar", username="ayse")
    instagram_urun.taslaklari_uret_async("g1", yenile=True)
    db.session.refresh(yorum)
    assert yorum.ai_draft is None and uretilen == [[yorum.id]]


def test_yorum_karti_urun_bagini_tasir(urun_ortami):
    from trendyol_qna.qna_routes import _instagram_yorum_to_dict
    yorum = InstagramComment.query.filter_by(comment_id="u1").one()
    assert _instagram_yorum_to_dict(yorum)["urun"] is None
    instagram_urun.bagla("g1", "8814245511346", "Bej Leopar", confirmed=False)
    kart = _instagram_yorum_to_dict(yorum, instagram_urun.bagli_urun("g1"))
    assert kart["urun"] == {"title": "Timsah Desenli Tokalı Loafer", "renk": "Bej Leopar", "onayli": False,
                            "url": "https://www.gullushoes.com/products/03155-loafer?variant=501",
                            "product_id": "8814245511346"}


def test_onceden_dusmus_bekleyen_yorumun_gonderisi_de_oneriye_girer(urun_ortami):
    # u1 yorumu g1 gönderisinde bekliyor ve gönderi bağsız → öneri listesinde
    assert instagram_dm._bagsiz_bekleyen_gonderiler() == ["g1"]
    instagram_urun.bagla("g1", "8814245511346", "Bej Leopar", confirmed=False)
    assert instagram_dm._bagsiz_bekleyen_gonderiler() == []     # önerisi/bağı olan tekrar sorulmaz
    instagram_urun.bagi_kaldir("g1")
    InstagramComment.query.filter_by(comment_id="u1").one().status = "answered"
    db.session.commit()
    assert instagram_dm._bagsiz_bekleyen_gonderiler() == []     # bekleyeni kalmayan gönderi de


def test_dm_konusmasina_elle_baglanan_urun_taslak_istemine_girer(urun_ortami):
    from trendyol_qna.qna_ai import _instagram_draft_prompt
    from trendyol_qna.qna_routes import _instagram_mesajlari, _instagram_to_dict

    _gonder(_olay("mid-dm", text="fiyat nedir"))
    conv = InstagramConversation.query.one()
    mesajlar = _instagram_mesajlari([conv.id])[conv.id]
    anahtar = instagram_urun.konusma_anahtari(conv.id)
    assert anahtar == f"conv:{conv.id}"
    # Bağ yokken: fiyat yok, netleştirme istenir; kartta ürün yok
    assert instagram_urun.urun_baglami(anahtar) is None
    assert "netleştirmesini iste" in _instagram_draft_prompt(conv, mesajlar)
    assert _instagram_to_dict(conv, mesajlar)["urun"] is None
    # Kullanıcı ürünü bağlayınca: canlı fiyat + bağlantı isteme girer, kart bağı taşır
    assert instagram_urun.bagla(anahtar, "8814245511346", "Bej Leopar", username="ayse")["ok"] is True
    bilgi = instagram_urun.urun_baglami(anahtar)
    prompt = _instagram_draft_prompt(conv, mesajlar, urun_bilgisi=bilgi)
    assert "1.449,99 TL" in prompt and "/products/03155-loafer?variant=501" in prompt and "AYNEN" in prompt
    kart = _instagram_to_dict(conv, mesajlar, instagram_urun.bagli_urun(anahtar))
    assert kart["urun"]["title"] == "Timsah Desenli Tokalı Loafer" and kart["urun"]["onayli"] is True
    # Konuşma bağı, gönderi önerisi taramasına karışmaz
    assert instagram_dm._bagsiz_bekleyen_gonderiler() == ["g1"]


def test_baglanan_urunun_hazir_metni_fiyat_stok_ve_baglanti_tasir(urun_ortami):
    assert instagram_urun.hazir_metin("g1") == ""                       # bağ yok
    instagram_urun.bagla("g1", "8814245511346", "Bej Leopar", confirmed=False)
    assert instagram_urun.hazir_metin("g1") == ""                       # onaysız öneri metin üretmez
    instagram_urun.bagi_kaldir("g1")
    instagram_urun.bagla("g1", "8814245511346", "Bej Leopar", username="ayse")
    assert instagram_urun.hazir_metin("g1") == (
        "Timsah Desenli Tokalı Loafer (Bej Leopar) fiyatı 1.449,99 TL. Stokta olan numaralar: 36.\n"
        "Detaylar ve sipariş için: https://www.gullushoes.com/products/03155-loafer?variant=501")
    # Tüm renkler bağlıysa renk renk yazılır
    instagram_urun.bagla("g1", "8814245511346", "", username="ayse")
    metin = instagram_urun.hazir_metin("g1")
    assert "- Bej Leopar: 1.449,99 TL. Stokta olan numaralar: 36." in metin
    assert "- Siyah: 1.349,61 TL. Stokta olan numaralar: 36." in metin
    assert "variant=" not in metin                                      # tüm renkler → düz ürün adresi
    assert metin.endswith("Detaylar ve sipariş için: https://www.gullushoes.com/products/03155-loafer")


def test_bagli_urunun_baglantisi_gonderimde_mesaja_eklenir(urun_ortami, monkeypatch):
    url = "https://www.gullushoes.com/products/03155-loafer?variant=501"
    giden = []

    def sahte_api(method, path, **kw):
        giden.append((path, (kw.get("json_body") or {}).get("message", {}).get("text")))
        return {"recipient_id": MUSTERI, "message_id": f"mid-{len(giden)}"}

    monkeypatch.setattr(instagram_dm, "_api", sahte_api)

    # DM: ürün konuşmaya önceden bağlı, kullanıcı yalnız kendi cümlesini yazıyor
    _gonder(_olay("mid-in", text="fiyat nedir"))
    conv = InstagramConversation.query.one()
    assert instagram_dm.answer_conversation(conv.id, "Merhaba, mevcut.")["ok"] is True
    assert giden[-1][1] == "Merhaba, mevcut."                       # bağ yokken metne dokunulmaz
    _gonder(_olay("mid-in2", text="link atar mısınız", dk_once=0))
    instagram_urun.bagla(instagram_urun.konusma_anahtari(conv.id), "8814245511346", "Bej Leopar", username="ayse")
    assert instagram_dm.answer_conversation(conv.id, "Tabii, buyurun.")["ok"] is True
    assert giden[-1][1] == f"Tabii, buyurun.\n\nDetaylar ve sipariş için: {url}"
    # Bağlantı zaten yazılıysa ikinci kez eklenmez
    _gonder(_olay("mid-in3", text="teşekkürler", dk_once=0))
    assert instagram_dm.answer_conversation(conv.id, f"Buradan: {url}")["ok"] is True
    assert giden[-1][1] == f"Buradan: {url}"

    # Yorum: gönderi ürüne bağlı; özelden giden cevaba bağlantı eklenir, yorum notuna eklenmez
    instagram_urun.bagla("g1", "8814245511346", "Bej Leopar", username="ayse")
    yorum = InstagramComment.query.filter_by(comment_id="u1").one()
    giden.clear()
    assert instagram_dm.answer_comment(yorum.id, "Merhaba, 1.449,99 TL.", public_note="Özelden yazdık")["ok"] is True
    assert giden[0] == ("me/messages", f"Merhaba, 1.449,99 TL.\n\nDetaylar ve sipariş için: {url}")
    db.session.refresh(yorum)
    assert yorum.answer.endswith(url) and yorum.public_note == "Özelden yazdık"


def test_onaysiz_oneri_gonderime_baglanti_eklemez(urun_ortami):
    instagram_urun.bagla("g1", "8814245511346", "Bej Leopar", confirmed=False)
    assert instagram_dm.urun_baglantisi_ekle("Merhaba", "g1") == "Merhaba"
    assert instagram_dm.urun_baglantisi_ekle("Merhaba", "bagsiz-gonderi") == "Merhaba"


def test_baglanti_secilen_rengin_stoktaki_varyantina_gider(urun_ortami):
    taban = "https://www.gullushoes.com/products/03155-loafer"
    urun = instagram_urun.urun_getir("8814245511346")
    assert instagram_urun.renk_url(urun, "Bej Leopar") == taban + "?variant=501"
    assert instagram_urun.renk_url(urun, "Siyah") == taban + "?variant=602"    # 35 tükenmiş → stoktaki 36
    assert instagram_urun.renk_url(urun, "") == taban
    assert instagram_urun.renk_url(urun, "Olmayan Renk") == taban
    instagram_urun.bagla("g1", "8814245511346", "Siyah", username="ayse")
    assert instagram_urun.bagli_urun("g1").url == taban + "?variant=602"
    assert instagram_urun.hazir_metin("g1").endswith(taban + "?variant=602")
    bilgi = instagram_urun.urun_baglami("g1")
    assert "Kullanıcının bağladığı renk: Siyah" in bilgi and "Bej Leopar" not in bilgi


def test_eski_renksiz_bag_gonderimde_renk_adresine_tamamlanir(urun_ortami):
    taban = "https://www.gullushoes.com/products/03155-loafer"
    instagram_urun.bagla("g1", "8814245511346", "Siyah", username="ayse")
    bag = instagram_urun.bagli_urun("g1")
    bag.url = taban                      # bu düzeltmeden önce bağlanmış kayıt
    db.session.commit()
    assert instagram_dm.urun_baglantisi_ekle("Merhaba", "g1") == (
        f"Merhaba\n\nDetaylar ve sipariş için: {taban}?variant=602")
    assert instagram_urun.bagli_urun("g1").url == taban + "?variant=602"
    # Aynı ürün sayfası başka bedenle zaten yazılıysa ikinci bağlantı eklenmez
    metin = f"Buyurun: {taban}?variant=601"
    assert instagram_dm.urun_baglantisi_ekle(metin, "g1") == metin


# ── Trendyol: müşterinin önceki soruları ─────────────────────────────────────

from models import TrendyolQuestion  # noqa: E402

with app.app_context():
    TrendyolQuestion.__table__.create(bind=db.engine, checkfirst=True)


@pytest.fixture
def trendyol_sorulari():
    db.session.query(TrendyolQuestion).delete()
    simdi = datetime.now(timezone.utc)

    def soru(qid, musteri, metin, gun_once, model="0121", urun="Topuklu Sandalet", cevap=None, durum=None):
        db.session.add(TrendyolQuestion(
            id=qid, customer_id=musteri, text=metin, user_name="Ayşe Y.", product_name=urun,
            product_main_id=model, status=durum or ("ANSWERED" if cevap else "WAITING_FOR_ANSWER"),
            creation_date=simdi - timedelta(days=gun_once), answer_text=cevap,
            answer_date=(simdi - timedelta(days=gun_once)) if cevap else None,
            answered_by="ayse" if cevap else None))

    soru(1, 77, "38 numara dar mı?", 5, cevap="Tam kalıptır.")
    soru(2, 77, "Bot su geçirir mi?", 3, model="0155", urun="Deri Bot", cevap="Su geçirmez.")
    soru(3, 77, "O zaman 38 alayım, ne zaman kargolanır?", 0)
    soru(4, 88, "Kapıda ödeme var mı?", 1)
    db.session.commit()


def test_trendyol_karti_musterinin_onceki_sorularini_balon_olarak_verir(trendyol_sorulari):
    from trendyol_qna.qna_routes import _to_dict
    from trendyol_qna.qna_service import musteri_gecmisi

    gecmis = musteri_gecmisi([77, 88, None])
    assert [g.id for g in gecmis[77]] == [1, 2, 3] and [g.id for g in gecmis[88]] == [4]
    kart = _to_dict(db.session.get(TrendyolQuestion, 3), gecmis[77])
    assert [(m["yon"], m["text"]) for m in kart["mesajlar"]] == [
        ("in", "38 numara dar mı?"), ("out", "Tam kalıptır."),
        ("in", "Bot su geçirir mi?"), ("out", "Su geçirmez."),
        ("in", "O zaman 38 alayım, ne zaman kargolanır?"),
    ]
    assert [m["simdiki"] for m in kart["mesajlar"]] == [False, False, False, False, True]
    # Başka ürüne sorulan soruda ürün adı görünür; aynı üründe ve şimdiki soruda görünmez
    assert [m["urun"] for m in kart["mesajlar"]] == ["", "", "Deri Bot", "", ""]
    assert kart["mesajlar"][1]["gonderen"] == "ayse"
    # Tek sorusu olan müşteride yazışma yok → kart eskisi gibi tek soruyu gösterir
    assert _to_dict(db.session.get(TrendyolQuestion, 4), gecmis[88])["mesajlar"] == []
    assert _to_dict(db.session.get(TrendyolQuestion, 4))["mesajlar"] == []


def test_trendyol_taslak_istemi_onceki_soru_cevaplari_icerir(trendyol_sorulari):
    from trendyol_qna.qna_ai import _draft_prompt
    from trendyol_qna.qna_service import musteri_gecmisi

    satir = db.session.get(TrendyolQuestion, 3)
    prompt = _draft_prompt(satir, "38: 4 adet", gecmis=musteri_gecmisi([77])[77])
    assert "ÖNCEKİ soruları" in prompt
    assert "Müşteri: 38 numara dar mı?" in prompt and "Biz: Tam kalıptır." in prompt
    assert "Müşteri [başka ürün: Deri Bot]: Bot su geçirir mi?" in prompt
    assert prompt.index("ÖNCEKİ soruları") < prompt.index("Müşteri sorusu:")
    assert prompt.count("O zaman 38 alayım") == 1            # şimdiki soru geçmişte tekrarlanmaz
    # Geçmişi olmayan müşteride istem eskisiyle aynı kalır
    tek = db.session.get(TrendyolQuestion, 4)
    assert "ÖNCEKİ" not in _draft_prompt(tek, "stok", gecmis=musteri_gecmisi([88])[88])
    assert "ÖNCEKİ" not in _draft_prompt(tek, "stok")


# ── Trendyol: model koduna özel hafıza + art arda soru ───────────────────────

@pytest.fixture
def model_sorulari(monkeypatch):
    db.session.query(TrendyolQuestion).delete()
    simdi = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)

    def soru(qid, musteri, ad, metin, gun_once, dk_once=0, model="0121", cevap=None, taslak=None):
        zaman = simdi - timedelta(days=gun_once, minutes=dk_once)
        db.session.add(TrendyolQuestion(
            id=qid, customer_id=musteri, user_name=ad, text=metin, product_name="Topuklu Sandalet",
            product_main_id=model, status="ANSWERED" if cevap else "WAITING_FOR_ANSWER",
            creation_date=zaman, answer_text=cevap, answer_date=zaman if cevap else None,
            ai_draft=taslak, ai_draft_status="ready" if taslak else "none"))

    soru(1, 11, "Ayşe Y.", "37 numara ne zaman gelir?", 14, cevap="Merhaba, 2 hafta sonra stoklarımızda olacak.")
    soru(2, 12, "Zeynep K.", "Kalıbı dar mı?", 3, cevap="Merhaba, tam kalıptır.")
    soru(3, 13, "Elif Ş.", "Bot su geçirir mi?", 2, model="0155", cevap="Su geçirmez.")     # başka model
    soru(4, 20, "Hale Ş.", "38 var mı?", 0, dk_once=5, taslak="Merhaba, 38 numara mevcut.")
    soru(5, 20, "Hale Ş.", "Peki kargo ne zaman çıkar?", 0, dk_once=3)
    soru(6, 20, "Hale Ş.", "Kapıda ödeme var mı?", 0, dk_once=1)
    db.session.commit()
    return simdi


def test_model_hafizasi_yalniz_ayni_modelin_baska_musterilere_verilen_cevaplarini_getirir(model_sorulari):
    from trendyol_qna.qna_service import model_hafizasi

    assert [g.id for g in model_hafizasi("0121", haric_id=6, haric_musteri=20)] == [1, 2]   # eskiden yeniye
    assert [g.id for g in model_hafizasi("0155")] == [3]
    assert model_hafizasi(None) == [] and model_hafizasi("yok-boyle-model") == []
    # Müşterinin kendi cevaplanmış sorusu model hafızasına girmez (müşteri geçmişinde zaten var)
    assert [g.id for g in model_hafizasi("0121", haric_id=99, haric_musteri=11)] == [2]


def test_taslak_istemi_model_hafizasini_tarihiyle_ve_notla_verir(model_sorulari):
    from trendyol_qna.qna_ai import _draft_prompt
    from trendyol_qna.qna_service import model_hafizasi

    satir = db.session.get(TrendyolQuestion, 6)
    prompt = _draft_prompt(satir, "37: stok yok", simdi=model_sorulari,
                           model_cevaplari=model_hafizasi("0121", haric_id=6, haric_musteri=20),
                           model_notu="Yeni parti 20 Ekim'de gelecek.")
    assert "Bugünün tarihi: 06.10.2026" in prompt
    assert "22.09.2026 (14 gün önce) — Ayşe Y. sordu: 37 numara ne zaman gelir?" in prompt
    assert "Biz: Merhaba, 2 hafta sonra stoklarımızda olacak." in prompt
    assert "03.10.2026 (3 gün önce) — Zeynep K. sordu" in prompt
    assert "SÜRELİ ifadeleri" in prompt and "Başka müşterilerin adını cevapta kullanma" in prompt
    assert "MAĞAZA NOTU" in prompt and "Yeni parti 20 Ekim'de gelecek." in prompt
    assert prompt.index("MAĞAZA NOTU") < prompt.index("BU MODELE daha önce")     # not önce gelir
    assert "Bot su geçirir mi?" not in prompt                                    # başka modelin cevabı yok
    # Hafıza ve not yoksa istem bu bölümleri hiç içermez
    yalin = _draft_prompt(satir, "stok", simdi=model_sorulari)
    assert "MAĞAZA NOTU" not in yalin and "BU MODELE daha önce" not in yalin


def test_art_arda_soruda_ikinci_cevap_selamla_baslamaz(model_sorulari):
    from trendyol_qna.qna_ai import _draft_prompt
    from trendyol_qna.qna_service import musteri_gecmisi

    gecmis = musteri_gecmisi([20])[20]
    ilk = _draft_prompt(db.session.get(TrendyolQuestion, 4), "stok", gecmis=gecmis, simdi=model_sorulari)
    ikinci = _draft_prompt(db.session.get(TrendyolQuestion, 5), "stok", gecmis=gecmis, simdi=model_sorulari)
    ucuncu = _draft_prompt(db.session.get(TrendyolQuestion, 6), "stok", gecmis=gecmis, simdi=model_sorulari)
    assert "selamlamayla BAŞLAMA" not in ilk                 # konuşmanın ilk sorusu selamlanır
    assert "yalnızca 2 dakika önce" in ikinci and "selamlamayla BAŞLAMA" in ikinci
    assert "yalnızca 2 dakika önce" in ucuncu                # en yakın önceki soruya göre
    # Henüz gönderilmemiş hazır taslak da bağlama girer ki aynı şey tekrarlanmasın
    assert "Biz (hazırlanan taslak, henüz gönderilmedi): Merhaba, 38 numara mevcut." in ikinci
    # Günler önce soru sormuş müşteriye yine selam verilir
    eski = musteri_gecmisi([11])[11]
    db.session.add(TrendyolQuestion(id=7, customer_id=11, user_name="Ayşe Y.", text="Geldi mi?",
                                    product_main_id="0121", status="WAITING_FOR_ANSWER",
                                    creation_date=model_sorulari))
    db.session.commit()
    sonra = _draft_prompt(db.session.get(TrendyolQuestion, 7), "stok", gecmis=musteri_gecmisi([11])[11],
                          simdi=model_sorulari)
    assert "ÖNCEKİ soruları" in sonra and "selamlamayla BAŞLAMA" not in sonra


def test_model_notu_takip_notlarindan_okunur(monkeypatch):
    import types
    from trendyol_qna import qna_service

    sahte = types.SimpleNamespace(get_takip_entries=lambda: [
        {"model": "0121", "colors": ["Siyah", "Kırmızı"], "note": "Yeni parti 20 Ekim'de.",
         "color_notes": {"Kırmızı": "Üretimi bitti, gelmeyecek.", "Siyah": "37-38 haftaya."}},
    ])
    monkeypatch.setitem(sys.modules, "takip_notu", sahte)
    assert qna_service.model_notu("0121", "kırmızı") == "Yeni parti 20 Ekim'de.\nKırmızı rengi: Üretimi bitti, gelmeyecek."
    tum = qna_service.model_notu("0121")
    assert "Kırmızı rengi:" in tum and "Siyah rengi:" in tum     # renk bilinmiyorsa hepsi etiketli
    assert qna_service.model_notu("0999") == "" and qna_service.model_notu(None) == ""


def test_model_kodu_aramasi_yalniz_o_modeli_getirir(monkeypatch):
    def urun(pid, baslik, handle, skular):
        return {"legacyResourceId": pid, "title": baslik, "handle": handle, "status": "ACTIVE",
                "onlineStoreUrl": f"https://www.gullushoes.com/products/{handle}", "featuredImage": None,
                "variants": {"nodes": [{"legacyResourceId": f"{pid}{i}", "sku": sku, "title": "Bej / 36",
                                        "price": "100.00", "compareAtPrice": None, "inventoryQuantity": 1,
                                        "availableForSale": True} for i, sku in enumerate(skular)]}}

    katalog = [
        urun("1", "Bilekten Bağlamalı Çift Tokalı", "155-bilekten", ["155-35 Bej Rugan", "155-36 Bej Rugan"]),
        urun("2", "Yakın Kodlu Başka Model", "1550-baska", ["1550-36 Siyah"]),
        urun("3", "Adında 155 Geçen Ürün", "0107-bilekten", ["0107-35Bej"]),
        urun("4", "Timsah Loafer", "03155-loafer", ["03155-36Bej Leopar"]),
        urun("5", "Timsah Loafer Siyah", "03155-siyah", ["03155-Siyah Timsah DSN 35"]),
    ]
    sorgular = []

    def sahte_shopify(query, variables):
        sorgular.append(variables["query"])
        q = variables["query"].replace("status:active ", "")
        if q.startswith("sku:"):
            onek = q[4:].rstrip("*")
            nodes = [u for u in katalog if any(v["sku"].startswith(onek) for v in u["variants"]["nodes"])]
        else:   # sitenin serbest araması: ad/açıklamada da gezer, alakasızları da döndürür
            nodes = [u for u in katalog if q in u["title"] or q in u["handle"]]
        return {"products": {"nodes": nodes, "pageInfo": {"hasNextPage": False}}}

    monkeypatch.setattr(instagram_urun, "_shopify", sahte_shopify)
    assert [u["id"] for u in instagram_urun.urun_ara("155")] == ["1"]            # 1550 ve 0107 gelmez
    assert sorgular[-1] == "status:active sku:155*"
    assert [u["id"] for u in instagram_urun.urun_ara("03155")] == ["4", "5"]     # aynı modelin iki ilanı
    assert [u["id"] for u in instagram_urun.urun_ara("15")] == ["1", "2"]        # kod yazılırken: önek
    assert instagram_urun.urun_ara("9999") == []                                 # yakın ürün gösterilmez
    assert [u["model"] for u in instagram_urun.urun_ara("1550")] == ["1550"]
    # Ürün adıyla arama eskisi gibi çalışır
    assert [u["id"] for u in instagram_urun.urun_ara("Timsah")] == ["4", "5"]
    assert sorgular[-1] == "status:active Timsah"


def test_uretim_modundaki_model_kartta_ve_istemde_isaretlenir(trendyol_sorulari):
    from trendyol_qna.qna_ai import _draft_prompt
    from trendyol_qna.qna_routes import _to_dict, _shopify_to_dict
    from models import ShopifyQuestion

    satir = db.session.get(TrendyolQuestion, 3)          # model 0121
    assert _to_dict(satir, uretim={"0121"})["uretim_modu"] is True
    assert _to_dict(satir, uretim={"0155"})["uretim_modu"] is False
    assert _to_dict(satir)["uretim_modu"] is False
    sh = ShopifyQuestion(contact_type="email", question="?", product_sku="0121")
    assert _shopify_to_dict(sh, uretim={"0121"})["uretim_modu"] is True
    assert _shopify_to_dict(sh)["uretim_modu"] is False
    prompt = _draft_prompt(satir, "38: stok yok", uretim_modu=True)
    assert "ÜRETİM MODU" in prompt and "'Stok yok, alamazsınız' DEME" in prompt
    assert "ÜRETİM MODU" not in _draft_prompt(satir, "38: stok yok")


def test_gercek_uygulama_hala_yuklenmedi():
    assert "app" not in sys.modules
