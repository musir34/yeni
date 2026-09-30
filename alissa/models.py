# -*- coding: utf-8 -*-
"""Alissa hesabı tabloları. Hepsi yeni (alissa_*); panelin mevcut tablolarına dokunmaz.

Tarih kuralı: bu tablolardaki tüm tarih-saatler İSTANBUL duvar saatidir (naive).
"""
from datetime import datetime

from models import db

# Hareket türleri
FINANS_TURLERI = ('satis', 'iade', 'indirim', 'indirim_iptal', 'kupon', 'kupon_iptal')
KARGO_GONDERI = ('kargo_gonderi', 'kargo_gonderi_tahmin', 'kargo_gonderi_fark')
KARGO_IADE = ('kargo_iade', 'kargo_iade_tahmin', 'kargo_iade_fark')


class AlissaHareket(db.Model):
    """Hesap defteri: Alissa hakedişini artıran/azaltan her kalem tek satır.

    Satırlar yalnız eklenir (append-only); (tur, kaynak_id) tekilliği senkronu
    tekrar çalıştırılabilir yapar. `tutar` işaretlidir: + hakediş, − kesinti.
    """
    __tablename__ = 'alissa_hareket'
    __table_args__ = (db.UniqueConstraint('tur', 'kaynak_id', name='uq_alissa_hareket_tur_kaynak'),)

    id = db.Column(db.Integer, primary_key=True)
    tur = db.Column(db.String(24), nullable=False)
    kaynak_id = db.Column(db.String(96), nullable=False)      # Trendyol kayıt no / paket / sipariş / koli
    order_number = db.Column(db.String(32), index=True)
    shipment_package_id = db.Column(db.String(32))
    barcode = db.Column(db.String(64))
    model_kodu = db.Column(db.String(32), index=True)
    islem_tarihi = db.Column(db.DateTime, nullable=False, index=True)
    adet = db.Column(db.Integer, nullable=False, default=0)
    brut = db.Column(db.Numeric(12, 2), nullable=False, default=0)       # satış/iade/indirim ham tutarı (işaretli)
    komisyon = db.Column(db.Numeric(12, 2), nullable=False, default=0)   # işaretli; tutar = brut − komisyon
    tutar = db.Column(db.Numeric(12, 2), nullable=False)
    pay = db.Column(db.Numeric(7, 4))                                    # karma siparişte Alissa payı (0-1)
    aciklama = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.now)


class AlissaKargoKalem(db.Model):
    """Trendyol kargo faturası kalemleri (mağazanın tümü; Alissa'ya ait olanlar hesaba işlenir)."""
    __tablename__ = 'alissa_kargo_kalem'
    __table_args__ = (db.UniqueConstraint('fatura_no', 'parcel_id', 'tip', name='uq_alissa_kargo_kalem'),)

    id = db.Column(db.Integer, primary_key=True)
    fatura_no = db.Column(db.String(32), nullable=False, index=True)
    fatura_tarihi = db.Column(db.DateTime, nullable=False)
    order_number = db.Column(db.String(32), index=True)
    parcel_id = db.Column(db.String(32), nullable=False)
    tip = db.Column(db.String(8), nullable=False)             # gonderi | iade
    tutar = db.Column(db.Numeric(12, 2), nullable=False)
    desi = db.Column(db.Numeric(8, 2))


class AlissaSiparis(db.Model):
    """Sipariş v2 satırları (yalnız Alissa barkodları) — gelen/iptal/yolda bilgisi için."""
    __tablename__ = 'alissa_siparis'

    line_id = db.Column(db.String(32), primary_key=True)
    order_number = db.Column(db.String(32), index=True)
    shipment_package_id = db.Column(db.String(32))
    barcode = db.Column(db.String(64))
    model_kodu = db.Column(db.String(32))
    renk = db.Column(db.String(64))
    beden = db.Column(db.String(16))
    adet = db.Column(db.Integer, nullable=False, default=1)
    statu = db.Column(db.String(32))
    siparis_tarihi = db.Column(db.DateTime, index=True)
    birim_fiyat = db.Column(db.Numeric(12, 2))
    iptal_eden = db.Column(db.String(32))
    iptal_sebebi = db.Column(db.String(255))
    guncellendi = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class AlissaOdeme(db.Model):
    """Alissa'ya yapılan ödemeler. Silinmez; iptal edilir."""
    __tablename__ = 'alissa_odeme'

    id = db.Column(db.Integer, primary_key=True)
    tarih = db.Column(db.Date, nullable=False)
    tutar = db.Column(db.Numeric(12, 2), nullable=False)
    aciklama = db.Column(db.String(255))
    kullanici = db.Column(db.String(120))
    iptal = db.Column(db.Boolean, nullable=False, default=False)
    iptal_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now)


class AlissaAyar(db.Model):
    """Anahtar-değer: tutar ayarları + senkron durumu."""
    __tablename__ = 'alissa_ayar'

    anahtar = db.Column(db.String(40), primary_key=True)
    deger = db.Column(db.Text)


TABLOLAR = (AlissaHareket, AlissaKargoKalem, AlissaSiparis, AlissaOdeme, AlissaAyar)
