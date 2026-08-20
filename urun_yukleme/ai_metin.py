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
    return f"""Yeni ürün için Trendyol içeriği üret.
{talimat_blok}
ÜRÜN BİLGİLERİ
- Kategori: {bilgi.get('kategori_yolu', '')}
- Ürün türü öbeği (ana arama kelimesi): {bilgi.get('urun_turu', '')}
- Renkler: {renkler}
- Beden aralığı: {bilgi.get('beden_araligi', '')}
- Teknik özellikler:
{teknik}
- Satıcı notu (varsa tasarım detayı): {bilgi.get('not', '') or '-'}
{gorsel_notu}
İSTENEN JSON (bire bir bu şema, her renk için ayrı):
{{
  "renkler": {{
    "<RenkAdı>": {{
      "baslik": "<95-100 karakter başlık>",
      "vurgu": "<öne çıkanların ilk maddesi: renge/detaya özel tek cümle, kalın kısım — açıklama>",
      "neden": "<NEDEN BU MODEL paragrafı, 4-6 cümle, renge özel>",
      "kombin": "<KOMBİN ÖNERİLERİ paragrafı, 3-5 cümle, renge özel>"
    }}
  }},
  "renk_secenekleri": "<tüm renkleri tek cümlede tanıtan paragraf: 'Bu model (X) ... renklerinde üretilmektedir: ...'>"
}}"""


def _claude_calistir(prompt: str, gorsel_var: bool) -> str | None:
    from ai_asistan.blueprint import _claude_bin, BASE_DIR as AI_ASISTAN_DIR, CLAUDE_MODEL

    claude_bin = _claude_bin()
    if not claude_bin:
        logger.warning("[URUN-AI] claude binary bulunamadı")
        return None
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith("ANTHROPIC")
                   or (k.startswith("CLAUDE") and k not in ("CLAUDE_BIN", "CLAUDE_CODE_OAUTH_TOKEN")))}
    cmd = [claude_bin, "-p", prompt, "--model", CLAUDE_MODEL,
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
