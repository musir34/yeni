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
    hedefler = bilgi.get("hedefler") or ["trendyol"]
    shopify_blok = ""
    if "shopify" in hedefler:
        shopify_blok = """
AYRICA SİTE (gullushoes.com) İÇİN RENK-NÖTR İÇERİK — sitede tüm renkler TEK üründe
toplanır, bu yüzden şu alanlar hiçbir renge özel olmamalı:
- "genel.h1": ürünün tam adı (60-85 karakter; renk adı GEÇMEZ; ör. "Rugan Fiyonk Tokalı Arkası Açık Topuklu Sandalet 9 cm Kadeh Topuk")
- "genel.seo_baslik": 50-60 karakter, sonu " - Güllü Shoes" ile biter, ana kelime önde
- "genel.seo_aciklama": 140-160 karakter; ana kelime + malzeme/kalıp + renk seçenekleri imasi + "35-41 numara"
- "genel.vurgu" / "genel.neden" (EN AZ 120 kelime) / "genel.kombin" (EN AZ 70 kelime):
  renk-nötr sürümler (renklerden toplu bahsedebilir)
- "genel.maddeler": ürüne özel 3-4 ek özellik maddesi ("<b>Detay</b> — açıklama")
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
{duzeltme_blok}{talimat_blok}{ozellik_blok}{shopify_blok}
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
  "ozellikler": {{"<ÖzellikAdı>": "<izinli değerlerden birebir seçim>"}},
  "genel": {{"h1": "...", "seo_baslik": "...", "seo_aciklama": "...", "vurgu": "...", "neden": "...", "kombin": "..."}}
}}
("genel" alanı yalnızca site içeriği istendiyse doldurulur; istenmediyse boş bırakılabilir.)"""


def _claude_calistir(prompt: str, gorsel_var: bool) -> str | None:
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
           "--append-system-prompt", KURALLAR,
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


def _run_ai(prompt: str, gorsel_var: bool) -> str | None:
    from ai_asistan.motor_ayar import aktif_motor, codex_model
    from ai_asistan.blueprint import _codex_calistir, BASE_DIR as AI_ASISTAN_DIR

    if aktif_motor(ALAN) != "codex":
        return _claude_calistir(prompt, gorsel_var)
    sonuc = _codex_calistir(prompt, KURALLAR, TIMEOUT_SN, cwd=AI_ASISTAN_DIR,
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
                         renk_secenekleri: str) -> str:
    """Site için RENK-NÖTR açıklama (tüm renkler tek üründe — tema kuralı)."""
    teknik = "\n".join(f"<li>{t}</li>" for t in bilgi.get("teknik") or [])
    beden = bilgi.get("beden_araligi", "35-41")
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
<p>{renk_secenekleri}</p>
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
