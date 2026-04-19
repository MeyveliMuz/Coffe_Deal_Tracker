"""Basit kahve çekirdeği .ico üretici.

Çok çözünürlüklü (16, 24, 32, 48, 64, 128, 256) .ico dosyası oluşturur.
Şeffaf arkaplan + iki-tonlu kahverengi gövde + pürüzsüz S-şeklinde çatlak.

Kullanım:
    python assets/make_icon.py
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


OUT = Path(__file__).resolve().parent / "icon.ico"
SIZES = [16, 24, 32, 48, 64, 128, 256]

# Palet
BEAN_DARK = (58, 32, 18, 255)      # alt / dış koyu kahve
BEAN_LIGHT = (135, 82, 45, 255)    # üst / vurgu açık kahve
SPLIT = (30, 16, 8, 255)           # ortadaki çatlak
HIGHLIGHT = (235, 190, 130, 190)   # parıltı
SHADOW = (0, 0, 0, 90)             # ince dış gölge


def draw_bean(size: int) -> Image.Image:
    # 4× supersample — yumuşak kenar
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Çekirdek gövdesi — hafif dikey oval (bean-like)
    pad_x = S * 0.18
    pad_y = S * 0.07
    bbox = [pad_x, pad_y, S - pad_x, S - pad_y]

    # İnce dış gölge (3D his)
    shadow_bbox = [bbox[0] + S * 0.01, bbox[1] + S * 0.03,
                   bbox[2] + S * 0.01, bbox[3] + S * 0.03]
    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow_layer).ellipse(shadow_bbox, fill=SHADOW)
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(S * 0.015))
    img = Image.alpha_composite(img, shadow_layer)
    d = ImageDraw.Draw(img)

    # Ana gövde — koyu
    d.ellipse(bbox, fill=BEAN_DARK)

    # Üst parıltılı bölge — biraz küçük oval, hafif yukarı
    inner_bbox = [bbox[0] + S * 0.04, bbox[1] + S * 0.015,
                  bbox[2] - S * 0.04, bbox[3] - S * 0.18]
    d.ellipse(inner_bbox, fill=BEAN_LIGHT)

    # Ortadaki pürüzsüz S-çatlak — polyline
    cx = S / 2
    top_y = bbox[1] + S * 0.05
    bot_y = bbox[3] - S * 0.05
    amp = S * 0.055  # salınım genişliği
    line_w = max(3, int(S * 0.04))

    num = 80
    points = []
    for i in range(num):
        t = i / (num - 1)  # 0..1
        y = top_y + t * (bot_y - top_y)
        # Tek salınımlı S: -sin(2πt) ile yumuşak sağ-sol-sağ kıvrım
        x_off = math.sin(t * math.pi * 2) * amp * 0.9
        points.append((cx + x_off, y))

    # Kalın polyline: çoklu line + yuvarlak uçlar için ellipse dot'lar
    for i in range(len(points) - 1):
        d.line([points[i], points[i + 1]], fill=SPLIT, width=line_w)
    # Her köşede küçük bir yuvarlak — kesikliği gizle
    r = line_w / 2
    for p in points[::2]:
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=SPLIT)

    # Sol üst parıltı — yumuşak ışık
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    hl_bbox = [bbox[0] + S * 0.12, bbox[1] + S * 0.06,
               bbox[0] + S * 0.42, bbox[1] + S * 0.22]
    od.ellipse(hl_bbox, fill=HIGHLIGHT)
    overlay = overlay.filter(ImageFilter.GaussianBlur(S * 0.018))
    img = Image.alpha_composite(img, overlay)

    # Küçült
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    images = [draw_bean(s) for s in SIZES]
    images[-1].save(
        OUT,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=images[:-1],
    )
    print(f"Yazıldı: {OUT} ({OUT.stat().st_size} bayt, {len(SIZES)} çözünürlük)")

    # Önizleme PNG
    preview = OUT.parent / "icon_preview.png"
    images[-1].save(preview)
    print(f"Önizleme: {preview}")


if __name__ == "__main__":
    main()
