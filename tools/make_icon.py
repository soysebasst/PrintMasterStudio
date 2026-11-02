"""Genera el icono de la app (rollo de impresión con hoja) en ICO y PNG."""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "src" / "printmaster" / "ui" / "assets"


def draw(size: int = 256) -> Image.Image:
    s = size / 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8 * s, 8 * s, 248 * s, 248 * s), radius=48 * s, fill=(31, 111, 219, 255))
    d.rectangle((64 * s, 92 * s, 192 * s, 214 * s), fill=(255, 255, 255, 255))
    d.rectangle((80 * s, 112 * s, 176 * s, 150 * s), fill=(126, 231, 135, 255))
    d.rectangle((80 * s, 160 * s, 150 * s, 170 * s), fill=(160, 170, 185, 255))
    d.rectangle((80 * s, 180 * s, 166 * s, 190 * s), fill=(160, 170, 185, 255))
    d.rounded_rectangle((40 * s, 56 * s, 216 * s, 96 * s), radius=20 * s, fill=(232, 236, 242, 255))
    d.ellipse((188 * s, 60 * s, 212 * s, 92 * s), fill=(190, 198, 210, 255))
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    big = draw(256)
    big.save(OUT / "printmaster.png")
    big.save(OUT / "printmaster.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                             (128, 128), (256, 256)])
    print("ok", OUT)
