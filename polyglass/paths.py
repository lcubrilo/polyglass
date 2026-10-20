"""Where Polyglass keeps its files: settings in %APPDATA%\\Polyglass, logs in %LOCALAPPDATA%\\Polyglass\\logs."""

import os
from pathlib import Path

APP_NAME = "Polyglass"


def config_dir() -> Path:
    path = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_NAME / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
