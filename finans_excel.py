# finans_excel.py
"""
📥 Finans — Excel'den gelir yükleme (İşbankası hesap ekstresi), finans_bp'ye eklenir.

Eski kasadaki (kasa.py excel_gelir_yukle) ile aynı dosya düzeni:
  A sütunu tarih/saat ("28/11/2025-12:55:35"), D sütunu işlem tutarı, I sütunu açıklama.
Başlık/boş satırlar atlanır, yalnızca pozitif tutarlar gelir olur → Beyazıt (Ana Bakiye).

Akış: dosya seç → sunucu okur → önizleme (geçerli satırlar seçili, geçersizler nedeniyle)
→ gelir kategorisi seç → Kaydet: seçili satırlar tek transaction'da finans_service.gelir_ekle
ile yazılır. Aynı tarih+tutar+açıklama daha önce (iptal edilmemiş) yüklendiyse atlanır.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
from flask import render_template, request, redirect, url_for, flash

from login_logout import login_required, roles_required
from models import db, FinansIslem
from time_utils import ist_to_utc, to_ist
from finans import finans_bp, _uid, _log
import finans_service as fs
from finans_service import FinansHata

BASLIK_IPUCLARI = ('tarih', 'saat', 'net bakiye', 'hesap', 'türkiye', 'işlem saatleri')
TARIH_FORMATLARI = (
    '%d/%m/%Y-%H:%M:%S', '%d/%m/%Y-%H:%M', '%d.%m.%Y-%H:%M:%S', '%d.%m.%Y-%H:%M',
    '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M',
    '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y',
)
ISO_FMT = '%Y-%m-%dT%H:%M:%S'


def _tarih_parse(raw):
    """Excel hücresi → naive İstanbul datetime; tanınmazsa None."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, pd.Timestamp):
        return raw.to_pydatetime()
    s = str(raw).strip()
    for fmt in TARIH_FORMATLARI:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _tutar_parse(raw):
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        if isinstance(raw, str):
            # Negatif (çıkış) satırlar da okunmalı ki nedeni doğru gösterilsin
            t = raw.strip().replace(' ', '')
            if ',' in t:
                t = t.replace('.', '').replace(',', '.')
            return Decimal(t).quantize(fs.IKI_HANE)
        return Decimal(str(round(float(raw), 2))).quantize(fs.IKI_HANE)
    except (InvalidOperation, ValueError, TypeError):
        return None


def excel_satirlari(file) -> list[dict]:
    """Dosyayı okuyup her satır için {satir, tarih, tutar, aciklama, gecerli, neden} döner."""
    df = pd.read_excel(file, header=None)
    satirlar = []
    for idx, row in df.iterrows():
        tarih_raw = row.iloc[0] if len(row) > 0 else None
        tutar_raw = row.iloc[3] if len(row) > 3 else None
        acik_raw = row.iloc[8] if len(row) > 8 else None
        bos = (tarih_raw is None or pd.isna(tarih_raw)) and (tutar_raw is None or pd.isna(tutar_raw))
        if bos:
            continue
        neden = None
        if tarih_raw is not None and not pd.isna(tarih_raw) and \
                any(x in str(tarih_raw).lower() for x in BASLIK_IPUCLARI):
            neden = 'başlık satırı'
        tarih = _tarih_parse(tarih_raw) if not neden else None
        tutar = _tutar_parse(tutar_raw) if not neden else None
        if not neden and tarih is None:
            neden = 'tarih tanınamadı'
        elif not neden and tutar is None:
            neden = 'tutar yok/okunamadı'
        elif not neden and tutar <= 0:
            neden = 'çıkış / sıfır tutar'
        aciklama = '' if acik_raw is None or pd.isna(acik_raw) else str(acik_raw).strip()[:500]
        satirlar.append({
            'satir': int(idx) + 1,
            'tarih': tarih, 'tarih_iso': tarih.strftime(ISO_FMT) if tarih else '',
            'tarih_str': tarih.strftime('%d.%m.%Y %H:%M') if tarih else (str(tarih_raw)[:30] if tarih_raw is not None and not pd.isna(tarih_raw) else '-'),
            'tutar': tutar, 'tutar_str': f'{tutar:.2f}' if tutar is not None else (str(tutar_raw)[:20] if tutar_raw is not None and not pd.isna(tutar_raw) else '-'),
            'aciklama': aciklama, 'gecerli': neden is None, 'neden': neden,
        })
    return satirlar


def _mukerrer_mi(tarih_utc: datetime, tutar: Decimal, aciklama: str) -> bool:
    return db.session.query(FinansIslem.id).filter(
        FinansIslem.tur == 'gelir', FinansIslem.iptal.is_(False),
        FinansIslem.tarih == tarih_utc, FinansIslem.tutar == tutar,
        FinansIslem.aciklama == aciklama).first() is not None


@finans_bp.route('/gelir/excel', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def gelir_excel():
    """GET: yükleme ekranı. POST: dosyayı oku, önizleme göster (henüz yazmaz)."""
    ctx = {'kategoriler': fs.kategoriler('gelir'), 'satirlar': None}
    if request.method == 'GET':
        return render_template('finans_gelir_excel.html', **ctx)
    f = request.files.get('excel_file')
    if not f or not f.filename:
        flash('Lütfen bir Excel dosyası seçin.', 'danger')
        return redirect(url_for('finans.gelir_excel'))
    if not f.filename.lower().endswith(('.xlsx', '.xls')):
        flash('Sadece .xlsx / .xls dosyaları kabul edilir.', 'danger')
        return redirect(url_for('finans.gelir_excel'))
    try:
        satirlar = excel_satirlari(f)
    except Exception as e:  # bozuk dosya vb.
        flash(f'Excel okunamadı: {e}', 'danger')
        return redirect(url_for('finans.gelir_excel'))
    for s in satirlar:
        if s['gecerli'] and _mukerrer_mi(ist_to_utc(s['tarih']), s['tutar'], s['aciklama']):
            s['gecerli'], s['neden'] = False, 'zaten yüklenmiş'
    gecerli = [s for s in satirlar if s['gecerli']]
    ctx.update(satirlar=satirlar, dosya_adi=f.filename, gecerli_adet=len(gecerli),
               gecerli_toplam=sum((s['tutar'] for s in gecerli), Decimal('0.00')),
               secili_kategori=request.form.get('kategori_id', type=int))
    return render_template('finans_gelir_excel.html', **ctx)


@finans_bp.route('/gelir/excel/kaydet', methods=['POST'])
@login_required
@roles_required('admin')
def gelir_excel_kaydet():
    """Önizlemede seçilen satırları tek transaction'da gelir olarak yazar."""
    f = request.form
    kategori_id = f.get('kategori_id')
    secili = f.getlist('sec')
    if not secili:
        flash('Kaydedilecek satır seçilmedi.', 'warning')
        return redirect(url_for('finans.gelir_excel'))
    eklenen, atlanan, toplam = 0, 0, Decimal('0.00')
    try:
        for i in secili:
            tarih_iso, tutar_raw = f.get(f'tarih_{i}', ''), f.get(f'tutar_{i}', '')
            aciklama = f.get(f'aciklama_{i}', '').strip()[:500]
            try:
                tarih_utc = ist_to_utc(datetime.strptime(tarih_iso, ISO_FMT))
                tutar = fs.parse_tutar(tutar_raw)
            except (ValueError, FinansHata):
                atlanan += 1
                continue
            if _mukerrer_mi(tarih_utc, tutar, aciklama):
                atlanan += 1
                continue
            fs.gelir_ekle(kategori_id, tutar, tarih_utc, aciklama, _uid(), commit=False)
            eklenen += 1
            toplam += tutar
        if eklenen == 0:
            db.session.rollback()
            flash(f'Hiçbir satır yazılmadı ({atlanan} atlandı).', 'warning')
            return redirect(url_for('finans.gelir_excel'))
        db.session.commit()
    except FinansHata as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('finans.gelir_excel'))
    _log("CREATE", f"Finans Excel gelir — {eklenen} kayıt, {toplam}₺ ({atlanan} atlandı)",
         eklenen=eklenen, atlanan=atlanan, tutar=str(toplam))
    flash(f'✅ {eklenen} gelir kaydı yüklendi, toplam {toplam:.2f} ₺ Beyazıt hesabına eklendi.'
          + (f' ({atlanan} satır atlandı.)' if atlanan else ''), 'success')
    ay = to_ist(datetime.utcnow()).strftime('%Y-%m')
    return redirect(url_for('finans.gelir', donem=ay))
