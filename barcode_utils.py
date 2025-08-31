# barcode_utils.py
import io, base64
from barcode import get as get_barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont

def generate_barcode_data_uri(value: str) -> str:
    # python-barcode görseli bellekte üret
    writer_opts = {
        "write_text": False,      # alt yazıyı biz basacağız
        "module_width": 0.2,
        "module_height": 15.0,
        "quiet_zone": 4.0,
    }
    bc = get_barcode("code128", value, writer=ImageWriter())
    img = bc.render(writer_opts)                 # PIL.Image

    # Altına yazı ekle (Pillow 10+: textbbox)
    w, h = img.size
    text = value
    text_h = 28
    canvas = Image.new("RGB", (w, h + text_h), "white")
    canvas.paste(img, (0, 0))

    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((w - tw) // 2, h + (text_h - th) // 2), text, fill="black", font=font)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{data}"



# barcode_utils.py
import os, io, base64
from barcode import get as get_barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont

def _draw_text_below(img, text, font_name="arial.ttf", font_size=16, extra_h=28):
    """Barkodun altına yazıyı ekler (Pillow 10+ uyumlu)."""
    w, h = img.size
    canvas = Image.new("RGB", (w, h + extra_h), "white")
    canvas.paste(img, (0, 0))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(font_name, font_size)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (w - tw) // 2
    y = h + (extra_h - th) // 2
    draw.text((x, y), text, fill="black", font=font)
    return canvas

def generate_barcode_data_uri(value: str) -> str:
    """Dosyaya KAYDETMEDEN barkodu base64 (data URI) olarak döndürür."""
    writer_opts = {
        "write_text": False,    # getsize hatasını by-pass
        "module_width": 0.2,
        "module_height": 15.0,
        "quiet_zone": 4.0,
    }
    bc = get_barcode("code128", value, writer=ImageWriter())
    pil_img = bc.render(writer_opts)          # PIL.Image
    final_img = _draw_text_below(pil_img, value)

    buf = io.BytesIO()
    final_img.save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{data}"

def generate_barcode(value: str,
                     out_dir: str = os.path.join("static", "barcodes"),
                     filename: str | None = None) -> str:
    """
    Geri uyumlu fonksiyon: barkodu DOSYAYA kaydeder, STATIC'e göre RELATIF path döner.
    Eski kodlarda url_for('static', filename=returned_path) ile çalışır.
    """
    os.makedirs(out_dir, exist_ok=True)
    name = filename or f"bc_{value}"

    writer_opts = {
        "write_text": False,    # python-barcode yazıyı çizmesin
        "module_width": 0.2,
        "module_height": 15.0,
        "quiet_zone": 4.0,
    }
    bc = get_barcode("code128", value, writer=ImageWriter())
    pil_img = bc.render(writer_opts)
    final_img = _draw_text_below(pil_img, value)

    fs_path = os.path.join(out_dir, f"{name}.png")
    final_img.save(fs_path, format="PNG")

    # url_for('static', filename=...) için relatife çevir (çift /static sorununu önler)
    rel = os.path.relpath(fs_path, "static").replace("\\", "/")  # örn: "barcodes/bc_123.png"
    return rel
