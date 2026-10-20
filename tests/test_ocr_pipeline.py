"""End-to-end check of OCR + layout on a rendered French page. Needs the French Windows OCR language,
so it is skipped where that isn't installed (for example on CI runners)."""

import asyncio

import numpy as np
import pytest

from polyglass.layout import build_blocks
from polyglass.ocr import WindowsOcr, installed_languages

PAGE = """<div style='background:#ffffff;color:#222;font-family:Georgia'>
<h1 style='background:#1a237e;color:#ffd54f;font-family:Segoe UI'>Bienvenue à la gare de Lyon</h1>
<p style='font-size:20px'>Les trains à destination de Marseille partiront avec un retard d'environ vingt minutes.</p>
<p style='font-size:16px;color:#b71c1c'>Le quai numéro 7 est fermé pour travaux.</p></div>"""


@pytest.fixture(scope="module")
def page_image():
    from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QTextDocument

    # Qt must start before WinRT is touched on this thread (see polyglass/ocr.py)
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    if "fr-FR" not in installed_languages():
        pytest.skip("French Windows OCR not installed")
    doc = QTextDocument()
    doc.setHtml(PAGE)
    doc.setTextWidth(900)
    size = doc.size().toSize()
    image = QImage(size.width(), size.height(), QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    doc.drawContents(painter)
    painter.end()
    return np.ascontiguousarray(np.array(image.constBits(), dtype=np.uint8).reshape(size.height(), size.width(), 4))


def test_rendered_french_page_becomes_three_styled_blocks(page_image):
    lines = WindowsOcr("fr-FR").recognize(page_image, asyncio.new_event_loop())
    blocks = build_blocks(page_image, lines)
    texts = [b.text for b in blocks]
    assert len(blocks) == 3, texts
    assert "Bienvenue" in texts[0] and "Marseille" in texts[1] and "quai" in texts[2]
    heading, body, warning = blocks
    assert heading.background == pytest.approx((26, 35, 126), abs=12)
    assert heading.bold and not body.bold
    assert warning.foreground[0] > 150 and warning.foreground[1] < 80  # red text stays red
