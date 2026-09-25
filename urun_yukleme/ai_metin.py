# -*- coding: utf-8 -*-
"""
AI ile başlık + açıklama üretimi (motor: panel ayarı > .env AI_MOTOR).

Yazım kuralları claude-science SEO araştırmasından süzülmüştür
(~/Documents/Shopify/codex-yazim-brifi.md + canlı yüklemelerde alınan dersler):
- Yapı: ana kelime önde → kalıp/malzeme → kullanım senaryosu → 35-41 → kapanış
- Başlık 95-100 karakter (kullanıcı standardı, kod zorunlu kılar)
- Fiyat/indirim, yıl, "ortopedik", uydurma rakam YASAK
- "trendyol", iade/garanti/kargo/değişim söylemleri YASAK (içerik reddi)

AI serbest HTML üretmez: alan alan JSON döndürür, açıklama HTML'i sunucuda
sabit iskeletle kurulur — politika ihlali iskelet düzeyinde imkânsızlaşır.
"""
import json
import logging
import os
import re
import subprocess

logger = logging.getLogger(__name__)

ALAN = "urun"  # ai_asistan.motor_ayar GECERLI_ALANLAR içindeki ad
TIMEOUT_SN = 240

_JSON_DESENI = re.compile(r"\{.*\}", re.S)

KURALLAR = """Sen Güllü Shoes'un (kadın ayakkabı, gullushoes.com) Trendyol içerik yazarısın.
SEO araştırmamızın kuralları (claude-science çıktısı) — HEPSİ ZORUNLU:
1) BAŞLIK: 95-100 karakter arası (boşluk dahil, kendin say ve doğrula). Renk adıyla başlar,
   ana arama öbeği önde (ör. "topuklu sandalet", "stiletto"), kalıp/detay ortada,
   kullanım senaryosu sonda. Marka adı YAZILMAZ (Trendyol otomatik ekler).
2) YASAK kelimeler (başlık+tüm metinlerde): trendyol, iade, garanti(li dahil), kargo,
   değişim, ortopedik, indirim, kampanya, fiyat, ücretsiz, yıl (2025/2026 gibi),
   link/telefon. Satış-iade koşulu ANLATILMAZ — sadece ürün özelliği anlatılır.
3) Uydurma rakam yok: beden aralığı ve verilen ölçüler dışında sayı kullanma.
4) Türkçe akıcılık > anahtar kelime; bozuk cümle kurma.
5) Mağazanın farklılaştırıcıları uygun yerde işlensin: vegan deri, hafızalı ped,
   yerli üretim, rahatlık.
SADECE istenen JSON'u döndür; başka hiçbir şey yazma."""


def _prompt(bilgi: dict) -> str:
    renkler = ", ".join(bilgi.get("renkler") or [])
    teknik = "\n".join(f"- {t}" for t in bilgi.get("teknik") or [])
    ozellik_katalogu = bilgi.get("ozellik_katalogu") or {}
    ozellik_blok = ""
    secmeli = ozellik_katalogu.get("secmeli") or {}
    serbest = ozellik_katalogu.get("serbest") or []
    if secmeli or serbest:
        satirlar = "\n".join(
            f"- {ad}: {' | '.join(degerler)}" for ad, degerler in secmeli.items())
        serbest_blok = (
            "\nŞu özellikler SERBEST METİNDİR — ürüne uygun KISA bir değeri kendin yaz "
            "(yer tutucu/parantezli cevap yazma):\n"
            + "\n".join(f"- {ad}" for ad in serbest) + "\n"
        ) if serbest else ""
        ozellik_blok = f"""
TRENDYOL ÖZELLİK SEÇİMİ — aşağıdaki HER özellik için, verilen izinli değerlerden
ürüne en uygun BİRİNİ seç (değeri birebir aynı yazımla döndür; emin olamadığını atla):
{satirlar}
{serbest_blok}"""
    gorseller = "\n".join(f"- {g}" for g in bilgi.get("gorsel_yollari") or [])
    gorsel_notu = (
        f"\nHer rengin ilk görselinin dosya yolu aşağıda; Read aracıyla AÇIP BAK ve "
        f"ürünü gördüğün haliyle anlat (toka/fiyonk/taş gibi detayları atlama):\n{gorseller}\n"
        if gorseller else ""
    )
    talimat = (bilgi.get("genel_talimat") or "").strip()
    talimat_blok = (
        f"\nSATICININ KALICI TALİMATLARI (her üründe uygula; yasak listesiyle çelişirse yasak kazanır):\n{talimat}\n"
        if talimat else ""
    )
    aktarim_blok = ""
    if bilgi.get("trendyol_aciklama"):
        aktarim_blok = f"""
BU ÜRÜN TRENDYOL'DAN AKTARILIYOR. Mevcut Trendyol açıklaması aşağıda — içindeki
ürün bilgilerini/karakterini KAYNAK olarak kullan ama metni birebir kopyalama,
site için yeniden yaz:
--- TRENDYOL AÇIKLAMASI ---
{bilgi['trendyol_aciklama'][:4000]}
---
"""
    duzeltme_blok = ""
    if bilgi.get("duzeltme_talimati"):
        onceki = bilgi.get("onceki_metin") or {}
        duzeltme_blok = f"""
BU BİR REVİZYONDUR. Önceki üretim aşağıda; satıcının düzeltme talebini uygula,
istenmeyen kısımları koru (baştan yazma, talebi işle):
--- ÖNCEKİ ÜRETİM (JSON) ---
{json.dumps(onceki, ensure_ascii=False)[:6000]}
--- SATICININ DÜZELTME TALEBİ ---
{bilgi['duzeltme_talimati']}
"""
    return f"""Yeni ürün için Trendyol içeriği üret.
{aktarim_blok}{duzeltme_blok}{talimat_blok}{ozellik_blok}
ÜRÜN BİLGİLERİ
- Kategori: {bilgi.get('kategori_yolu', '')}
- ÜRÜN TÜRÜ ÖBEĞİ (ZORUNLU): "{bilgi.get('urun_turu', '')}" — bu öbek HER başlıkta
  birebir geçmeli ve açıklamaların ana ekseni olmalı.
- SATICI NOTU (ZORUNLU DETAYLAR): "{bilgi.get('not', '') or '-'}" — buradaki her
  detayı hem başlıklarda hem açıklamalarda mutlaka işle; bunlar ürünün ayırt edici
  özellikleridir, atlanamaz.
- Renkler: {renkler}
- Beden aralığı: {bilgi.get('beden_araligi', '')}
- Teknik özellikler:
{teknik}

UZUNLUK ŞARTLARI (kısa metin KABUL EDİLMEZ):
- Her rengin "neden" paragrafı EN AZ 120 kelime (5-8 cümle, renge özel, satıcı notundaki detayları işleyerek)
- Her rengin "kombin" paragrafı EN AZ 70 kelime (4-6 cümle, takı/çanta uyumları dahil)
- Her rengin "maddeler" listesi: ürüne/renge özel 3-4 EK özellik maddesi
  ("<b>başlık</b> — açıklama" biçiminde; genel kalıpları değil, BU ürünün detaylarını yaz)
{gorsel_notu}
İSTENEN JSON (bire bir bu şema, her renk için ayrı):
{{
  "renkler": {{
    "<RenkAdı>": {{
      "baslik": "<95-100 karakter başlık — ürün türü öbeği ve satıcı notu detayları içinde>",
      "vurgu": "<öne çıkanların ilk maddesi: renge/detaya özel tek cümle>",
      "maddeler": ["<b>Detay</b> — açıklama", "... renge/ürüne özel 3-4 madde"],
      "neden": "<NEDEN BU MODEL paragrafı, EN AZ 120 kelime, renge özel>",
      "kombin": "<KOMBİN ÖNERİLERİ paragrafı, EN AZ 70 kelime, renge özel>"
    }}
  }},
  "renk_secenekleri": "<tüm renkleri tek cümlede tanıtan paragraf: 'Bu model (X) ... renklerinde üretilmektedir: ...'>",
  "ozellikler": {{"<ÖzellikAdı>": "<izinli değerlerden birebir seçim>"}}
}}"""


# ------------------------------------------------ SİTE (Shopify) — Google SEO
# Trendyol promptundan AYRI: platform kuralları farklı (Trendyol: 95-100 karakter
# başlık + içerik politikası; site: Google arama/görsel arama uyumu). İki hedef
# seçilince iki ayrı üretim yapılır — kullanıcı emri ("shopify için google ile
# uyumlu, trendyol için trendyol'a uygun").
KURALLAR_SITE = """Sen Güllü Shoes'un (kadın ayakkabı, gullushoes.com) web sitesi SEO içerik yazarısın.
Hedef: Google organik arama ve Google Görseller'de görünürlük. Kurallar — HEPSİ ZORUNLU:
1) Doğal, akıcı Türkçe; anahtar kelime yığmak YASAK (Google spam sayar). Ana arama öbeğini
   (ör. "topuklu sandalet") H1'de, SEO başlığında, meta açıklamada ve ilk paragrafta
   DOĞAL biçimde bir kez kullan.
2) H1 (ürün adı): 50-70 karakter, renk adı geçmez (sitede tüm renkler tek üründe).
3) SEO başlığı: 50-60 karakter, ana öbek önde, sonu " - Güllü Shoes" ile biter.
4) Meta açıklama: 140-160 karakter, ana öbek + malzeme/kalıp + renk çeşitliliği iması +
   "35-41 numara" + kullanıcıyı tıklamaya çağıran doğal bir kapanış.
5) Her renk için AYRI ve BENZERSİZ bir paragraf yaz (40-70 kelime): o rengin görünümü,
   hangi kombin/ortama uyduğu; şablon cümle tekrarı YASAK (Google yinelenen içerik).
6) YASAK: trendyol, iade, garanti, kargo, değişim, ortopedik, indirim, kampanya, fiyat,
   ücretsiz, yıl (2025/2026), link/telefon. Uydurma rakam yok.
7) Mağazanın farklılaştırıcıları uygun yerde: vegan deri, hafızalı ped, yerli üretim, rahatlık.
SADECE istenen JSON'u döndür; başka hiçbir şey yazma."""


def _site_prompt(bilgi: dict) -> str:
    renkler = ", ".join(bilgi.get("renkler") or [])
    teknik = "\n".join(f"- {t}" for t in bilgi.get("teknik") or [])
    gorseller = "\n".join(f"- {g}" for g in bilgi.get("gorsel_yollari") or [])
    gorsel_notu = (
        f"\nHer rengin ilk görselinin dosya yolu aşağıda; Read aracıyla AÇIP BAK ve "
        f"ürünü gördüğün haliyle anlat (toka/fiyonk/taş gibi detayları atlama):\n{gorseller}\n"
        if gorseller else ""
    )
    talimat = (bilgi.get("genel_talimat") or "").strip()
    talimat_blok = (
        f"\nSATICININ KALICI TALİMATLARI (yasak listesiyle çelişirse yasak kazanır):\n{talimat}\n"
        if talimat else ""
    )
    aktarim_blok = ""
    if bilgi.get("trendyol_aciklama"):
        aktarim_blok = f"""
Ürün Trendyol'da da satılıyor; mevcut açıklaması KAYNAK olarak aşağıda — bilgileri
kullan ama birebir kopyalama, site için Google uyumlu yeniden yaz:
--- TRENDYOL AÇIKLAMASI ---
{bilgi['trendyol_aciklama'][:4000]}
---
"""
    duzeltme_blok = ""
    if bilgi.get("duzeltme_talimati"):
        onceki = (bilgi.get("onceki_metin") or {}).get("shopify") or {}
        duzeltme_blok = f"""
BU BİR REVİZYONDUR. Önceki site üretimi aşağıda; satıcının düzeltme talebini uygula,
istenmeyen kısımları koru:
--- ÖNCEKİ ÜRETİM (JSON) ---
{json.dumps(onceki, ensure_ascii=False)[:6000]}
--- SATICININ DÜZELTME TALEBİ ---
{bilgi['duzeltme_talimati']}
"""
    return f"""gullushoes.com için Google SEO uyumlu ürün içeriği üret.
{aktarim_blok}{duzeltme_blok}{talimat_blok}
ÜRÜN BİLGİLERİ
- Kategori: {bilgi.get('kategori_yolu', '')}
- ÜRÜN TÜRÜ ÖBEĞİ (ana arama öbeği, ZORUNLU): "{bilgi.get('urun_turu', '')}"
- SATICI NOTU (ZORUNLU DETAYLAR): "{bilgi.get('not', '') or '-'}" — ayırt edici özellikler, atlanamaz.
- Renkler: {renkler}
- Beden aralığı: {bilgi.get('beden_araligi', '')}
- Teknik özellikler:
{teknik}
{gorsel_notu}
UZUNLUK ŞARTLARI: "neden" EN AZ 120 kelime, "kombin" EN AZ 70 kelime, her renk paragrafı 40-70 kelime.

İSTENEN JSON (bire bir bu şema):
{{
  "genel": {{
    "h1": "<50-70 karakter ürün adı, renk adı yok>",
    "seo_baslik": "<50-60 karakter, sonu ' - Güllü Shoes'>",
    "seo_aciklama": "<140-160 karakter meta açıklama>",
    "vurgu": "<öne çıkan tek cümle, renk-nötr>",
    "maddeler": ["<b>Detay</b> — açıklama", "... ürüne özel 3-4 madde"],
    "neden": "<NEDEN BU MODEL paragrafı, EN AZ 120 kelime, renk-nötr>",
    "kombin": "<KOMBİN ÖNERİLERİ paragrafı, EN AZ 70 kelime, renk-nötr>"
  }},
  "renk_bolumleri": {{"<RenkAdı>": "<o renge özel benzersiz 40-70 kelimelik paragraf>"}},
  "renk_secenekleri": "<tüm renkleri tek cümlede tanıtan paragraf>"
}}"""


def site_metin_uret(bilgi: dict) -> dict:
    """Site (Shopify) içeriği: {"genel": {...}, "renk_bolumleri": {renk: str}, "renk_secenekleri": str}."""
    ham = _run_ai(_site_prompt(bilgi), gorsel_var=bool(bilgi.get("gorsel_yollari")),
                  kurallar=KURALLAR_SITE)
    if not ham:
        raise ValueError("AI motoru site içeriği için yanıt vermedi — motor ayarını kontrol edin.")
    eslesme = _JSON_DESENI.search(ham)
    if not eslesme:
        raise ValueError("Site içeriği AI çıktısı çözümlenemedi (JSON bulunamadı).")
    try:
        veri = json.loads(eslesme.group(0))
    except json.JSONDecodeError:
        raise ValueError("Site içeriği AI çıktısı geçerli JSON değil — tekrar deneyin.")
    if not isinstance(veri.get("genel"), dict) or not veri["genel"].get("h1"):
        raise ValueError("Site içeriğinde H1 üretilemedi — tekrar deneyin.")
    if not isinstance(veri.get("renk_bolumleri"), dict):
        veri["renk_bolumleri"] = {}
    return veri


# ------------------------------------------------ GÖRSEL BAŞINA ALT METNİ
# Google Görseller ALT metnini okur; her görsele AYRI, gördüğünü anlatan metin
# kullanıcı emriyle zorunlu. AI (claude yolu) görselleri Read ile açıp bakar;
# bakamayan motorda/hatada açı şablonuna düşülür — yükleme asla bloklanmaz.
KURALLAR_ALT = """Sen bir e-ticaret görsel SEO uzmanısın. Verilen ürün fotoğraflarının HER BİRİ için
Google Görseller'e uygun Türkçe ALT metni yaz. Kurallar:
- 60-125 karakter; her görsel için FARKLI metin (aynı cümleyi tekrarlama).
- Görselde gerçekten ne görünüyorsa onu yaz: açı (önden/yandan/arkadan/üstten),
  görünen detay (toka, fiyonk, topuk, taban, bilek bandı), ürün adı ve rengi.
- "resim", "görsel", "fotoğraf" kelimeleri ve anahtar kelime yığını YASAK.
- YASAK: trendyol, iade, garanti, kargo, indirim, fiyat, yıl, link/telefon.
SADECE istenen JSON'u döndür."""

_ACI_SABLONU = ["önden görünüm", "yandan görünüm", "arkadan görünüm", "topuk detayı",
                "üstten görünüm", "taban görünümü", "yakın detay", "kombin görünümü"]


def alt_sablon(renk: str, urun_adi: str, adet: int) -> list[str]:
    """AI'sız yedek ALT listesi (açı şablonu) — yine her görselde farklı metin."""
    return [f"{renk} {urun_adi} {_ACI_SABLONU[i % len(_ACI_SABLONU)]}".strip()[:125]
            for i in range(adet)]


def alt_uret(renk: str, gorsel_yollari: list[str], urun_adi: str) -> list[str]:
    """
    Rengin görselleri için ALT listesi (görsel sırasıyla). Claude yolu görsellere
    bakar; codex yolu görsel açamaz → şablon. Hatada da şablon (loglanır).
    """
    from ai_asistan.motor_ayar import aktif_motor
    adet = len(gorsel_yollari)
    if not adet:
        return []
    if aktif_motor(ALAN) == "codex":
        return alt_sablon(renk, urun_adi, adet)
    liste = "\n".join(f"{i + 1}. {y}" for i, y in enumerate(gorsel_yollari))
    prompt = f"""Ürün: "{urun_adi}" — Renk: {renk}
Aşağıdaki {adet} fotoğrafı Read aracıyla SIRAYLA aç ve her biri için ALT metni yaz:
{liste}

İSTENEN JSON: {{"alt": ["<1. görsel ALT>", "<2. görsel ALT>", ...]}} — tam {adet} eleman, aynı sırayla."""
    ham = _run_ai(prompt, gorsel_var=True, kurallar=KURALLAR_ALT)
    try:
        veri = json.loads(_JSON_DESENI.search(ham or "").group(0))
        altlar = [str(a).strip()[:125] for a in veri.get("alt") or []]
    except (AttributeError, json.JSONDecodeError, TypeError):
        altlar = []
    if len(altlar) != adet or not all(altlar):
        logger.warning("[URUN-AI] %s için ALT üretimi eksik (%d/%d) — şablona düşüldü",
                       renk, len(altlar), adet)
        yedek = alt_sablon(renk, urun_adi, adet)
        altlar = [(altlar[i] if i < len(altlar) and altlar[i] else yedek[i]) for i in range(adet)]
    return altlar


def _claude_calistir(prompt: str, gorsel_var: bool, kurallar: str = KURALLAR) -> str | None:
    from ai_asistan.blueprint import _claude_bin, BASE_DIR as AI_ASISTAN_DIR, CLAUDE_MODEL

    claude_bin = _claude_bin()
    if not claude_bin:
        logger.warning("[URUN-AI] claude binary bulunamadı")
        return None
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith("ANTHROPIC")
                   or (k.startswith("CLAUDE") and k not in ("CLAUDE_BIN", "CLAUDE_CODE_OAUTH_TOKEN")))}
    from .katalog import claude_model_getir
    try:
        model = claude_model_getir() or CLAUDE_MODEL
    except Exception:
        model = CLAUDE_MODEL
    cmd = [claude_bin, "-p", prompt, "--model", model,
           "--append-system-prompt", kurallar,
           "--output-format", "json"]
    if gorsel_var:
        cmd += ["--allowedTools", "Read"]  # görselleri açıp bakabilsin
    try:
        sonuc = subprocess.run(cmd, cwd=str(AI_ASISTAN_DIR), env=env,
                               capture_output=True, text=True, timeout=TIMEOUT_SN)
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("[URUN-AI] claude çalıştırılamadı: %s", e)
        return None
    if sonuc.returncode != 0:
        logger.warning("[URUN-AI] claude hata: %s", (sonuc.stderr or "")[:300])
        return None
    try:
        data = json.loads(sonuc.stdout)
        return (data.get("result") or data.get("text") or "").strip() or None
    except (json.JSONDecodeError, AttributeError):
        return (sonuc.stdout or "").strip() or None


def _run_ai(prompt: str, gorsel_var: bool, kurallar: str = KURALLAR) -> str | None:
    from ai_asistan.motor_ayar import aktif_motor, codex_model
    from ai_asistan.blueprint import _codex_calistir, BASE_DIR as AI_ASISTAN_DIR

    if aktif_motor(ALAN) != "codex":
        return _claude_calistir(prompt, gorsel_var, kurallar)
    sonuc = _codex_calistir(prompt, kurallar, TIMEOUT_SN, cwd=AI_ASISTAN_DIR,
                            model=codex_model(ALAN))
    if not sonuc["ok"]:
        logger.warning("[URUN-AI] codex hata: %s", sonuc.get("hata"))
        return None
    return sonuc["cevap"] or None


def metin_uret(bilgi: dict) -> dict:
    """
    AI'dan renk başına başlık+metin alır. Dönen sözlük:
    {"renkler": {renk: {baslik, vurgu, neden, kombin}}, "renk_secenekleri": str}
    Hata durumunda ValueError (kullanıcıya gösterilecek Türkçe mesajla).
    """
    ham = _run_ai(_prompt(bilgi), gorsel_var=bool(bilgi.get("gorsel_yollari")))
    if not ham:
        raise ValueError("AI motoru yanıt vermedi — motor ayarını ve sunucu kurulumunu kontrol edin.")
    eslesme = _JSON_DESENI.search(ham)
    if not eslesme:
        raise ValueError("AI çıktısı çözümlenemedi (JSON bulunamadı).")
    try:
        veri = json.loads(eslesme.group(0))
    except json.JSONDecodeError:
        raise ValueError("AI çıktısı geçerli JSON değil — tekrar deneyin.")
    if not isinstance(veri.get("renkler"), dict) or not veri["renkler"]:
        raise ValueError("AI çıktısında renk içerikleri eksik — tekrar deneyin.")
    return veri


def shopify_aciklama_kur(genel: dict, bilgi: dict, renkler: list[str],
                         renk_secenekleri: str, renk_bolumleri: dict | None = None) -> str:
    """
    Site için RENK-NÖTR açıklama (tüm renkler tek üründe — tema kuralı).
    renk_bolumleri: {renk: paragraf} — sitede SEO başlığı/meta üründe TEK olduğundan
    renk bazlı Google görünürlüğü açıklama içindeki renk bölümlerinden gelir.
    """
    teknik = "\n".join(f"<li>{t}</li>" for t in bilgi.get("teknik") or [])
    beden = bilgi.get("beden_araligi", "35-41")
    renk_html = "".join(
        f"\n<h4>{r}</h4>\n<p>{(renk_bolumleri or {}).get(r, '')}</p>"
        for r in renkler if (renk_bolumleri or {}).get(r))
    return f"""
<p>{genel.get('vurgu', '')}</p>
<h3>✨ Öne Çıkan Özellikler</h3>
<ul>
{"".join(f"<li>{m}</li>" for m in (genel.get('maddeler') or []))}
<li><strong>Hafızalı ped</strong> — iç tabanda ayağın şeklini alarak baskıyı dağıtır, uzun süre ayakta kalmayı kolaylaştırır</li>
<li><strong>Kaymaz taban</strong> — parke ve mermer zeminde de açık havada da güvenli adım</li>
<li><strong>%100 vegan deri</strong> — hayvansal deri kullanılmadan üretilmiş, hayvan dostu ve etik tercih</li>
<li><strong>Türkiye üretimi</strong> — yerli işçilikle üretilen kalıp ve montaj kalitesi</li>
</ul>
<h3>📋 Teknik Ürün Bilgileri</h3>
<ul>
<li>Renk Seçenekleri: {", ".join(renkler)}</li>
{teknik}
<li>Kalıp: Tam kalıp — Beden Aralığı: {beden} — Menşei: Türkiye</li>
</ul>
<h3>💡 Neden Bu Model?</h3>
<p>{genel.get('neden', '')}</p>
<h3>👗 Kombin Önerileri</h3>
<p>{genel.get('kombin', '')}</p>
<h3>🎨 Renk Seçenekleri</h3>
<p>{renk_secenekleri}</p>{renk_html}
<h3>📏 Beden ve Uyum</h3>
<p>Ürün {beden} beden aralığında üretilmiştir ve tam kalıptır; normal numaranızı seçebilirsiniz.</p>
<h3>🧴 Bakım</h3>
<p>Yüzeyi nemli ve yumuşak bir bezle silin; deri cilası, boya veya çözücü içeren temizleyici kullanmayın. Kullanmadığınız dönemde kutusunda ve doğrudan güneş görmeyen bir yerde saklayın.</p>
<h3>🌱 Üretim ve Sürdürülebilirlik</h3>
<p>Bu ürün %100 vegan deriden üretilmiştir; hiçbir aşamasında hayvansal deri kullanılmaz. Hayvan dostu, etik ve sürdürülebilir üretim anlayışıyla Türkiye'de üretilmektedir.</p>
""".strip()


# --------------------------------------------------- açıklama HTML iskeleti

def aciklama_kur(renk: str, icerik: dict, bilgi: dict, renk_secenekleri: str) -> str:
    """Sabit iskeletle politika-uyumlu açıklama HTML'i (0121/0122'de onaylanan yapı)."""
    teknik = "\n".join(f"<li>{t}</li>" for t in bilgi.get("teknik") or [])
    beden = bilgi.get("beden_araligi", "35-41")
    return f"""
<p><b>GÜLLÜ SHOES — {renk.upper()} {bilgi.get('urun_turu', '').upper()}</b></p>
<p><b>✨ ÖNE ÇIKAN ÖZELLİKLER</b></p>
<ul>
<li><b>{icerik.get('vurgu', '')}</b></li>
{"".join(f"<li>{m}</li>" for m in (icerik.get('maddeler') or []))}
<li><b>Hafızalı ped</b> — iç tabanda ayağın şeklini alarak baskıyı dağıtır, uzun süre ayakta kalmayı kolaylaştırır</li>
<li><b>Kaymaz taban</b> — parke ve mermer zeminde de açık havada da güvenli adım</li>
<li><b>%100 vegan deri</b> — hayvansal deri kullanılmadan üretilmiş, hayvan dostu ve etik tercih</li>
<li><b>Türkiye üretimi</b> — yerli işçilikle üretilen kalıp ve montaj kalitesi</li>
</ul>
<p><b>📋 TEKNİK ÜRÜN BİLGİLERİ</b></p>
<ul>
<li>Renk: {renk}</li>
{teknik}
<li>Kalıp: Tam kalıp, normal numaranızı seçebilirsiniz</li>
<li>Beden Aralığı: {beden} — Menşei: Türkiye</li>
</ul>
<p><b>💡 NEDEN BU MODEL?</b></p>
<p>{icerik.get('neden', '')}</p>
<p><b>👗 KOMBİN ÖNERİLERİ</b></p>
<p>{icerik.get('kombin', '')}</p>
<p><b>🎨 RENK SEÇENEKLERİ</b></p>
<p>{renk_secenekleri}</p>
<p><b>📏 BEDEN VE UYUM</b></p>
<p>Ürün {beden} beden aralığında üretilmiştir ve tam kalıptır; normal numaranızı seçebilirsiniz.</p>
<p><b>🧴 BAKIM</b></p>
<p>Yüzeyi nemli ve yumuşak bir bezle silin; deri cilası, boya veya çözücü içeren temizleyici kullanmayın. Kullanmadığınız dönemde kutusunda ve doğrudan güneş görmeyen bir yerde saklayın.</p>
<p><b>🌱 ÜRETİM VE SÜRDÜRÜLEBİLİRLİK</b></p>
<p>Bu ürün %100 vegan deriden üretilmiştir; hiçbir aşamasında hayvansal deri kullanılmaz. Hayvan dostu, etik ve sürdürülebilir üretim anlayışıyla Türkiye'de üretilmektedir.</p>
""".strip()
