"""`Polyglass.exe --selftest`: render a sample page and run it through OCR and layout, then load the speech
stack, with no window or network. Exit code 0 means the packaged app can read text and has everything live
captions need except the downloaded model; used to check release builds."""

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
    # Windows OCR sometimes drops a line's first letter (e.g. "elcome"), so compare words, not exact text
    expected = {w.strip(".,'").lower() for w in f"{heading} {body}".split()}
    read = {w.strip(".,'").lower() for w in found.split()}
    ok = len(blocks) == 2 and len(expected & read) >= 0.8 * len(expected)
    log.info("Self-test with %s: %d blocks, %s", tag, len(blocks), "passed" if ok else f"failed: {found!r}")
    if not ok:
        return 1
    return 0 if speech_stack_loads() else 3


def speech_stack_loads() -> bool:
    """ctranslate2's native library, the voice-activity model on onnxruntime and the sound library all load.
    The speech model itself downloads on first use, so it isn't checked here."""
    try:
        import ctranslate2
        import soundcard  # noqa: F401
        from faster_whisper.vad import get_vad_model

        get_vad_model()
        types = ctranslate2.get_supported_compute_types("cpu")
    except Exception:
        log.exception("Self-test: the speech stack failed to load")
        return False
    log.info("Self-test: speech stack loads (CPU compute types: %s)", ", ".join(sorted(types)))
    return True
