"""Generate the rose-window concept, then render all concepts into one comparison sheet."""

import math
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

out = Path(sys.argv[1])

cx = cy = 128
R, r = 104, 36
cols = ["#dc2626", "#f59e0b", "#16a34a", "#0891b2", "#2563eb", "#7c3aed", "#db2777", "#ea580c"]
glyphs = [
    ("A", "Segoe UI"),
    ("文", "Yu Gothic"),
    ("Ж", "Segoe UI"),
    ("α", "Segoe UI"),
    ("ع", "Segoe UI"),
    ("あ", "Yu Gothic"),
    ("한", "Malgun Gothic"),
    ("अ", "Nirmala UI"),
]
svg = [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">',
    "<!-- Rose window: a cathedral stained-glass rosette whose panes hold eight scripts. -->",
    '<rect width="256" height="256" rx="56" fill="#111827"/>',
]


def pt(angle, radius):
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


for i in range(8):
    a0, a1 = math.radians(i * 45 - 112.5), math.radians(i * 45 - 67.5)
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pt(a0, r), pt(a0, R), pt(a1, R), pt(a1, r)
    svg.append(
        f'<path d="M{x0:.1f} {y0:.1f} L{x1:.1f} {y1:.1f} A{R} {R} 0 0 1 {x2:.1f} {y2:.1f} '
        f'L{x3:.1f} {y3:.1f} A{r} {r} 0 0 0 {x0:.1f} {y0:.1f} Z" fill="{cols[i]}" '
        f'stroke="#111827" stroke-width="6" stroke-linejoin="round"/>'
    )
    gx, gy = pt((a0 + a1) / 2, 72)
    glyph, font = glyphs[i]
    svg.append(
        f'<text x="{gx:.1f}" y="{gy + 10:.1f}" font-family="{font}" font-weight="800" '
        f'font-size="28" fill="#fff" text-anchor="middle">{glyph}</text>'
    )
svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r - 3}" fill="#fde68a" stroke="#111827" stroke-width="6"/>')
svg.append(f'<circle cx="{cx}" cy="{cy}" r="{R + 2}" fill="none" stroke="#111827" stroke-width="8"/>')
svg.append(
    f'<text x="{cx}" y="{cy + 15}" font-family="Georgia" font-weight="700" font-size="44" '
    f'fill="#111827" text-anchor="middle">P</text></svg>'
)
(out / "5-rose.svg").write_text("\n".join(svg), encoding="utf-8")

app = QGuiApplication([])
items = [
    ("1-polly", "1  Polly, the glass parrot"),
    ("2-prism", "2  Prism"),
    ("3-octopus", "3  Glotto, the octopus"),
    ("4-spectacles", "4  The Look"),
    ("5-rose", "5  Rose window"),
    ("6-cocktail", "6  Polyglot cocktail"),
]
img = QImage(3 * 320 + 20, 2 * 420 + 20, QImage.Format_ARGB32)
img.fill(QColor("#e5e7eb"))
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
for i, (name, label) in enumerate(items):
    x, y = 20 + (i % 3) * 320, 20 + (i // 3) * 420
    renderer = QSvgRenderer(str(out / f"{name}.svg"))
    renderer.render(p, QRectF(x, y, 280, 280))
    renderer.render(p, QRectF(x + 40, y + 300, 64, 64))
    renderer.render(p, QRectF(x + 140, y + 316, 32, 32))
    renderer.render(p, QRectF(x + 210, y + 324, 16, 16))
    p.setPen(QColor("#111827"))
    p.setFont(QFont("Segoe UI", 13, QFont.Bold))
    p.drawText(x, y + 372, 280, 26, Qt.AlignCenter, label)
p.end()
img.save(str(out / "sheet.png"))
print("ok")
