"""Gelen Yorumlar — Güllü Yorum SQLite salt-okunur okuma testleri (Flask/DB yok).

Çalıştırma (conftest canlı app'i yükler, o yüzden):
    DISABLE_JOBS=1 python -m pytest tests/test_gelen_yorumlar.py --noconftest -q
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gelen_yorumlar_service import (  # noqa: E402
    DURUM_ACMADI,
    DURUM_BAKTI,
    DURUM_YORUM,
    GelenYorumHata,
    email_maskele,
    oku,
    oku_yorumlar,
    utc_parse,
)

SEMA = """
CREATE TABLE requests (
  order_id INTEGER PRIMARY KEY, order_name TEXT, email TEXT, customer_name TEXT,
  fulfilled_at TEXT, sent_at TEXT, delivered INTEGER, reminder_sent_at TEXT,
  incentive_amount INTEGER, refunded_at TEXT, first_viewed_at TEXT);
CREATE TABLE submissions (
  handle TEXT PRIMARY KEY, order_id INTEGER, product_id INTEGER, submitted_at TEXT, updated_at TEXT);
"""
SEMA_YORUM = """
CREATE TABLE reviews_cache (
  review_id TEXT PRIMARY KEY, product_id INTEGER, product_title TEXT, order_id INTEGER, order_name TEXT,
  display_name TEXT, rating INTEGER, title TEXT, body TEXT, variant_title TEXT, status TEXT, reply TEXT,
  photo_count INTEGER, submitted_at TEXT, synced_at TEXT);
"""


@pytest.fixture
def db(tmp_path):
    yol = tmp_path / "gullu_yorum.sqlite3"
    conn = sqlite3.connect(yol)
    conn.executescript(SEMA)
    conn.executemany(
        "INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            # yorum yaptı, teşvikli, iade bekliyor, 2 ürün
            (1, "#1372", "ayse.yilmaz@gmail.com", "Ayşe Y.", "2026-10-01T10:00:00Z", "2026-10-27T11:41:30Z", 1, None, 100, None, "2026-10-27T12:00:00Z"),
            # baktı, yazmadı; hatırlatma gitti
            (2, "#1373", "mehmet@x.com", "Mehmet K.", "2026-10-01T10:00:00Z", "2026-10-27T11:41:31Z", 1, "2026-10-29T09:00:00Z", 100, None, "2026-10-27T13:00:00Z"),
            # açmadı
            (3, "#1374", "z@y.com", "Zeynep A.", "2026-10-01T10:00:00Z", "2026-10-27T11:41:32Z", 1, None, 100, None, None),
            # yorum yaptı, iade yapıldı
            (4, "#1375", "ali@y.com", "Ali B.", "2026-10-01T10:00:00Z", "2026-10-26T11:00:00Z", 1, None, 100, "2026-10-28T08:00:00Z", "2026-10-26T12:00:00Z"),
            # gönderim yarıda kaldı → sayılmaz
            (5, "#1376", "bos@y.com", "Boş C.", "2026-10-01T10:00:00Z", "2026-10-27T11:41:33Z", 0, None, 100, None, None),
        ],
    )
    conn.executemany(
        "INSERT INTO submissions VALUES (?,?,?,?,?)",
        [
            ("o1-p10", 1, 10, "2026-10-27T12:05:00Z", None),
            ("o1-p11", 1, 11, "2026-10-27T12:06:00Z", None),
            ("o4-p12", 4, 12, "2026-10-26T12:30:00Z", None),
        ],
    )
    conn.commit()
    conn.close()
    return str(yol)


@pytest.fixture
def db_yorumlu(db):
    conn = sqlite3.connect(db)
    conn.executescript(SEMA_YORUM)
    conn.executemany(
        "INSERT INTO reviews_cache VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("901", 10, "Taba Bot", 1, "#1372", "Ayşe Y.", 5, "Harika", "<b>Çok</b> rahat & şık", "Taba / 39", "approved", "Teşekkürler!", 2, "2026-10-27T12:05:00Z", "2026-10-27T12:10:00Z"),
            ("902", 11, "Siyah Çizme", 1, "#1372", "Ayşe Y.", 4, "", "İyi", "Siyah / 39", "approved", None, 0, "2026-10-27T12:06:00Z", None),
            ("903", 12, "Bej Sandalet", 4, "#1375", "Ali B.", 2, "", "Dar geldi", "Bej / 42", "pending", None, 0, "2026-10-26T12:30:00Z", None),
        ],
    )
    conn.commit()
    conn.close()
    return db


def test_ozet_brif_sorgusuyla_ayni(db):
    ozet, _ = oku(db)
    assert ozet.gonderilen == 4            # delivered=0 hariç
    assert ozet.bakan == 3
    assert ozet.yorum_yapan == 2           # sipariş bazında (1'in 2 ürünü tek sayılır)
    assert ozet.hatirlatma_giden == 1
    assert ozet.iade_bekleyen == 1 and ozet.iade_bekleyen_tutar == 100
    assert ozet.bakan_yuzde == 75 and ozet.yorum_yuzde == 50


def test_liste_durumlari_ve_siralama(db):
    _, satirlar = oku(db)
    assert [s.order_name for s in satirlar] == ["#1374", "#1373", "#1372", "#1375"]  # sent_at DESC
    durum = {s.order_name: s.durum for s in satirlar}
    assert durum == {"#1372": DURUM_YORUM, "#1373": DURUM_BAKTI, "#1374": DURUM_ACMADI, "#1375": DURUM_YORUM}
    s1372 = next(s for s in satirlar if s.order_name == "#1372")
    assert s1372.yorum_sayisi == 2 and s1372.iade_bekliyor
    assert s1372.reviewed_at.isoformat() == "2026-10-27T12:05:00+00:00"   # MIN(submitted_at)
    assert s1372.email_maskeli == "ay***@gmail.com"
    s1375 = next(s for s in satirlar if s.order_name == "#1375")
    assert not s1375.iade_bekliyor and s1375.refunded_at is not None


def test_sadece_yorum_filtresi(db):
    _, satirlar = oku(db, sadece_yorum=True)
    assert [s.order_name for s in satirlar] == ["#1372", "#1375"]


def test_salt_okunur_ve_dosya_yoksa_hata(db, tmp_path):
    with pytest.raises(GelenYorumHata):
        oku(str(tmp_path / "yok.sqlite3"))
    # mode=ro: servis üzerinden yazma mümkün değil; dosya değişmemeli
    onceki = Path(db).read_bytes()
    oku(db)
    assert Path(db).read_bytes() == onceki
    assert not (Path(db).parent / "gullu_yorum.sqlite3-wal").exists()


def test_yardimcilar():
    dt = utc_parse("2026-10-27T11:41:30Z")
    assert dt.tzinfo is not None and dt.utcoffset() == timezone.utc.utcoffset(dt)
    assert utc_parse(None) is None and utc_parse("bozuk") is None
    assert email_maskele("a@b.com") == "a***@b.com"
    assert email_maskele("") == ""


def test_yorumlar_ve_yildiz_dagilimi(db_yorumlu):
    yorumlar, yildiz = oku_yorumlar(db_yorumlu)
    assert [y.review_id for y in yorumlar] == ["902", "901", "903"]           # submitted_at DESC
    y901 = next(y for y in yorumlar if y.review_id == "901")
    assert y901.yildiz_metni == "★★★★★" and y901.durum_etiketi == "Yayında"
    assert y901.body == "<b>Çok</b> rahat & şık"                            # ham tutulur; kaçırma şablonda
    assert y901.reply == "Teşekkürler!" and y901.photo_count == 2
    assert y901.iade_bekliyor                                               # #1372 teşvikli, iade yok
    y903 = next(y for y in yorumlar if y.review_id == "903")
    assert not y903.iade_bekliyor and y903.durum_renk == "warning"          # #1375 iadesi yapılmış, pending
    assert yildiz.adetler == {5: 1, 4: 1, 3: 0, 2: 0, 1: 0}                 # pending sayılmaz
    assert yildiz.toplam == 2 and yildiz.ortalama == 4.5 and yildiz.yuzde(5) == 50


def test_reviews_cache_tablosu_yoksa_bos_doner(db):
    yorumlar, yildiz = oku_yorumlar(db)                                     # eski Güllü Yorum sürümü
    assert yorumlar == [] and yildiz.toplam == 0 and yildiz.ortalama == 0.0
