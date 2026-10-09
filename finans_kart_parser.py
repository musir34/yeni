"""İşbankası Maximum kredi kartı hesap özeti (PDF) ayrıştırıcı — saf mantık, DB/Flask yok.

Ekstre metni (pypdf) satır satır okunur. İşlem satırı düzeni:
    DD/MM/YYYY AÇIKLAMA TUTAR [n/m taksidi (TOPLAM)] [MAXIPUAN]
Negatif tutar = karta giriş (bankadan ödeme "HESAPTAN AKTARIM" ya da iade/iptal), pozitif = harcama.
Döviz satırında TL karşılığı son tutardır ("49,97 USD SATIŞ 2.480,01 0,24").

Başlık, "BİR ÖNCEKİ HESAP ÖZETİ BAKİYENİZ", "SANAL KART NO", toplam satırları işlem değildir;
önceki bakiye ve hesap özeti borcu mutabakat için ayrıca alınır.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

TUTAR = r'-?(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}'
SATIR_RE = re.compile(
    rf'^(?P<tarih>\d{{2}}/\d{{2}}/\d{{4}})\s+(?P<aciklama>.+?)\s+(?P<tutar>{TUTAR})'
    rf'(?:\s+(?P<taksit>\d+/\d+)\s+taksidi\s+\((?P<taksit_toplam>{TUTAR})\))?'
    rf'(?:\s+(?P<puan>{TUTAR}))?\s*$'
)
ONCEKI_RE = re.compile(rf'B[İI]R ÖNCEK[İI] HESAP ÖZET[İI] BAK[İI]YEN[İI]Z\s*\**\s*(?P<tutar>{TUTAR})')
BORC_RE = re.compile(rf'Hesap Özeti Borcu:\s*(?P<tutar>{TUTAR})')
KESIM_RE = re.compile(r'Hesap Kesim Tarihi:\s*(?P<tarih>\d{2}[./]\d{2}[./]\d{4})')
SON_ODEME_RE = re.compile(r'Son Ödeme Tarihi:\s*(?P<tarih>\d{2}[./]\d{2}[./]\d{4})')
KART_RE = re.compile(r'Kart Numarası:\s*(?P<kart>[\d*]+)')

# Satır türleri (önizlemede seçilebilir; satıcı hafızası bunu öğrenir)
TUR_GIDER = 'gider'              # işletme gideri → kucuk_gider (raporlara girer)
TUR_SAHSI = 'sahsi'              # şahsi harcama → kart_sahsi (kart borcunu artırır, raporlara girmez)
TUR_ODEME_BANKA = 'odeme_banka'  # "HESAPTAN AKTARIM" → transfer Banka → Kredi Kartı
TUR_ODEME_ELDE = 'odeme_elde'    # "ATMDEN ÖDEME" (nakit yatırma) → transfer Elde → Kredi Kartı
TUR_IADE = 'iade'                # iade/iptal → kart_iade (kart borcunu azaltır)
TUR_NAKIT = 'nakit'              # nakit avans (pozitif, "NAKİT") → transfer Kredi Kartı → Elde (henüz ekstrede görülmedi)
TUR_ATLA = 'atla'                # yazılmaz
TURLER = (TUR_GIDER, TUR_SAHSI, TUR_ODEME_BANKA, TUR_ODEME_ELDE, TUR_IADE, TUR_NAKIT, TUR_ATLA)
TUR_ETIKET = {
    TUR_GIDER: 'İşletme gideri', TUR_SAHSI: 'Şahsi harcama',
    TUR_ODEME_BANKA: 'Ödeme (Banka → Kart)', TUR_ODEME_ELDE: 'Ödeme (Elde → Kart)',
    TUR_IADE: 'İade / iptal', TUR_NAKIT: 'Nakit avans (Kart → Elde)', TUR_ATLA: 'Atla',
}


@dataclass
class EkstreSatiri:
    sira: int
    tarih: date
    aciklama: str
    tutar: Decimal                 # işaretli: + harcama, − karta giriş
    taksit: str = ''               # "6/9"
    taksit_toplam: Decimal | None = None
    puan: Decimal | None = None
    sanal_kart: bool = False
    oneri_tur: str = TUR_GIDER     # otomatik öneri (hafıza/anahtar kelime öncesi)
    satici_anahtari: str = ''


@dataclass
class Ekstre:
    satirlar: list[EkstreSatiri] = field(default_factory=list)
    onceki_bakiye: Decimal | None = None
    borc: Decimal | None = None
    kesim_tarihi: date | None = None
    son_odeme_tarihi: date | None = None
    kart: str = ''
    okunamayan: list[str] = field(default_factory=list)   # tarih ile başlayıp ayrıştırılamayan satırlar

    @property
    def satir_toplami(self) -> Decimal:
        return sum((s.tutar for s in self.satirlar), Decimal('0.00'))

    @property
    def ic_tutarlilik_farki(self) -> Decimal | None:
        """önceki bakiye + satırlar − borç; 0 ise ekstre eksiksiz okundu."""
        if self.onceki_bakiye is None or self.borc is None:
            return None
        return (self.onceki_bakiye + self.satir_toplami - self.borc).quantize(Decimal('0.01'))


def tutar_cevir(metin: str) -> Decimal:
    """'2.124,28' / '-248.717,70' → Decimal."""
    try:
        return Decimal(metin.replace('.', '').replace(',', '.'))
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f'Tutar okunamadı: {metin!r}') from exc


def tarih_cevir(metin: str) -> date:
    g, a, y = re.split(r'[./]', metin)
    return date(int(y), int(a), int(g))


def satici_anahtari(aciklama: str) -> str:
    """Satıcı hafızası anahtarı: rakam/kod/şehir parçaları atılır, ilk iki kelime kalır.

    'FACEBK *CBHB32JRQ4 FACEBOOK.COM IE' → 'FACEBK FACEBOOK.COM'
    'UBER EATS/TRENDYOL GO/G ISTANBUL TR' → 'UBER EATS/TRENDYOL'
    '5366648299 TURKCELL FAT.ÖDE.' → 'TURKCELL FAT.ÖDE.'
    """
    kelimeler = []
    for k in aciklama.upper().replace('İ', 'I').split():
        if any(ch.isdigit() for ch in k) or '*' in k:
            continue
        if k in ('TR', 'TU', 'IE', 'GB', 'US', 'WAUS', 'ISTANBUL', 'İSTANBUL'):
            continue
        kelimeler.append(k)
        if len(kelimeler) == 2:
            break
    return ' '.join(kelimeler)


def oneri_tur(aciklama: str, tutar: Decimal) -> str:
    a = aciklama.upper().replace('İ', 'I')
    if tutar < 0:
        if 'HESAPTAN AKTARIM' in a:
            return TUR_ODEME_BANKA
        if 'ATMDEN' in a or 'ODEME' in a or 'ÖDEME' in a:
            return TUR_ODEME_ELDE
        return TUR_IADE
    if 'NAKIT' in a:
        return TUR_NAKIT
    return TUR_GIDER


def ekstre_ayristir(metin: str) -> Ekstre:
    e = Ekstre()
    sanal = False
    sira = 0
    for ham in metin.splitlines():
        satir = ' '.join(ham.split())
        if not satir:
            continue
        m = ONCEKI_RE.search(satir)
        if m:
            e.onceki_bakiye = tutar_cevir(m.group('tutar'))
            continue
        m = BORC_RE.search(satir)
        if m and e.borc is None:
            e.borc = tutar_cevir(m.group('tutar'))
            continue
        m = KESIM_RE.search(satir)
        if m and e.kesim_tarihi is None:
            e.kesim_tarihi = tarih_cevir(m.group('tarih'))
            continue
        m = SON_ODEME_RE.search(satir)
        if m and e.son_odeme_tarihi is None:
            e.son_odeme_tarihi = tarih_cevir(m.group('tarih'))
            continue
        m = KART_RE.search(satir)
        if m and not e.kart:
            e.kart = m.group('kart')
            continue
        if satir.upper().startswith('SANAL KART'):
            sanal = True
            continue
        if not re.match(r'^\d{2}/\d{2}/\d{4}\s', satir):
            continue
        m = SATIR_RE.match(satir)
        if not m:
            e.okunamayan.append(satir)
            continue
        sira += 1
        tutar = tutar_cevir(m.group('tutar'))
        aciklama = m.group('aciklama').strip()
        e.satirlar.append(EkstreSatiri(
            sira=sira, tarih=tarih_cevir(m.group('tarih')), aciklama=aciklama, tutar=tutar,
            taksit=m.group('taksit') or '',
            taksit_toplam=tutar_cevir(m.group('taksit_toplam')) if m.group('taksit_toplam') else None,
            puan=tutar_cevir(m.group('puan')) if m.group('puan') else None,
            sanal_kart=sanal, oneri_tur=oneri_tur(aciklama, tutar), satici_anahtari=satici_anahtari(aciklama),
        ))
    return e


def pdf_metni(dosya) -> str:
    """PDF (yol ya da dosya nesnesi) → tüm sayfaların metni. pypdf requirements'ta."""
    from pypdf import PdfReader
    okuyucu = PdfReader(dosya)
    return '\n'.join((s.extract_text() or '') for s in okuyucu.pages)
