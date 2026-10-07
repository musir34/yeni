"""
Trendyol soruları için AI cevap taslağı üretimi.

ai_asistan altyapısını (headless Claude Code, Max aboneliği, salt-okunur
postgres MCP) yeniden kullanır. Taslak asla otomatik gönderilmez — panelde
insan onayından geçer.
"""
import json
import logging
import os
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from ai_asistan.blueprint import (
    _claude_bin,
    _codex_calistir,
    BASE_DIR as AI_ASISTAN_DIR,
    CLAUDE_MODEL,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
KURALLAR_MD = BASE_DIR / "CEVAP_KURALLARI.md"
ALLOWED_TOOLS = "mcp__gulludb__query"  # salt-okunur DB (opsiyonel; stok zaten prompta gömülü)
DRAFT_TIMEOUT_SN = 120
FALLBACK_PROMPT = "Sen Güllü Shoes'un Trendyol müşteri sorularına kısa, kibar Türkçe cevap taslağı yazan asistanısın. Sadece cevap metnini yaz."


def _kurallar() -> str:
    """Sistem promptu: cevap kuralları + panel genel talimatı + bilgi notları."""
    try:
        kurallar = KURALLAR_MD.read_text(encoding="utf-8")
    except OSError:
        kurallar = FALLBACK_PROMPT
    from trendyol_qna.qna_ayar import genel_talimat
    talimat = genel_talimat()
    if talimat:
        kurallar += (
            "\n\n---\n\n# Panel Genel Talimatı\n"
            "Mağaza yöneticisinin panelden girdiği güncel talimat — TÜM taslaklarda uygula:\n\n"
            + talimat
        )
    from trendyol_qna.qna_notes import load_vault_notes
    notlar = load_vault_notes()
    if notlar:
        kurallar += (
            "\n\n---\n\n# Bilgi Bankası (geçmiş cevaplar ve notlar)\n"
            "Aşağıdaki notlar mağazanın GERÇEK geçmiş cevaplarından derlendi. "
            "Üslubu ve bilgileri örnek al; ama STOK için her zaman sana verilen "
            "CANLI STOK verisini esas al (geçmiş 'üretimi sonlandı' notu bugün geçersiz olabilir).\n"
            "Kayıtlar '(model X · renk Y)' etiketlidir: cevapladığın ürünün model kodu "
            "VE rengiyle eşleşen dersleri kural gibi uygula; yalnızca model kodu eşleşenleri "
            "dikkate al ama başka renge özgü bilgiyi (kalıp, ton, malzeme vb.) bu renge TAŞIMA.\n\n"
            + notlar
        )
    return kurallar


GECMIS_ISTEM_SORU = 5   # taslak istemine giren önceki soru sayısı
ART_ARDA_SORU = timedelta(minutes=60)   # bu süre içinde gelen sorular tek konuşma sayılır
_IST = ZoneInfo("Europe/Istanbul")


def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if (dt is not None and dt.tzinfo is None) else dt


def _tarih_etiketi(dt, simdi) -> str:
    """'22.09.2026 (14 gün önce)' — AI göreli süreleri ('2 hafta sonra') bugüne göre hesaplasın diye."""
    dt = _utc(dt)
    if dt is None:
        return "tarih bilinmiyor"
    gun = (simdi.astimezone(_IST).date() - dt.astimezone(_IST).date()).days
    ne_zaman = "bugün" if gun <= 0 else ("dün" if gun == 1 else f"{gun} gün önce")
    return f"{dt.astimezone(_IST):%d.%m.%Y} ({ne_zaman})"


def _gecmis_metni(row, gecmis, simdi=None) -> str:
    """Aynı müşterinin önceki soru-cevapları (istem için); yoksa ''."""
    simdi = simdi or datetime.now(timezone.utc)
    onceki = [g for g in (gecmis or []) if g.id != row.id][-GECMIS_ISTEM_SORU:]
    if not onceki:
        return ""
    satirlar = []
    for g in onceki:
        urun = "" if g.product_main_id == row.product_main_id else f" [başka ürün: {g.product_name or 'bilinmiyor'}]"
        satirlar.append(f"{_tarih_etiketi(g.creation_date, simdi)} — Müşteri{urun}: {(g.text or '').strip()}")
        if g.answer_text:
            satirlar.append(f"Biz: {g.answer_text.strip()}")
        elif g.ai_draft_status == "ready" and g.ai_draft:
            satirlar.append(f"Biz (hazırlanan taslak, henüz gönderilmedi): {g.ai_draft.strip()}")
        else:
            satirlar.append("Biz: (henüz cevaplanmadı)")
    metin = (
        "Bu müşterinin ÖNCEKİ soruları ve cevaplarımız (eskiden yeniye). Yeni soru bunlara atıf "
        "yapıyor olabilir; çelişme, gerekiyorsa önceki cevabı dikkate al:\n"
        + "\n".join(satirlar) + "\n\n"
    )
    # Art arda soru: müşteri az önce de yazdıysa her cevaba baştan selam verilmez
    bu, yakin = _utc(row.creation_date), None
    for g in onceki:
        diger = _utc(g.creation_date)
        if bu is not None and diger is not None and timedelta(0) <= bu - diger <= ART_ARDA_SORU:
            yakin = bu - diger if yakin is None else min(yakin, bu - diger)
    if yakin is not None:
        metin += (
            f"DİKKAT: Bu müşteri bu sorudan yalnızca {max(int(yakin.total_seconds() // 60), 1)} dakika önce "
            "başka bir soru daha sordu; ikisi aynı konuşmanın devamı. Bu cevapta 'Merhaba', 'Merhabalar' gibi "
            "bir selamlamayla BAŞLAMA (genel kuraldaki selamlama şartı burada geçerli değil), doğrudan cevaba "
            "gir ve az önceki cevapta söyleneni tekrar etme.\n\n"
        )
    return metin


def _uretim_modunda(model_kodu) -> bool:
    """Model üretim modunda mı (uretim_modu ayarı). Okunamazsa False — taslak yine üretilir."""
    if not model_kodu:
        return False
    try:
        from uretim_modu import get_uretim_models
        return model_kodu in get_uretim_models()
    except Exception:
        logger.warning("[QNA-AI] üretim modu listesi okunamadı", exc_info=True)
        return False


def _model_hafizasi_metni(model_cevaplari, not_metni: str, simdi) -> str:
    """Model koduna özel hafıza: yöneticinin notu + bu modele verilmiş tarihli eski cevaplar."""
    metin = ""
    if not_metni:
        metin += (
            "MAĞAZA NOTU — yöneticinin bu model için yazdığı güncel bilgi; eski cevaplardan ve "
            f"tahminden ÖNCE gelir, aynen uy:\n{not_metni}\n\n"
        )
    if model_cevaplari:
        satirlar = []
        for g in model_cevaplari:
            kim = (g.user_name or "bir müşteri").strip()
            satirlar.append(f"{_tarih_etiketi(g.answer_date or g.creation_date, simdi)} — {kim} sordu: "
                            f"{(g.text or '').strip()}\n  Biz: {(g.answer_text or '').strip()}")
        metin += (
            "BU MODELE daha önce başka müşterilere verdiğimiz cevaplar (eskiden yeniye, tarihleriyle). "
            "Tutarlı ol. Bu cevaplardaki '2 hafta sonra gelecek', 'haftaya' gibi SÜRELİ ifadeleri o cevabın "
            "tarihine göre bugüne çevir: süre hâlâ dolmadıysa kalan süreyi söyle; dolduysa aynı sözü "
            "tekrarlama, CANLI STOK ve mağaza notuna göre cevapla. Başka müşterilerin adını cevapta kullanma:\n"
            + "\n".join(satirlar) + "\n\n"
        )
    return metin


URETIM_MODU_NOTU = (
    "ÜRETİM MODU: Bu model üretim modunda — stokta görünmeyen numaralar için de sipariş alınır, "
    "ürün üretilip gönderilir. 'Stok yok, alamazsınız' DEME; sipariş verilebileceğini söyle. "
    "Üretim/teslim süresini yalnız mağaza notunda ya da genel talimatta yazıyorsa belirt; "
    "yazmıyorsa kesin gün verme, 'üretim süresi eklenir' de.\n"
)


def _draft_prompt(row, stok_bilgisi: str, talimat: str | None = None,
                  mevcut_metin: str | None = None, renk: str | None = None,
                  gecmis=None, model_cevaplari=None, model_notu: str = "", simdi=None,
                  uretim_modu: bool = False) -> str:
    simdi = simdi or datetime.now(timezone.utc)
    prompt = (
        f"Bugünün tarihi: {simdi.astimezone(_IST):%d.%m.%Y}\n"
        f"Ürün: {row.product_name or 'bilinmiyor'}\n"
        f"Model kodu: {row.product_main_id or 'bilinmiyor'}\n"
        f"Renk: {renk or 'bilinmiyor'}\n"
        f"CANLI STOK: {stok_bilgisi}\n"
        + (URETIM_MODU_NOTU if uretim_modu else "") + "\n"
        + _model_hafizasi_metni(model_cevaplari, model_notu, simdi)
        + _gecmis_metni(row, gecmis, simdi) +
        f"Müşteri sorusu:\n{row.text}\n\n"
    )
    if talimat:
        prompt += (
            f"Mevcut taslak (panelde görünen hali):\n{mevcut_metin or row.ai_draft or '(boş)'}\n\n"
            f"Kullanıcının düzeltme talimatı: {talimat}\n\n"
            "Mevcut taslağı bu talimata göre düzelt; talimatın dokunmadığı kısımları koru. "
            "Kurallara uygun, Trendyol'a gönderilmeye hazır TEK bir cevap taslağı yaz."
        )
    else:
        prompt += "Bu soruya kurallara uygun, Trendyol'a gönderilmeye hazır TEK bir cevap taslağı yaz."
    return prompt


def _run_claude(prompt: str) -> str | None:
    """Headless Claude çağır, taslak metnini döndür (hata → None)."""
    claude_bin = _claude_bin()
    if not claude_bin:
        logger.warning("[QNA-AI] claude binary bulunamadı (CLAUDE_BIN ayarlayın)")
        return None

    # Abonelik kullanılsın (API faturası yok) + üst süreçten sızan Claude
    # oturum değişkenleri nested-session/401 hatası yaratmasın.
    env = {
        k: v for k, v in os.environ.items()
        if not (k.startswith("ANTHROPIC") or (k.startswith("CLAUDE") and k not in ("CLAUDE_BIN", "CLAUDE_CODE_OAUTH_TOKEN")))
    }

    cmd = [
        claude_bin,
        "-p", prompt,
        "--model", CLAUDE_MODEL,
        "--append-system-prompt", _kurallar(),
        "--allowedTools", ALLOWED_TOOLS,
        "--output-format", "json",
    ]
    try:
        sonuc = subprocess.run(
            cmd,
            cwd=str(AI_ASISTAN_DIR),  # .mcp.json (gulludb) buradan yüklenir
            env=env,
            capture_output=True,
            text=True,
            timeout=DRAFT_TIMEOUT_SN,
        )
    except subprocess.TimeoutExpired:
        logger.warning("[QNA-AI] taslak üretimi zaman aşımı")
        return None
    except OSError as e:
        logger.warning("[QNA-AI] claude çalıştırılamadı: %s", e)
        return None

    if sonuc.returncode != 0:
        logger.warning("[QNA-AI] claude hata: %s", (sonuc.stderr or "")[:300])
        return None
    try:
        data = json.loads(sonuc.stdout)
        text = (data.get("result") or data.get("text") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        text = (sonuc.stdout or "").strip()
    return text or None


def _run_ai(prompt: str) -> str | None:
    """Seçili motorla (panel ayarı > .env AI_MOTOR) taslak üret (hata → None)."""
    from ai_asistan.motor_ayar import aktif_motor, codex_model

    if aktif_motor("qna") != "codex":
        return _run_claude(prompt)

    sonuc = _codex_calistir(prompt, _kurallar(), DRAFT_TIMEOUT_SN, cwd=AI_ASISTAN_DIR,
                            model=codex_model("qna"))
    if not sonuc["ok"]:
        logger.warning("[QNA-AI] codex hata: %s", sonuc.get("hata"))
        return None
    return sonuc["cevap"] or None


def generate_draft(question_id: int, talimat: str | None = None,
                   mevcut_metin: str | None = None) -> dict:
    """
    Tek soru için taslak üret ve kaydet (senkron; app context İÇİNDE çağrılmalı).
    talimat verilirse mevcut taslak o talimata göre yeniden yazılır (revizyon).
    Dönen: {'ok': bool, 'taslak'/'hata': str}
    """
    from models import db, TrendyolQuestion
    from trendyol_qna.qna_service import stock_context, question_renk, ANSWER_MAX

    row = db.session.get(TrendyolQuestion, question_id)
    if not row:
        return {"ok": False, "hata": "Soru bulunamadı."}

    # Çifte üretim koruması: zaten üretiliyorsa (ve takılı kalmadıysa) atla.
    # ai_draft_at pending'e geçerken de damgalanır; 5 dk'yı aşan pending
    # çökmüş sayılır ve yeniden üretime izin verilir.
    if row.ai_draft_status == "pending" and row.ai_draft_at:
        ts = row.ai_draft_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - ts < timedelta(minutes=5):
            return {"ok": False, "hata": "Taslak zaten üretiliyor."}

    row.ai_draft_status = "pending"
    row.ai_draft_at = datetime.now(timezone.utc)
    db.session.commit()

    onceki_taslak = mevcut_metin or row.ai_draft
    renk = question_renk(row.product_main_id, row.product_name)
    from trendyol_qna.qna_service import model_hafizasi, model_notu, musteri_gecmisi
    gecmis = musteri_gecmisi([row.customer_id]).get(row.customer_id, [])
    taslak = _run_ai(_draft_prompt(
        row, stock_context(row.product_main_id),
        talimat=talimat, mevcut_metin=mevcut_metin, renk=renk, gecmis=gecmis,
        model_cevaplari=model_hafizasi(row.product_main_id, haric_id=row.id,
                                       haric_musteri=row.customer_id),
        model_notu=model_notu(row.product_main_id, renk),
        uretim_modu=_uretim_modunda(row.product_main_id)))
    if taslak:
        if talimat:
            # Düzeltme talimatını ders olarak bilgi bankasına not düş
            from trendyol_qna.qna_notes import log_correction
            log_correction(row.product_name, row.product_main_id, row.text,
                           talimat, onceki_taslak, taslak[:ANSWER_MAX], renk=renk)
        row.ai_draft = taslak[:ANSWER_MAX]
        row.ai_draft_status = "ready"
        row.ai_draft_at = datetime.now(timezone.utc)
        db.session.commit()
        return {"ok": True, "taslak": row.ai_draft}

    row.ai_draft_status = "failed"
    db.session.commit()
    return {"ok": False, "hata": "AI taslak üretilemedi (sunucu loglarına bakın)."}


def _shopify_draft_prompt(row, stok_bilgisi: str | None = None,
                          talimat: str | None = None,
                          mevcut_metin: str | None = None) -> str:
    kanal = "e-posta" if row.contact_type == "email" else "WhatsApp"
    sku = getattr(row, "product_sku", "") or ""
    if sku:
        stok_satiri = (
            f"Model kodu: {sku}\n"
            f"CANLI STOK: {stok_bilgisi or 'alınamadı'}\n"
        )
    else:
        stok_satiri = (
            "Model kodu bilinmiyor; stok bilgisi gerekiyorsa mcp__gulludb__query ile "
            "ürün adından bakabilirsin, emin olamazsan stok sözü verme.\n"
        )
    prompt = (
        "Bu soru Trendyol'dan DEĞİL, kendi sitemizden (gullushoes.com) geldi; "
        f"cevap müşteriye {kanal} ile iletilecek. Trendyol'a özgü ifadeler kullanma.\n"
        f"Ürün: {row.product_title or 'belirtilmemiş (genel soru)'}\n"
        f"Soru sorulan sayfa: {row.page_url or 'bilinmiyor'}\n"
        + stok_satiri +
        f"\nMüşteri sorusu:\n{row.question}\n\n"
    )
    if talimat:
        prompt += (
            f"Mevcut taslak (panelde görünen hali):\n{mevcut_metin or row.ai_draft or '(boş)'}\n\n"
            f"Kullanıcının düzeltme talimatı: {talimat}\n\n"
            "Mevcut taslağı bu talimata göre düzelt; talimatın dokunmadığı kısımları koru. "
            "Kurallara uygun, müşteriye gönderilmeye hazır TEK bir cevap taslağı yaz."
        )
    else:
        prompt += "Bu soruya kurallara uygun, müşteriye gönderilmeye hazır TEK bir cevap taslağı yaz."
    return prompt


def generate_shopify_draft(question_id: int, talimat: str | None = None,
                           mevcut_metin: str | None = None) -> dict:
    """
    Shopify (site) sorusu için taslak üret ve kaydet (senkron; app context
    İÇİNDE çağrılmalı). Trendyol tarafındaki generate_draft ile aynı akış;
    model kodu/stok bağlamı ve bilgi bankası ders kaydı yoktur.
    """
    from models import db, ShopifyQuestion
    from trendyol_qna.qna_service import ANSWER_MAX, stock_context

    row = db.session.get(ShopifyQuestion, question_id)
    if not row:
        return {"ok": False, "hata": "Soru bulunamadı."}

    if row.ai_draft_status == "pending" and row.ai_draft_at:
        ts = row.ai_draft_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - ts < timedelta(minutes=5):
            return {"ok": False, "hata": "Taslak zaten üretiliyor."}

    row.ai_draft_status = "pending"
    row.ai_draft_at = datetime.now(timezone.utc)
    db.session.commit()

    # SKU paneldeki model koduyla eşleşirse canlı stok promptta hazır gelir;
    # eşleşmezse stock_context 'bulunamadı' der, AI stok sözü vermez.
    stok = stock_context(row.product_sku) if getattr(row, "product_sku", "") else None
    taslak = _run_ai(_shopify_draft_prompt(row, stok_bilgisi=stok,
                                           talimat=talimat, mevcut_metin=mevcut_metin))
    if taslak:
        row.ai_draft = taslak[:ANSWER_MAX]
        row.ai_draft_status = "ready"
        row.ai_draft_at = datetime.now(timezone.utc)
        db.session.commit()
        return {"ok": True, "taslak": row.ai_draft}

    row.ai_draft_status = "failed"
    db.session.commit()
    return {"ok": False, "hata": "AI taslak üretilemedi (sunucu loglarına bakın)."}


def generate_shopify_drafts_async(question_ids: list[int], talimat: str | None = None,
                                  mevcut_metin: str | None = None) -> None:
    """Shopify soruları için taslakları arka plan thread'inde sırayla üret."""
    if not question_ids:
        return

    def _worker():
        from app import app
        with app.app_context():
            for qid in question_ids:
                try:
                    generate_shopify_draft(qid, talimat=talimat, mevcut_metin=mevcut_metin)
                except Exception:
                    logger.exception("[QNA-AI] shopify taslak hatası (soru %s)", qid)

    t = threading.Thread(target=_worker, name="qna-ai-shopify-draft", daemon=True)
    t.start()


INSTAGRAM_BAGLAM_MESAJ = 12   # taslak için konuşmanın son kaç mesajı verilir


def _instagram_draft_prompt(conv, mesajlar, talimat: str | None = None,
                            mevcut_metin: str | None = None,
                            urun_bilgisi: str | None = None) -> str:
    from trendyol_qna.instagram_dm import TEXT_MAX

    if urun_bilgisi:
        # Ürünü kullanıcı konuşmaya elle bağladı: canlı site fiyatı/stok/bağlantı hazır
        urun_kismi = (
            f"Kullanıcı bu konuşmayı şu ürüne bağladı (gönderi değil, konuşma):\n{urun_bilgisi}\n"
            "Fiyat sorulduysa fiyatı bu listeden AYNEN yaz (yuvarlama, tahmin etme). Numara/stok "
            "sorulduysa listedeki stok durumuna göre cevapla. Mesajın sonuna ürün sayfası bağlantısını "
            "'Detaylar ve sipariş için:' diyerek ekle. Listede olmayan bir bilgi için söz verme.\n"
        )
    else:
        urun_kismi = (
            "Hangi üründen bahsettiği yalnızca yazışmadan anlaşılır; stok/fiyat gerekiyorsa "
            "mcp__gulludb__query ile bakabilirsin, emin olamazsan söz verme ve müşteriden "
            "ürünü (model/renk/numara) netleştirmesini iste.\n"
        )

    satirlar = []
    for m in mesajlar:
        kim = "Müşteri" if m.direction == "in" else "Biz"
        ek = f" [ek: {m.attachment_type}]" if m.attachment_type else ""
        satirlar.append(f"{kim}: {(m.text or '').strip()}{ek}")
    prompt = (
        "Bu mesaj Trendyol'dan DEĞİL, Instagram hesabımıza gelen direkt mesajdan (DM); "
        "cevap müşteriye Instagram mesajı olarak gidecek. Trendyol'a özgü ifadeler kullanma, "
        "mesajlaşma diline uygun kısa ve samimi yaz. "
        f"Cevap en fazla {TEXT_MAX} karakter olmalı.\n"
        f"Müşteri: {conv.name or 'bilinmiyor'}"
        f"{' (@' + conv.username + ')' if conv.username else ''}\n"
        + urun_kismi +
        "\nYazışma (eskiden yeniye):\n" + "\n".join(satirlar) + "\n\n"
    )
    if talimat:
        prompt += (
            f"Mevcut taslak (panelde görünen hali):\n{mevcut_metin or conv.ai_draft or '(boş)'}\n\n"
            f"Kullanıcının düzeltme talimatı: {talimat}\n\n"
            "Mevcut taslağı bu talimata göre düzelt; talimatın dokunmadığı kısımları koru. "
            "Kurallara uygun, müşteriye gönderilmeye hazır TEK bir cevap taslağı yaz."
        )
    else:
        prompt += ("Müşterinin cevaplanmamış son mesaj(lar)ına kurallara uygun, "
                   "gönderilmeye hazır TEK bir cevap taslağı yaz.")
    return prompt


def generate_instagram_draft(conv_id: int, talimat: str | None = None,
                             mevcut_metin: str | None = None) -> dict:
    """
    Instagram konuşması için taslak üret ve kaydet (senkron; app context
    İÇİNDE çağrılmalı). generate_shopify_draft ile aynı akış; bağlam tek soru
    değil konuşmanın son mesajlarıdır.
    """
    from models import db, InstagramConversation, InstagramMessage
    from trendyol_qna.instagram_dm import TEXT_MAX

    conv = db.session.get(InstagramConversation, conv_id)
    if not conv:
        return {"ok": False, "hata": "Konuşma bulunamadı."}

    if conv.ai_draft_status == "pending" and conv.ai_draft_at:
        ts = conv.ai_draft_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - ts < timedelta(minutes=5):
            return {"ok": False, "hata": "Taslak zaten üretiliyor."}

    conv.ai_draft_status = "pending"
    conv.ai_draft_at = datetime.now(timezone.utc)
    db.session.commit()

    mesajlar = (
        db.session.query(InstagramMessage)
        .filter_by(conversation_id=conv.id)
        .order_by(InstagramMessage.created_at.desc(), InstagramMessage.id.desc())
        .limit(INSTAGRAM_BAGLAM_MESAJ)
        .all()
    )[::-1]
    from trendyol_qna.instagram_urun import konusma_anahtari, urun_baglami
    try:
        urun_bilgisi = urun_baglami(konusma_anahtari(conv.id))
    except Exception:
        db.session.rollback()
        logger.exception("[QNA-AI] ürün bilgisi okunamadı (konuşma %s)", conv_id)
        urun_bilgisi = None
    taslak = _run_ai(_instagram_draft_prompt(conv, mesajlar, talimat=talimat,
                                             mevcut_metin=mevcut_metin,
                                             urun_bilgisi=urun_bilgisi))
    if taslak:
        conv.ai_draft = taslak[:TEXT_MAX]
        conv.ai_draft_status = "ready"
        conv.ai_draft_at = datetime.now(timezone.utc)
        db.session.commit()
        return {"ok": True, "taslak": conv.ai_draft}

    conv.ai_draft_status = "failed"
    db.session.commit()
    return {"ok": False, "hata": "AI taslak üretilemedi (sunucu loglarına bakın)."}


def generate_instagram_drafts_async(conv_ids: list[int], talimat: str | None = None,
                                    mevcut_metin: str | None = None) -> None:
    """Instagram konuşmaları için taslakları arka plan thread'inde sırayla üret."""
    if not conv_ids:
        return

    def _worker():
        from app import app
        with app.app_context():
            for cid in conv_ids:
                try:
                    generate_instagram_draft(cid, talimat=talimat, mevcut_metin=mevcut_metin)
                except Exception:
                    logger.exception("[QNA-AI] instagram taslak hatası (konuşma %s)", cid)

    t = threading.Thread(target=_worker, name="qna-ai-instagram-draft", daemon=True)
    t.start()


def _instagram_comment_draft_prompt(yorum, talimat: str | None = None,
                                    mevcut_metin: str | None = None,
                                    urun_bilgisi: str | None = None) -> str:
    from trendyol_qna.instagram_dm import TEXT_MAX

    if urun_bilgisi:
        urun_kismi = (
            f"\n{urun_bilgisi}\n"
            "Fiyat sorulduysa fiyatı bu listeden AYNEN yaz (yuvarlama, tahmin etme). Numara/stok "
            "sorulduysa listedeki stok durumuna göre cevapla. Mesajın sonuna ürün sayfası bağlantısını "
            "'Detaylar ve sipariş için:' diyerek ekle. Listede olmayan bir bilgi için söz verme.\n"
        )
    else:
        urun_kismi = (
            "\nBu gönderinin hangi ürüne ait olduğu panelde ONAYLANMAMIŞ. Fiyat, stok ya da ürün "
            "bağlantısı YAZMA; müşteriden hangi modeli/rengi/numarayı sorduğunu netleştirmesini iste.\n"
        )

    prompt = (
        "Bu soru Trendyol'dan DEĞİL, Instagram gönderimizin altına yazılmış bir yorumdan geldi. "
        "Cevap yorum sahibine özelden (Instagram direkt mesajı) gidecek; yorumun altına ayrıca "
        "kısa bir 'özelden yanıtladık' notu düşülüyor, o notu SEN yazma. Trendyol'a özgü ifadeler "
        f"kullanma, mesajlaşma diline uygun kısa ve samimi yaz. Cevap en fazla {TEXT_MAX} karakter olmalı.\n"
        f"Yorumu yazan: {'@' + yorum.username if yorum.username else 'bilinmiyor'}\n"
        f"Gönderinin açıklaması (hangi üründen bahsedildiği buradan anlaşılır):\n"
        f"{(yorum.media_caption or '(açıklama yok)')[:1200]}\n"
        + urun_kismi +
        f"\nMüşteri yorumu:\n{yorum.text}\n\n"
    )
    if talimat:
        prompt += (
            f"Mevcut taslak (panelde görünen hali):\n{mevcut_metin or yorum.ai_draft or '(boş)'}\n\n"
            f"Kullanıcının düzeltme talimatı: {talimat}\n\n"
            "Mevcut taslağı bu talimata göre düzelt; talimatın dokunmadığı kısımları koru. "
            "Kurallara uygun, müşteriye gönderilmeye hazır TEK bir cevap taslağı yaz."
        )
    else:
        prompt += "Bu yoruma kurallara uygun, özelden gönderilmeye hazır TEK bir cevap taslağı yaz."
    return prompt


def generate_instagram_comment_draft(yorum_id: int, talimat: str | None = None,
                                     mevcut_metin: str | None = None) -> dict:
    """Instagram yorumu için taslak üret ve kaydet (senkron; app context İÇİNDE çağrılmalı)."""
    from models import db, InstagramComment
    from trendyol_qna.instagram_dm import TEXT_MAX

    yorum = db.session.get(InstagramComment, yorum_id)
    if not yorum:
        return {"ok": False, "hata": "Yorum bulunamadı."}

    if yorum.ai_draft_status == "pending" and yorum.ai_draft_at:
        ts = yorum.ai_draft_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - ts < timedelta(minutes=5):
            return {"ok": False, "hata": "Taslak zaten üretiliyor."}

    yorum.ai_draft_status = "pending"
    yorum.ai_draft_at = datetime.now(timezone.utc)
    db.session.commit()

    from trendyol_qna.instagram_urun import urun_baglami
    try:
        urun_bilgisi = urun_baglami(yorum.media_id)
    except Exception:
        db.session.rollback()
        logger.exception("[QNA-AI] ürün bilgisi okunamadı (yorum %s)", yorum_id)
        urun_bilgisi = None
    taslak = _run_ai(_instagram_comment_draft_prompt(yorum, talimat=talimat,
                                                     mevcut_metin=mevcut_metin,
                                                     urun_bilgisi=urun_bilgisi))
    if taslak:
        yorum.ai_draft = taslak[:TEXT_MAX]
        yorum.ai_draft_status = "ready"
        yorum.ai_draft_at = datetime.now(timezone.utc)
        db.session.commit()
        return {"ok": True, "taslak": yorum.ai_draft}

    yorum.ai_draft_status = "failed"
    db.session.commit()
    return {"ok": False, "hata": "AI taslak üretilemedi (sunucu loglarına bakın)."}


def generate_instagram_comment_drafts_async(yorum_ids: list[int], talimat: str | None = None,
                                            mevcut_metin: str | None = None) -> None:
    """Instagram yorumları için taslakları arka plan thread'inde sırayla üret."""
    if not yorum_ids:
        return

    def _worker():
        from app import app
        with app.app_context():
            for yid in yorum_ids:
                try:
                    generate_instagram_comment_draft(yid, talimat=talimat, mevcut_metin=mevcut_metin)
                except Exception:
                    logger.exception("[QNA-AI] instagram yorum taslağı hatası (yorum %s)", yid)

    t = threading.Thread(target=_worker, name="qna-ai-instagram-comment-draft", daemon=True)
    t.start()


def generate_drafts_async(question_ids: list[int], talimat: str | None = None,
                          mevcut_metin: str | None = None) -> None:
    """Yeni sorular için taslakları arka plan thread'inde sırayla üret."""
    if not question_ids:
        return

    def _worker():
        from app import app
        with app.app_context():
            for qid in question_ids:
                try:
                    generate_draft(qid, talimat=talimat, mevcut_metin=mevcut_metin)
                except Exception:
                    logger.exception("[QNA-AI] taslak hatası (soru %s)", qid)

    t = threading.Thread(target=_worker, name="qna-ai-draft", daemon=True)
    t.start()
