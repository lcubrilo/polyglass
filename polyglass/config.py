"""User settings, stored as JSON in %APPDATA%\\Polyglass. API keys live in keys.py, never in this file."""

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .keys import get_key
from .paths import config_dir

log = logging.getLogger(__name__)

# Bump when a setting is renamed or its meaning changes, and add a step to _migrate().
CONFIG_VERSION = 1


@dataclass
class Config:
    config_version: int = CONFIG_VERSION
    # OCR language tag (must be an installed Windows OCR language, e.g. "fr-FR", "en-US")
    source_lang: str = "fr-FR"
    # Target language as an ISO code ("en", "sr", "de", ...)
    target_lang: str = "en"
    # "auto" picks the first available of claude, deepl (and google when allowed below)
    translator: str = "auto"
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "low"
    # Google's keyless web endpoint is unofficial and not covered by its terms of service.
    # Off by default; only for personal use at your own risk.
    allow_unofficial_google: bool = False
    # Seconds between screen checks
    poll_interval: float = 0.35
    # Hotkeys, as "Mod+Mod+Key"
    hotkey_select: str = "Ctrl+Alt+L"
    hotkey_toggle: str = "Ctrl+Alt+K"
    hotkey_stop: str = "Ctrl+Alt+X"
    hotkey_captions: str = "Ctrl+Alt+S"
    # Live captions: language spoken ("auto" or an ISO code), Whisper model size ("auto": large-v3-turbo on
    # a GPU, small on a CPU) and where it runs ("auto", "cuda", "cpu")
    speech_lang: str = "auto"
    speech_model: str = "auto"
    speech_device: str = "auto"
    # Corner marks around the watched area
    show_frame: bool = True
    # Ask GitHub once a day whether a newer release exists
    check_updates: bool = True

    @classmethod
    def path(cls) -> Path:
        return config_dir() / "config.json"

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        path = cls.path()
        if not path.exists():
            cfg.save()
            return cfg
        try:
            data = _migrate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Ignoring unreadable %s: %s", path, exc)
            return cfg
        known = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key in known:
                setattr(cfg, key, value)
        cfg.config_version = CONFIG_VERSION
        return cfg

    def save(self) -> None:
        self.path().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def _migrate(data: dict) -> dict:
    """Upgrade settings written by older versions. Files from before versioning have no config_version."""
    version = data.get("config_version", 0)
    if version < 1:
        # 0 -> 1: the stop hotkey moved from Ctrl+Alt+Shift+L to Ctrl+Alt+X
        if data.get("hotkey_stop") == "Ctrl+Alt+Shift+L":
            data["hotkey_stop"] = "Ctrl+Alt+X"
    data["config_version"] = CONFIG_VERSION
    return data


def deepl_key() -> str | None:
    return get_key("deepl")


def has_claude_credentials() -> bool:
    return bool(
        get_key("anthropic")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("ANTHROPIC_PROFILE")
        or (Path.home() / ".config" / "anthropic").exists()
    )
