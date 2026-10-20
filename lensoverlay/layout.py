"""Measure each OCR line's look (colours, size, weight) and group lines into text blocks."""
from dataclasses import dataclass

import numpy as np

from .ocr import Box, OcrLine

DESCENDERS = set("gjpqyQ,;()[]{}|/")
# Word boxes span ascender-to-descender. Relative to the font's pixel size that is about
# 0.95 when the line has descenders and about 0.74 when it doesn't.
BOX_TO_EM_WITH_DESC = 0.95
BOX_TO_EM_NO_DESC = 0.74
# Median horizontal stroke width as a fraction of the font size; bold sits above this
BOLD_STROKE_RATIO = 0.13


@dataclass
class LineStyle:
    background: tuple[int, int, int]
    foreground: tuple[int, int, int]
    em: float          # estimated font pixel size
    stroke: float      # median stroke width in pixels


@dataclass
class TextBlock:
    lines: list[OcrLine]
    styles: list[LineStyle]
    box: Box
    translation: str | None = None

    @property
    def text(self) -> str:
        """Lines that wrap mid-sentence are joined with spaces; list-like lines (short, or ending a
        sentence) keep their line break so menus and lists stay one item per line."""
        parts = [self.lines[0].text]
        for prev, line in zip(self.lines, self.lines[1:]):
            short = prev.box.right < self.box.x + 0.7 * self.box.w
            ends_sentence = prev.text.rstrip()[-1:] in ".!?:;"
            # Wrapped paragraph lines rarely start with a capital; new list items usually do
            new_item = line.text[:1].isupper() and prev.text.rstrip()[-1:] not in ",-"
            parts.append(("\n" if short or ends_sentence or new_item else " ") + line.text)
        return "".join(parts)

    @property
    def background(self) -> tuple[int, int, int]:
        return _median_color([s.background for s in self.styles])

    @property
    def foreground(self) -> tuple[int, int, int]:
        return _median_color([s.foreground for s in self.styles])

    @property
    def em(self) -> float:
        return float(np.median([s.em for s in self.styles]))

    @property
    def line_height(self) -> float:
        return float(np.median([line.box.h for line in self.lines]))

    @property
    def bold(self) -> bool:
        return float(np.median([s.stroke / max(1.0, s.em) for s in self.styles])) > BOLD_STROKE_RATIO


def build_blocks(img: np.ndarray, lines: list[OcrLine]) -> list[TextBlock]:
    """img is the BGRA frame the lines were read from."""
    blocks: list[TextBlock] = []
    for line in sorted(lines, key=lambda l: (l.box.y, l.box.x)):
        line.box = _extend_over_missed_ink(img, line.box)
        style = measure_line(img, line)
        target = None
        for block in reversed(blocks[-6:]):
            if _continues(block, line, style):
                target = block
                break
        if target is None:
            blocks.append(TextBlock([line], [style], line.box))
        else:
            target.lines.append(line)
            target.styles.append(style)
            target.box = target.box.union(line.box)
    return blocks


def _continues(block: TextBlock, line: OcrLine, style: LineStyle) -> bool:
    """Does `line` read as the next line of the same paragraph?"""
    last, last_style = block.lines[-1].box, block.styles[-1]
    em = max(last_style.em, style.em)
    gap = line.box.y - last.bottom
    if not (-0.3 * em < gap < 0.8 * em):
        return False
    if max(last_style.em, style.em) / max(1.0, min(last_style.em, style.em)) > 1.2:
        return False
    if abs(last_style.stroke / max(1.0, last_style.em) - style.stroke / max(1.0, style.em)) > 0.035:
        return False  # weight changes, e.g. a bold heading above regular text
    if _distance(last_style.foreground, style.foreground) > 70 or _distance(last_style.background, style.background) > 45:
        return False
    overlap = min(last.right, line.box.right) - max(last.x, line.box.x)
    return abs(last.x - line.box.x) < 1.5 * em or overlap > 0.3 * min(last.w, line.box.w)


def measure_line(img: np.ndarray, line: OcrLine) -> LineStyle:
    box = line.box
    pad = max(2, int(box.h * 0.15))
    ring = _ring(img, box, pad)
    bg = np.median(ring, axis=0) if len(ring) else np.array([255.0, 255.0, 255.0])

    x0, y0 = max(0, int(box.x)), max(0, int(box.y))
    patch = img[y0:int(np.ceil(box.bottom)), x0:int(np.ceil(box.right)), :3].astype(float)
    has_desc = any(ch in DESCENDERS for ch in line.text)
    em = box.h / (BOX_TO_EM_WITH_DESC if has_desc else BOX_TO_EM_NO_DESC)
    if patch.size == 0:
        return LineStyle(_rgb(bg), _rgb(255 - bg), em, 1.0)

    dist = np.linalg.norm(patch - bg, axis=2)
    ink = dist > max(40.0, 0.5 * dist.max())
    strong = patch[ink]
    fg = np.median(strong, axis=0) if len(strong) else 255 - bg
    return LineStyle(_rgb(bg), _rgb(fg), em, _stroke_width(ink))


def _extend_over_missed_ink(img: np.ndarray, box: Box) -> Box:
    """OCR sometimes drops the first or last characters of a line. Grow the box sideways over
    adjacent ink in the same band, stopping at a gap wider than a word space."""
    h, w = img.shape[:2]
    y0, y1 = max(0, int(box.y)), min(h, int(np.ceil(box.bottom)))
    if y1 <= y0:
        return box
    pad = max(2, int(box.h * 0.15))
    ring = _ring(img, box, pad)
    if not len(ring):
        return box
    bg = np.median(ring, axis=0)
    max_gap = max(3, int(box.h * 0.45))
    band = img[y0:y1, :, :3].astype(float)
    has_ink = (np.linalg.norm(band - bg, axis=2) > 60).any(axis=0)

    def walk(start: int, step: int) -> int:
        edge, gap, x = start, 0, start + step
        while 0 <= x < w and gap <= max_gap:
            if has_ink[x]:
                edge, gap = x, 0
            else:
                gap += 1
            x += step
        return edge

    left = walk(int(box.x), -1)
    right = walk(min(w - 1, int(np.ceil(box.right))), 1)
    return Box(float(left), box.y, float(right + 1 - left), box.h)


def _stroke_width(ink: np.ndarray) -> float:
    """Median length of horizontal ink runs: thin for regular text, thicker for bold."""
    padded = np.pad(ink.astype(np.int8), ((0, 0), (1, 1)))
    edges = np.diff(padded, axis=1)
    starts, ends = np.nonzero(edges == 1), np.nonzero(edges == -1)
    runs = ends[1] - starts[1]
    return float(np.median(runs)) if len(runs) else 1.0


def _ring(img: np.ndarray, box: Box, pad: int) -> np.ndarray:
    """Pixels in a thin frame just outside the box: the local background."""
    h, w = img.shape[:2]
    x0, y0 = max(0, int(box.x) - pad), max(0, int(box.y) - pad)
    x1, y1 = min(w, int(box.right) + pad), min(h, int(box.bottom) + pad)
    if x1 <= x0 or y1 <= y0:
        return np.empty((0, 3))
    patch = img[y0:y1, x0:x1, :3]
    t = max(1, min(pad, patch.shape[0] // 2, patch.shape[1] // 2))
    return np.concatenate([patch[:t].reshape(-1, 3), patch[-t:].reshape(-1, 3),
                           patch[:, :t].reshape(-1, 3), patch[:, -t:].reshape(-1, 3)]).astype(float)


def _distance(a, b) -> float:
    return float(np.linalg.norm(np.subtract(a, b)))


def _median_color(colors) -> tuple[int, int, int]:
    return tuple(int(v) for v in np.median(np.array(colors), axis=0))


def _rgb(bgr) -> tuple[int, int, int]:
    b, g, r = (int(round(v)) for v in bgr[:3])
    return r, g, b
