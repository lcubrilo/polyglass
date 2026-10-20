"""User settings, stored as JSON next to the app. API keys come from the environment, never this file."""
import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


@dataclass
class Config:
    # OCR language tag (must be an installed Windows OCR language, e.g. "fr-FR", "en-US")
    source_lang: str = "fr-FR"
    # Target language as an ISO code ("en", "sr", "de", ...)
    target_lang: str = "en"
    # "auto" picks claude -> deepl -> google depending on which credentials exist
    translator: str = "auto"
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "low"
    # Seconds between screen checks
    poll_interval: float = 0.35
    # Hotkeys, as "Mod+Mod+Key"
    hotkey_select: str = "Ctrl+Alt+L"
    hotkey_toggle: str = "Ctrl+Alt+K"
    hotkey_stop: str = "Ctrl+Alt+X"

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                known = {f.name for f in fields(cls)}
                for key, value in data.items():
                    if key in known:
                        setattr(cfg, key, value)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"Ignoring unreadable {CONFIG_PATH.name}: {exc}")
        else:
            cfg.save()
        return cfg

    def save(self) -> None:
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def deepl_key() -> str | None:
    return os.environ.get("DEEPL_API_KEY") or None


def has_claude_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("ANTHROPIC_PROFILE")
                or (Path.home() / ".config" / "anthropic").exists())
