"""
Trendyol "Ürün Sorularınız" Excel dışa aktarımlarını Soru-Cevap AI bilgi
bankasına (trendyol_qna/vault/gecmis-excel-ozeti.md) dönüştürür.

Kullanım:
    python scripts/import_qna_excel.py <excel1.xlsx> [excel2.xlsx ...]

Birden çok Excel verilirse hepsi birlikte işlenir ve özet dosyası BAŞTAN
yazılır (idempotent — aynı Excel'i tekrar vermek çift kayıt üretmez).
Beklenen kolonlar: Ürün İsmi, Marka, Model Kodu, Statü, Soru Detayı,
Soru Oluşturma Tarihi, Onaylanan Cevap, Cevaplanma Tarihi, Cevaplama Süresi (dk.)
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl  # noqa: E402

VAULT_DIR = Path(__file__).resolve().parent.parent / "trendyol_qna" / "vault"
OUT_MD = VAULT_DIR / "gecmis-excel-ozeti.md"

# Kategori başına dahil edilecek azami örnek Q&A sayısı (çeşitlilik için)
MAX_ORNEK = 10
# Sık kullanılan şablonlardan dahil edilecek azami adet
MAX_SABLON = 15

KATEGORILER = [
    ("stok / yeniden gelir mi", ["gelir mi", "gelecek mi", "stok", "tekrar", "var mı", "varmı", "mevcut"]),
    ("kalıp / beden tavsiyesi", ["kalıp", "tam kalıp", "dar mı", "geniş", "taraklı", "büyük mü", "küçük mü", "numara als", "beden"]),
    ("kargo / teslimat", ["kargo", "ne zaman gel", "teslim", "gönder", "yetişir"]),
    ("iade / değişim", ["iade", "değişim", "degisim"]),
    ("toptan / fatura", ["toptan", "fatura"]),
    ("fiyat / indirim", ["fiyat", "indirim", "pahalı", "kupon"]),
    ("ürün özelliği", ["topuk", "malzeme", "deri", "astar", "taban", "renk", "cm", "ölçü"]),
]


def kategori(soru: str) -> str:
    s = (soru or "").lower()
    for ad, anahtarlar in KATEGORILER:
        if any(a in s for a in anahtarlar):
            return ad
    return "diğer"


def oku(path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(h or "").strip() for h in rows[0]]

    def col(ad):
        for i, h in enumerate(header):
            if ad.lower() in h.lower():
                return i
        return None

    i_soru, i_cevap = col("Soru Detayı"), col("Onaylanan Cevap")
    i_urun, i_model = col("Ürün İsmi"), col("Model Kodu")
    if i_soru is None or i_cevap is None:
        print(f"UYARI: {path.name} beklenen kolonları içermiyor, atlandı.")
        return []

    kayitlar = []
    for r in rows[1:]:
        if not r or not r[i_soru] or not r[i_cevap]:
            continue
        kayitlar.append({
            "soru": str(r[i_soru]).strip(),
            "cevap": str(r[i_cevap]).strip(),
            "urun": str(r[i_urun] or "").strip() if i_urun is not None else "",
            "model": str(r[i_model] or "").strip() if i_model is not None else "",
        })
    return kayitlar


def main(paths: list[str]) -> None:
    tum = []
    for p in paths:
        pf = Path(p).expanduser()
        if not pf.exists():
            print(f"HATA: {pf} bulunamadı."); continue
        kayitlar = oku(pf)
        print(f"{pf.name}: {len(kayitlar)} soru-cevap okundu")
        tum.extend(kayitlar)
    if not tum:
        print("İşlenecek kayıt yok."); return

    # Sık şablonlar (aynı cevabın tekrar sayısı)
    sablonlar = Counter(k["cevap"] for k in tum)

    # Kategori bazlı çeşitli örnekler (aynı cevabı iki kez alma)
    gruplar: dict[str, list[dict]] = defaultdict(list)
    for k in tum:
        gruplar[kategori(k["soru"])].append(k)

    satirlar = [
        "# Geçmiş Soru-Cevap Özeti (Excel'den otomatik üretildi)",
        "",
        f"Toplam {len(tum)} gerçek soru-cevap işlendi. Bu örnekler mağazanın",
        "üslubunu ve bilgi tarzını gösterir. STOK bilgisi için daima canlı veriyi esas al.",
        "",
        "## Sık Kullanılan Şablon Cevaplar",
        "",
    ]
    for cevap, adet in sablonlar.most_common(MAX_SABLON):
        if adet < 3:
            break
        satirlar.append(f"- ({adet} kez) {cevap[:300]}")

    for ad in [k for k, _ in KATEGORILER] + ["diğer"]:
        grup = gruplar.get(ad) or []
        if not grup:
            continue
        satirlar += ["", f"## {ad.title()} ({len(grup)} soru)", ""]
        gorulen = set()
        ornek = 0
        for k in grup:
            anahtar = k["cevap"][:80]
            if anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            model = f" (model {k['model']})" if k["model"] else ""
            satirlar.append(f"- **Soru{model}:** {k['soru'][:250]}")
            satirlar.append(f"  **Cevap:** {k['cevap'][:350]}")
            ornek += 1
            if ornek >= MAX_ORNEK:
                break

    VAULT_DIR.mkdir(exist_ok=True)
    OUT_MD.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    print(f"OK: {OUT_MD} yazıldı ({len(satirlar)} satır). AI taslakları artık bu bilgiyi kullanır.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    main(sys.argv[1:])
