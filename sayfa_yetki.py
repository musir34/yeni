"""Sayfa yetkileri — hangi kullanıcı hangi sayfaya girebilir.

Model: ETKİN YETKİ = rol varsayılanı ± kişiye özel istisna.
- Rol varsayılanı kodda (SAYFALAR[*].roller): admin tüm sayfalar, manager/worker bugün fiilen
  açabildikleri sayfalar → sistem devreye girince kimsenin erişimi DEĞİŞMEZ.
- İstisna DB'de (kullanici_sayfa_yetki: user_id, sayfa_kodu, izin). izin=True → rolünde olmayan
  sayfa eklenir; izin=False → rolünde olan sayfa kaldırılır. Yalnız varsayılandan FARK saklanır.
- Sahip (users.is_owner) her sayfaya girer ve istisnaları yalnız o düzenler.

Uygulama noktaları:
- app.py before_request (check_authentication'dan sonra): istek bir katalog sayfasına düşüyorsa ve
  kullanıcı yetkili değilse engeller. Katalog dışı endpoint'ler eski kurallarıyla çalışır.
- login_logout.roles_required: rol tutmuyorsa ama kişiye o sayfa için izin=True istisnası varsa geçer
  (örn. finans'a açılan personel finans.py'deki @roles_required('admin')'e takılmaz). İstisnasız
  kullanıcıda rol kontrolü aynen sürer → sayfası herkese açık ama alt eylemi admin/manager olan
  rotalar (ürün listesi varyant silme gibi) korunur.
- Jinja global sayfa_erisebilir('kod'): menü görünürlüğü = açılabilirlik.

Sayfa eşleme sırası: yollar (path öneki) → endpoints (tam ad) → blueprints (blueprint adı).
Böylece tek blueprint'te yaşayan alt sayfalar (finans/cari, finans/kart, shopify fiyat) ayrı yetkilenir.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

HERKES = ("admin", "manager", "worker")
YONETIM = ("admin", "manager")
SADECE_ADMIN = ("admin",)
ROLLER = HERKES


@dataclass(frozen=True)
class Sayfa:
    kod: str
    ad: str
    grup: str
    blueprints: tuple = ()
    endpoints: tuple = ()
    yollar: tuple = ()          # URL path önekleri (blueprint içi alt sayfalar için)
    roller: tuple = HERKES      # varsayılan olarak erişen roller


SAYFALAR: tuple[Sayfa, ...] = (
    # ── Siparişler ──
    Sayfa("soru_cevap", "Soru-Cevap", "Siparişler", blueprints=("qna",)),
    Sayfa("siparis_hazirla", "Sipariş Hazırla", "Siparişler", blueprints=("siparis_hazirla",)),
    Sayfa("yeni_siparis", "Yeni Sipariş", "Siparişler", blueprints=("siparisler_bp",)),
    Sayfa("siparis_listesi", "Sipariş Listesi", "Siparişler",
          blueprints=("order_list_service", "order_service", "new_orders_service",
                      "processed_orders_service", "all_orders_service")),
    Sayfa("degisim", "Değişim Talepleri", "Siparişler", blueprints=("degisim",)),
    Sayfa("uretim", "Üretim Siparişleri", "Siparişler", blueprints=("uretim",)),
    Sayfa("kargo_mutabakat", "Kargo Mutabakat", "Siparişler", blueprints=("kargo_mutabakat_bp",), roller=SADECE_ADMIN),
    Sayfa("arsiv", "Arşiv", "Siparişler", blueprints=("archive",)),
    Sayfa("siparis_takip", "Sipariş Takip", "Siparişler", blueprints=("siparis_zaman",), roller=YONETIM),
    Sayfa("siparis_iz", "Sipariş İz Sürme", "Siparişler", blueprints=("order_audit",), roller=YONETIM),
    # ── Ürünler & Stok ──
    Sayfa("urun_yukleme", "Ürün Yükleme (AI)", "Ürünler & Stok", blueprints=("urun_yukleme",), roller=SADECE_ADMIN),
    Sayfa("urun_listesi", "Ürün Listesi", "Ürünler & Stok", blueprints=("get_products", "product_service", "product_label")),
    Sayfa("urun_tedarik", "Ürün Tedarik", "Ürünler & Stok", blueprints=("siparis_fisi_bp",)),
    Sayfa("gorsel_yonetimi", "Görsel Yönetimi", "Ürünler & Stok", blueprints=("image_manager",)),
    Sayfa("stok_ekleme", "Stok Ekleme", "Ürünler & Stok", blueprints=("stock_management", "stock_report")),
    Sayfa("raf", "Raf Listesi", "Ürünler & Stok", blueprints=("raf",)),
    Sayfa("stok_senkron", "Stok Senkronizasyon", "Ürünler & Stok", blueprints=("stock_sync",)),
    Sayfa("iade_listesi", "Trendyol İade Listesi", "Ürünler & Stok", blueprints=("iade_islemleri", "claims_service")),
    # ── Analiz & Fiyat ──
    Sayfa("kar_analizi", "Kâr Analizi", "Analiz & Fiyat", blueprints=("profit",)),
    Sayfa("canli_panel", "Canlı Satış & Stok", "Analiz & Fiyat", blueprints=("canli_panel",)),
    Sayfa("komisyon_yukle", "Excel Komisyon Yükle", "Analiz & Fiyat", blueprints=("commission_update_bp",)),
    Sayfa("komisyon_tarifeleri", "Ürün Komisyon Tarifeleri", "Analiz & Fiyat",
          blueprints=("akilli_motor", "komisyon_tarife"), roller=SADECE_ADMIN),
    Sayfa("flas_indirim", "Flaş İndirimler", "Analiz & Fiyat", blueprints=("flas_indirim",), roller=SADECE_ADMIN),
    Sayfa("raporlama", "Raporlama", "Analiz & Fiyat", blueprints=("rapor_gir",)),
    # ── Finans (alt sayfalar ayrı yetkilenir; yollar blueprint'ten önce eşleşir) ──
    Sayfa("kasa", "Kasa (eski)", "Finans", blueprints=("kasa",), roller=SADECE_ADMIN),
    Sayfa("finans_cari", "Finans — Cari Hesaplar", "Finans", yollar=("/finans/cari",), roller=SADECE_ADMIN),
    Sayfa("finans_calisan", "Finans — Çalışan Hakediş", "Finans", yollar=("/finans/calisan",), roller=SADECE_ADMIN),
    Sayfa("finans_kart", "Finans — Kredi Kartı", "Finans", yollar=("/finans/kart",), roller=SADECE_ADMIN),
    Sayfa("finans_excel", "Finans — Excel Gelir Yükleme", "Finans", yollar=("/finans/gelir/excel",), roller=SADECE_ADMIN),
    Sayfa("finans", "Finans — Kasa Paneli", "Finans", blueprints=("finans",), roller=SADECE_ADMIN),
    # ── Paneller ──
    Sayfa("shopify_fiyat", "Shopify ↔ Trendyol Fiyat", "Paneller",
          endpoints=("shopify.price_compare_dashboard", "shopify.price_compare_api", "shopify.price_compare_export")),
    Sayfa("shopify_siparisler", "Shopify Siparişler", "Paneller", blueprints=("shopify",)),
    Sayfa("site_iade", "Site İade Yönetimi", "Paneller", blueprints=("iade_yonetimi",)),
    Sayfa("idefix", "Idefix", "Paneller", blueprints=("idefix",)),
    Sayfa("hepsiburada", "Hepsiburada", "Paneller", blueprints=("hepsiburada",)),
    Sayfa("amazon", "Amazon", "Paneller", blueprints=("amazon",)),
    Sayfa("ai_asistan", "AI Asistan", "Paneller", blueprints=("ai_asistan",)),
    # ── Kullanıcı & Yönetim ──
    Sayfa("kullanici_yonetimi", "Kullanıcı Yönetimi", "Yönetim", roller=SADECE_ADMIN, endpoints=(
        "login_logout.register", "login_logout.approve_users", "login_logout.delete_user",
        "login_logout.update_notify", "login_logout.update_whatsapp", "login_logout.set_notification_image",
        "login_logout.clear_notification_image", "login_logout.update_max_pc", "login_logout.admin_reset_password",
        "login_logout.admin_reset_2fa", "login_logout.admin_reset_all", "login_logout.show_qr_code",
        "login_logout.admin_force_logout_user", "login_logout.force_logout_all")),
    Sayfa("kullanici_hareketleri", "Kullanıcı Hareketleri", "Yönetim", blueprints=("user_logs",), roller=YONETIM),
    Sayfa("whatsapp_mesajlari", "WhatsApp Mesajları", "Yönetim",
          blueprints=("whatsapp_duyuru", "whatsapp_baglanti"), roller=SADECE_ADMIN),
    Sayfa("alissa", "Muhammet Alissa", "Yönetim", blueprints=("alissa",), roller=SADECE_ADMIN),
    Sayfa("gizli_ozellikler", "Gizli Özellikler", "Yönetim", blueprints=("gizli_ozellikler",), roller=SADECE_ADMIN),
)

SAYFA_MAP: dict[str, Sayfa] = {s.kod: s for s in SAYFALAR}
_BLUEPRINT_MAP: dict[str, Sayfa] = {bp: s for s in SAYFALAR for bp in s.blueprints}
_ENDPOINT_MAP: dict[str, Sayfa] = {ep: s for s in SAYFALAR for ep in s.endpoints}
_YOL_LISTESI: tuple[tuple[str, Sayfa], ...] = tuple((y, s) for s in SAYFALAR for y in s.yollar)

GRUP_SIRASI = ("Siparişler", "Ürünler & Stok", "Analiz & Fiyat", "Finans", "Paneller", "Yönetim")


# ─────────────────────────── Saf mantık (DB/Flask yok) ───────────────────────────

def sayfa_bul(endpoint: str | None, path: str | None = None) -> Sayfa | None:
    """İsteğin düştüğü katalog sayfası; katalog dışı → None (eski kurallar geçerli)."""
    if path:
        for yol, sayfa in _YOL_LISTESI:
            if path == yol or path.startswith(yol + "/") or path.startswith(yol + "?"):
                return sayfa
    if not endpoint:
        return None
    if endpoint in _ENDPOINT_MAP:
        return _ENDPOINT_MAP[endpoint]
    bp = endpoint.rsplit(".", 1)[0] if "." in endpoint else None
    return _BLUEPRINT_MAP.get(bp) if bp else None


def rol_varsayilani(rol: str | None) -> set[str]:
    return {s.kod for s in SAYFALAR if rol in s.roller}


def erisebilir(kod: str, rol: str | None, istisnalar: dict[str, bool] | None = None, sahip: bool = False) -> bool:
    """Etkin yetki: sahip → her şey; istisna varsa o; yoksa rol varsayılanı."""
    if sahip:
        return True
    if kod not in SAYFA_MAP:
        return True                      # katalog dışı kod → kısıt yok
    if istisnalar and kod in istisnalar:
        return bool(istisnalar[kod])
    return rol in SAYFA_MAP[kod].roller


def etkin_sayfalar(rol: str | None, istisnalar: dict[str, bool] | None = None, sahip: bool = False) -> set[str]:
    return {s.kod for s in SAYFALAR if erisebilir(s.kod, rol, istisnalar, sahip)}


def istisna_farki(rol: str | None, secili: set[str]) -> dict[str, bool]:
    """Sahibin işaretlediği küme → saklanacak istisnalar (yalnız varsayılandan fark)."""
    varsayilan = rol_varsayilani(rol)
    fark: dict[str, bool] = {}
    for kod in SAYFA_MAP:
        acik = kod in secili
        if acik != (kod in varsayilan):
            fark[kod] = acik
    return fark


def gruplu_sayfalar() -> list[tuple[str, list[Sayfa]]]:
    """Ekran için gruplanmış katalog (GRUP_SIRASI düzeninde)."""
    return [(g, [s for s in SAYFALAR if s.grup == g]) for g in GRUP_SIRASI if any(s.grup == g for s in SAYFALAR)]


# ─────────────────────────── Flask/DB bağlı yardımcılar ───────────────────────────

def ensure_schema() -> None:
    """Açılış garantisi (additive, idempotent): users.is_owner kolonu + istisna tablosu.
    Script çalıştırılmadan servis yeniden başlasa bile User sorguları kırılmaz; sahip ataması
    yine scripts/add_sayfa_yetki.py --sahip ile yapılır. Hata → log (uygulama açılır)."""
    from sqlalchemy import inspect, text
    from models import KullaniciSayfaYetki, db
    try:
        denetci = inspect(db.engine)
        if "users" not in denetci.get_table_names():
            return                      # ilk kurulum: tabloyu create_all/migration açar
        kolonlar = {c["name"] for c in denetci.get_columns("users")}
        if "is_owner" not in kolonlar:
            db.session.execute(text("ALTER TABLE users ADD COLUMN is_owner BOOLEAN NOT NULL DEFAULT false"))
            db.session.commit()
            logger.info("[SAYFA-YETKI] users.is_owner kolonu eklendi")
        KullaniciSayfaYetki.__table__.create(bind=db.engine, checkfirst=True)
    except Exception:
        db.session.rollback()
        logger.exception("[SAYFA-YETKI] şema garantisi başarısız")


def _istisnalari_oku(user_id: int) -> dict[str, bool]:
    """Kullanıcının istisnaları; istek boyunca g'de önbellek. Hata → {} (rol varsayılanı geçerli)."""
    from flask import g
    onbellek = getattr(g, "_sayfa_istisna", None)
    if onbellek is None:
        onbellek = g._sayfa_istisna = {}
    if user_id in onbellek:
        return onbellek[user_id]
    from models import KullaniciSayfaYetki, db
    try:
        satirlar = KullaniciSayfaYetki.query.filter_by(user_id=user_id).all()
        sonuc = {r.sayfa_kodu: bool(r.izin) for r in satirlar}
    except Exception:
        logger.warning("[SAYFA-YETKI] istisnalar okunamadı (user_id=%s)", user_id, exc_info=True)
        db.session.rollback()
        sonuc = {}
    onbellek[user_id] = sonuc
    return sonuc


def _aktif_kullanici():
    from flask_login import current_user
    return current_user if getattr(current_user, "is_authenticated", False) else None


def kullanici_erisebilir(kod: str) -> bool:
    """Jinja global: oturumdaki kullanıcı bu sayfaya girebilir mi (menü görünürlüğü)."""
    user = _aktif_kullanici()
    if user is None:
        return False
    return erisebilir(kod, user.role, _istisnalari_oku(user.id), bool(getattr(user, "is_owner", False)))


def istek_engelli_sayfa() -> Sayfa | None:
    """before_request için: istek yetkisiz bir katalog sayfasına düşüyorsa o sayfayı döner."""
    from flask import request
    user = _aktif_kullanici()
    if user is None:
        return None                      # giriş kontrolü check_authentication'ın işi
    sayfa = sayfa_bul(request.endpoint, request.path)
    if sayfa is None:
        return None
    if erisebilir(sayfa.kod, user.role, _istisnalari_oku(user.id), bool(getattr(user, "is_owner", False))):
        return None
    return sayfa


def istisna_ile_acik_mi() -> bool:
    """roles_required için: rol tutmasa da bu sayfa kullanıcıya istisna (izin=True) ile açılmış mı?"""
    from flask import request
    user = _aktif_kullanici()
    if user is None:
        return False
    if getattr(user, "is_owner", False):
        return True
    sayfa = sayfa_bul(request.endpoint, request.path)
    if sayfa is None:
        return False
    return _istisnalari_oku(user.id).get(sayfa.kod) is True


def kullanici_yetki_durumu(user) -> dict[str, dict]:
    """Kullanıcı Yönetimi ekranı için: {kod: {'acik': bool, 'varsayilan': bool}}."""
    istisnalar = _istisnalari_oku(user.id)
    sahip = bool(getattr(user, "is_owner", False))
    return {
        s.kod: {"varsayilan": user.role in s.roller,
                "acik": erisebilir(s.kod, user.role, istisnalar, sahip)}
        for s in SAYFALAR
    }


def istisnalari_kaydet(user, secili: set[str]) -> dict[str, bool]:
    """Sahibin işaretlediği kümeyi istisna satırlarına yazar (fark yoksa satır silinir). Fark sözlüğünü döner."""
    from models import KullaniciSayfaYetki, db
    fark = istisna_farki(user.role, {k for k in secili if k in SAYFA_MAP})
    mevcut = {r.sayfa_kodu: r for r in KullaniciSayfaYetki.query.filter_by(user_id=user.id).all()}
    for kod, satir in mevcut.items():
        if kod not in fark:
            db.session.delete(satir)
    for kod, izin in fark.items():
        satir = mevcut.get(kod)
        if satir is None:
            db.session.add(KullaniciSayfaYetki(user_id=user.id, sayfa_kodu=kod, izin=izin))
        elif satir.izin != izin:
            satir.izin = izin
    db.session.commit()
    return fark
