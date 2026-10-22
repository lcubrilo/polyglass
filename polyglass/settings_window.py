"""The settings window: translator and languages, API keys, hotkeys and appearance."""

from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QIcon, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import keys, system
from .config import Config
from .hotkeys import parse as parse_hotkey
from .ocr import installed_languages
from .translate import LANGUAGE_NAMES, available_translators

TRANSLATOR_LABELS = {
    "auto": "Automatic (first one with a key)",
    "claude": "Claude (best with context)",
    "deepl": "DeepL",
    "google": "Google, unofficial (personal use)",
}
CLAUDE_MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
EFFORTS = ["low", "medium", "high"]
KEY_LINKS = {
    "deepl": ("DeepL API key", "https://www.deepl.com/your-account/keys", "free plan: 500,000 characters a month"),
    "anthropic": ("Claude API key", "https://console.anthropic.com/settings/keys", "pay per use"),
}


def ocr_language_label(tag: str) -> str:
    locale = QLocale(tag)
    name = QLocale.languageToString(locale.language())
    if locale.script() != QLocale.AnyScript and tag.count("-") > 1:
        name += f", {QLocale.scriptToString(locale.script())}"
    return f"{name} ({tag})"


class SettingsWindow(QDialog):
    def __init__(self, cfg: Config, icon: QIcon, start_tab: int = 0):
        super().__init__(None, Qt.WindowCloseButtonHint | Qt.WindowTitleHint)
        self.cfg = cfg
        self.setWindowTitle("Polyglass settings")
        self.setWindowIcon(icon)
        self.setMinimumWidth(480)

        tabs = QTabWidget()
        tabs.addTab(self._translation_tab(), "Translation")
        tabs.addTab(self._keys_tab(), "Keys")
        tabs.addTab(self._general_tab(), "Hotkeys && look")
        tabs.setCurrentIndex(start_tab)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        self.error = QLabel()
        self.error.setStyleSheet("color: #dc2626")
        self.error.hide()

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    # ---- tabs --------------------------------------------------------------------------------
    def _translation_tab(self) -> QWidget:
        page, form = QWidget(), QFormLayout()
        page.setLayout(form)

        self.translator = QComboBox()
        for name in available_translators(self.cfg):
            self.translator.addItem(TRANSLATOR_LABELS.get(name, name), name)
        self._select(self.translator, self.cfg.translator)
        form.addRow("Translator", self.translator)

        self.source = QComboBox()
        for tag in installed_languages():
            self.source.addItem(ocr_language_label(tag), tag)
        self._select(self.source, self.cfg.source_lang)
        form.addRow("Translate from", self.source)
        hint = QLabel("Languages Windows can read. Add more in Windows Settings → Time & language → Language & region.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray")
        form.addRow("", hint)

        self.target = QComboBox()
        for code, name in sorted(LANGUAGE_NAMES.items(), key=lambda item: item[1]):
            self.target.addItem(name, code)
        self._select(self.target, self.cfg.target_lang)
        form.addRow("Translate to", self.target)

        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(CLAUDE_MODELS)
        self.model.setCurrentText(self.cfg.claude_model)
        form.addRow("Claude model", self.model)
        self.effort = QComboBox()
        self.effort.addItems(EFFORTS)
        self.effort.setCurrentText(self.cfg.claude_effort)
        form.addRow("Claude effort", self.effort)
        return page

    def _keys_tab(self) -> QWidget:
        page, form = QWidget(), QFormLayout()
        page.setLayout(form)
        intro = QLabel(
            "Keys are stored in Windows Credential Manager, never in Polyglass's files. "
            "An environment variable (DEEPL_API_KEY, ANTHROPIC_API_KEY) takes precedence."
        )
        intro.setWordWrap(True)
        form.addRow(intro)
        self.key_fields: dict[str, QLineEdit] = {}
        for name, (label, url, note) in KEY_LINKS.items():
            field = QLineEdit()
            field.setEchoMode(QLineEdit.Password)
            source = keys.key_source(name)
            if source == "environment":
                field.setPlaceholderText("set by environment variable")
                field.setEnabled(False)
            elif source:
                field.setPlaceholderText("saved (type to replace, clear the box and save to remove)")
            self.key_fields[name] = field
            form.addRow(label, field)
            link = QLabel(f'<a href="{url}">Get a key</a> · {note}')
            link.setOpenExternalLinks(True)
            form.addRow("", link)
        return page

    def _general_tab(self) -> QWidget:
        page, form = QWidget(), QFormLayout()
        page.setLayout(form)
        self.hotkey_edits = {}
        for attr, label in (
            ("hotkey_select", "Pick an area"),
            ("hotkey_toggle", "Show / hide overlay"),
            ("hotkey_stop", "Stop watching"),
        ):
            edit = QKeySequenceEdit(QKeySequence(getattr(self.cfg, attr)))
            edit.setMaximumSequenceLength(1)
            self.hotkey_edits[attr] = edit
            form.addRow(label, edit)
        self.show_frame = QCheckBox("Show corner marks around the watched area")
        self.show_frame.setChecked(self.cfg.show_frame)
        form.addRow(self.show_frame)
        self.autostart = QCheckBox("Start Polyglass with Windows")
        self.autostart.setChecked(system.starts_with_windows())
        form.addRow(self.autostart)
        self.updates = QCheckBox("Check GitHub for a new version when Polyglass starts")
        self.updates.setChecked(self.cfg.check_updates)
        form.addRow(self.updates)
        return page

    # ---- saving ------------------------------------------------------------------------------
    @staticmethod
    def _select(combo: QComboBox, value: str):
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))

    def _fail(self, message: str):
        self.error.setText(message)
        self.error.show()

    def _save(self):
        hotkeys = {}
        for attr, edit in self.hotkey_edits.items():
            text = edit.keySequence().toString(QKeySequence.PortableText)
            try:
                parse_hotkey(text)
            except ValueError:
                return self._fail(f"'{text or 'empty'}' can't be used as a hotkey. Use something like Ctrl+Alt+L.")
            hotkeys[attr] = text
        if len(set(hotkeys.values())) < len(hotkeys):
            return self._fail("Each action needs its own hotkey.")

        for name, field in self.key_fields.items():
            if field.isEnabled() and field.isModified():  # an emptied box removes the saved key
                keys.save_key(name, field.text().strip())

        self.cfg.translator = self.translator.currentData()
        self.cfg.source_lang = self.source.currentData() or self.cfg.source_lang
        self.cfg.target_lang = self.target.currentData()
        self.cfg.claude_model = self.model.currentText().strip() or self.cfg.claude_model
        self.cfg.claude_effort = self.effort.currentText()
        for attr, text in hotkeys.items():
            setattr(self.cfg, attr, text)
        self.cfg.show_frame = self.show_frame.isChecked()
        self.cfg.check_updates = self.updates.isChecked()
        if self.autostart.isChecked() != system.starts_with_windows():
            system.set_start_with_windows(self.autostart.isChecked())
        self.cfg.save()
        self.accept()
