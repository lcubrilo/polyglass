"""Windows built-in OCR (Windows.Media.Ocr) with per-line bounding boxes."""
import asyncio
from dataclasses import dataclass

import numpy as np
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter

# Windows OCR misses small text; upscale regions whose text is likely below ~20 px
UPSCALE_BELOW_PIXELS = 1_500_000


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def union(self, other: "Box") -> "Box":
        x, y = min(self.x, other.x), min(self.y, other.y)
        return Box(x, y, max(self.right, other.right) - x, max(self.bottom, other.bottom) - y)


@dataclass
class OcrLine:
    text: str
    box: Box


def installed_languages() -> list[str]:
    return [lang.language_tag for lang in OcrEngine.available_recognizer_languages]


class WindowsOcr:
    def __init__(self, language_tag: str):
        self.set_language(language_tag)

    def set_language(self, language_tag: str) -> None:
        engine = OcrEngine.try_create_from_language(Language(language_tag))
        if engine is None:
            raise ValueError(f"Windows OCR language '{language_tag}' is not installed. "
                             f"Installed: {', '.join(installed_languages())}")
        self._engine = engine
        self.language_tag = language_tag

    def recognize(self, bgra: np.ndarray, loop: asyncio.AbstractEventLoop) -> list[OcrLine]:
        """bgra: HxWx4 uint8 screenshot. Returns lines in the screenshot's pixel coordinates."""
        scale = 2 if bgra.shape[0] * bgra.shape[1] < UPSCALE_BELOW_PIXELS else 1
        if scale > 1:
            bgra = bgra.repeat(scale, axis=0).repeat(scale, axis=1)
        limit = OcrEngine.max_image_dimension
        if max(bgra.shape[:2]) > limit:
            step = int(np.ceil(max(bgra.shape[:2]) / limit))
            bgra, scale = bgra[::step, ::step], scale / step
        return loop.run_until_complete(self._recognize(np.ascontiguousarray(bgra), scale))

    async def _recognize(self, bgra: np.ndarray, scale: float) -> list[OcrLine]:
        h, w = bgra.shape[:2]
        writer = DataWriter()
        writer.write_bytes(bgra.tobytes())
        bitmap = SoftwareBitmap.create_copy_from_buffer(
            writer.detach_buffer(), BitmapPixelFormat.BGRA8, w, h)
        result = await self._engine.recognize_async(bitmap)

        lines = []
        for line in result.lines:
            words = list(line.words)
            if not words:
                continue
            box = None
            for word in words:
                r = word.bounding_rect
                wb = Box(r.x / scale, r.y / scale, r.width / scale, r.height / scale)
                box = wb if box is None else box.union(wb)
            lines.append(OcrLine(line.text, box))
        return lines
