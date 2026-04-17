from flask import Blueprint, render_template, request, redirect, url_for, jsonify, current_app, send_from_directory
import json
import logging
from datetime import datetime
from models import db, SiparisFisi, Product, Tedarikci, MaliyetKategori, MaliyetKalem, ModelMaliyet, ModelDirekMaliyet
from user_logs import log_user_action
import os
import qrcode
import qrcode.image.svg
import io

logger = logging.getLogger(__name__)
siparis_fisi_bp = Blueprint("siparis_fisi_bp", __name__)


@siparis_fisi_bp.app_template_filter('json_loads')
def json_loads_filter(s):
    if not s or (isinstance(s, str) and not s.strip()):
        return []
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        logger.error(f"JSON Decode Error: {s}")
        return []


# ── QR Kod Oluşturma ──
def generate_and_save_qr_code(barcode_data):
    qr_codes_dir = os.path.join(current_app.root_path, 'static', 'qrcodes')
    os.makedirs(qr_codes_dir, exist_ok=True)

    safe_barcode_data = "".join(c for c in (barcode_data or "") if c.isalnum() or c in ('-', '_', '.'))
    if not safe_barcode_data:
        safe_barcode_data = "empty_barcode"

    qr_file_name = f"{safe_barcode_data}.svg"
    qr_file_path = os.path.join(qr_codes_dir, qr_file_name)
    qr_web_path = url_for('static', filename=f'qrcodes/{qr_file_name}')

    if os.path.exists(qr_file_path):
        return qr_web_path

    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(barcode_data)
        qr.make(fit=True)

        img = qr.make_image(image_factory=qrcode.image.svg.SvgImage)
        with open(qr_file_path, 'wb') as f:
            img.save(f)

        return qr_web_path
    except Exception as e:
        logger.error(f"QR kod oluşturma hatası: {e}")
        return url_for('static', filename='logo/gullu.png')


# ── Yardımcı Fonksiyonlar ──
def group_products_by_model_and_color(products):
    grouped_products = {}
    for product in products:
        key = (product.product_main_id or '', product.color or '')
        grouped_products.setdefault(key, []).append(product)
    return grouped_products


def sort_variants_by_size(product_group):
    try:
        return sorted(product_group, key=lambda x: float(x.size), reverse=True)
    except (ValueError, TypeError):
        return sorted(product_group, key=lambda x: x.size, reverse=True)


def _parse_or_zero(lst, index):
    if not lst or len(lst) <= index or not lst[index]:
        return 0
    try:
        return int(lst[index])
    except ValueError:
        return 0


def _parse_or_float_zero(lst, index):
    if not lst or len(lst) <= index or not lst[index]:
        return 0.0
    try:
        return float(lst[index])
    except ValueError:
        return 0.0


# ── Ürün Listesi (Gruplı) ──
@siparis_fisi_bp.route("/siparis_fisi_urunler")
def siparis_fisi_urunler():
    products = Product.query.all()
    grouped_products = group_products_by_model_and_color(products)

    page = request.args.get('page', 1, type=int)
    per_page = 9
    total_groups = len(grouped_products)

    sorted_keys = sorted(grouped_products.keys())
    paginated_keys = sorted_keys[(page - 1) * per_page : page * per_page]

    paginated_product_groups = {
        key: sort_variants_by_size(grouped_products[key])
        for key in paginated_keys
    }

    total_pages = (total_groups + per_page - 1) // per_page

    return render_template(
        "siparis_fisi_urunler.html",
        grouped_products=paginated_product_groups,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


# ── Canlı USD Maliyet Yardımcıları ──
def _usd_maliyet_map(model_ids):
    """Model kodlarına karşılık gelen güncel USD birim maliyetini döndürür.
    Öncelik: ModelDirekMaliyet (>0); aksi halde ModelMaliyet toplamı."""
    ids = [m for m in (model_ids or []) if m]
    if not ids:
        return {}
    ids = list(set(ids))

    # Direkt maliyet
    direk_rows = ModelDirekMaliyet.query.filter(ModelDirekMaliyet.model_id.in_(ids)).all()
    direk = {d.model_id: float(d.deger or 0) for d in direk_rows}

    # Kalem toplamı
    kalem_rows = db.session.query(
        ModelMaliyet.model_id,
        db.func.sum(ModelMaliyet.deger).label("toplam"),
    ).filter(ModelMaliyet.model_id.in_(ids)).group_by(ModelMaliyet.model_id).all()
    kalem = {r.model_id: float(r.toplam or 0) for r in kalem_rows}

    result = {}
    for m in ids:
        dv = direk.get(m, 0.0)
        kv = kalem.get(m, 0.0)
        result[m] = dv if dv > 0 else kv
    return result


@siparis_fisi_bp.route("/api/model_maliyet/<model_id>", methods=["GET"])
def api_model_maliyet_tek(model_id):
    """Tek bir modelin canlı USD birim maliyetini döndür."""
    try:
        mp = _usd_maliyet_map([model_id])
        toplam = mp.get(model_id, 0.0)
        direk = ModelDirekMaliyet.query.get(model_id)
        return jsonify({
            "ok": True,
            "model": model_id,
            "toplam_usd": round(toplam, 2),
            "direk": bool(direk and (direk.deger or 0) > 0),
            "girilmis": toplam > 0,
        })
    except Exception as e:
        logger.error(f"Model maliyet hatası: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


# ── 1) Fiş Liste Sayfası ──
@siparis_fisi_bp.route("/siparis_fisi_sayfasi", methods=["GET"])
def siparis_fisi_sayfasi():
    model_kodu = request.args.get('model_kodu', '')
    renk = request.args.get('renk', '')

    query = SiparisFisi.query
    if model_kodu:
        query = query.filter(SiparisFisi.urun_model_kodu.ilike(f'%{model_kodu}%'))
    if renk:
        query = query.filter(SiparisFisi.renk.ilike(f'%{renk}%'))

    page = request.args.get('page', 1, type=int)
    per_page = 20

    pagination = query.order_by(SiparisFisi.created_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Tüm model kodlarını topla, canlı USD maliyetlerini bir kerede çek
    tum_modeller = set()
    fis_kalemler_cache = {}
    for fis in pagination.items:
        try:
            kk = json.loads(fis.kalemler_json or "[]")
        except Exception:
            kk = []
        fis_kalemler_cache[fis.siparis_id] = kk
        for k in kk:
            mc = k.get("model_code")
            if mc:
                tum_modeller.add(mc)

    usd_map = _usd_maliyet_map(list(tum_modeller))

    # Her fiş için canlı USD toplamı
    canli_toplam_map = {}
    for fis in pagination.items:
        kk = fis_kalemler_cache.get(fis.siparis_id, [])
        toplam = 0.0
        for k in kk:
            birim = usd_map.get(k.get("model_code"), 0.0)
            adet = int(k.get("satir_toplam_adet") or 0)
            toplam += birim * adet
        canli_toplam_map[fis.siparis_id] = round(toplam, 2)

    return render_template(
        "siparis_fisi.html",
        fisler=pagination.items,
        pagination=pagination,
        canli_toplam_usd=canli_toplam_map,
        usd_map=usd_map,
    )


# ── 2) Özet Liste ──
@siparis_fisi_bp.route("/siparis_fisi_listesi", methods=["GET"])
def siparis_fisi_listesi():
    return redirect(url_for("siparis_fisi_bp.siparis_fisi_sayfasi"))


# ── 3) Tek Fiş Yazdırma ──
@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/yazdir", methods=["GET"])
def siparis_fisi_yazdir(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    fis.print_date = datetime.now()
    db.session.commit()

    try:
        log_user_action("PRINT", {
            "işlem_açıklaması": f"Tedarik fişi yazdırıldı — #{siparis_id} ({fis.urun_model_kodu})",
            "sayfa": "Ürün Tedarik",
            "fiş_id": siparis_id,
        })
    except Exception:
        pass

    return render_template("siparis_fisi_print.html", fis=fis, multiple=False)


# ── 4) Boş Teslimat Fişi ──
@siparis_fisi_bp.route("/siparis_fisi/bos_yazdir")
def bos_yazdir():
    return render_template("siparis_fisi_bos_print.html")


# ── 5) Toplu Fiş Yazdırma ──
@siparis_fisi_bp.route("/siparis_fisi/toplu_yazdir/<fis_ids>")
def toplu_yazdir(fis_ids):
    try:
        id_list = [int(id_) for id_ in fis_ids.split(',')]
        fisler = SiparisFisi.query.filter(SiparisFisi.siparis_id.in_(id_list)).all()
        if not fisler:
            return jsonify({"mesaj": "Seçili fişler bulunamadı"}), 404

        current_time = datetime.now()
        for fis in fisler:
            fis.print_date = current_time
        db.session.commit()

        try:
            log_user_action("PRINT", {
                "işlem_açıklaması": f"Toplu fiş yazdırıldı — {len(fisler)} fiş (#{', #'.join(str(f.siparis_id) for f in fisler)})",
                "sayfa": "Ürün Tedarik",
                "fiş_sayısı": len(fisler),
            })
        except Exception:
            pass

        return render_template("siparis_fisi_toplu_print.html", fisler=fisler, multiple=True)
    except Exception as e:
        logger.error(f"Toplu yazdırma hatası: {e}", exc_info=True)
        return jsonify({"mesaj": "Hata oluştu", "error": str(e)}), 500


# ── 6) Fiş Detay ──
@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/detay", methods=["GET"])
def siparis_fisi_detay(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    if not fis.teslim_kayitlari:
        fis.teslim_kayitlari = "[]"
        db.session.commit()

    # Kalemlerdeki modeller için canlı USD maliyet
    try:
        kalemler = json.loads(fis.kalemler_json or "[]")
    except Exception:
        kalemler = []
    model_ids = [k.get("model_code") for k in kalemler if k.get("model_code")]
    usd_map = _usd_maliyet_map(model_ids)

    # Fiş canlı USD toplamı
    canli_toplam_usd = 0.0
    for k in kalemler:
        birim = usd_map.get(k.get("model_code"), 0.0)
        adet = int(k.get("satir_toplam_adet") or 0)
        canli_toplam_usd += birim * adet

    return render_template(
        "siparis_fisi_detay.html",
        fis=fis,
        usd_map=usd_map,
        canli_toplam_usd=round(canli_toplam_usd, 2),
    )


# ── 7) Teslimat Kaydı Ekle ──
@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/teslimat", methods=["POST"])
def teslimat_kaydi_ekle(siparis_id):
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "")
    )

    def _fail(msg, status=400):
        if wants_json:
            return jsonify({"ok": False, "error": msg}), status
        return redirect(url_for("siparis_fisi_bp.siparis_fisi_detay",
                                siparis_id=siparis_id, error=msg))

    try:
        fis = SiparisFisi.query.get(siparis_id)
        if not fis:
            return _fail("Sipariş fişi bulunamadı", 404)

        kayitlar = json.loads(fis.teslim_kayitlari or "[]")
        kalemler_list = json.loads(fis.kalemler_json or "[]")

        model_code = request.form.get("model_code")
        color = request.form.get("color")

        target_kalem = next(
            (k for k in kalemler_list
             if k.get("model_code") == model_code and k.get("color") == color),
            None,
        )

        beden_adetleri = {}
        toplam = 0
        for size in range(35, 42):
            key = f"beden_{size}"
            try:
                adet = int(request.form.get(key, 0) or 0)
            except (TypeError, ValueError):
                adet = 0
            if adet < 0:
                adet = 0
            beden_adetleri[key] = adet
            toplam += adet

        if toplam <= 0:
            return _fail("Teslim edilecek ürün adeti 0'dan büyük olmalı.")

        # Kalan kontrolü (server-side güvenlik)
        if target_kalem:
            for size in range(35, 42):
                size_s = str(size)
                siparis_adet = int(target_kalem.get(f"beden_{size}", 0) or 0)
                onceden_teslim = sum(
                    int(k.get(f"beden_{size}", 0) or 0)
                    for k in kayitlar
                    if k.get("model_code") == model_code and k.get("color") == color
                )
                kalan = siparis_adet - onceden_teslim
                if beden_adetleri[f"beden_{size}"] > kalan:
                    return _fail(f"Beden {size} için kalandan fazla giremezsiniz (kalan: {kalan}).")

        yeni_kayit = {
            "tarih": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "model_code": model_code,
            "color": color,
            **beden_adetleri,
            "toplam": toplam,
        }
        kayitlar.append(yeni_kayit)

        total_teslim = sum(k.get("toplam", 0) for k in kayitlar)

        fis.teslim_kayitlari = json.dumps(kayitlar, ensure_ascii=False)
        fis.kalan_adet = fis.toplam_adet - total_teslim

        # Stokları güncelle (tek seferde barkodları topla, tek sorgu ile çek)
        if target_kalem:
            barkodlar_map = target_kalem.get("barkodlar", {}) or {}
            barkod_adet = {}
            for size_key, adet in beden_adetleri.items():
                if adet > 0:
                    size_num = size_key.split("_")[1]
                    barkod = barkodlar_map.get(size_num)
                    if barkod:
                        barkod_adet[barkod] = adet
            if barkod_adet:
                products = Product.query.filter(Product.barcode.in_(list(barkod_adet.keys()))).all()
                for p in products:
                    p.quantity = (p.quantity or 0) - barkod_adet[p.barcode]

        db.session.commit()

        try:
            log_user_action("UPDATE", {
                "işlem_açıklaması": f"Teslimat kaydı eklendi — Fiş #{siparis_id}, {model_code} {color}, {toplam} adet",
                "sayfa": "Ürün Tedarik Detay",
                "fiş_id": siparis_id,
                "model": model_code,
                "renk": color,
                "teslim_adet": toplam,
            })
        except Exception:
            pass

        if wants_json:
            # Güncel kalanları (bu kalem) döndür
            kalanlar = {}
            if target_kalem:
                for size in range(35, 42):
                    siparis_adet = int(target_kalem.get(f"beden_{size}", 0) or 0)
                    teslim_toplam = sum(
                        int(k.get(f"beden_{size}", 0) or 0)
                        for k in kayitlar
                        if k.get("model_code") == model_code and k.get("color") == color
                    )
                    kalanlar[str(size)] = siparis_adet - teslim_toplam
            return jsonify({
                "ok": True,
                "toplam": toplam,
                "yeni_kayit": yeni_kayit,
                "kalanlar": kalanlar,
                "fis_kalan_adet": fis.kalan_adet,
                "fis_toplam_teslim": total_teslim,
            })

        return redirect(url_for("siparis_fisi_bp.siparis_fisi_detay", siparis_id=siparis_id,
                                success=f"Teslimat eklendi ({toplam} adet)"))

    except Exception as e:
        logger.error(f"Teslimat kaydı eklerken hata: {e}", exc_info=True)
        return _fail(f"Teslimat eklenirken bir hata oluştu: {str(e)}", 500)


# ── 8) Fiş Oluştur ──
@siparis_fisi_bp.route("/siparis_fisi/olustur", methods=["GET", "POST"])
def siparis_fisi_olustur():
    search_query = request.args.get('search', '').strip()

    query = Product.query.with_entities(
        Product.product_main_id.label('title'),
    )
    if search_query:
        query = query.filter(Product.product_main_id.ilike(f'%{search_query}%'))

    urunler = query.group_by(Product.product_main_id).order_by(Product.product_main_id).all()

    if request.method == "POST":
        model_codes = request.form.getlist("model_codes[]")
        colors = request.form.getlist("colors[]")
        cift_basi_fiyat_list = request.form.getlist("cift_basi_fiyat[]")
        beden_lists = {
            size: request.form.getlist(f"beden_{size}[]")
            for size in range(35, 42)
        }
        acil_lists = {
            size: request.form.getlist(f"acil_{size}[]")
            for size in range(35, 42)
        }

        kalemler = []
        total_adet = 0
        total_fiyat = 0

        for i in range(len(model_codes)):
            mcode = (model_codes[i] or "").strip()
            clr = (colors[i] or "").strip()
            if not mcode:
                continue

            beden_vals = {}
            acil_vals = {}
            satir_toplam_adet = 0
            for size in range(35, 42):
                val = _parse_or_zero(beden_lists[size], i)
                beden_vals[f"beden_{size}"] = val
                acil_val = acil_lists[size][i] if i < len(acil_lists[size]) else "0"
                acil_vals[f"acil_{size}"] = acil_val in ("1", "on", "true")
                satir_toplam_adet += val

            cift_fiyat = _parse_or_float_zero(cift_basi_fiyat_list, i)
            satir_toplam_fiyat = satir_toplam_adet * cift_fiyat

            # Model+renk'e ait barkodları çek
            products_for_barcode = Product.query.filter_by(product_main_id=mcode, color=clr).all()
            barkodlar = {}
            for p in products_for_barcode:
                if p.size and p.barcode:
                    barkodlar[str(int(float(p.size)))] = p.barcode

            kalemler.append({
                "model_code": mcode,
                "color": clr,
                **beden_vals,
                **acil_vals,
                "cift_basi_fiyat": cift_fiyat,
                "satir_toplam_adet": satir_toplam_adet,
                "satir_toplam_fiyat": satir_toplam_fiyat,
                "barkodlar": barkodlar,
            })

            total_adet += satir_toplam_adet
            total_fiyat += satir_toplam_fiyat

        if not kalemler:
            return redirect(url_for("siparis_fisi_bp.siparis_fisi_olustur",
                                    error="Sipariş fişi oluşturmak için en az bir geçerli ürün satırı eklemelisiniz."))

        yeni_fis = SiparisFisi(
            urun_model_kodu="Çoklu Model",
            renk="Birden Fazla",
            toplam_adet=total_adet,
            toplam_fiyat=total_fiyat,
            created_date=datetime.now(),
            kalemler_json=json.dumps(kalemler, ensure_ascii=False),
            image_url="/static/logo/gullu.png",
            kalan_adet=total_adet,
        )

        db.session.add(yeni_fis)
        db.session.commit()

        try:
            model_list = [k["model_code"] for k in kalemler]
            log_user_action("CREATE", {
                "işlem_açıklaması": f"Tedarik fişi oluşturuldu — {len(kalemler)} kalem, toplam {total_adet} adet",
                "sayfa": "Ürün Tedarik",
                "fiş_id": yeni_fis.siparis_id,
                "modeller": ", ".join(model_list),
                "toplam_adet": total_adet,
            })
        except Exception:
            pass

        return redirect(url_for("siparis_fisi_bp.siparis_fisi_sayfasi"))

    return render_template("siparis_fisi_olustur.html", urunler=urunler)


# ── 9) JSON API Endpoint'leri ──
@siparis_fisi_bp.route("/siparis_fisi", methods=["GET"])
def get_siparis_fisi_list():
    fisler = SiparisFisi.query.order_by(SiparisFisi.created_date.desc()).all()
    sonuc = []
    for fis in fisler:
        sonuc.append({
            "siparis_id": fis.siparis_id,
            "urun_model_kodu": fis.urun_model_kodu,
            "renk": fis.renk,
            "beden_35": fis.beden_35,
            "beden_36": fis.beden_36,
            "beden_37": fis.beden_37,
            "beden_38": fis.beden_38,
            "beden_39": fis.beden_39,
            "beden_40": fis.beden_40,
            "beden_41": fis.beden_41,
            "cift_basi_fiyat": float(fis.cift_basi_fiyat),
            "toplam_adet": fis.toplam_adet,
            "toplam_fiyat": float(fis.toplam_fiyat),
            "created_date": fis.created_date.strftime("%Y-%m-%d %H:%M:%S") if fis.created_date else None,
            "image_url": fis.image_url,
            "kalan_adet": fis.kalan_adet,
        })
    return jsonify(sonuc), 200


@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>", methods=["GET"])
def get_siparis_fisi(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    kalemler_data = json.loads(fis.kalemler_json or "[]")

    return jsonify({
        "siparis_id": fis.siparis_id,
        "urun_model_kodu": fis.urun_model_kodu,
        "renk": fis.renk,
        "beden_35": fis.beden_35,
        "beden_36": fis.beden_36,
        "beden_37": fis.beden_37,
        "beden_38": fis.beden_38,
        "beden_39": fis.beden_39,
        "beden_40": fis.beden_40,
        "beden_41": fis.beden_41,
        "cift_basi_fiyat": float(fis.cift_basi_fiyat),
        "toplam_adet": fis.toplam_adet,
        "toplam_fiyat": float(fis.toplam_fiyat),
        "created_date": fis.created_date.strftime("%Y-%m-%d %H:%M:%S") if fis.created_date else None,
        "image_url": fis.image_url,
        "kalan_adet": fis.kalan_adet,
        "kalemler": kalemler_data,
    }), 200


@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>", methods=["PUT"])
def update_siparis_fisi(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    data = request.json or {}
    fis.urun_model_kodu = data.get("urun_model_kodu", fis.urun_model_kodu)
    fis.renk = data.get("renk", fis.renk)
    fis.cift_basi_fiyat = data.get("cift_basi_fiyat", fis.cift_basi_fiyat)

    fis.beden_35 = data.get("beden_35", fis.beden_35)
    fis.beden_36 = data.get("beden_36", fis.beden_36)
    fis.beden_37 = data.get("beden_37", fis.beden_37)
    fis.beden_38 = data.get("beden_38", fis.beden_38)
    fis.beden_39 = data.get("beden_39", fis.beden_39)
    fis.beden_40 = data.get("beden_40", fis.beden_40)
    fis.beden_41 = data.get("beden_41", fis.beden_41)

    fis.toplam_adet = (
        int(fis.beden_35 or 0) + int(fis.beden_36 or 0) + int(fis.beden_37 or 0) +
        int(fis.beden_38 or 0) + int(fis.beden_39 or 0) + int(fis.beden_40 or 0) + int(fis.beden_41 or 0)
    )
    fis.toplam_fiyat = float(fis.toplam_adet) * float(fis.cift_basi_fiyat or 0.0)

    kayitlar = json.loads(fis.teslim_kayitlari or "[]")
    total_teslim = sum(k.get("toplam", 0) for k in kayitlar)
    fis.kalan_adet = fis.toplam_adet - total_teslim

    db.session.commit()
    return jsonify({"mesaj": "Sipariş fişi güncellendi."}), 200


@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>", methods=["DELETE"])
def delete_siparis_fisi(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    fis_model = fis.urun_model_kodu
    fis_adet = fis.toplam_adet
    db.session.delete(fis)
    db.session.commit()

    try:
        log_user_action("DELETE", {
            "işlem_açıklaması": f"Tedarik fişi silindi — #{siparis_id} ({fis_model}, {fis_adet} adet)",
            "sayfa": "Ürün Tedarik",
            "fiş_id": siparis_id,
            "model": fis_model,
        })
    except Exception:
        pass

    return jsonify({"mesaj": "Sipariş fişi silindi."}), 200


# ── 10) Maliyet Fişi ──
@siparis_fisi_bp.route("/maliyet_fisi_bos", methods=["GET"])
def maliyet_fisi_bos():
    return render_template("maliyet_fisi_print.html", now=datetime.now)


@siparis_fisi_bp.route("/maliyet_fisi/<int:siparis_id>/yazdir", methods=["GET"])
def maliyet_fisi_yazdir(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify({"mesaj": "Sipariş fişi bulunamadı"}), 404

    return render_template("maliyet_fisi_print.html", fis=fis)


# ── 11) Ürün Detay API ──
@siparis_fisi_bp.route("/get_product_details/<model_code>")
def get_product_details(model_code):
    products = Product.query.filter_by(product_main_id=model_code).all()
    if not products:
        return jsonify({"success": False, "message": "Ürün bulunamadı"})

    colors = list(set(p.color for p in products if p.color))

    product_data = {}
    tedarikci_info = {"tedarikci_kodu": "", "tedarikci_adi": ""}
    for color in colors:
        product_data[color] = {}
        color_products = [p for p in products if p.color == color]
        for product in color_products:
            if product.size and product.barcode:
                try:
                    size_key = str(int(float(product.size)))
                    product_data[color][size_key] = product.barcode
                except (ValueError, TypeError):
                    product_data[color][str(product.size)] = product.barcode
            if not tedarikci_info["tedarikci_kodu"] and product.tedarikci_kodu:
                tedarikci_info = {"tedarikci_kodu": product.tedarikci_kodu or "", "tedarikci_adi": product.tedarikci_adi or ""}

    return jsonify({
        "success": True,
        "colors": colors,
        "product_data": product_data,
        "tedarikci": tedarikci_info,
    })


# ── 11b) Tedarikçi Bilgisi Güncelle ──
@siparis_fisi_bp.route("/update_tedarikci", methods=["POST"])
def update_tedarikci():
    data = request.get_json(force=True) or {}
    model_code = data.get("model_code", "").strip()
    tedarikci_kodu = data.get("tedarikci_kodu", "").strip()
    tedarikci_adi = data.get("tedarikci_adi", "").strip()

    if not model_code:
        return jsonify(success=False, message="Model kodu gerekli"), 400

    products = Product.query.filter_by(product_main_id=model_code).all()
    if not products:
        return jsonify(success=False, message="Ürün bulunamadı"), 404

    for p in products:
        p.tedarikci_kodu = tedarikci_kodu or None
        p.tedarikci_adi = tedarikci_adi or None
    db.session.commit()

    try:
        log_user_action("UPDATE", {
            "işlem_açıklaması": f"Tedarikçi atandı — {model_code} → {tedarikci_kodu or 'Kaldırıldı'} ({tedarikci_adi or '-'})",
            "sayfa": "Tedarikçi Yönetimi",
            "model": model_code,
            "tedarikçi_kodu": tedarikci_kodu or "Kaldırıldı",
            "tedarikçi_adı": tedarikci_adi,
        })
    except Exception:
        pass

    return jsonify(success=True, message=f"{len(products)} ürün güncellendi")


# ── 11c) Tedarikçi Yönetim Sayfası ──
@siparis_fisi_bp.route("/tedarikci", methods=["GET"])
def tedarikci_sayfasi():
    return render_template("tedarikci_yonetimi.html")


@siparis_fisi_bp.route("/api/tedarikcilar", methods=["GET"])
def api_tedarikcilar():
    """Tedarikci tablosundan tüm tedarikçileri listele."""
    rows = Tedarikci.query.order_by(Tedarikci.kod).all()
    return jsonify([{"id": r.id, "kod": r.kod, "adi": r.adi or ""} for r in rows])


@siparis_fisi_bp.route("/api/tedarikci_ekle", methods=["POST"])
def api_tedarikci_ekle():
    data = request.get_json(force=True) or {}
    kod = (data.get("kod") or "").strip()
    adi = (data.get("adi") or "").strip()

    if not kod:
        return jsonify(success=False, message="Tedarikçi kodu gerekli"), 400

    existing = Tedarikci.query.filter_by(kod=kod).first()
    if existing:
        existing.adi = adi or existing.adi
        db.session.commit()
        return jsonify(success=True, message="Tedarikçi güncellendi", id=existing.id)

    yeni = Tedarikci(kod=kod, adi=adi or None)
    db.session.add(yeni)
    db.session.commit()

    try:
        log_user_action("CREATE", {
            "işlem_açıklaması": f"Yeni tedarikçi eklendi — {kod} ({adi or '-'})",
            "sayfa": "Tedarikçi Yönetimi",
            "tedarikçi_kodu": kod,
            "tedarikçi_adı": adi,
        })
    except Exception:
        pass

    return jsonify(success=True, message="Tedarikçi eklendi", id=yeni.id), 201


@siparis_fisi_bp.route("/api/tedarikci_sil/<int:tid>", methods=["DELETE"])
def api_tedarikci_sil(tid):
    ted = Tedarikci.query.get(tid)
    if not ted:
        return jsonify(success=False, message="Tedarikçi bulunamadı"), 404
    ted_kod = ted.kod
    ted_adi = ted.adi
    db.session.delete(ted)
    db.session.commit()

    try:
        log_user_action("DELETE", {
            "işlem_açıklaması": f"Tedarikçi silindi — {ted_kod} ({ted_adi or '-'})",
            "sayfa": "Tedarikçi Yönetimi",
            "tedarikçi_kodu": ted_kod,
        })
    except Exception:
        pass

    return jsonify(success=True, message="Tedarikçi silindi")


@siparis_fisi_bp.route("/api/tedarikci_modeller", methods=["GET"])
def api_tedarikci_modeller():
    """Modelleri tedarikçi bilgisiyle birlikte listele. Opsiyonel ?search= ve ?tedarikci= filtresi."""
    search = (request.args.get("search") or "").strip()
    tedarikci_filter = (request.args.get("tedarikci") or "").strip()

    query = (
        db.session.query(
            Product.product_main_id,
            db.func.min(Product.tedarikci_kodu).label("tedarikci_kodu"),
            db.func.min(Product.tedarikci_adi).label("tedarikci_adi"),
            db.func.count(Product.barcode).label("varyant_sayisi"),
        )
        .filter(Product.product_main_id.isnot(None), Product.product_main_id != "")
        .group_by(Product.product_main_id)
        .order_by(Product.product_main_id)
    )

    if search:
        query = query.filter(Product.product_main_id.ilike(f"%{search}%"))
    if tedarikci_filter:
        if tedarikci_filter == "__yok__":
            query = query.having(
                db.or_(
                    db.func.min(Product.tedarikci_kodu).is_(None),
                    db.func.min(Product.tedarikci_kodu) == "",
                )
            )
        else:
            query = query.having(db.func.min(Product.tedarikci_kodu) == tedarikci_filter)

    rows = query.limit(200).all()
    return jsonify([
        {
            "model": r[0],
            "tedarikci_kodu": r[1] or "",
            "tedarikci_adi": r[2] or "",
            "varyant_sayisi": r[3],
        }
        for r in rows
    ])


@siparis_fisi_bp.route("/api/toplu_tedarikci_ata", methods=["POST"])
def toplu_tedarikci_ata():
    """Birden fazla modele aynı tedarikçiyi ata."""
    data = request.get_json(force=True) or {}
    modeller = data.get("modeller", [])
    tedarikci_kodu = (data.get("tedarikci_kodu") or "").strip()
    tedarikci_adi = (data.get("tedarikci_adi") or "").strip()

    if not modeller:
        return jsonify(success=False, message="Model listesi boş"), 400

    updated = 0
    for model in modeller:
        products = Product.query.filter_by(product_main_id=model).all()
        for p in products:
            p.tedarikci_kodu = tedarikci_kodu or None
            p.tedarikci_adi = tedarikci_adi or None
            updated += 1

    db.session.commit()

    try:
        eylem = f"Toplu tedarikçi atandı — {len(modeller)} model → {tedarikci_kodu or 'Kaldırıldı'}" if tedarikci_kodu else f"Toplu tedarikçi kaldırıldı — {len(modeller)} model"
        log_user_action("UPDATE", {
            "işlem_açıklaması": eylem,
            "sayfa": "Tedarikçi Yönetimi",
            "modeller": ", ".join(modeller[:10]) + ("..." if len(modeller) > 10 else ""),
            "model_sayısı": len(modeller),
            "tedarikçi_kodu": tedarikci_kodu or "Kaldırıldı",
        })
    except Exception:
        pass

    return jsonify(success=True, message=f"{updated} ürün güncellendi ({len(modeller)} model)")


# ── 12) Barkod Etiket Yazdırma ──
@siparis_fisi_bp.route("/siparis_fisi/<int:siparis_id>/barkod_yazdir", methods=["GET"])
def siparis_fisi_barkod_yazdir(siparis_id):
    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return "Sipariş fişi bulunamadı", 404

    try:
        kalemler = json.loads(fis.kalemler_json or "[]")
    except json.JSONDecodeError:
        kalemler = []

    printed_set = set(fis.printed_barcodes or [])
    unique_barcodes_to_print = []

    for kalem in kalemler:
        for size in range(35, 42):
            size_str = str(size)
            barcode = kalem.get("barkodlar", {}).get(size_str)
            quantity = int(kalem.get(f"beden_{size_str}", 0))
            if quantity > 0 and barcode:
                unique_barcodes_to_print.append({
                    "barcode": barcode,
                    "model": kalem.get("model_code", "N/A"),
                    "color": kalem.get("color", "N/A"),
                    "size": size_str,
                    "qr_image_path": generate_and_save_qr_code(barcode),
                    "print_count": quantity * 3,
                    "is_printed": barcode in printed_set,
                })

    return render_template(
        "siparis_fisi_barkod_print.html",
        barcodes=unique_barcodes_to_print,
        siparis_id=siparis_id,
    )


# ── 13) Yazdırma Durumu Güncelle ──
@siparis_fisi_bp.route("/mark_as_printed", methods=["POST"])
def mark_as_printed():
    data = request.get_json(force=True) or {}
    siparis_id = data.get("siparis_id")
    barcodes = data.get("barcodes", [])

    if not siparis_id:
        return jsonify(success=False, message="Sipariş ID'si eksik"), 400

    fis = SiparisFisi.query.get(siparis_id)
    if not fis:
        return jsonify(success=False, message="Fiş bulunamadı"), 404

    fis.printed_barcodes = fis.printed_barcodes or []

    new_ones = [bc for bc in barcodes if bc not in fis.printed_barcodes]
    if new_ones:
        fis.printed_barcodes.extend(new_ones)
        db.session.commit()

    return jsonify(success=True, added=new_ones), 200


# ── 14) Canlı Panelden Tedarik Oluştur ──
@siparis_fisi_bp.route("/siparis_fisi/tedarik_olustur", methods=["POST"])
def tedarik_olustur_from_panel():
    """
    Canlı panelden seçilen kartların satış adetlerine göre
    otomatik tedarik siparişi (SiparisFisi) oluşturur.
    Beklenen JSON:
    {
      "kartlar": [
        {
          "model": "099-001",
          "renk": "SİYAH",
          "detay": [
            {"beden": "35", "net": 5},
            {"beden": "36", "net": 3}, ...
          ]
        }, ...
      ]
    }
    """
    data = request.get_json(force=True) or {}
    secilen_kartlar = data.get("kartlar", [])

    if not secilen_kartlar:
        return jsonify(success=False, message="Hiç kart seçilmedi."), 400

    kalemler = []
    total_adet = 0

    for kart in secilen_kartlar:
        mcode = (kart.get("model") or "").strip()
        clr = (kart.get("renk") or "").strip()
        if not mcode:
            continue

        # Detaydan beden adetlerini ve acil flag'lerini çıkar
        beden_vals = {}
        acil_vals = {}
        satir_toplam_adet = 0
        for d in (kart.get("detay") or []):
            beden_str = str(d.get("beden", "")).replace(",", ".").strip()
            try:
                beden_num = str(int(float(beden_str)))
            except (ValueError, TypeError):
                continue
            net = max(0, int(d.get("net", 0)))
            if 35 <= int(beden_num) <= 41:
                beden_vals[f"beden_{beden_num}"] = net
                acil_vals[f"acil_{beden_num}"] = bool(d.get("acil", False))
                satir_toplam_adet += net

        if satir_toplam_adet <= 0:
            continue

        # 35-41 arası eksik bedenleri 0 olarak doldur
        for size in range(35, 42):
            beden_vals.setdefault(f"beden_{size}", 0)
            acil_vals.setdefault(f"acil_{size}", False)

        # Barkodları çek
        products_for_barcode = Product.query.filter_by(product_main_id=mcode, color=clr).all()
        barkodlar = {}
        for p in products_for_barcode:
            if p.size and p.barcode:
                try:
                    barkodlar[str(int(float(p.size)))] = p.barcode
                except (ValueError, TypeError):
                    pass

        kalemler.append({
            "model_code": mcode,
            "color": clr,
            **beden_vals,
            **acil_vals,
            "cift_basi_fiyat": 0,
            "satir_toplam_adet": satir_toplam_adet,
            "satir_toplam_fiyat": 0,
            "barkodlar": barkodlar,
        })
        total_adet += satir_toplam_adet

    if not kalemler:
        return jsonify(success=False, message="Seçilen kartlarda geçerli satış adeti bulunamadı."), 400

    # Fiş oluştur
    urun_baslik = kalemler[0]["model_code"] if len(kalemler) == 1 else "Çoklu Model"
    renk_baslik = kalemler[0]["color"] if len(kalemler) == 1 else "Birden Fazla"

    yeni_fis = SiparisFisi(
        urun_model_kodu=urun_baslik,
        renk=renk_baslik,
        toplam_adet=total_adet,
        toplam_fiyat=0,
        created_date=datetime.now(),
        kalemler_json=json.dumps(kalemler, ensure_ascii=False),
        image_url="/static/logo/gullu.png",
        kalan_adet=total_adet,
    )

    db.session.add(yeni_fis)
    db.session.commit()

    try:
        model_list = [k["model_code"] for k in kalemler]
        log_user_action("CREATE", {
            "işlem_açıklaması": f"Canlı panelden tedarik siparişi oluşturuldu — {len(kalemler)} kalem, toplam {total_adet} adet",
            "sayfa": "Canlı Panel → Tedarik",
            "fiş_id": yeni_fis.siparis_id,
            "modeller": ", ".join(model_list),
            "toplam_adet": total_adet,
        })
    except Exception:
        pass

    return jsonify(
        success=True,
        message=f"Tedarik siparişi oluşturuldu. {len(kalemler)} kalem, toplam {total_adet} adet.",
        siparis_id=yeni_fis.siparis_id,
        redirect_url=url_for("siparis_fisi_bp.siparis_fisi_detay", siparis_id=yeni_fis.siparis_id),
    ), 201


# ════════════════════════════════════════════════════════════════════
# MALİYET KALEMLERİ API'leri
# ════════════════════════════════════════════════════════════════════

def _ensure_maliyet_tables():
    """Maliyet tablolarını oluştur (yoksa), eksik kolonları ekle."""
    from sqlalchemy import inspect as sa_inspect, text
    inspector = sa_inspect(db.engine)
    if not inspector.has_table('maliyet_kategori'):
        MaliyetKategori.__table__.create(db.engine)
    if not inspector.has_table('maliyet_kalem'):
        MaliyetKalem.__table__.create(db.engine)
    else:
        # model_id kolonu yoksa ekle
        columns = {c["name"] for c in inspector.get_columns("maliyet_kalem")}
        if "model_id" not in columns:
            db.session.execute(text("ALTER TABLE maliyet_kalem ADD COLUMN model_id VARCHAR(255)"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_maliyet_kalem_model_id ON maliyet_kalem (model_id)"))
            db.session.commit()
    if not inspector.has_table('model_maliyet'):
        ModelMaliyet.__table__.create(db.engine)
    if not inspector.has_table('model_direk_maliyet'):
        ModelDirekMaliyet.__table__.create(db.engine)


def seed_maliyet_sablonu():
    """Varsayılan maliyet kalemlerini oluşturur (sadece tablo boşsa)."""
    _ensure_maliyet_tables()
    if MaliyetKategori.query.first():
        return

    sablon = [
        ("Kesim Giderleri", [
            ("Malzemeler", [
                ("Astar", 0.50),
                ("Kırışık Rugan", 1.50),
                ("Mat", 1.20),
                ("Süet", 1.20),
                ("Düz Rugan", 1.25),
            ]),
            ("İşçilik", [
                ("Kesim İşçiliği", 0.40),
            ]),
        ]),
        ("Kalfa Giderleri", [
            ("Malzemeler", [
                ("Çelik Taban", 1.00),
                ("Ökçe", 0.90),
                ("Neolit Jurdan", 0.80),
                ("Beyaz İlaç", 0.36),
                ("Sarı İlaç", 0.15),
                ("Fort", 0.05),
                ("Silme Suyu", 0.10),
                ("Çivi ve Zımba", 0.15),
            ]),
            ("İşçilik", [
                ("Kalfa İşçiliği", 2.05),
            ]),
        ]),
        ("Sayacı Giderleri", [
            ("Malzemeler", [
                ("Tranta", 0.09),
            ]),
            ("İşçilik", [
                ("Sayacı İşçiliği", 1.12),
            ]),
        ]),
        ("Ökçe Çakma / Temizleme", [
            ("Malzemeler", [
                ("Temizleme Malzemesi", 0.50),
            ]),
            ("İşçilik", [
                ("Ökçe Çakma/Temizleme İşçiliği", 1.55),
            ]),
        ]),
        ("Kiralar ve Diğer Giderler", [
            ("Genel", [
                ("Dükkan Kirası", 0.0),
                ("Elektrik", 0.0),
                ("Çay / Su / Şeker", 0.0),
                ("Kira+Elektrik Çift Başı", 0.67),
            ]),
        ]),
    ]

    kalem_sira = 0
    for kat_sira, (kat_ad, alt_basliklar) in enumerate(sablon):
        kat = MaliyetKategori(ad=kat_ad, sira=kat_sira)
        db.session.add(kat)
        db.session.flush()
        for alt_baslik, kalemler_list in alt_basliklar:
            for kalem_ad, varsayilan in kalemler_list:
                kalem = MaliyetKalem(
                    kategori_id=kat.id,
                    alt_baslik=alt_baslik,
                    ad=kalem_ad,
                    varsayilan_deger=varsayilan,
                    birim="USD",
                    sira=kalem_sira,
                )
                db.session.add(kalem)
                kalem_sira += 1

    db.session.commit()


@siparis_fisi_bp.route("/api/maliyet/sablon", methods=["GET"])
def api_maliyet_sablon():
    """Maliyet şablonunu döndür. ?model_id= verilirse modele özel kalemler de dahil."""
    seed_maliyet_sablonu()
    model_id = (request.args.get("model_id") or "").strip()
    kategoriler = MaliyetKategori.query.order_by(MaliyetKategori.sira).all()
    result = []
    for kat in kategoriler:
        # Şablon kalemleri (model_id IS NULL) + modele özel kalemler
        query = MaliyetKalem.query.filter_by(kategori_id=kat.id).filter(
            db.or_(MaliyetKalem.model_id.is_(None), MaliyetKalem.model_id == model_id)
        ).order_by(MaliyetKalem.sira) if model_id else \
            MaliyetKalem.query.filter_by(kategori_id=kat.id, model_id=None).order_by(MaliyetKalem.sira)
        kalemler = query.all()
        kalemler_data = []
        for k in kalemler:
            kalemler_data.append({
                "id": k.id,
                "alt_baslik": k.alt_baslik or "",
                "ad": k.ad,
                "varsayilan_deger": k.varsayilan_deger,
                "birim": k.birim,
                "ozel": k.model_id is not None,  # modele özel mi?
            })
        result.append({
            "id": kat.id,
            "ad": kat.ad,
            "kalemler": kalemler_data,
        })
    return jsonify(result)


@siparis_fisi_bp.route("/api/maliyet/kategori_ekle", methods=["POST"])
def api_maliyet_kategori_ekle():
    """Yeni maliyet kategorisi (başlık) ekle."""
    data = request.get_json(force=True) or {}
    ad = (data.get("ad") or "").strip()
    if not ad:
        return jsonify(success=False, message="Kategori adı gerekli"), 400

    max_sira = db.session.query(db.func.max(MaliyetKategori.sira)).scalar() or 0
    kat = MaliyetKategori(ad=ad, sira=max_sira + 1)
    db.session.add(kat)
    db.session.commit()
    return jsonify(success=True, message="Kategori eklendi", id=kat.id), 201


@siparis_fisi_bp.route("/api/maliyet/kategori_sil/<int:kat_id>", methods=["DELETE"])
def api_maliyet_kategori_sil(kat_id):
    """Maliyet kategorisi sil (alt kalemler cascade silinir)."""
    kat = MaliyetKategori.query.get(kat_id)
    if not kat:
        return jsonify(success=False, message="Kategori bulunamadı"), 404
    db.session.delete(kat)
    db.session.commit()
    return jsonify(success=True, message="Kategori silindi")


@siparis_fisi_bp.route("/api/maliyet/kalem_ekle", methods=["POST"])
def api_maliyet_kalem_ekle():
    """Kategoriye yeni maliyet kalemi ekle. model_id verilirse modele özel olur."""
    data = request.get_json(force=True) or {}
    kategori_id = data.get("kategori_id")
    alt_baslik = (data.get("alt_baslik") or "").strip()
    ad = (data.get("ad") or "").strip()
    varsayilan = data.get("varsayilan_deger", 0.0)
    birim = (data.get("birim") or "USD").strip()
    model_id = (data.get("model_id") or "").strip() or None  # None = şablon

    if not kategori_id or not ad:
        return jsonify(success=False, message="Kategori ID ve kalem adı gerekli"), 400

    kat = MaliyetKategori.query.get(kategori_id)
    if not kat:
        return jsonify(success=False, message="Kategori bulunamadı"), 404

    max_sira = db.session.query(db.func.max(MaliyetKalem.sira)).filter_by(kategori_id=kategori_id).scalar() or 0
    kalem = MaliyetKalem(
        kategori_id=kategori_id,
        model_id=model_id,
        alt_baslik=alt_baslik or None,
        ad=ad,
        varsayilan_deger=float(varsayilan or 0),
        birim=birim,
        sira=max_sira + 1,
    )
    db.session.add(kalem)
    db.session.commit()
    tip = "modele özel" if model_id else "şablon"
    return jsonify(success=True, message=f"Kalem eklendi ({tip})", id=kalem.id), 201


@siparis_fisi_bp.route("/api/maliyet/kalem_sil/<int:kalem_id>", methods=["DELETE"])
def api_maliyet_kalem_sil(kalem_id):
    """Maliyet kalemi sil. Şablon kalemler sadece şablon yönetiminden, modele özel kalemler model görünümünden silinebilir."""
    kalem = MaliyetKalem.query.get(kalem_id)
    if not kalem:
        return jsonify(success=False, message="Kalem bulunamadı"), 404
    if kalem.model_id is None:
        # Şablon kalemi - şablon yönetiminden siliniyor, force parametresi lazım
        force = request.args.get("force") == "1"
        if not force:
            return jsonify(success=False, message="Bu şablon kalemi tüm modelleri etkiler. Şablon yönetiminden silin."), 400
    db.session.delete(kalem)
    db.session.commit()
    return jsonify(success=True, message="Kalem silindi")


@siparis_fisi_bp.route("/api/maliyet/model/<model_id>", methods=["GET"])
def api_maliyet_model_get(model_id):
    """Bir modelin tüm maliyet değerlerini getir (kalem + direkt)."""
    kayitlar = ModelMaliyet.query.filter_by(model_id=model_id).all()
    result = {str(k.kalem_id): k.deger for k in kayitlar}

    direk = ModelDirekMaliyet.query.get(model_id)
    direk_deger = direk.deger if direk else None

    return jsonify(success=True, degerler=result, direk_maliyet=direk_deger)


@siparis_fisi_bp.route("/api/maliyet/model/<model_id>", methods=["POST"])
def api_maliyet_model_kaydet(model_id):
    """Bir modelin maliyet değerlerini toplu kaydet (kalem + direkt)."""
    data = request.get_json(force=True) or {}
    degerler = data.get("degerler", {})  # {kalem_id: deger}
    direk_maliyet = data.get("direk_maliyet")  # float veya None

    for kalem_id_str, deger in degerler.items():
        kalem_id = int(kalem_id_str)
        existing = ModelMaliyet.query.filter_by(model_id=model_id, kalem_id=kalem_id).first()
        if existing:
            existing.deger = float(deger or 0)
            existing.updated_at = datetime.utcnow()
        else:
            yeni = ModelMaliyet(model_id=model_id, kalem_id=kalem_id, deger=float(deger or 0))
            db.session.add(yeni)

    # Direkt toplam maliyet
    if direk_maliyet is not None and direk_maliyet != "":
        direk = ModelDirekMaliyet.query.get(model_id)
        if direk:
            direk.deger = float(direk_maliyet)
            direk.updated_at = datetime.utcnow()
        else:
            direk = ModelDirekMaliyet(model_id=model_id, deger=float(direk_maliyet))
            db.session.add(direk)
    elif direk_maliyet == "":
        # Boş gönderilirse direkt maliyeti sil
        direk = ModelDirekMaliyet.query.get(model_id)
        if direk:
            db.session.delete(direk)

    db.session.commit()

    try:
        log_user_action("UPDATE", {
            "işlem_açıklaması": f"Model maliyeti güncellendi — {model_id}, {len(degerler)} kalem" + (f", direkt: {direk_maliyet}$" if direk_maliyet else ""),
            "sayfa": "Maliyet Yönetimi",
            "model": model_id,
        })
    except Exception:
        pass

    return jsonify(success=True, message="Maliyet kaydedildi")


@siparis_fisi_bp.route("/api/maliyet/model_listesi", methods=["GET"])
def api_maliyet_model_listesi():
    """Maliyeti girilmiş modellerin listesi."""
    _ensure_maliyet_tables()
    search = (request.args.get("search") or "").strip()

    query = db.session.query(
        Product.product_main_id,
        db.func.count(Product.barcode).label("varyant"),
    ).filter(
        Product.product_main_id.isnot(None),
        Product.product_main_id != "",
    ).group_by(Product.product_main_id).order_by(Product.product_main_id)

    if search:
        query = query.filter(Product.product_main_id.ilike(f"%{search}%"))

    rows = query.limit(200).all()

    # Maliyet girilmiş modeller
    maliyet_modeller = db.session.query(
        ModelMaliyet.model_id,
        db.func.sum(ModelMaliyet.deger).label("toplam"),
    ).group_by(ModelMaliyet.model_id).all()
    maliyet_map = {m.model_id: float(m.toplam or 0) for m in maliyet_modeller}

    # Direkt maliyet girilmiş modeller
    direk_modeller = ModelDirekMaliyet.query.all()
    direk_map = {d.model_id: float(d.deger or 0) for d in direk_modeller}

    filtre = (request.args.get("filtre") or "").strip()  # "var" veya "yok"

    result = []
    for r in rows:
        model_id = r[0]
        kalem_toplam = maliyet_map.get(model_id, 0)
        direk = direk_map.get(model_id, 0)
        toplam = direk if direk > 0 else kalem_toplam
        girilmis = model_id in maliyet_map or model_id in direk_map

        if filtre == "var" and not girilmis:
            continue
        if filtre == "yok" and girilmis:
            continue

        result.append({
            "model": model_id,
            "varyant": r[1],
            "toplam_maliyet": toplam,
            "maliyet_girilmis": girilmis,
            "direk": model_id in direk_map,
        })
    return jsonify(result)
