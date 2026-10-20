"""Entry point: tray icon, hotkeys, and the glue between picker, worker and overlay."""

import getpass
import logging
import os
import sys
import time
from importlib.metadata import PackageNotFoundError, version

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"  # work in physical pixels, like the screen grabber

from PySide6.QtCore import QObject, QRect, Qt, QUrl, Signal  # noqa: E402
from PySide6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap  # noqa: E402
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon  # noqa: E402

from .config import Config  # noqa: E402
from .hotkeys import HotkeyListener  # noqa: E402
from .logs import setup_logging  # noqa: E402
from .ocr import installed_languages  # noqa: E402
from .paths import APP_NAME, log_dir  # noqa: E402
from .translate import LANGUAGE_NAMES, NoTranslator, available_translators, create_translator  # noqa: E402
from .ui import AreaPicker, Overlay, screens  # noqa: E402
from .worker import Worker  # noqa: E402

log = logging.getLogger(__name__)

TARGETS = ["en", "fr", "de", "es", "it", "sr", "hr", "ru", "nl", "pt", "pl", "tr", "ja", "zh", "ko"]
# One running copy per Windows user; a second launch asks the first one to pick an area instead
INSTANCE_KEY = f"{APP_NAME}-{getpass.getuser()}"
CRASH_DIALOG_COOLDOWN = 60.0


def app_version() -> str:
    try:
        return version("polyglass")
    except PackageNotFoundError:
        return "dev"


class Bridge(QObject):
    """Signals that carry events from background threads onto the Qt thread."""

    select = Signal()
    toggle = Signal()
    stop = Signal()
    blocks = Signal(object)
    error = Signal(str)
    crash = Signal(str)


def make_icon() -> QIcon:
    # Placeholder until the logo is chosen
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(66, 133, 244))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setPen(QColor("white"))
    p.setFont(QFont("Segoe UI", 26, QFont.Bold))
    p.drawText(pix.rect(), Qt.AlignCenter, "文A")
    p.end()
    return QIcon(pix)


def notify_running_instance() -> bool:
    """True if another copy is already running (it has been asked to start picking)."""
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_KEY)
    if not socket.waitForConnected(300):
        return False
    socket.write(b"pick")
    socket.waitForBytesWritten(300)
    socket.disconnectFromServer()
    return True


class PolyglassApp:
    def __init__(self, qt_app: QApplication):
        self.app = qt_app
        self.app.setQuitOnLastWindowClosed(False)
        self.bridge = Bridge()
        setup_logging(on_crash=self.bridge.crash.emit)
        log.info("Polyglass %s starting", app_version())

        self.cfg = Config.load()
        try:
            self.translator = create_translator(self.cfg)
        except Exception as exc:
            log.warning("Translator unavailable: %s", exc)
            self.translator = NoTranslator()
        self.pickers: list[AreaPicker] = []
        self.overlay: Overlay | None = None
        self.worker: Worker | None = None
        self._last_error_at = 0.0
        self._last_crash_at = 0.0

        self.bridge.select.connect(self.start_picking)
        self.bridge.toggle.connect(self.toggle_overlay)
        self.bridge.stop.connect(self.stop_watching)
        self.bridge.blocks.connect(self._on_blocks)
        self.bridge.error.connect(self._on_error)
        self.bridge.crash.connect(self._on_crash)

        self.server = QLocalServer()
        QLocalServer.removeServer(INSTANCE_KEY)  # clears a stale name left by a crashed copy
        self.server.listen(INSTANCE_KEY)
        self.server.newConnection.connect(self._on_second_launch)

        self.tray = QSystemTrayIcon(make_icon())
        self.tray.setToolTip(APP_NAME)
        self._build_menu()
        self.tray.activated.connect(lambda reason: reason == QSystemTrayIcon.Trigger and self.start_picking())
        self.tray.show()

        self.hotkeys = HotkeyListener(
            {
                self.cfg.hotkey_select: self.bridge.select.emit,
                self.cfg.hotkey_toggle: self.bridge.toggle.emit,
                self.cfg.hotkey_stop: self.bridge.stop.emit,
            }
        )
        self.hotkeys.start()
        self.hotkeys.wait_ready()

        status = (
            f"{self.cfg.hotkey_select}: pick an area · {self.cfg.hotkey_toggle}: show/hide · "
            f"{self.cfg.hotkey_stop}: stop\nTranslator: {self.translator.name} · "
            f"{self.cfg.source_lang} → {self.cfg.target_lang}"
        )
        if self.hotkeys.failed:
            status += f"\nHotkeys already taken by another app: {', '.join(self.hotkeys.failed)}"
        if isinstance(self.translator, NoTranslator):
            status += "\nNo translator set up yet: set DEEPL_API_KEY or ANTHROPIC_API_KEY."
        log.info(status.replace("\n", " | "))
        self.tray.showMessage(f"{APP_NAME} is running", status, QSystemTrayIcon.Information, 6000)

    # ---- menu -------------------------------------------------------------------------------
    def _build_menu(self):
        menu = QMenu()
        menu.addAction(f"Pick area ({self.cfg.hotkey_select})", self.start_picking)
        menu.addAction(f"Show / hide ({self.cfg.hotkey_toggle})", self.toggle_overlay)
        menu.addAction(f"Stop ({self.cfg.hotkey_stop})", self.stop_watching)
        menu.addSeparator()
        self._choice_menu(
            menu, "Translate from", installed_languages(), self.cfg.source_lang, lambda tag: tag, self._set_source
        )
        self._choice_menu(
            menu,
            "Translate to",
            TARGETS,
            self.cfg.target_lang,
            lambda code: LANGUAGE_NAMES.get(code, code),
            self._set_target,
        )
        self._choice_menu(
            menu,
            "Translator",
            available_translators(self.cfg),
            self.cfg.translator,
            lambda name: name,
            self._set_translator,
        )
        menu.addSeparator()
        menu.addAction("Open log folder", self._open_logs)
        menu.addAction(f"About {APP_NAME} {app_version()}", self._about)
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

    def _open_logs(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir())))

    def _about(self):
        QMessageBox.about(
            None,
            APP_NAME,
            f"<b>{APP_NAME} {app_version()}</b><br>Live on-screen translation.<br>"
            f"Licensed under the GNU GPL v3 or later.",
        )

    # ---- picking and watching ---------------------------------------------------------------
    def _on_second_launch(self):
        connection = self.server.nextPendingConnection()
        connection.readyRead.connect(lambda: connection.readAll() and self.start_picking())
        connection.disconnected.connect(connection.deleteLater)

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
        self.overlay.show()
        log.info(
            "Watching %dx%d at (%d, %d), %s -> %s via %s",
            region.width(),
            region.height(),
            region.x(),
            region.y(),
            self.cfg.source_lang,
            self.cfg.target_lang,
            self.translator.name,
        )
        self.worker = Worker(
            (region.x(), region.y(), region.width(), region.height()),
            self.cfg.source_lang,
            self.cfg.target_lang,
            self.translator,
            self.cfg.poll_interval,
            self.bridge.blocks.emit,
            self.bridge.error.emit,
        )
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
        log.warning(message)
        if time.monotonic() - self._last_error_at > 15:  # don't spam notifications
            self._last_error_at = time.monotonic()
            self.tray.showMessage(APP_NAME, message, QSystemTrayIcon.Warning, 5000)

    def _on_crash(self, message: str):
        """An unhandled exception: it is already in the log. Tell the user, at most once a minute."""
        if time.monotonic() - self._last_crash_at < CRASH_DIALOG_COOLDOWN:
            return
        self._last_crash_at = time.monotonic()
        box = QMessageBox(
            QMessageBox.Critical,
            f"{APP_NAME} hit an error",
            f"Something went wrong:\n\n{message}\n\nPolyglass keeps running, but it may not "
            f"work correctly. The details are in the log file.",
        )
        open_logs = box.addButton("Open log folder", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is open_logs:
            self._open_logs()

    def quit(self):
        log.info("Quitting")
        self._stop_worker()
        self.hotkeys.stop()
        self.server.close()
        self.tray.hide()
        self.app.quit()

    def run(self) -> int:
        return self.app.exec()


def main():
    qt_app = QApplication(sys.argv)
    if notify_running_instance():
        sys.exit(0)
    sys.exit(PolyglassApp(qt_app).run())


if __name__ == "__main__":
    main()
