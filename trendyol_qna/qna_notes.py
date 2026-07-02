"""
Trendyol Soru-Cevap bilgi bankası (Obsidian-uyumlu vault).

trendyol_qna/vault/ altındaki tüm .md dosyaları AI taslak üretirken sistem
promptuna eklenir. Klasör Obsidian ile açılıp elle de düzenlenebilir:
- gecmis-excel-ozeti.md  → scripts/import_qna_excel.py üretir (geçmiş Excel'ler)
- onaylanan-cevaplar.md  → panelden gönderilen her cevap otomatik not düşülür
- (istediğin başka .md notları da buraya koyabilirsin — hepsi okunur)
"""
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

VAULT_DIR = Path(__file__).resolve().parent / "vault"
APPROVED_MD = VAULT_DIR / "onaylanan-cevaplar.md"

MAX_VAULT_CHARS = 30_000     # sistem promptuna eklenecek azami not hacmi
MAX_APPROVED_LINES = 1_200   # onaylanan-cevaplar.md bu satırı aşınca en eskiler silinir
IST = ZoneInfo("Europe/Istanbul")


def load_vault_notes(max_chars: int = MAX_VAULT_CHARS) -> str:
    """Vault'taki tüm .md notlarını (ada göre sıralı) birleştirip döndür."""
    if not VAULT_DIR.is_dir():
        return ""
    parcalar = []
    for md in sorted(VAULT_DIR.glob("*.md")):
        try:
            parcalar.append(f"## Not: {md.stem}\n\n{md.read_text(encoding='utf-8')}")
        except OSError:
            continue
    metin = "\n\n---\n\n".join(parcalar)
    if len(metin) > max_chars:
        # En güncel bilgiler dosyaların sonunda birikir (onaylanan cevaplar
        # sona eklenir) — taşarsa baştan değil SONDAN max_chars kadar al.
        metin = "...(eski notlar kırpıldı)...\n" + metin[-max_chars:]
    return metin


def log_approved_answer(product_name: str | None, model_kodu: str | None,
                        soru: str, cevap: str, username: str | None) -> None:
    """
    Panelden Trendyol'a gönderilen (insan onaylı) cevabı vault'a not düş.
    AI sonraki taslaklarda bu örneklerden öğrenir. Hata asla yükseltilmez.
    """
    try:
        VAULT_DIR.mkdir(exist_ok=True)
        if not APPROVED_MD.exists():
            APPROVED_MD.write_text(
                "# Onaylanan Cevaplar (otomatik)\n\n"
                "Panelden gönderilen insan onaylı cevaplar — en yenisi en altta.\n\n",
                encoding="utf-8",
            )
        tarih = datetime.now(IST).strftime("%d.%m.%Y %H:%M")
        blok = (
            f"\n### {tarih} — {(product_name or 'Ürün')[:70]}"
            f"{f' (model {model_kodu})' if model_kodu else ''}\n"
            f"- **Soru:** {(soru or '').strip()[:400]}\n"
            f"- **Onaylı cevap ({username or 'panel'}):** {(cevap or '').strip()[:600]}\n"
        )
        with APPROVED_MD.open("a", encoding="utf-8") as f:
            f.write(blok)

        # Dosya büyürse en eski kayıtları kırp (başlık + son kayıtlar kalır)
        satirlar = APPROVED_MD.read_text(encoding="utf-8").splitlines(keepends=True)
        if len(satirlar) > MAX_APPROVED_LINES:
            bas = satirlar[:4]
            kalan = satirlar[-(MAX_APPROVED_LINES - 4):]
            # Kırpma bir kaydın ortasına denk gelmesin: ilk tam kayıttan başla
            for i, s in enumerate(kalan):
                if s.startswith("### "):
                    kalan = kalan[i:]
                    break
            APPROVED_MD.write_text("".join(bas) + "".join(kalan), encoding="utf-8")
    except OSError:
        logger.exception("[QNA] onaylanan cevap notu yazılamadı")
