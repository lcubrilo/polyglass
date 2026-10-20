"""Background loop: capture the area, OCR it when the content changes and settles, translate, publish blocks."""

import asyncio
import logging
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import mss
import numpy as np

from .layout import TextBlock, build_blocks
from .ocr import WindowsOcr
from .translate import Translator

log = logging.getLogger(__name__)

CHANGE_THRESHOLD = 2.0  # mean abs grey-level difference that counts as "the screen changed"
CONTEXT_BLOCKS = 12  # earlier source blocks sent along as translation context
HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def _normalize(text: str) -> str:
    return "\n".join(" ".join(line.split()) for line in text.lower().splitlines())


class Worker(threading.Thread):
    def __init__(
        self,
        region: tuple[int, int, int, int],
        ocr_lang: str,
        target: str,
        translator: Translator,
        poll_interval: float,
        publish,
        report_error,
    ):
        super().__init__(daemon=True, name="polyglass-worker")
        self.region = region
        self.ocr_lang = ocr_lang
        self.target = target
        self.translator = translator
        self.poll_interval = poll_interval
        self._publish = publish
        self._report_error = report_error
        self._stop = threading.Event()
        self._rerender = threading.Event()
        self._cache: dict[str, str] = {}
        self._inflight: set[str] = set()
        self._context: deque[str] = deque(maxlen=CONTEXT_BLOCKS)
        self._lock = threading.Lock()
        self._translate_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="polyglass-translate")
        self._latest: tuple[list[TextBlock], np.ndarray] | None = None

    def stop(self):
        self._stop.set()

    def run(self):
        loop = asyncio.new_event_loop()
        ocr = WindowsOcr(self.ocr_lang)
        processed = previous = None
        left, top, width, height = self.region
        with mss.MSS() as grabber:
            while not self._stop.is_set():
                started = time.monotonic()
                try:
                    frame = np.asarray(grabber.grab({"left": left, "top": top, "width": width, "height": height}))
                    small = frame[::4, ::4, :3].mean(axis=2)
                    changed = processed is None or np.abs(small - processed).mean() > CHANGE_THRESHOLD
                    settled = previous is not None and np.abs(small - previous).mean() <= CHANGE_THRESHOLD
                    if changed and (settled or processed is None):
                        self._process(frame, ocr, loop)
                        processed = small
                    elif self._rerender.is_set() and self._latest:
                        self._rerender.clear()
                        self._emit(*self._latest)
                    previous = small
                except Exception as exc:  # keep the loop alive; surface the problem
                    log.exception("Capture/OCR failed")
                    self._report_error(f"Capture/OCR error: {exc}")
                    self._stop.wait(2)
                self._stop.wait(max(0.0, self.poll_interval - (time.monotonic() - started)))
        self._translate_pool.shutdown(wait=False, cancel_futures=True)

    def _process(self, frame: np.ndarray, ocr: WindowsOcr, loop):
        blocks = [
            b
            for b in build_blocks(frame, ocr.recognize(frame, loop))
            if len(b.text.strip()) > 1 and HAS_LETTER.search(b.text)
        ]
        self._latest = (blocks, frame)
        self._emit(blocks, frame)

        with self._lock:
            pending, seen = [], set()
            for block in blocks:
                key = _normalize(block.text)
                if key not in self._cache and key not in self._inflight and key not in seen:
                    pending.append(block.text)
                    seen.add(key)
            self._inflight.update(seen)
        if pending:
            self._translate_pool.submit(self._translate, pending)

    def _translate(self, texts: list[str]):
        keys = [_normalize(t) for t in texts]
        try:
            results = self.translator.translate(texts, self.ocr_lang, self.target, list(self._context))
            with self._lock:
                for key, src, result in zip(keys, texts, results, strict=True):
                    self._cache[key] = result
                    self._context.append(src)
            self._rerender.set()
        except Exception as exc:
            log.exception("Translation failed")
            self._report_error(f"Translation failed ({self.translator.name}): {exc}")
        finally:
            with self._lock:
                self._inflight.difference_update(keys)

    def _emit(self, blocks: list[TextBlock], frame: np.ndarray):
        with self._lock:
            for block in blocks:
                block.translation = self._cache.get(_normalize(block.text))
        self._publish(list(blocks))
