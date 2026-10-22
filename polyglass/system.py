"""Windows integration: start with Windows, the update check, and opening pre-filled bug reports."""

import json
import logging
import platform
import sys
import time
import urllib.parse
import urllib.request
import winreg
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .paths import APP_NAME, REPO_URL, log_dir

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RELEASES_API = "https://api.github.com/repos/lcubrilo/polyglass/releases/latest"
REPORTS_PER_DAY = 3


def app_version() -> str:
    try:
        return version("polyglass")
    except PackageNotFoundError:
        return "dev"


# ---- start with Windows -----------------------------------------------------------------------
def launch_command() -> str:
    """The command that starts this copy of Polyglass: the installed .exe, or pythonw -m polyglass."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else sys.executable}" -m polyglass'


def starts_with_windows() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False


def set_start_with_windows(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


# ---- update check -----------------------------------------------------------------------------
def _version_tuple(text: str) -> tuple[int, ...]:
    parts = []
    for piece in text.lstrip("v").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def newer_release() -> tuple[str, str] | None:
    """(version, url) of the latest GitHub release if it is newer than this one. Sends nothing but the request."""
    current = app_version()
    if current == "dev":
        return None
    request = urllib.request.Request(RELEASES_API, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        release = json.loads(response.read().decode("utf-8"))
    latest = release.get("tag_name", "")
    if latest and _version_tuple(latest) > _version_tuple(current):
        return latest.lstrip("v"), release.get("html_url", f"{REPO_URL}/releases")
    return None


# ---- bug reports ------------------------------------------------------------------------------
def _reports_file() -> Path:
    return log_dir().parent / "reports.json"


def reports_left_today() -> int:
    try:
        stamps = json.loads(_reports_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        stamps = []
    recent = [t for t in stamps if time.time() - t < 86_400]
    return max(0, REPORTS_PER_DAY - len(recent))


def _record_report() -> None:
    try:
        stamps = json.loads(_reports_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        stamps = []
    stamps = [t for t in stamps if time.time() - t < 86_400] + [time.time()]
    _reports_file().write_text(json.dumps(stamps), encoding="utf-8")


def bug_report_url(error: str) -> str | None:
    """A GitHub 'new issue' link pre-filled with the error, version and the end of the log.
    The user reviews everything on GitHub before submitting. None once today's limit is reached."""
    if reports_left_today() <= 0:
        return None
    try:
        log_tail = (log_dir() / "polyglass.log").read_text(encoding="utf-8", errors="replace").splitlines()[-30:]
    except OSError:
        log_tail = []
    fields = {
        "template": "bug_report.yml",
        "title": f"Crash: {error[:80]}",
        "what": f"Polyglass showed this error:\n\n{error}\n\n(What were you doing when it happened?)",
        "version": app_version(),
        "windows": f"{platform.system()} {platform.version()}",
        "log": "\n".join(log_tail)[-3000:],
    }
    _record_report()
    return f"{REPO_URL}/issues/new?{urllib.parse.urlencode(fields)}"
