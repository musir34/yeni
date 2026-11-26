"""Tek adet raf teyidi — saf teyit_gecerli / tek_adet_miktari testleri (DB/app yok).

Modül dosya yolundan yüklenir: `stock_sync` paketinin __init__'i models'i import ettiği
için paket üzerinden import edilmez.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

_YOL = Path(__file__).resolve().parent.parent / "stock_sync" / "tek_adet_teyit.py"
_spec = importlib.util.spec_from_file_location("tek_adet_teyit_saf", _YOL)
tat = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tat)

T0 = datetime(2026, 11, 26, 10, 0, 0)


def test_teyit_stok_degisiminden_sonra_gecerli():
    assert tat.teyit_gecerli(1, T0, T0 + timedelta(minutes=5))
    assert tat.teyit_gecerli(1, T0, T0)                         # aynı an geçerli


def test_stok_teyitten_sonra_degisince_teyit_duser():
    assert not tat.teyit_gecerli(1, T0 + timedelta(seconds=1), T0)   # 1→2→1 vb.


def test_teyit_yok_ya_da_qty_bir_degil():
    assert not tat.teyit_gecerli(1, T0, None)
    assert not tat.teyit_gecerli(2, T0, T0 + timedelta(minutes=5))
    assert not tat.teyit_gecerli(0, T0, T0 + timedelta(minutes=5))


def test_updated_at_bos_ise_teyit_gecerli():
    assert tat.teyit_gecerli(1, None, T0)


def test_teyitsiz_tek_adet_sifir_gider():
    assert tat.tek_adet_miktari(1, 0, 1, teyitli=False, muaf=False) == 0


def test_teyitli_tek_adet_tampon_uygulanmaz_rezerv_duser():
    # normal formül (tampon yüzünden) 0 verse de teyitli tek adet 1 gider
    assert tat.tek_adet_miktari(1, 0, 0, teyitli=True, muaf=False) == 1
    assert tat.tek_adet_miktari(1, 1, 0, teyitli=True, muaf=False) == 0
    assert tat.tek_adet_miktari(1, 3, 0, teyitli=True, muaf=False) == 0


def test_qty_bir_degilse_normal_formul_aynen():
    assert tat.tek_adet_miktari(5, 1, 3, teyitli=False, muaf=False) == 3
    assert tat.tek_adet_miktari(0, 0, 0, teyitli=True, muaf=False) == 0
    assert tat.tek_adet_miktari(None, 0, 0, teyitli=False, muaf=False) == 0


def test_uretim_modu_muaf_normal_formul():
    assert tat.tek_adet_miktari(1, 0, 1, teyitli=False, muaf=True) == 1
