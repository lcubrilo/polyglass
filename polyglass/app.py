"""Entry point: tray icon, hotkeys, settings, and the glue between picker, worker and overlay."""

import getpass
import logging
import os
import sys
import threading
import time
from pathlib import Path

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"  # work in physical pixels, like the screen grabber

from PySide6.QtCore import QObject, QRect, QTimer, QUrl, Signal  # noqa: E402
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon  # noqa: E402
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon  # noqa: E402

from . import system  # noqa: E402
from .config import Config  # noqa: E402
from .hotkeys import HotkeyListener  # noqa: E402
from .logs import setup_logging  # noqa: E402
from .ocr import installed_languages  # noqa: E402
from .paths import APP_NAME, REPO_URL, log_dir  # noqa: E402
from .settings_window import SettingsWindow, ocr_language_label  # noqa: E402
from .translate import LANGUAGE_NAMES, NoTranslator, available_translators, create_translator  # noqa: E402
from .ui import AreaPicker, Overlay, screens  # noqa: E402
from .worker import Worker  # noqa: E402

log = logging.getLogger(__name__)

# One running copy per Windows user; a second launch asks the first one to pick an area instead
INSTANCE_KEY = f"{APP_NAME}-{getpass.getuser()}"
CRASH_DIALOG_COOLDOWN = 60.0
RESOURCES = Path(__file__).resolve().parent / "resources"
KEYS_TAB = 1


class Bridge(QObject):
    """Signals that carry events from background threads onto the Qt thread."""

    select = Signal()
    toggle = Signal()
    stop = Signal()
    blocks = Signal(object)
    error = Signal(str)
    crash = Signal(str)
    update = Signal(str, str)


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
        self.icon = QIcon(str(RESOURCES / "polyglass.ico"))
        self.app.setWindowIcon(self.icon)
        self.bridge = Bridge()
        setup_logging(on_crash=self.bridge.crash.emit)
        log.info("Polyglass %s starting", system.app_version())

        self.cfg = Config.load()
        self.translator = self._make_translator()
        self.pickers: list[AreaPicker] = []
        self.overlay: Overlay | None = None
        self.worker: Worker | None = None
        self.hotkeys: HotkeyListener | None = None
        self.settings_window: SettingsWindow | None = None
        self._update_url = ""
        self._last_error_at = 0.0
        self._last_crash_at = 0.0

        self.bridge.select.connect(self.start_picking)
        self.bridge.toggle.connect(self.toggle_overlay)
        self.bridge.stop.connect(self.stop_watching)
        self.bridge.blocks.connect(self._on_blocks)
        self.bridge.error.connect(self._on_error)
        self.bridge.crash.connect(self._on_crash)
        self.bridge.update.connect(self._on_update)

        self.server = QLocalServer()
        QLocalServer.removeServer(INSTANCE_KEY)  # clears a stale name left by a crashed copy
        self.server.listen(INSTANCE_KEY)
        self.server.newConnection.connect(self._on_second_launch)

        self.tray = QSystemTrayIcon(self.icon)
        self.tray.setToolTip(APP_NAME)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.messageClicked.connect(self._on_message_clicked)
        self._build_menu()
        self.tray.show()
        self._start_hotkeys()

        status = self._status_text()
        log.info(status.replace("\n", " | "))
        self.tray.showMessage(f"{APP_NAME} is running", status, QSystemTrayIcon.Information, 6000)
        if isinstance(self.translator, NoTranslator):
            QTimer.singleShot(800, lambda: self.open_settings(KEYS_TAB))  # first run: set up a translator
        if self.cfg.check_updates:
            threading.Thread(target=self._check_for_update, name="update-check", daemon=True).start()

    # ---- setup ------------------------------------------------------------------------------
    def _make_translator(self):
        try:
            return create_translator(self.cfg)
        except Exception as exc:
            log.warning("Translator unavailable: %s", exc)
            return NoTranslator()

    def _start_hotkeys(self):
        if self.hotkeys:
            self.hotkeys.stop()
            self.hotkeys.join(2)
        self.hotkeys = HotkeyListener(
            {
                self.cfg.hotkey_select: self.bridge.select.emit,
                self.cfg.hotkey_toggle: self.bridge.toggle.emit,
                self.cfg.hotkey_stop: self.bridge.stop.emit,
            }
        )
        self.hotkeys.start()
        self.hotkeys.wait_ready()
        if self.hotkeys.failed:
            self._on_error(f"Hotkeys already taken by another app: {', '.join(self.hotkeys.failed)}")

    def _status_text(self) -> str:
        status = (
            f"{self.cfg.hotkey_select}: pick an area · {self.cfg.hotkey_toggle}: show/hide · "
            f"{self.cfg.hotkey_stop}: stop\nTranslator: {self.translator.name} · "
            f"{self.cfg.source_lang} → {self.cfg.target_lang}"
        )
        if isinstance(self.translator, NoTranslator):
            status += "\nNo translator set up yet: add a DeepL or Claude key in Settings."
        return status

    # ---- menu -------------------------------------------------------------------------------
    def _build_menu(self):
        menu = QMenu()
        menu.addAction(f"Pick area ({self.cfg.hotkey_select})", self.start_picking)
        menu.addAction(f"Show / hide ({self.cfg.hotkey_toggle})", self.toggle_overlay)
        menu.addAction(f"Stop ({self.cfg.hotkey_stop})", self.stop_watching)
        menu.addSeparator()
        self._choice_menu(
            menu, "Translate from", installed_languages(), self.cfg.source_lang, ocr_language_label, self._set_source
        )
        targets = sorted(LANGUAGE_NAMES, key=LANGUAGE_NAMES.get)
        self._choice_menu(
            menu, "Translate to", targets, self.cfg.target_lang, lambda c: LANGUAGE_NAMES[c], self._set_target
        )
        self._choice_menu(
            menu, "Translator", available_translators(self.cfg), self.cfg.translator, str, self._set_translator
        )
        menu.addSeparator()
        menu.addAction("Settings…", self.open_settings)
        menu.addAction("Open log folder", self._open_logs)
        menu.addAction(f"About {APP_NAME} {system.app_version()}", self._about)
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
        self._build_menu()
        if self.worker and self.overlay:
            self._start_worker(self.overlay.geometry())

    def open_settings(self, tab: int = 0):
        if self.settings_window and self.settings_window.isVisible():
            self.settings_window.raise_()
            self.settings_window.activateWindow()
            return
        self.settings_window = SettingsWindow(self.cfg, self.icon, tab)
        self.settings_window.accepted.connect(self._on_settings_saved)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _on_settings_saved(self):
        log.info("Settings saved")
        self.translator = self._make_translator()
        self._start_hotkeys()
        if self.overlay:
            self.overlay.show_frame = self.cfg.show_frame
            self.overlay.update()
        self._apply_settings()
        self.tray.showMessage(APP_NAME, self._status_text(), QSystemTrayIcon.Information, 4000)

    def _open_logs(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir())))

    def _about(self):
        QMessageBox.about(
            None,
            APP_NAME,
            f"<b>{APP_NAME} {system.app_version()}</b><br>Live on-screen translation.<br><br>"
            f'<a href="{REPO_URL}">{REPO_URL}</a><br>Licensed under the GNU GPL v3 or later.',
        )

    # ---- picking and watching ---------------------------------------------------------------
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.start_picking()

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
        self.overlay.show_frame = self.cfg.show_frame
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

    # ---- messages, updates and crashes --------------------------------------------------------
    def _on_error(self, message: str):
        log.warning(message)
        if time.monotonic() - self._last_error_at > 15:  # don't spam notifications
            self._last_error_at = time.monotonic()
            self.tray.showMessage(APP_NAME, message, QSystemTrayIcon.Warning, 5000)

    def _check_for_update(self):
        try:
            found = system.newer_release()
        except Exception as exc:  # offline, rate-limited, no releases yet: not worth bothering the user
            log.info("Update check skipped: %s", exc)
            return
        if found:
            self.bridge.update.emit(*found)

    def _on_update(self, new_version: str, url: str):
        log.info("Version %s is available", new_version)
        self._update_url = url
        self.tray.showMessage(
            f"{APP_NAME} {new_version} is available",
            "Click to open the download page.",
            QSystemTrayIcon.Information,
            10000,
        )

    def _on_message_clicked(self):
        if self._update_url:
            QDesktopServices.openUrl(QUrl(self._update_url))
            self._update_url = ""

    def _on_crash(self, message: str):
        """An unhandled exception: it is already in the log. Tell the user, at most once a minute."""
        if time.monotonic() - self._last_crash_at < CRASH_DIALOG_COOLDOWN:
            return
        self._last_crash_at = time.monotonic()
        box = QMessageBox(
            QMessageBox.Critical,
            f"{APP_NAME} hit an error",
            f"Something went wrong:\n\n{message}\n\n{APP_NAME} keeps running, but it may not work correctly. "
            "The details are in the log file.",
        )
        box.setWindowIcon(self.icon)
        report = None
        if system.reports_left_today() > 0:
            report = box.addButton("Report on GitHub…", QMessageBox.ActionRole)
            report.setToolTip("Opens a pre-filled bug report on GitHub. You can review and edit it before sending.")
        open_logs = box.addButton("Open log folder", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is open_logs:
            self._open_logs()
        elif report is not None and box.clickedButton() is report:
            url = system.bug_report_url(message)
            if url:
                QDesktopServices.openUrl(QUrl(url))

    def quit(self):
        log.info("Quitting")
        self._stop_worker()
        if self.hotkeys:
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
