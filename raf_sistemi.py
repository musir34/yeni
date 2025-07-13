import os
import json
import qrcode
import barcode
from barcode.writer import ImageWriter

RAF_VERISI_DOSYA = "raf_verileri.json"

# Dosya yoksa oluştur
if not os.path.exists(RAF_VERISI_DOSYA):
    with open(RAF_VERISI_DOSYA, "w") as f:
        json.dump([], f)

def raf_var_mi(kod):
    with open(RAF_VERISI_DOSYA) as f:
        raflar = json.load(f)
    return any(r["kod"] == kod for r in raflar)

def raf_olustur():
    print("Raf oluşturma başlatıldı...")

    ana_kod = input("Ana raf kodu (örnek A): ").strip().upper()
    ikincil_kod = input("İkincil kod (örnek B): ").strip().upper()
    kat = input("Kat (örnek 01): ").zfill(2)

    tam_kod = f"{ana_kod}-{ikincil_kod}-{kat}"

    if raf_var_mi(tam_kod):
        print("❌ Bu raf kodu zaten kullanılıyor.")
        return

    print(f"✅ Raf oluşturuluyor: {tam_kod}")

    # Barkod ve QR üret
    barcode_path = f"static/barcode_{tam_kod}.png"
    qr_path = f"static/qr_{tam_kod}.png"

    # Barcode
    code128 = barcode.get("code128", tam_kod, writer=ImageWriter())
    code128.save(barcode_path.replace(".png", ""))

    # QR
    img = qrcode.make(tam_kod)
    img.save(qr_path)

    # JSON'a kaydet
    with open(RAF_VERISI_DOSYA) as f:
        raflar = json.load(f)

    raflar.append({
        "kod": tam_kod,
        "ana": ana_kod,
        "ikincil": ikincil_kod,
        "kat": kat,
        "barcode": barcode_path,
        "qr": qr_path
    })

    with open(RAF_VERISI_DOSYA, "w") as f:
        json.dump(raflar, f, indent=2)

    print(f"✅ Raf başarıyla kaydedildi ve görseller oluşturuldu.\nKod: {tam_kod}")

# Test için aktif edebilirsin
# raf_olustur()
