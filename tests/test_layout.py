import numpy as np

from polyglass.layout import build_blocks, measure_line
from polyglass.ocr import Box, OcrLine


def canvas(bg=(255, 255, 255), w=400, h=300):
    """BGRA image filled with an RGB background colour."""
    img = np.zeros((h, w, 4), dtype=np.uint8)
    img[..., 0], img[..., 1], img[..., 2], img[..., 3] = bg[2], bg[1], bg[0], 255
    return img


def ink(img, box: Box, rgb, stroke=2, gap=4):
    """Fake glyphs: vertical bars of the given colour and stroke width across the box."""
    x = int(box.x)
    while x + stroke <= box.right:
        img[int(box.y) : int(box.bottom), x : x + stroke, :3] = rgb[::-1]
        x += stroke + gap


def line(text, x, y, w, h):
    return OcrLine(text, Box(x, y, w, h))


def test_measure_line_finds_background_and_text_colour():
    img = canvas(bg=(26, 35, 126))
    ln = line("Bienvenue", 20, 20, 200, 30)
    ink(img, ln.box, (255, 213, 79))
    style = measure_line(img, ln)
    assert style.background == (26, 35, 126)
    assert style.foreground == (255, 213, 79)


def test_paragraph_lines_are_grouped_and_joined_with_spaces():
    img = canvas()
    lines = [
        line("Les trains partiront avec un retard", 10, 20, 300, 20),
        line("d'environ vingt minutes.", 10, 44, 200, 20),
    ]
    for ln in lines:
        ink(img, ln.box, (40, 40, 40))
    blocks = build_blocks(img, lines)
    assert len(blocks) == 1
    assert blocks[0].text == "Les trains partiront avec un retard d'environ vingt minutes."


def test_list_items_keep_their_line_breaks():
    img = canvas()
    # Real OCR boxes stop at the baseline when a line has no descenders (g, p, q, y), so it is shorter
    lines = [line("Modifier le mot de passe", 10, 20, 220, 20), line("Se déconnecter", 10, 44, 140, 16)]
    for ln in lines:
        ink(img, ln.box, (40, 40, 40))
    (block,) = build_blocks(img, lines)
    assert block.text == "Modifier le mot de passe\nSe déconnecter"


def test_differently_coloured_line_starts_a_new_block():
    img = canvas()
    body, warning = line("Nous vous prions de nous excuser", 10, 20, 300, 20), line("Attention", 10, 44, 120, 20)
    ink(img, body.box, (40, 40, 40))
    ink(img, warning.box, (183, 28, 28))
    assert len(build_blocks(img, [body, warning])) == 2


def test_far_apart_lines_are_separate_blocks():
    img = canvas()
    lines = [line("Titre", 10, 20, 100, 20), line("Texte", 10, 120, 100, 20)]
    for ln in lines:
        ink(img, ln.box, (40, 40, 40))
    assert len(build_blocks(img, lines)) == 2


def test_thick_strokes_read_as_bold():
    img = canvas()
    regular, heavy = line("regular", 10, 20, 200, 30), line("heavy", 10, 120, 200, 30)
    ink(img, regular.box, (0, 0, 0), stroke=2, gap=6)
    ink(img, heavy.box, (0, 0, 0), stroke=7, gap=6)
    blocks = build_blocks(img, [regular, heavy])
    assert [b.bold for b in blocks] == [False, True]
