"""Entry point: tray icon, hotkeys, and the glue between picker, worker and overlay."""
import os
import sys
import time

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"  # work in physical pixels, like the screen grabber

from PySide6.QtCore import QObject, QRect, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .config import Config
from .hotkeys import HotkeyListener
from .ocr import installed_languages
from .translate import LANGUAGE_NAMES, create_translator
from .ui import AreaPicker, Overlay, screens
from .worker import Worker

TARGETS = ["en", "fr", "de", "es", "it", "sr", "hr", "ru", "nl", "pt", "pl", "tr", "ja", "zh", "ko"]


class Bridge(QObject):
    """Signals that carry events from background threads onto the Qt thread."""
    select = Signal()
    toggle = Signal()
    stop = Signal()
    blocks = Signal(object)
    error = Signal(str)


def make_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(66, 133, 244))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setPen(QColor("white"))
    font = QFont("Segoe UI", 26, QFont.Bold)
    p.setFont(font)
    p.drawText(pix.rect(), Qt.AlignCenter, "文A")
    p.end()
    return QIcon(pix)


class LensApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.cfg = Config.load()
        self.bridge = Bridge()
        self.translator = create_translator(self.cfg)
        self.pickers: list[AreaPicker] = []
        self.overlay: Overlay | None = None
        self.worker: Worker | None = None
        self._last_error_at = 0.0

        self.bridge.select.connect(self.start_picking)
        self.bridge.toggle.connect(self.toggle_overlay)
        self.bridge.stop.connect(self.stop_watching)
        self.bridge.blocks.connect(self._on_blocks)
        self.bridge.error.connect(self._on_error)

        self.tray = QSystemTrayIcon(make_icon())
        self.tray.setToolTip("Lens Overlay")
        self._build_menu()
        self.tray.activated.connect(lambda reason: reason == QSystemTrayIcon.Trigger and self.start_picking())
        self.tray.show()

        self.hotkeys = HotkeyListener({
            self.cfg.hotkey_select: self.bridge.select.emit,
            self.cfg.hotkey_toggle: self.bridge.toggle.emit,
            self.cfg.hotkey_stop: self.bridge.stop.emit,
        })
        self.hotkeys.start()
        self.hotkeys.wait_ready()

        status = (f"{self.cfg.hotkey_select}: pick an area · {self.cfg.hotkey_toggle}: show/hide · "
                  f"{self.cfg.hotkey_stop}: stop\nTranslator: {self.translator.name} · "
                  f"{self.cfg.source_lang} → {self.cfg.target_lang}")
        if self.hotkeys.failed:
            status += f"\nHotkeys already taken by another app: {', '.join(self.hotkeys.failed)}"
        print(status)
        self.tray.showMessage("Lens Overlay is running", status, QSystemTrayIcon.Information, 6000)

    # ---- menu -------------------------------------------------------------------------------
    def _build_menu(self):
        menu = QMenu()
        menu.addAction(f"Pick area ({self.cfg.hotkey_select})", self.start_picking)
        menu.addAction(f"Show / hide ({self.cfg.hotkey_toggle})", self.toggle_overlay)
        menu.addAction(f"Stop ({self.cfg.hotkey_stop})", self.stop_watching)
        menu.addSeparator()
        self._choice_menu(menu, "Translate from", installed_languages(), self.cfg.source_lang,
                          lambda tag: tag, self._set_source)
        self._choice_menu(menu, "Translate to", TARGETS, self.cfg.target_lang,
                          lambda code: LANGUAGE_NAMES.get(code, code), self._set_target)
        self._choice_menu(menu, "Translator", ["auto", "claude", "deepl", "google"], self.cfg.translator,
                          lambda name: name, self._set_translator)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self.menu = menu
        self.tray.setContextMenu(menu)

    def _choice_menu(self, parent, title, options, current, label, on_pick):
        sub = parent.addMenu(title)
        group = QActionGroup(sub)
        for option in options:
            action = QAction(label(option), sub, checkable=True, checked=option == current)
            action.triggered.connect(lambda _=False, o=option: on_pick(o))
            group.addAction(action)
            sub.addAction(action)

    def _set_source(self, tag):
        self.cfg.source_lang = tag
        self._apply_settings()

    def _set_target(self, code):
        self.cfg.target_lang = code
        self._apply_settings()

    def _set_translator(self, name):
        previous = self.cfg.translator
        self.cfg.translator = name
        try:
            self.translator = create_translator(self.cfg)
        except Exception as exc:
            self.cfg.translator = previous
            self._on_error(str(exc))
            return
        self._apply_settings()

    def _apply_settings(self):
        self.cfg.save()
        if self.worker and self.overlay:
            self._start_worker(self.overlay.geometry())

    # ---- picking and watching ---------------------------------------------------------------
    def start_picking(self):
        self._close_pickers()
        for screen in screens():
            picker = AreaPicker(screen)
            picker.picked.connect(self._on_picked)
            picker.cancelled.connect(self._close_pickers)
            picker.show()
            picker.raise_()
            picker.activateWindow()
            self.pickers.append(picker)

    def _close_pickers(self):
        for picker in self.pickers:
            picker.close()
            picker.deleteLater()
        self.pickers = []

    def _on_picked(self, region: QRect):
        self._close_pickers()
        self._start_worker(region)

    def _start_worker(self, region: QRect):
        self._stop_worker()
        if self.overlay is None:
            self.overlay = Overlay(region)
        else:
            self.overlay.setGeometry(region)
            self.overlay.set_blocks([])
            self.overlay._outline = True
        self.overlay.show()
        self.worker = Worker((region.x(), region.y(), region.width(), region.height()),
                             self.cfg.source_lang, self.cfg.target_lang, self.translator,
                             self.cfg.poll_interval, self.bridge.blocks.emit, self.bridge.error.emit)
        self.worker.start()

    def _stop_worker(self):
        if self.worker:
            self.worker.stop()
            self.worker = None

    def stop_watching(self):
        self._stop_worker()
        if self.overlay:
            self.overlay.hide()

    def toggle_overlay(self):
        if self.overlay and self.worker:
            self.overlay.setVisible(not self.overlay.isVisible())

    def _on_blocks(self, blocks):
        if self.overlay and self.worker:
            self.overlay.set_blocks(blocks)

    def _on_error(self, message: str):
        print(message)
        if time.monotonic() - self._last_error_at > 15:  # don't spam notifications
            self._last_error_at = time.monotonic()
            self.tray.showMessage("Lens Overlay", message, QSystemTrayIcon.Warning, 5000)

    def quit(self):
        self._stop_worker()
        self.hotkeys.stop()
        self.tray.hide()
        self.app.quit()

    def run(self) -> int:
        return self.app.exec()


def main():
    sys.exit(LensApp().run())


if __name__ == "__main__":
    main()
