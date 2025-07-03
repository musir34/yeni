#!/usr/bin/env python3
from PIL import Image, ImageDraw
import os

# Test PNG'si oluştur - basit border çizimi
def test_border():
    # A4 boyutları
    dpi = 300
    page_width_mm = 210
    page_height_mm = 297
    page_width_px = int((page_width_mm / 25.4) * dpi)
    page_height_px = int((page_height_mm / 25.4) * dpi)
    
    # Sayfa oluştur
    page = Image.new('RGB', (page_width_px, page_height_px), 'white')
    draw = ImageDraw.Draw(page)
    
    # Etiket boyutları
    label_width_mm = 63.33
    label_height_mm = 37.2
    label_width_px = int((label_width_mm / 25.4) * dpi)
    label_height_px = int((label_height_mm / 25.4) * dpi)
    
    # İlk etiket pozisyonu
    x = 100
    y = 100
    
    # Siyah kalın çerçeve çiz
    border_color = (0, 0, 0)
    border_width = 5
    
    draw.rectangle(
        [x, y, x + label_width_px - 1, y + label_height_px - 1],
        outline=border_color,
        width=border_width
    )
    
    # Test metni
    draw.text((x + 10, y + 10), "TEST BORDER", fill='red')
    draw.text((x + 10, y + 30), f"Size: {label_width_px}x{label_height_px}px", fill='blue')
    
    # Kaydet
    os.makedirs('static/generated', exist_ok=True)
    page.save('static/generated/test_border.png', 'PNG', dpi=(dpi, dpi))
    print(f"Test PNG kaydedildi: border boyut {label_width_px}x{label_height_px}px")

if __name__ == "__main__":
    test_border()