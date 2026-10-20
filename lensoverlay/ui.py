"""Qt windows: the click-through translation overlay and the drag-to-select area picker.

Qt runs with high-DPI scaling disabled (see app.py), so every coordinate here is a physical screen
pixel, the same space mss captures in.
"""
import ctypes

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .layout import TextBlock

WDA_EXCLUDEFROMCAPTURE = 0x11
FONT_FAMILY = "Segoe UI"


class Overlay(QWidget):
    """Always on top, ignores the mouse, and is invisible to screen capture so OCR never reads it."""

    def __init__(self, region: QRect):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setGeometry(region)
        self._blocks: list[TextBlock] = []
        self._outline = True

    def showEvent(self, event):
        super().showEvent(event)
        ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), WDA_EXCLUDEFROMCAPTURE)

    def set_blocks(self, blocks: list[TextBlock]):
        self._blocks = blocks
        self._outline = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        if self._outline:
            # Until the first translation arrives, show where the watched area is
            painter.setPen(QPen(QColor(66, 133, 244, 200), 2, Qt.DashLine))
            painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
        for block in self._blocks:
            if block.translation:
                self._paint_block(painter, block)

    def _paint_block(self, painter: QPainter, block: TextBlock):
        em = block.em
        pad_x, pad_y = max(2, round(em * 0.25)), max(1, round(em * 0.08))
        rect = QRect(round(block.box.x) - pad_x, round(block.box.y) - pad_y,
                     round(block.box.w) + 2 * pad_x, round(block.box.h) + 2 * pad_y)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(*block.background))
        painter.drawRoundedRect(rect, pad_y + 1, pad_y + 1)

        # Start the text where the original text started, and keep it inside the overlay
        left = max(0, round(block.box.x))
        text_rect = QRect(left, rect.y(), min(self.width(), rect.right() - pad_x // 2) - left, rect.height())
        font = QFont(FONT_FAMILY)
        font.setBold(block.bold)
        flags = Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter
        size = max(8, round(em))
        while True:
            font.setPixelSize(size)
            needed = QFontMetrics(font).boundingRect(text_rect, flags, block.translation)
            if (needed.height() <= text_rect.height() + em * 0.15 and needed.width() <= text_rect.width()) or size <= 8:
                break
            size -= 1
        painter.setFont(font)
        painter.setPen(QColor(*block.foreground))
        painter.drawText(text_rect, flags, block.translation)


class AreaPicker(QWidget):
    """One per monitor: shows a frozen, dimmed screenshot; drag to pick an area, Esc to cancel."""
    picked = Signal(QRect)
    cancelled = Signal()

    def __init__(self, screen):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setScreen(screen)
        self._shot = screen.grabWindow(0)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CrossCursor)
        self._start: QPoint | None = None
        self._end: QPoint | None = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._shot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
        if self._start and self._end:
            sel = QRect(self._start, self._end).normalized()
            painter.drawPixmap(sel, self._shot, sel)
            painter.setPen(QPen(QColor(66, 133, 244), 2))
            painter.drawRect(sel)
        else:
            painter.setPen(QColor(255, 255, 255))
            font = QFont(FONT_FAMILY)
            font.setPixelSize(22)
            painter.setFont(font)
            painter.drawText(self.rect().adjusted(0, 40, 0, 0), Qt.AlignHCenter | Qt.AlignTop,
                             "Drag over the text to translate  ·  Esc to cancel")

    def mousePressEvent(self, event):
        self._start = self._end = event.position().toPoint()
        self.update()

    def mouseMoveEvent(self, event):
        if self._start:
            self._end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if not self._start:
            return
        sel = QRect(self._start, event.position().toPoint()).normalized()
        self._start = self._end = None
        if sel.width() < 12 or sel.height() < 8:
            self.update()
            return
        self.picked.emit(sel.translated(self.geometry().topLeft()))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()


def screens():
    return QGuiApplication.screens()
