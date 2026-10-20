"""Logging to a rotating file, and catching crashes so they end up in that file instead of vanishing."""

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from .paths import log_dir

LOG_FILE_NAME = "polyglass.log"
log = logging.getLogger("polyglass")


def setup_logging(on_crash=None) -> None:
    """on_crash(message) is called for any unhandled exception, on whichever thread raised it."""
    handler = RotatingFileHandler(log_dir() / LOG_FILE_NAME, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None:  # pythonw has no console
        root.addHandler(logging.StreamHandler(sys.stderr))

    def report(exc_type, exc, tb, where: str):
        log.critical("Unhandled exception in %s", where, exc_info=(exc_type, exc, tb))
        if on_crash:
            on_crash(f"{exc_type.__name__}: {exc}")

    sys.excepthook = lambda t, e, tb: report(t, e, tb, "main thread")
    threading.excepthook = lambda args: report(
        args.exc_type, args.exc_value, args.exc_traceback, f"thread {args.thread.name if args.thread else '?'}"
    )
