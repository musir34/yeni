"""
AI asistanı için kendini güncelleyen bilgi eki.

Komutan emri (2026-10-14): asistan "neyin nerede olduğunu" bilsin ve yeni eklenen
şeyleri de kendiliğinden öğrensin. İki kaynak her soruda taze üretilir:

1. Proje notları dizini — repo `memory/` klasöründeki geliştirme notları (her
   değişiklikte oraya not yazılır; proje kuralı). Dosya adı + başlık + kısa özet.
   Yeni not eklendikçe asistan ek iş yapılmadan öğrenir.
2. Canlı şema özeti — information_schema'dan tablo/sütun listesi (sql_kopru.sema_ozeti).
   Yeni tablo/kolon açıldıkça kendiliğinden görünür. AI_DB_URL yoksa sessizce atlanır.

Vault'taki `40_veri_haritasi.md` elle derlenmiş "hangi bilgi nerede" haritasıdır; bu
modül onu tamamlar, yerine geçmez. Hiçbir hata asistanı durdurmaz: bölüm boş kalır.
"""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_KOK = Path(__file__).resolve().parent.parent
NOT_DIZINI = REPO_KOK / "memory"

NOT_OZET_KARAKTER = 420        # not başına özet sınırı
DIZIN_TOPLAM_KARAKTER = 45_000  # dizinin tamamı için üst sınır (en yeni notlar önce)

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_DESCRIPTION = re.compile(r"^description:\s*(.+)$", re.M)


def _not_ozeti(yol: Path) -> tuple[str, str] | None:
    """(başlık, özet) — okunamaz/boşsa None."""
    try:
        metin = yol.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    baslik = ""
    fm = _FRONTMATTER.match(metin)
    if fm:
        d = _DESCRIPTION.search(fm.group(1))
        if d:
            baslik = d.group(1).strip().strip('"').strip("'")
        metin = metin[fm.end():]
    satirlar = [s.strip() for s in metin.splitlines()]
    if not baslik:
        for s in satirlar:
            if s.startswith("#"):
                baslik = s.lstrip("#").strip()
                break
    govde = " ".join(s for s in satirlar if s and not s.startswith("#") and not s.startswith("---"))
    govde = re.sub(r"\s+", " ", govde)
    if len(govde) > NOT_OZET_KARAKTER:
        govde = govde[:NOT_OZET_KARAKTER].rsplit(" ", 1)[0] + "…"
    if not baslik and not govde:
        return None
    return baslik or yol.stem, govde


def proje_notlari_dizini() -> str:
    """memory/*.md notlarının dizini; en yeni notlar önce, toplam boyut sınırlı."""
    if not NOT_DIZINI.is_dir():
        return ""
    try:
        dosyalar = sorted(NOT_DIZINI.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        logger.warning("[BILGI-DIZINI] memory/ listelenemedi", exc_info=True)
        return ""
    satirlar, toplam, atlanan = [], 0, 0
    for yol in dosyalar:
        ozet = _not_ozeti(yol)
        if ozet is None:
            continue
        baslik, govde = ozet
        satir = f"- `{yol.name}` — **{baslik}**" + (f": {govde}" if govde else "")
        if toplam + len(satir) > DIZIN_TOPLAM_KARAKTER:
            atlanan += 1
            continue
        satirlar.append(satir)
        toplam += len(satir)
    if not satirlar:
        return ""
    kuyruk = f"\n\n(+{atlanan} eski not sığmadı)" if atlanan else ""
    return (
        "# Proje Notları Dizini (geliştirme hafızası; otomatik üretilir, en yeni önce)\n"
        "Panelde yapılan her değişiklik `memory/` klasörüne not olarak düşer. Bir özellik,\n"
        "tablo veya iş kuralı sorulduğunda ilgili notun özeti burada; notta geçen tablo/kolon\n"
        "adları sorgunun kaynağıdır. 'Deploy bekliyor' ibaresi: kod yazıldı, canlıda olmayabilir.\n\n"
        + "\n".join(satirlar) + kuyruk
    )


def canli_sema_ozeti() -> str:
    """information_schema'dan tablo(kolon tip, …) listesi; bağlantı yoksa boş."""
    try:
        from ai_asistan.sql_kopru import sema_ozeti
        ozet = sema_ozeti()
    except Exception:
        logger.warning("[BILGI-DIZINI] şema özeti alınamadı", exc_info=True)
        return ""
    if not ozet or ozet.startswith("("):
        return ""
    return (
        "# Canlı Şema Özeti (public; otomatik üretilir — yeni tablo/kolon burada görünür)\n"
        "Biçim: tablo(kolon tip, …). Tablo adını tahmin etme; burada ara.\n\n" + ozet
    )


def bilgi_eki(sema: bool = False) -> str:
    """Sistem promptunun sonuna eklenecek bölümler (boş bölümler atlanır)."""
    bolumler = [proje_notlari_dizini()]
    if sema:
        bolumler.append(canli_sema_ozeti())
    bolumler = [b for b in bolumler if b]
    return ("\n\n---\n\n" + "\n\n---\n\n".join(bolumler)) if bolumler else ""
