"""Render assets/polyglass.svg into the PNG and ICO files the app, installer and README use:

python tools/build_icons.py
"""

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "assets" / "polyglass.svg"
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(str(SVG)).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def write_ico(path: Path, sizes: list[int]) -> None:
    """Multi-resolution .ico with PNG-compressed entries (supported since Windows Vista)."""
    images = [png_bytes(render(s)) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blobs = b"", b""
    for size, blob in zip(sizes, images, strict=True):
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset + len(blobs))
        blobs += blob
    path.write_bytes(header + entries + blobs)


def main() -> None:
    app = QGuiApplication([])  # noqa: F841
    out = ROOT / "polyglass" / "resources"
    out.mkdir(exist_ok=True)
    render(256).save(str(out / "polyglass.png"))
    write_ico(out / "polyglass.ico", ICO_SIZES)
    render(512).save(str(ROOT / "assets" / "polyglass-512.png"))
    print(f"Wrote {out / 'polyglass.png'}, {out / 'polyglass.ico'} and assets/polyglass-512.png")


if __name__ == "__main__":
    main()
