"""Genera geoform/assets/geoform.ico (+ .png): tres estratos isométricos apilados sobre
un cuadrado redondeado en degradado, paleta del tema.  python docs/make_icon.py"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "geoform", "assets", "geoform.ico")
S = 1024  # se dibuja grande y se reduce (antialiasing)
# estratos de arriba a abajo: (cara superior, cara izquierda, cara derecha)
SLABS = [("#5eead4", "#2dd4bf", "#14b8a6"),
         ("#7dd3fc", "#38bdf8", "#0ea5e9"),
         ("#a5b4fc", "#818cf8", "#6366f1")]


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def background():
    y = np.linspace(0, 1, S)[:, None]
    top, bot = np.array(rgb("#1e293b")), np.array(rgb("#0b1220"))
    grad = (top * (1 - y) + bot * y)[:, None, :].repeat(S, axis=1).reshape(S, S, 3)
    im = Image.fromarray(grad.astype(np.uint8)).convert("RGBA")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, S - 40, S - 40), radius=230, fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(im, mask=mask)
    ImageDraw.Draw(out).rounded_rectangle((40, 40, S - 40, S - 40), radius=230, outline=(255, 255, 255, 28), width=6)
    return out


def slab(d, cx, y, w, t, cols):
    """Prisma isométrico: techo en rombo (y = vértice superior), espesor t."""
    k = w * 0.5
    T, R, F, L = (cx, y), (cx + w, y + k), (cx, y + 2 * k), (cx - w, y + k)
    top, left, right = cols
    d.polygon([L, F, (F[0], F[1] + t), (L[0], L[1] + t)], fill=left)
    d.polygon([F, R, (R[0], R[1] + t), (F[0], F[1] + t)], fill=right)
    d.polygon([T, R, F, L], fill=top)
    d.line([L, F, R], fill=(255, 255, 255, 90), width=5)  # brillo en las aristas frontales


def draw():
    im = background()
    fg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(fg)
    cx, w, t, gap = S / 2, 285, 86, 60
    y0 = 205
    for i, cols in reversed(list(enumerate(SLABS))):  # de abajo hacia arriba
        slab(d, cx, y0 + i * (t + gap), w, t, cols)
    # sombra suave bajo el bloque
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((cx - 280, 770, cx + 280, 850), fill=(0, 0, 0, 120))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(28)))
    im.alpha_composite(fg)
    return im


if __name__ == "__main__":
    img = draw()
    img.save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.resize((256, 256), Image.LANCZOS).save(OUT.replace(".ico", ".png"))
    print("icono:", OUT)
