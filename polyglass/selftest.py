"""`Polyglass.exe --selftest`: render a sample page and run it through OCR and layout, with no window or
network. Exit code 0 means the packaged app can read text; used to check release builds."""

import asyncio
import logging

import numpy as np
from PySide6.QtGui import QColor, QImage, QPainter, QTextDocument

from .layout import build_blocks
from .ocr import WindowsOcr, installed_languages

log = logging.getLogger(__name__)

SAMPLES = {
    "fr": ("Bienvenue à la gare de Lyon", "Les trains partiront avec un retard d'environ vingt minutes."),
    "en": ("Welcome to the station", "Trains will leave about twenty minutes late."),
}


def run() -> int:
    tags = installed_languages()
    tag = next((t for t in tags if t.startswith("fr")), None) or next((t for t in tags if t.startswith("en")), None)
    if tag is None:
        log.error("Self-test: no French or English Windows OCR language installed (have: %s)", ", ".join(tags))
        return 2
    heading, body = SAMPLES[tag[:2]]
    doc = QTextDocument()
    # Explicit colours: without them Qt uses the theme's text colour, which is white in dark mode
    doc.setHtml(
        f"<div style='color:#222222'><h1 style='background:#1a237e;color:#ffd54f'>{heading}</h1>"
        f"<p style='font-size:20px'>{body}</p></div>"
    )
    doc.setTextWidth(900)
    size = doc.size().toSize()
    image = QImage(size.width(), size.height(), QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    doc.drawContents(painter)
    painter.end()
    frame = np.array(image.constBits(), dtype=np.uint8).reshape(size.height(), size.width(), 4)

    blocks = build_blocks(frame, WindowsOcr(tag).recognize(np.ascontiguousarray(frame), asyncio.new_event_loop()))
    found = " ".join(b.text for b in blocks)
    ok = len(blocks) == 2 and heading.split()[0] in found and body.split()[0] in found
    log.info("Self-test with %s: %d blocks, %s", tag, len(blocks), "passed" if ok else f"failed: {found!r}")
    return 0 if ok else 1
